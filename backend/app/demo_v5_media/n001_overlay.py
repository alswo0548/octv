"""N001-only read-only visual overlay data for its *original* approved MP4.

This file does not call the detector or alter event creation. Frame-time bbox
metadata is prepared offline by scripts/prepare_demo_n001_bbox.py.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ai.demo_v5.model_router import APPROVED_HASHES

OVERLAY_FILE = "N001_bbox.json"
VIDEO_HASH = APPROVED_HASHES["../N001_demo.mp4"]
MODEL_HASH = APPROVED_HASHES["weights/N052_S2_epoch005.pt"]


def read_n001_overlay(video_path: Path) -> dict[str, Any]:
    """Return no overlay if not prepared; refuse stale/unapproved metadata.

    Access to this method is gated by the existing authenticated Demo playback
    endpoint and the active-N001 check. Never expose arbitrary paths.
    """
    path = video_path.parent / "_v5" / OVERLAY_FILE
    if not video_path.is_file() or not path.is_file():
        return {"ready": False, "frames": []}
    if path.stat().st_size > 2_000_000:
        return {"ready": False, "frames": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            data.get("schema") != 1
            or data.get("camera") != "DEMO-N001"
            or data.get("video_sha256") != VIDEO_HASH
            or data.get("model_sha256") != MODEL_HASH
            or not (0 < float(data.get("duration_sec", 0)) <= 7200)
            or not (0 < int(data.get("width", 0)) <= 7680)
            or not (0 < int(data.get("height", 0)) <= 4320)
            or not isinstance(data.get("frames"), list)
            or len(data["frames"]) > 3000
        ):
            return {"ready": False, "frames": []}
        # Never draw rectangles from another video, even if a local MP4 was
        # replaced after the Demo Runtime started. Checked only on selection.
        digest = hashlib.sha256()
        with video_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != VIDEO_HASH:
            return {"ready": False, "frames": []}
        previous_t = -1.0
        for frame in data["frames"]:
            if not isinstance(frame, dict) or not isinstance(frame.get("boxes"), list):
                return {"ready": False, "frames": []}
            if not isinstance(frame.get("t"), (float, int)) or not 0 <= frame["t"] <= data["duration_sec"]:
                return {"ready": False, "frames": []}
            if frame["t"] <= previous_t:
                return {"ready": False, "frames": []}
            previous_t = frame["t"]
            if len(frame["boxes"]) > 5:
                return {"ready": False, "frames": []}
            for box in frame["boxes"]:
                if (not isinstance(box.get("bbox"), list)
                    or len(box["bbox"]) != 4
                    or not all(isinstance(n, (float, int)) for n in box["bbox"])
                    or not 0 <= float(box.get("confidence", -1)) <= 1):
                    return {"ready": False, "frames": []}
        return {
            "ready": True, "width": data["width"], "height": data["height"],
            "duration_sec": data["duration_sec"], "frames": data["frames"],
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {"ready": False, "frames": []}
