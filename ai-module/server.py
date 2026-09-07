"""
安全隐患分析 AI 服务 — FastAPI HTTP 接口。
启动: python server.py  (默认 0.0.0.0:8000)
"""
import json
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Query, Request, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from agents import (
    create_router_agent, create_vision_agent,
    create_retrieval_agent, create_report_agent,
)
from core import Orchestrator
from core.agent import Agent
from core.memory import get_session
from core.cancellation import CancellationToken
from core.assistant_graph import run_stream_events as assistant_graph_stream
from core.assistant_agent import create_assistant_agent
from config import MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL

app = FastAPI(title="Safety AI", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 全局单例
_orch: Orchestrator = None


def get_orch() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator(base_url=MIMO_BASE_URL, api_key=MIMO_API_KEY, model=MIMO_MODEL)
        _orch.register(create_router_agent(MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL))
        _orch.register(create_vision_agent(MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL))
        _orch.register(create_retrieval_agent(MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL))
        _orch.register(create_report_agent(MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL))
    return _orch


# ====== REST API ======

@app.post("/api/ai/analyze")
def analyze(
    file: UploadFile = File(None),
    text: str = Form(default="请分析这张图片中的安全隐患，并生成报告"),
    session_id: str = Form(default=""),
):
    """
    完整分析（非流式），返回 JSON。
    前端调用示例: multipart/form-data, file + text + session_id
    Java 调用示例: RestClient POST multipart
    """
    image_path = _save_upload(file) if file else None
    sid = session_id or str(uuid.uuid4())
    orch = get_orch()
    result = orch.analyze(text, image_path=image_path, session_id=sid)

    response = {
        "session_id": sid,
        "vision": result.get("vision"),
        "report": result.get("report", ""),
    }

    # 清理临时图片
    if image_path:
        try:
            Path(image_path).unlink()
        except Exception:
            pass

    return response


@app.post("/api/ai/analyze/stream")
async def analyze_stream(
    request: Request,
    file: UploadFile = File(None),
    text: str = Form(default="请分析这张图片中的安全隐患，并生成报告"),
    session_id: str = Form(default=""),
):
    """
    SSE 流式分析报告。
    前端断开连接（取消分析）时自动停止，节省 Token。
    """
    image_path = _save_upload(file) if file else None
    sid = session_id or str(uuid.uuid4())
    orch = get_orch()

    async def generate():
        for payload in orch.analyze_stream(text, image_path=image_path, session_id=sid):
            if await request.is_disconnected():
                print("[SSE] 客户端断开，停止分析")
                break
            yield f"data: {payload}\n\n"
        if image_path:
            try:
                Path(image_path).unlink()
            except Exception:
                pass

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"X-Session-Id": sid})


@app.post("/api/ai/chat")
def chat(message: str = Form(...), session_id: str = Form(...)):
    """
    多轮对话（非流式）。
    在 /api/ai/analyze 之后，用同一个 session_id 追问。
    """
    orch = get_orch()
    reply = orch.chat(message, session_id)
    return {"session_id": session_id, "reply": reply}


@app.post("/api/ai/chat/stream")
def chat_stream(message: str = Form(...), session_id: str = Form(...)):
    """
    多轮对话（SSE 流式）。
    """
    orch = get_orch()

    def generate():
        for sse_chunk in orch.chat_stream(message, session_id):
            yield sse_chunk

    return StreamingResponse(generate(), media_type="text/event-stream")



# ===== Assistant (ReAct 一期：多轮澄清 + 法规/案例) =====
_assistant: Agent = None

def get_assistant() -> Agent:
    global _assistant
    if _assistant is None:
        _assistant = create_assistant_agent(MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL)
    return _assistant

class AssistantRequest(BaseModel):
    message: str
    session_id: str = ""


@app.post("/api/ai/assistant/stream")
async def assistant_stream(
    request: Request,
    message: str = Form(None),
    session_id: str = Form(None),
    user_id: int = Form(None),
    file: UploadFile = File(None),
):
    # 兼容 JSON 和 multipart：有 file 走 FormData，无 file 走 JSON
    if message is None:
        try:
            body = await request.json()
            message = body.get("message", "") or body.get("text", "")
            session_id = body.get("session_id", "") or body.get("sessionId", "") or ""
            user_id = body.get("user_id")
        except Exception:
            message = ""
            session_id = ""
    message = (message or "").strip()
    if not message and (file is None or not getattr(file, "filename", "")):
        raise HTTPException(status_code=400, detail="message or file required")
    sid = session_id or str(uuid.uuid4())
    mem = get_session(sid)
    history = mem.get_history() if mem else []
    max_keep = getattr(mem, "max_turns", 10) * 2
    if len(history) > max_keep:
        history = history[-max_keep:]
    # 有图写死必调：先跑视觉，结果注入历史，保证有图必看
    image_path = None
    vision_injected = False
    if file is not None and getattr(file, "filename", ""):
        try:
            image_path = _save_upload(file)
            # 同步注入视觉结果到 history（不依赖模型是否调工具）
            try:
                from mimo_client import MiMoVisionClient
                from prompts import VISION_PROMPT
                vc = MiMoVisionClient()
                vision_json = vc.analyze_json(image_path, VISION_PROMPT)
                if not vision_json:
                    history = history + [{"role": "system", "content": "[视觉分析失败，请仅按用户文字描述判断，不要编造图中细节]"}]
                    try:
                        mem.messages.append({"role": "system", "content": "[视觉分析失败，请仅按用户文字描述判断，不要编造图中细节]"})
                        mem._trim()
                    except: pass
                else:
                    history = history + [{"role": "system", "content": f"[视觉分析] {vision_json}"}]
                # 立刻落库，保证第二轮能读到
                try:
                    mem.messages.append({"role": "system", "content": f"[视觉分析] {vision_json}"})
                    mem._trim()
                except: pass
                if len(history) > max_keep:
                    history = history[-max_keep:]
                vision_injected = True
            except Exception as ve:
                history = history + [{"role": "system", "content": f"[视觉分析失败] {ve}"}]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"图片处理失败: {e}")

    assistant = get_assistant()
    # 若没有文字但有图，给个默认提示让模型基于图回答
    if not message and image_path:
        message = "请分析这张图片中的安全隐患"
    # 立刻落库用户消息，保证第二轮多轮能读到（原来在 generate 结束后才落库，第二轮来得快就读不到）
    if mem:
        try:
            mem.add_user(message + (" [含图片]" if image_path else ""))
        except: pass

    async def generate():
        try:
            sent_any = False
            reply_parts = []
            vision_summary = ""
            for _h in history:
                _c = (_h.get("content") or "")
                if _c.startswith("[视觉分析]"):
                    vision_summary = _c
            cancel_token = CancellationToken()
            async for kind, text in assistant_graph_stream(
                message=message, history=history, slots={},
                vision_summary=vision_summary, session_id=sid, max_rounds=5,
                cancellation=cancel_token, user_id=user_id,
            ):
                if await request.is_disconnected():
                    cancel_token.cancel()
                    print("[Assistant] 客户端断开，停止")
                    break
                yield f"data: {json.dumps({'type': kind, 'content': text}, ensure_ascii=False)}\n\n"
                sent_any = True
                if kind in ("chunk", "error"):
                    reply_parts.append(text)
            if mem:
                try:
                    # 用户消息包含图时标注一下
                    user_log = message + (" [含图片]" if image_path else "")
                    mem.add_user(user_log)
                    if vision_injected:
                        # 避免重复存，history 已注入，这里只存一次
                        pass
                    if reply_parts:
                        mem.add_assistant("".join(reply_parts))
                except Exception:
                    pass
            if not sent_any:
                yield f"data: {json.dumps({'type':'done','content':''}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','content':str(e)}, ensure_ascii=False)}\n\n"
        finally:
            if image_path:
                try:
                    Path(image_path).unlink(missing_ok=True)
                except Exception:
                    pass
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"X-Session-Id": sid})

@app.get("/api/ai/history")
def history(session_id: str = Query(...)):
    """获取会话历史。"""
    mem = get_session(session_id)
    return {"session_id": session_id, "messages": mem.get_history()}


@app.delete("/api/ai/session")
def clear_session(session_id: str = Query(...)):
    """清除会话。"""
    mem = get_session(session_id)
    mem.clear()
    return {"session_id": session_id, "status": "cleared"}


@app.get("/api/ai/health")
def health():
    return {"status": "ok", "model": MIMO_MODEL}


# ====== 内部 ======

def _save_upload(file: UploadFile) -> str:
    ext = Path(file.filename).suffix or ".jpg"
    name = f"{uuid.uuid4().hex}{ext}"
    path = UPLOAD_DIR / name
    with path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return str(path.absolute())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)





