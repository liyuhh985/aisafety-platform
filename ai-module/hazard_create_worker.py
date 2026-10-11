# -*- coding: utf-8 -*-
"""AI 建任务 MQ worker（独立进程）：Relay + ResultConsumer 一起跑。

启动： python hazard_create_worker.py
生产：systemd 单独托管一个进程（见 docs/current/ai-hazard-create-mq.md）。
本地：也可设 HAZARD_CREATE_WORKER_INLINE=true 跑在 FastAPI lifespan 里（server.py）。

为什么独立进程：relay/consumer 是后台消费者，不是 HTTP 请求的一部分 ——
独立进程可单独重启/限流，不与 web 抢 GIL/CPU，天然只有一个实例扫 outbox。
"""
import logging
import signal
import threading

from tools.hazard_create_queue import (MetricsReporter, RelayWorker, RequestReconciler, ResultConsumer, RequestRetentionWorker)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("safety.ai.hazard_worker")


def main() -> int:
    stop = threading.Event()

    def _shutdown(signum, frame):  # noqa: ANN001
        LOGGER.info("signal %s received, stopping", signum)
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    relay = RelayWorker()

    threads = [
        threading.Thread(target=relay.run_forever, args=(stop,), name="hazard-relay", daemon=True),
        threading.Thread(target=ResultConsumer().run_forever, args=(stop,),
                         name="hazard-result-consumer", daemon=True),
        threading.Thread(target=RequestReconciler().run_forever, args=(stop,),
                         name="hazard-reconciler", daemon=True),
        threading.Thread(target=MetricsReporter().run_forever, args=(stop,),
                         name="hazard-metrics", daemon=True),
        threading.Thread(target=RequestRetentionWorker().run_forever, args=(stop,),
                         name="hazard-retention", daemon=True),
    ]
    for t in threads:
        t.start()
    LOGGER.info("hazard create worker started (relay + result consumer)")
    stop.wait()
    for t in threads:
        t.join(timeout=10)
    try:
        relay.publisher.close()
    except Exception:
        pass
    LOGGER.info("hazard create worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


