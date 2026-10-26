"""
安全隐患分析 AI 服务 — FastAPI HTTP 接口。
启动: python server.py  (默认 127.0.0.1:8000)
"""
import asyncio
import hmac
import json
import logging
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, Header, Query, Request, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import JSONResponse, StreamingResponse

from core.memory import (
    SessionStoreUnavailable,
    SessionTurnBusy,
    acquire_session_turn,
    get_session,
    session_backend_status,
)
from core.cancellation import CancellationToken
from core.assistant_graph import (
    checkpoint_backend_status,
    clear_thread,
    run_stream_events as assistant_graph_stream,
)
from tools.milvus_store import MilvusVectorStore
from config import (AI_BIND_HOST, AI_BIND_PORT, AI_CORS_ORIGINS, AI_INTERNAL_TOKEN,
                      MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL, HAZARD_CREATE_WORKER_INLINE)

logger = logging.getLogger("safety.ai")


def _log_backend_choice() -> None:
    """启动时把会话/checkpoint 后端打出来，并提醒 memory 后端不支持多 worker。"""
    session_backend = session_backend_status()
    checkpoint = checkpoint_backend_status()
    logger.info(
        "session backend=%s effective=%s | checkpoint backend=%s effective=%s",
        session_backend["configured"], session_backend["effective"],
        checkpoint["configured"], checkpoint["effective"],
    )
    for name, status in (("SESSION_BACKEND", session_backend), ("CHECKPOINT_BACKEND", checkpoint)):
        if status["configured"] == "memory":
            logger.warning(
                "%s=memory：状态只存在本进程，多 worker/重启会丢；生产请切 redis", name
            )
        elif status["effective"] == "memory":
            logger.error("%s=redis 但已降级到 memory：%s", name, status.get("error"))



@asynccontextmanager
async def _lifespan(_app):
    """本地开发可选：把建单 MQ worker 跑在进程内；生产用独立进程 hazard_create_worker.py。"""
    stop = threading.Event()
    threads = []
    if HAZARD_CREATE_WORKER_INLINE:
        from tools.hazard_create_queue import RelayWorker, RequestReconciler, ResultConsumer
        relay = RelayWorker()
        threads = [
            threading.Thread(target=relay.run_forever, args=(stop,), daemon=True),
            threading.Thread(target=ResultConsumer().run_forever, args=(stop,), daemon=True),
            threading.Thread(target=RequestReconciler().run_forever, args=(stop,), daemon=True),
        ]
        for t in threads:
            t.start()
        logger.info("hazard create worker started inline")
    _log_backend_choice()
    try:
        yield
    finally:
        stop.set()


app = FastAPI(title="Safety AI", version="1.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(AI_CORS_ORIGINS),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Internal-Token"],
)


@app.middleware("http")
async def require_internal_token(request: Request, call_next):
    """Python 只作为 Java 的内部服务；health 是唯一公开端点。"""
    path = request.url.path
    if path == "/api/ai/health":
        return await call_next(request)
    if path == "/api/ai" or path.startswith("/api/ai/"):
        supplied = request.headers.get("X-Internal-Token", "")
        if not AI_INTERNAL_TOKEN or not hmac.compare_digest(supplied, AI_INTERNAL_TOKEN):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 图片处理是阻塞的（PIL 解码/缩放 + 同步 HTTP 等视觉模型，最长 60s）。
# uvicorn 只有一个事件循环，而所有会话的 SSE 逐字输出都跑在这个循环上，
# 所以阻塞调用必须挪进线程池，否则一个带图请求会冻住所有人的打字机效果。
# 显式有界（8）而不是用默认池：默认是 min(32, CPU+4)，2 核机器上只有 6，且语义不明确。
_IMAGE_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="img-io")


async def _run_blocking(fn, *args):
    """把阻塞函数丢到线程池执行，避免卡住事件循环。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_IMAGE_EXECUTOR, fn, *args)

# ====== 兼容入口的共用部件 ======
# 全仓只有一套编排：老接口（analyze / chat）与新接口（assistant）都跑同一张助手图，
# 老接口只负责把事件名映射回旧契约。第二套编排（Orchestrator + agents/）已删除。
COMPAT_DEFAULT_TEXT = "请分析这张图片中的安全隐患，并生成报告"


def _sse(event_type: str, content) -> str:
    return "data: " + json.dumps(
        {"type": event_type, "content": content}, ensure_ascii=False
    ) + "\n\n"


def _require_user_id(user_id) -> int:
    if user_id is None:
        raise HTTPException(status_code=400, detail="user_id required")
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="user_id must be an integer")


def _begin_session_turn(user_id: int, session_id: str):
    try:
        return acquire_session_turn(user_id, session_id)
    except SessionTurnBusy:
        raise HTTPException(status_code=409, detail="session turn already in progress")
    except SessionStoreUnavailable:
        raise HTTPException(status_code=503, detail="session store unavailable")


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
    uid = _require_user_id(user_id)
    sid = session_id or str(uuid.uuid4())
    lease = _begin_session_turn(uid, sid)
    image_path = None
    try:
        image_path = await _run_blocking(_save_upload, file) if file else None
        vision_json, extra = await _run_blocking(_compat_vision, image_path)
        mem = get_session(uid, sid)
        history = mem.get_history() + extra
        if not text and image_path:
            text = "请分析这张图片中的安全隐患"
        try:
            mem.add_user(text + (" [含图片]" if image_path else ""))
        except Exception:
            pass
        reply = []
        async for kind, chunk in _compat_run(text, history, sid, uid):
            if kind == "chunk":
                reply.append(str(chunk))
            elif kind == "interrupt":
                question = str((chunk or {}).get("question") or "")
                if question:
                    reply.append(question)
        body = _collect_reply(reply)
        if body:
            try:
                mem.add_assistant(body)
            except Exception:
                pass
        return {"session_id": sid, "vision": vision_json, "report": body}
    finally:
        lease.release()
        _unlink_quietly(image_path)


@app.post("/api/ai/analyze/stream")
async def analyze_stream(
    request: Request,
    file: UploadFile = File(None),
    text: str = Form(default=COMPAT_DEFAULT_TEXT),
    session_id: str = Form(default=""),
    user_id: int = Form(None),
):
    """兼容（SSE）：事件名沿用旧契约 status/vision/no_hazard/report/error/done。"""
    uid = _require_user_id(user_id)
    sid = session_id or str(uuid.uuid4())
    lease = _begin_session_turn(uid, sid)
    image_path = None
    try:
        image_path = await _run_blocking(_save_upload, file) if file else None
        vision_json, extra = await _run_blocking(_compat_vision, image_path)
        mem = get_session(uid, sid)
        history = mem.get_history() + extra
        if not text and image_path:
            text = "请分析这张图片中的安全隐患"
        try:
            mem.add_user(text + (" [含图片]" if image_path else ""))
        except Exception:
            pass

        async def generate():
            reply = []
            try:
                yield _sse("status", "正在识别图片中的安全隐患...")
                if vision_json is not None:
                    yield _sse("vision", vision_json)
                    if isinstance(vision_json, dict) and vision_json.get("has_hazard") is False:
                        yield _sse("no_hazard", vision_json.get("reason_if_no_hazard", ""))
                        yield _sse("done", "")
                        return
                elif image_path:
                    yield _sse("error", "视觉识别失败")
                async for kind, chunk in _compat_run(text, history, sid, uid):
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
                if reply:
                    try:
                        mem.add_assistant(_collect_reply(reply))
                    except Exception:
                        pass
                lease.release()
                _unlink_quietly(image_path)

        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"X-Session-Id": sid})
    except Exception:
        lease.release()
        _unlink_quietly(image_path)
        raise


@app.post("/api/ai/chat")
async def chat(
    message: str = Form(...),
    session_id: str = Form(...),
    user_id: int = Form(None),
):
    """兼容（非流式）：追问，返回 {session_id, reply}。"""
    uid = _require_user_id(user_id)
    lease = _begin_session_turn(uid, session_id)
    try:
        mem = get_session(uid, session_id)
        history = mem.get_history()
        try:
            mem.add_user(message)
        except Exception:
            pass
        reply = []
        async for kind, chunk in _compat_run(message, history, session_id, uid):
            if kind == "chunk":
                reply.append(str(chunk))
            elif kind == "interrupt":
                question = str((chunk or {}).get("question") or "")
                if question:
                    reply.append(question)
        body = _collect_reply(reply)
        if body:
            try:
                mem.add_assistant(body)
            except Exception:
                pass
        return {"session_id": session_id, "reply": body}
    finally:
        lease.release()


@app.post("/api/ai/chat/stream")
async def chat_stream(
    request: Request,
    message: str = Form(...),
    session_id: str = Form(...),
    user_id: int = Form(None),
):
    """兼容（SSE）：追问。事件名与助手接口一致（type/content）。"""
    uid = _require_user_id(user_id)
    lease = _begin_session_turn(uid, session_id)
    try:
        mem = get_session(uid, session_id)
        history = mem.get_history()
        try:
            mem.add_user(message)
        except Exception:
            pass

        async def generate():
            reply = []
            try:
                async for kind, chunk in _compat_run(message, history, session_id, uid):
                    if await request.is_disconnected():
                        break
                    if kind == "chunk":
                        reply.append(str(chunk))
                    yield _sse(kind, chunk)
            finally:
                if reply:
                    try:
                        mem.add_assistant(_collect_reply(reply))
                    except Exception:
                        pass
                lease.release()

        return StreamingResponse(generate(), media_type="text/event-stream")
    except Exception:
        lease.release()
        raise

@app.post("/api/ai/assistant/stream")
async def assistant_stream(
    request: Request,
    message: str = Form(None),
    session_id: str = Form(None),
    user_id: int = Form(None),
    selected_major_code: str = Form(None),
    interrupt_reply: str = Form(None),
    image_url: str = Form(None),
    image_file_id: int = Form(None),
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
            interrupt_reply = (
                body.get("interrupt_reply")
                or body.get("interruptReply")
                or ""
            )
            image_url = body.get("image_url") or body.get("imageUrl") or ""
            image_file_id = body.get("image_file_id") or body.get("imageFileId")
        except Exception:
            message = ""
            session_id = ""
    uid = _require_user_id(user_id)
    message = (message or "").strip()
    if not message and (file is None or not getattr(file, "filename", "")):
        raise HTTPException(status_code=400, detail="message or file required")
    sid = session_id or str(uuid.uuid4())
    lease = _begin_session_turn(uid, sid)
    image_path = None
    try:
        mem = get_session(uid, sid)
        history = mem.get_history()
        max_keep = getattr(mem, "max_turns", 10) * 2
        if len(history) > max_keep:
            history = history[-max_keep:]
        # 有图写死必调：先跑视觉，结果注入历史，保证有图必看
        if file is not None and getattr(file, "filename", ""):
            try:
                image_path = await _run_blocking(_save_upload, file)
                # 同步注入视觉结果到 history（不依赖模型是否调工具）
                try:
                    from mimo_client import MiMoVisionClient
                    from prompts import VISION_PROMPT
                    vc = MiMoVisionClient()
                    vision_json = await _run_blocking(vc.analyze_json, image_path, VISION_PROMPT)
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
                    # add_system 在两种后端下语义一致（memory 追加到列表 / redis RPUSH+LTRIM），
                    # 不要再 mem.messages.append(...)：Redis 后端下 messages 是即时读出来的副本。
                    mem.add_system(vision_content)
                except Exception:
                    pass
                if len(history) > max_keep:
                    history = history[-max_keep:]
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"图片处理失败: {e}")

        if not message and image_path:
            message = "请分析这张图片中的安全隐患"
        # 立刻落库用户消息，保证第二轮多轮能读到（原来在 generate 结束后才落库，第二轮来得快就读不到）
        try:
            mem.add_user(message + (" [含图片]" if image_path else ""))
        except Exception:
            pass

        async def generate():
            try:
                sent_any = False
                reply_parts = []
                vision_summary = ""
                for item in history:
                    content = (item.get("content") or "")
                    if content.startswith("[视觉分析]"):
                        vision_summary = content
                cancel_token = CancellationToken()
                async for kind, text in assistant_graph_stream(
                    message=message, history=history, slots={},
                    vision_summary=vision_summary, session_id=sid, max_rounds=5,
                    cancellation=cancel_token, user_id=uid,
                    selected_major_code=selected_major_code or "",
                    interrupt_reply=interrupt_reply or "",
                    image_url=image_url or "",
                    image_file_id=image_file_id,
                ):
                    if await request.is_disconnected():
                        cancel_token.cancel()
                        print("[Assistant] 客户端断开，停止")
                        break
                    yield f"data: {json.dumps({'type': kind, 'content': text}, ensure_ascii=False)}\n\n"
                    sent_any = True
                    if kind in ("chunk", "error"):
                        reply_parts.append(text)
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
                lease.release()
                _unlink_quietly(image_path)

        return StreamingResponse(generate(), media_type="text/event-stream", headers={"X-Session-Id": sid})
    except Exception:
        lease.release()
        _unlink_quietly(image_path)
        raise


@app.get("/api/ai/history")
def history(session_id: str = Query(...), user_id: int = Query(...)):
    """获取会话历史；user_id 由 Java 从当前登录态注入。"""
    mem = get_session(user_id, session_id)
    return {"session_id": session_id, "messages": mem.get_history()}


@app.delete("/api/ai/session")
def clear_session(session_id: str = Query(...), user_id: int = Query(...)):
    """清除当前用户的会话；活跃 turn 先拒绝，避免 checkpoint 被并发写回。"""
    try:
        lease = acquire_session_turn(user_id, session_id)
    except SessionTurnBusy as exc:
        raise HTTPException(status_code=409, detail="会话正在处理中，请稍后再清空") from exc
    try:
        clear_thread(user_id, session_id)
        mem = get_session(user_id, session_id)
        mem.clear()
        return {"session_id": session_id, "status": "cleared"}
    finally:
        lease.release()


@app.get("/api/ai/hazard-create/requests/{request_id}")
def hazard_create_status(request_id: str, user_id: int = Query(...)):
    """AI 建单状态查询。Java 侧 /api/hazard/requests/{id} 代理到这里（前端只认 Java）。"""
    from tools.hazard_create_queue import get_request_status
    body = get_request_status(request_id, user_id=user_id)
    if body is None:
        raise HTTPException(status_code=404, detail="request not found")
    return body


@app.get("/api/ai/health")
def health():
    return {
        "status": "ok",
        "model": MIMO_MODEL,
        "session_backend": session_backend_status(),
        "checkpoint_backend": checkpoint_backend_status(),
    }



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
    if not AI_INTERNAL_TOKEN or not hmac.compare_digest(x_internal_token, AI_INTERNAL_TOKEN):
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
    uvicorn.run(app, host=AI_BIND_HOST, port=AI_BIND_PORT)


