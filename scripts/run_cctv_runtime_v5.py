"""Opt-in v5 CCTV Runtime, preserving original run_cctv_runtime.py unchanged.

Command: python -m scripts.run_cctv_runtime_v5
Only run ONE CCTV Runtime process against a DB at a time. The UI/API server
needs OCTV_DEMO_ENABLED=1 independently, using the same backend/.env.
"""
from __future__ import annotations

import os
import signal
from pathlib import Path

from dotenv import load_dotenv

from ai.demo_v5.model_router import ROOT, build_router
from ai.detection.detector import YoloDetector
from ai.detection.incident_runtime import IncidentAwareCctvDetectionRuntime
from backend.app.db.session import get_connection


def main() -> None:
    load_dotenv(ROOT / "backend" / ".env")
    if os.getenv("OCTV_DEMO_ENABLED", "0").strip() != "1":
        raise RuntimeError("Demo 비활성: backend/.env에 OCTV_DEMO_ENABLED=1 필요")

    model = os.getenv("OCTV_YOLO_MODEL_PATH", "").strip()
    if not model:
        raise RuntimeError("운영 CCTV 모델 미설정: OCTV_YOLO_MODEL_PATH에 기존 승인 운영 모델을 지정해주세요. Demo 모델로 운영 CCTV를 임의 대체하지 않습니다.")

    runtime = IncidentAwareCctvDetectionRuntime()
    with get_connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        router = build_router(
            runtime._detector,
            conn,
            yolo_factory=YoloDetector,
            imgsz=int(os.getenv("OCTV_YOLO_IMGSZ", "640")),
            device=os.getenv("OCTV_YOLO_DEVICE", "cpu"),
        )
    from ai.demo_v5.session_pipeline import SessionPipeline
    runtime._incident_pipeline = SessionPipeline(runtime._incident_pipeline, router.routes_by_id)
    from ai.demo_v5.live_metadata import enabled
    if enabled():
        from ai.demo_v5.timeline import attach_timeline
        attach_timeline(runtime)
    from ai.demo_v5.telemetry import observing_detector
    runtime._yolo_worker.detect_fn = observing_detector(router.detect)
    print("[V5] 기존 VERIFY/Incident Pipeline 유지, UTIC 3대 + Demo 분기 준비 완료")

    def _stop(signum, _frame):
        print(f"[V5] 종료 신호 수신: {signum}")
        runtime.request_stop()

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)
    runtime.run_forever()


if __name__ == "__main__":
    main()

