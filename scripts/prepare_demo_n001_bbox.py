"""Prepare presentation-only YOLO bbox overlay for the ORIGINAL N001 MP4.

Run once, with the project's existing ultralytics/cv2 environment:
  python -m scripts.prepare_demo_n001_bbox

The source video, .pt model, incident detection, DB and the two other Demo
videos are never modified. Output JSON is local-only (ignored by git).
The browser synchronizes annotations to the exact MP4 currentTime; this is
precomputed model inference, not real-time per-frame inference.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ai.demo_v5.model_router import APPROVED_HASHES, ROOT

VIDEO = ROOT / "demo/videos/N001_demo.mp4"
MODEL = ROOT / "demo/videos/_v5/weights/N052_S2_epoch005.pt"
OUTPUT = ROOT / "demo/videos/_v5/N001_bbox.json"
STEP_SEC = 0.35
ENTRY_CONF = 0.80
KEEP_CONF = 0.50


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    import cv2
    from ultralytics import YOLO

    if not VIDEO.is_file() or not MODEL.is_file():
        raise SystemExit("승인된 N001 영상 또는 모델이 없습니다. 원본을 보존해주세요.")
    video_hash = sha256(VIDEO)
    model_hash = sha256(MODEL)
    if video_hash != APPROVED_HASHES["../N001_demo.mp4"] or model_hash != APPROVED_HASHES["weights/N052_S2_epoch005.pt"]:
        raise SystemExit("승인된 N001 영상/모델 SHA256 불일치 · 중단합니다.")

    cap = cv2.VideoCapture(str(VIDEO))
    if not cap.isOpened():
        raise SystemExit("N001 MP4를 열 수 없습니다.")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if fps <= 0 or count <= 0 or width <= 0 or height <= 0:
            raise SystemExit("영상 FPS·길이·해상도를 확인할 수 없습니다.")
        duration = count / fps
        every = max(1, round(STEP_SEC * fps))
        model = YOLO(str(MODEL))
        frames = []
        active = False
        detected_samples = 0

        for index in range(count):
            if index % every != 0:
                if not cap.grab():
                    break
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            predictions = model.predict(source=frame, imgsz=640, device="cpu",
                                        conf=KEEP_CONF, verbose=False)[0]
            boxes = []
            if predictions.boxes is not None:
                coords = predictions.boxes.xyxy.cpu().tolist()
                scores = predictions.boxes.conf.cpu().tolist()
                classes = predictions.boxes.cls.cpu().tolist()
                for rect, conf, cls in zip(coords, scores, classes):
                    if predictions.names[int(cls)] != "flood":
                        continue
                    boxes.append({"bbox": [round(float(v), 2) for v in rect],
                                  "confidence": round(float(conf), 4)})
            boxes.sort(key=lambda item: item["confidence"], reverse=True)
            if not boxes or (not active and boxes[0]["confidence"] < ENTRY_CONF):
                active = False
                boxes = []
            else:
                active = True
                boxes = boxes[:3]
                detected_samples += 1
            frames.append({"t": round(index / fps, 4), "boxes": boxes})
            if len(frames) % 50 == 0:
                print(f"[N001 bbox] {index / fps:.1f}/{duration:.1f}초 분석 완료")
    finally:
        cap.release()

    if not frames or detected_samples == 0:
        raise SystemExit("N001 영상에서 승인 임계값을 통과한 침수 박스가 없습니다. 결과물을 생성하지 않습니다.")
    output = {
        "schema": 1, "camera": "DEMO-N001", "video_sha256": video_hash,
        "model_sha256": model_hash, "duration_sec": round(duration, 5),
        "width": width, "height": height, "sample_interval_sec": round(every / fps, 5),
        "frames": frames,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    try:
        temporary.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, OUTPUT)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"[N001 bbox] 준비 완료 · {len(frames)}개 시점 / 탐지 {detected_samples}개 시점 · {OUTPUT}")
    print("[N001 bbox] 시연 표시용 사전 YOLO 추론 결과입니다. 실제 사건 분석과 독립입니다.")


if __name__ == "__main__":
    main()
