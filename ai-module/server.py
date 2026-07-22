"""
安全隐患分析 AI 服务 — FastAPI HTTP 接口。
启动: python server.py  (默认 0.0.0.0:8000)
"""
import json
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agents import (
    create_router_agent, create_vision_agent,
    create_retrieval_agent, create_report_agent,
)
from core import Orchestrator
from core.memory import get_session
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
