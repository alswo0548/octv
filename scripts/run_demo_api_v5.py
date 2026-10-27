"""Opt-in FastAPI entrypoint that only adds the isolated Demo MP4 bridge."""
from __future__ import annotations

import os
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    from backend.app.main import app  # loads team's .env and its original routers
    if os.getenv("OCTV_DEMO_ENABLED", "0").strip() != "1":
        raise RuntimeError("Demo 비활성: backend/.env에 OCTV_DEMO_ENABLED=1 필요")
    from backend.app.demo_v5_media.router import router
    app.include_router(router)
    # v5-only bootstrap: schedule the existing safe mapping-cache task for
    # monitored UTIC and DEMO cameras. Never write to SQL or override Rules.
    if os.getenv("OCTV_AUTO_MAPPING_ENABLED", "0").strip() == "1":
        try:
            from backend.app.workers import prewarm_all_context_mappings
            prewarm_all_context_mappings.apply_async()
        except Exception:
            import logging
            logging.getLogger(__name__).warning("CCTV context mapping prewarm enqueue unavailable")
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
