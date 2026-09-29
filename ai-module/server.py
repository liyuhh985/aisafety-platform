"""
安全隐患分析 AI 服务 — FastAPI HTTP 接口。
启动: python server.py  (默认 0.0.0.0:8000)
"""
import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, Header, Query, Request, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from core.memory import get_session
from core.cancellation import CancellationToken
from core.assistant_graph import run_stream_events as assistant_graph_stream
from tools.milvus_store import MilvusVectorStore
from config import AI_INTERNAL_TOKEN, MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL

logger = logging.getLogger("safety.ai")

app = FastAPI(title="Safety AI", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ====== 兼容入口的共用部件 ======
# 全仓只有一套编排：老接口（analyze / chat）与新接口（assistant）都跑同一张助手图，
# 老接口只负责把事件名映射回旧契约。第二套编排（Orchestrator + agents/）已删除。
COMPAT_DEFAULT_TEXT = "请分析这张图片中的安全隐患，并生成报告"


def _sse(event_type: str, content) -> str:
    return "data: " + json.dumps(
        {"type": event_type, "content": content}, ensure_ascii=False
    ) + "\n\n"


def _find_vision_summary(history) -> str:
    for item in history or []:
        content = (item or {}).get("content") or ""
        if content.startswith("[视觉分析]"):
            return content
    return ""


def _compat_vision(image_path):
    """与助手链路共用同一个视觉客户端，返回 (解析结果, 注入 history 的条目)。"""
    if not image_path:
        return None, []
    try:
        from mimo_client import MiMoVisionClient
        from prompts import VISION_PROMPT
        vision_json = MiMoVisionClient().analyze_json(image_path, VISION_PROMPT)
    except Exception:
        vision_json = None
    content = (
        f"[视觉分析] {vision_json}" if vision_json
        else "[视觉分析失败，请仅按用户文字描述判断，不要编造图中细节]"
    )
    return vision_json, [{"role": "system", "content": content}]


def _unlink_quietly(path) -> None:
    if not path:
        return
    try:
        Path(path).unlink()
    except Exception:
        pass


def _compat_run(text, history, sid, user_id):
    return assistant_graph_stream(
        message=text, history=history, slots={},
        vision_summary=_find_vision_summary(history),
        session_id=sid, max_rounds=5, cancellation=None, user_id=user_id,
        selected_major_code="",
    )


def _collect_reply(reply: list) -> str:
    return "".join(reply)


# ====== REST API（兼容入口） ======

@app.post("/api/ai/analyze")
async def analyze(
    file: UploadFile = File(None),
    text: str = Form(default=COMPAT_DEFAULT_TEXT),
    session_id: str = Form(default=""),
    user_id: int = Form(None),
):
    """兼容（非流式）：返回 {session_id, vision, report}，内部走助手图。"""
    image_path = _save_upload(file) if file else None
    sid = session_id or str(uuid.uuid4())
    vision_json, extra = _compat_vision(image_path)
    mem = get_session(sid)
    history = (mem.get_history() if mem else []) + extra
    if not text and image_path:
        text = "请分析这张图片中的安全隐患"
    if mem:
        try:
            mem.add_user(text + (" [含图片]" if image_path else ""))
        except Exception:
            pass
    reply = []
    try:
        async for kind, chunk in _compat_run(text, history, sid, user_id):
            if kind == "chunk":
                reply.append(str(chunk))
            elif kind == "interrupt":
                question = str((chunk or {}).get("question") or "")
                if question:
                    reply.append(question)
    finally:
        _unlink_quietly(image_path)
    body = _collect_reply(reply)
    if mem and body:
        try:
            mem.add_assistant(body)
        except Exception:
            pass
    return {"session_id": sid, "vision": vision_json, "report": body}


@app.post("/api/ai/analyze/stream")
async def analyze_stream(
    request: Request,
    file: UploadFile = File(None),
    text: str = Form(default=COMPAT_DEFAULT_TEXT),
    session_id: str = Form(default=""),
    user_id: int = Form(None),
):
    """兼容（SSE）：事件名沿用旧契约 status/vision/no_hazard/report/error/done。"""
    image_path = _save_upload(file) if file else None
    sid = session_id or str(uuid.uuid4())
    vision_json, extra = _compat_vision(image_path)
    mem = get_session(sid)
    history = (mem.get_history() if mem else []) + extra
    if not text and image_path:
        text = "请分析这张图片中的安全隐患"
    if mem:
        try:
            mem.add_user(text + (" [含图片]" if image_path else ""))
        except Exception:
            pass

    async def generate():
        reply = []
        yield _sse("status", "正在识别图片中的安全隐患...")
        if vision_json is not None:
            yield _sse("vision", vision_json)
            if isinstance(vision_json, dict) and vision_json.get("has_hazard") is False:
                yield _sse("no_hazard", vision_json.get("reason_if_no_hazard", ""))
                yield _sse("done", "")
                _unlink_quietly(image_path)
                return
        elif image_path:
            yield _sse("error", "视觉识别失败")
        try:
            async for kind, chunk in _compat_run(text, history, sid, user_id):
                if await request.is_disconnected():
                    break
                if kind == "chunk":
                    reply.append(str(chunk))
                    yield _sse("report", chunk)
                elif kind == "interrupt":
                    question = str((chunk or {}).get("question") or "")
                    if question:
                        reply.append(question)
                        yield _sse("report", question)
                elif kind in ("status", "error", "done"):
                    yield _sse(kind, chunk)
        finally:
            if mem and reply:
                try:
                    mem.add_assistant(_collect_reply(reply))
                except Exception:
                    pass
            _unlink_quietly(image_path)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"X-Session-Id": sid})


@app.post("/api/ai/chat")
async def chat(
    message: str = Form(...),
    session_id: str = Form(...),
    user_id: int = Form(None),
):
    """兼容（非流式）：追问，返回 {session_id, reply}。"""
    mem = get_session(session_id)
    history = mem.get_history() if mem else []
    if mem:
        try:
            mem.add_user(message)
        except Exception:
            pass
    reply = []
    async for kind, chunk in _compat_run(message, history, session_id, user_id):
        if kind == "chunk":
            reply.append(str(chunk))
        elif kind == "interrupt":
            question = str((chunk or {}).get("question") or "")
            if question:
                reply.append(question)
    body = _collect_reply(reply)
    if mem and body:
        try:
            mem.add_assistant(body)
        except Exception:
            pass
    return {"session_id": session_id, "reply": body}


@app.post("/api/ai/chat/stream")
async def chat_stream(
    request: Request,
    message: str = Form(...),
    session_id: str = Form(...),
    user_id: int = Form(None),
):
    """兼容（SSE）：追问。事件名与助手接口一致（type/content）。"""
    mem = get_session(session_id)
    history = mem.get_history() if mem else []
    if mem:
        try:
            mem.add_user(message)
        except Exception:
            pass

    async def generate():
        reply = []
        try:
            async for kind, chunk in _compat_run(message, history, session_id, user_id):
                if await request.is_disconnected():
                    break
                if kind == "chunk":
                    reply.append(str(chunk))
                yield _sse(kind, chunk)
        finally:
            if mem and reply:
                try:
                    mem.add_assistant(_collect_reply(reply))
                except Exception:
                    pass

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/ai/assistant/stream")
async def assistant_stream(
    request: Request,
    message: str = Form(None),
    session_id: str = Form(None),
    user_id: int = Form(None),
    selected_major_code: str = Form(None),
    file: UploadFile = File(None),
):
    # 兼容 JSON 和 multipart：有 file 走 FormData，无 file 走 JSON
    if message is None:
        try:
            body = await request.json()
            message = body.get("message", "") or body.get("text", "")
            session_id = body.get("session_id", "") or body.get("sessionId", "") or ""
            user_id = body.get("user_id")
            selected_major_code = (
                body.get("selected_major_code")
                or body.get("selectedMajorCode")
                or ""
            )
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
    if file is not None and getattr(file, "filename", ""):
        try:
            image_path = _save_upload(file)
            # 同步注入视觉结果到 history（不依赖模型是否调工具）
            try:
                from mimo_client import MiMoVisionClient
                from prompts import VISION_PROMPT
                vc = MiMoVisionClient()
                vision_json = vc.analyze_json(image_path, VISION_PROMPT)
            except Exception:
                vision_json = None
            vision_content = (
                f"[视觉分析] {vision_json}"
                if vision_json
                else "[视觉分析失败，请仅按用户文字描述判断，不要编造图中细节]"
            )
            history = history + [{"role": "system", "content": vision_content}]
            # 立刻落库，保证第二轮能读到；失败也只记录这一条失败信息
            try:
                mem.messages.append({"role": "system", "content": vision_content})
                mem._trim()
            except Exception:
                pass
            if len(history) > max_keep:
                history = history[-max_keep:]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"图片处理失败: {e}")


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
                selected_major_code=selected_major_code or "",
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



# ====== 内部：Java 向量删除回执 ======

# 只允许删除这三张检索源表（与 Java 侧 VectorSyncOutboxService 的白名单一致）。
VECTOR_DELETE_TABLES = frozenset({
    "tb_hazard_case",
    "tb_regulation",
    "tb_hazard_knowledge",
})
VECTOR_DELETE_MAX_IDS = 100


@app.post("/api/ai/internal/vectors/delete")
def delete_vectors(payload: dict = Body(...), x_internal_token: str = Header(default="")):
    """Java 向量删除 outbox 的回执端点：按表名加主键删除 Milvus 里的向量。

    鉴权用共享密钥 X-Internal-Token（与 Java 侧 ai.internal-token 同源）。
    请求体故意收成 dict 而不是 Pydantic 模型：形状不合法时这里要回 400，
    不能退化成 FastAPI 默认的 422 —— Java 侧把 400/401/422 都当永久失败，
    但 422 的报文对排查没有帮助。
    """
    if not AI_INTERNAL_TOKEN or x_internal_token != AI_INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    table = payload.get("table")
    if table not in VECTOR_DELETE_TABLES:
        raise HTTPException(status_code=400, detail="Unsupported table")

    ids = payload.get("ids")
    if not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="ids must be a list")
    if not ids or len(ids) > VECTOR_DELETE_MAX_IDS:
        raise HTTPException(status_code=400, detail="ids length out of range")
    for doc_id in ids:
        if isinstance(doc_id, bool) or not isinstance(doc_id, int) or doc_id < 1:
            raise HTTPException(status_code=400, detail="ids must be positive integers")

    try:
        MilvusVectorStore().delete_ids(table, ids)
    except Exception:
        logger.exception("vector delete failed table=%s ids=%s", table, ids)
        raise HTTPException(status_code=503, detail="Vector store unavailable")

    return {"deleted_count": len(ids)}


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





