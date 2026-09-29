# Demo Day23 - 最小 FastAPI：hello + 流式，对照 server.py
# 目标：跑通 yield/StreamingResponse/asyncio.to_thread/Queue 这4个词
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import time

app = FastAPI(title="Day23 Demo")

# 1. 普通接口，对照 server.py 的 /api/ai/health
@app.get("/hello")
def hello():
    return {"msg": "hello from Day23"}

# 2. 最简流式，对照 server.py 的 yield f\"data: {payload}\\n\\n\"
#    逐块吐，不用等全算完
@app.get("/stream/simple")
async def stream_simple():
    async def gen():
        for i in range(5):
            yield f"data: {i}\n\n"  # SSE帧，必须 \\n\\n
            await asyncio.sleep(0.5)  # 对照 await，用 sleep 模拟LLM吐词
    return StreamingResponse(gen(), media_type="text/event-stream")

# 3. 进阶：同步阻塞任务丢线程池 + Queue，对照 _stream_with_disconnect 的核心
#    produce是同步的（像 orch.analyze_stream），不能卡事件循环
@app.get("/stream/thread-bridge")
async def stream_thread_bridge():
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def produce_blocking():
        # 模拟同步慢任务，每0.3秒产一块，共5块
        for i in range(5):
            time.sleep(0.3)
            # 跨线程往Queue放，必须用 run_coroutine_threadsafe
            asyncio.run_coroutine_threadsafe(queue.put(f"data: thread-{i}\n\n"), loop).result()
        asyncio.run_coroutine_threadsafe(queue.put("END"), loop).result()

    async def gen():
        worker = asyncio.create_task(asyncio.to_thread(produce_blocking))
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue  # 0.1秒没数据就继续循环，这里本可以查 is_disconnected
                if item == "END":
                    break
                yield item
        finally:
            if not worker.done():
                worker.cancel()

    return StreamingResponse(gen(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
