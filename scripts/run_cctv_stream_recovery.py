"""Optional monitored-UTIC MediaMTX watchdog; independent from YOLO and Celery."""
from __future__ import annotations

import logging
import os
import time

from backend.app.config import load_environment


def main() -> None:
    load_environment()
    if os.getenv("OCTV_CCTV_STREAM_RECOVERY_ENABLED", "0").strip() != "1":
        print("[CCTV STREAM RECOVERY] disabled; exiting without changes")
        return

    from redis import Redis
    from backend.app.cctvs.stream_recovery import POLL_SECONDS, StreamRecoveryWatchdog

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = Redis.from_url(
        os.environ["OCTV_REDIS_URL"],
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    watchdog = StreamRecoveryWatchdog(client)
    logging.info("Monitored UTIC stream watchdog started (poll=%ss)", POLL_SECONDS)
    while True:
        for cctv_id, status in watchdog.step().items():
            if status not in {"healthy", "observing", "not-warm-path"}:
                logging.info("CCTV %s stream recovery: %s", cctv_id, status)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
