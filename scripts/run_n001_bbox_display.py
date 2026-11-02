"""Optional *display-only* real YOLO process for DEMO-N001.

It never calls the incident pipeline, sends notifications or updates DB rows.
Run one instance only. A Docker CPU/memory quota protects the existing detector.
All outputs are ephemeral Redis JSON with a session stamp and a short TTL.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
from ultralytics import YOLO

from ai.demo_v5.model_router import APPROVED_HASHES
from ai.demo_v5.session_pipeline import active_session
from ai.demo_v5.telemetry import client

KEY = "octv:n001:display:bbox:v1"
INTERVAL = max(0.75, float(os.getenv("OCTV_N001_BBOX_INTERVAL_SEC", "1.0")))
VIDEO = Path(os.getenv("OCTV_DEMO_VIDEO_DIR", "/app/demo/videos")) / "N001_demo.mp4"
MODEL = VIDEO.parent / "_v5" / "weights" / "N052_S2_epoch005.pt"
stopping = False


def _stop(*_):
    global stopping
    stopping = True


def _hash_matches(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


def _n001_id() -> int:
    from backend.app.db.session import get_connection
    with get_connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute(
            "SELECT id FROM cctvs WHERE provider='DEMO' AND external_cctv_id='DEMO-N001'"
        ).fetchall()
    if len(rows) != 1:
        raise RuntimeError("N001 전용 CCTV ID가 유일하지 않습니다.")
    return int(rows[0]["id"])


def main() -> None:
    if os.getenv("OCTV_N001_LIVE_BBOX_ENABLED", "0").strip() != "1":
        raise SystemExit("N001 표시용 YOLO는 명시적으로 활성화된 경우에만 시작합니다.")
    if not _hash_matches(VIDEO, APPROVED_HASHES["../N001_demo.mp4"]):
        raise SystemExit("승인된 N001 원본 MP4가 아니므로 표시용 분석을 시작하지 않습니다.")
    if not _hash_matches(MODEL, APPROVED_HASHES["weights/N052_S2_epoch005.pt"]):
        raise SystemExit("승인된 N001 YOLO 가중치가 아니므로 시작하지 않습니다.")

    # Bound intra-inference CPU contention as well as the separate Docker quota.
    try:
        import torch
        torch.set_num_threads(1)
    except (ImportError, RuntimeError):
        pass
    model = YOLO(str(MODEL))
    cap = cv2.VideoCapture(str(VIDEO))
    if not cap.isOpened():
        raise SystemExit("N001 MP4 디코더 열기 실패")
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0 or count <= 0:
        cap.release()
        raise SystemExit("N001 영상 시간 정보가 올바르지 않습니다.")
    duration = count / fps
    cctv_id = _n001_id()
    redis = client()
    redis.delete(KEY)
    session = None
    last_check = 0.0
    last_tick = 0.0
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    print(f"[N001 BBOX] display-only started, cctv_id={cctv_id}, interval={INTERVAL}s", flush=True)
    try:
        while not stopping:
            now = time.monotonic()
            if now - last_check >= 2.0:
                try:
                    active = active_session(cctv_id)  # SELECT only; no incident writes
                except Exception:
                    active = None
                if active != session:
                    session = active
                    redis.delete(KEY)
                    last_tick = 0.0
                last_check = now
            if session is None:
                time.sleep(0.25)
                continue
            if now - last_tick < INTERVAL:
                time.sleep(0.05)
                continue
            last_tick = now
            captured_at = datetime.now(timezone.utc)
            if captured_at < session:
                time.sleep(0.1)
                continue
            t = (captured_at - session).total_seconds() % duration
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, image = cap.read()
            if not ok:
                time.sleep(0.2)
                continue
            pts = float(cap.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            if not 0 <= pts < duration + 0.1:
                continue
            result = model.predict(image, imgsz=640, device="cpu", conf=0.5, verbose=False)[0]
            boxes = []
            if result.boxes is not None:
                for xyxy, confidence, cls in zip(
                    result.boxes.xyxy.cpu().tolist(),
                    result.boxes.conf.cpu().tolist(),
                    result.boxes.cls.cpu().tolist(),
                ):
                    if result.names[int(cls)] != "flood" or confidence < 0.80:
                        continue
                    coords = [float(v) for v in xyxy]
                    if all(0 <= v for v in coords) and coords[0] < coords[2] and coords[1] < coords[3]:
                        boxes.append({
                            "bbox": coords, "confidence": float(confidence), "hazard_type": "flood"
                        })
            height, width = image.shape[:2]
            generated_at = datetime.now(timezone.utc)
            payload = {
                "session": session.isoformat(),
                "captured_at": captured_at.isoformat(),
                "generated_at": generated_at.isoformat(),
                "frame": {
                    "t": pts, "width": width, "height": height,
                    "source_epoch": session.isoformat(),
                    "boxes": boxes[:5],
                },
            }
            # Writer has no ability to change real detection or Incident state.
            redis.setex(KEY, 6, json.dumps(payload, allow_nan=False))
    finally:
        cap.release()
        try:
            redis.delete(KEY)
        except Exception:
            pass
        print("[N001 BBOX] display-only stopped", flush=True)


if __name__ == "__main__":
    main()
