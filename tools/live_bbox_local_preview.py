"""Isolated local N001 YOLO-to-browser preview. No database, Redis, FCM or production API.
Binds to 127.0.0.1 only. Exactly one YOLO model, one analysis thread.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "demo/videos/N001_demo.mp4"
MOBILE = ROOT / "demo/videos/N001_demo_mobile.mp4"
MODEL = ROOT / "demo/videos/_v5/weights/N052_S2_epoch005.pt"
PUBLIC_VIDEO = MOBILE if MOBILE.is_file() else VIDEO
PORT = 8765
INTERVAL_SEC = 3.0
ALLOWED_ORIGINS = {"http://127.0.0.1:4173", "http://localhost:4173"}

if not VIDEO.is_file() or not MODEL.is_file():
    raise SystemExit(f"Required N001 file missing: video={VIDEO.is_file()}, model={MODEL.is_file()}")

probe = cv2.VideoCapture(str(VIDEO))
fps = probe.get(cv2.CAP_PROP_FPS)
count = probe.get(cv2.CAP_PROP_FRAME_COUNT)
probe.release()
if fps <= 0 or count <= 0:
    raise SystemExit("Cannot read N001 video FPS/duration")
DURATION = count / fps

print("[PREVIEW] Loading actual N001 YOLO model...", flush=True)
detector = YOLO(str(MODEL))
detector_lock = threading.Lock()
state_lock = threading.Lock()
history: deque[dict] = deque(maxlen=20)
session = 0
stop_event = threading.Event()
active = False
samples = 0
positive = 0
last_pts = None
last_poll = time.monotonic()


def snapshot_status() -> dict:
    with state_lock:
        return {"active": active, "samples": samples, "positive": positive,
                "last_pts": last_pts, "fps": fps, "duration": DURATION,
                "playback_variant": PUBLIC_VIDEO.name}


def analysis_worker(token: int, stopper: threading.Event, offset: float, started: float):
    global samples, positive, last_pts, active
    cap = cv2.VideoCapture(str(VIDEO))
    next_tick = time.monotonic()
    try:
        while not stopper.is_set():
            with state_lock:
                if time.monotonic() - last_poll > 20:
                    stopper.set()  # Stop inference when preview tab is closed.
                    break
            if stopper.wait(max(0.0, next_tick - time.monotonic())):
                break
            captured_monotonic = time.monotonic()
            t = (offset + captured_monotonic - started) % DURATION
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, image = cap.read()
            if ok:
                pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                with detector_lock:
                    res = detector.predict(source=image, imgsz=640, device="cpu",
                                           conf=0.50, verbose=False)[0]
                boxes = []
                if res.boxes is not None:
                    for xyxy, conf, cls in zip(res.boxes.xyxy.cpu().tolist(),
                                               res.boxes.conf.cpu().tolist(),
                                               res.boxes.cls.cpu().tolist()):
                        if res.names[int(cls)] == "flood" and conf >= 0.80:
                            boxes.append({"bbox": xyxy, "confidence": float(conf),
                                          "hazard_type": "flood"})
                h, w = image.shape[:2]
                row = {"t": pts, "captured_monotonic": captured_monotonic,
                       "width": w, "height": h, "source_epoch": str(token),
                       "boxes": boxes}
                with state_lock:
                    if token != session or stopper.is_set():
                        break
                    history.append(row)
                    samples += 1
                    positive += bool(boxes)
                    last_pts = round(pts, 3)
                print(f"[REAL YOLO] time={pts:.2f} boxes={len(boxes)}", flush=True)
            # Stay near 3 seconds, matching observed production preview cadence;
            # never slow or seek the independent HTML video.
            next_tick = max(next_tick + INTERVAL_SEC, time.monotonic() + 0.01)
    finally:
        cap.release()
        with state_lock:
            if token == session:
                active = False


class Handler(BaseHTTPRequestHandler):
    def cors(self):
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def json_response(self, code: int, data: dict):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_GET(self):
        global last_poll
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            return self.json_response(200, snapshot_status())
        if path == "/api/demo/v5/live-boxes/4":
            now = time.monotonic()
            with state_lock:
                last_poll = now
                rows = [{**{k: v for k, v in row.items() if k != "captured_monotonic"},
                         "age_sec": max(0, now - row["captured_monotonic"])}
                        for row in history if now - row["captured_monotonic"] <= 3.0]
                running = active
            return self.json_response(200, {"enabled": running, "frames": rows})
        if path == "/video":
            return self.stream_video()
        return self.json_response(404, {"error": "not found"})

    def do_POST(self):
        global active, session, stop_event, samples, positive, last_pts, last_poll
        origin = self.headers.get("Origin", "")
        if origin and origin not in ALLOWED_ORIGINS:
            return self.json_response(403, {"error": "origin not allowed"})
        if self.path not in ("/api/start", "/api/stop"):
            return self.json_response(404, {"error": "not found"})
        if self.path == "/api/start":
            length = int(self.headers.get("Content-Length", "0"))
            if length > 128:
                return self.json_response(413, {"error": "body too long"})
            try:
                value = json.loads(self.rfile.read(length))
                offset = float(value["offset"])
                if not 0 <= offset < DURATION:
                    raise ValueError("out of range")
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                return self.json_response(400, {"error": "invalid playback offset"})
        with state_lock:
            stop_event.set()
            session += 1
            token = session
            stop_event = threading.Event()
            history.clear()
            samples, positive, last_pts = 0, 0, None
            active = self.path == "/api/start"
            last_poll = time.monotonic()
            if active:
                started = time.monotonic()
                threading.Thread(target=analysis_worker,
                                 args=(token, stop_event, offset, started),
                                 daemon=True, name="preview-yolo").start()
        return self.json_response(200, {"enabled": active, "session": token})

    def stream_video(self):
        length = PUBLIC_VIDEO.stat().st_size
        start = 0
        end = length - 1
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        if self.headers.get("Range"):
            if not match:
                self.send_response(416)
                self.cors()
                self.send_header("Content-Range", f"bytes */{length}")
                self.end_headers()
                return
            start = int(match.group(1))
            if match.group(2):
                end = min(int(match.group(2)), end)
            if start >= length or end < start:
                self.send_response(416)
                self.cors()
                self.send_header("Content-Range", f"bytes */{length}")
                self.end_headers()
                return
        part = start != 0 or end != length - 1 or bool(self.headers.get("Range"))
        self.send_response(206 if part else 200)
        self.cors()
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if part:
            self.send_header("Content-Range", f"bytes {start}-{end}/{length}")
        self.end_headers()
        try:
            with PUBLIC_VIDEO.open("rb") as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = stream.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, format, *args):
        if self.path.split("?", 1)[0] not in ("/api/demo/v5/live-boxes/4",):
            super().log_message(format, *args)


if __name__ == "__main__":
    print(f"[PREVIEW] localhost:{PORT}, file={PUBLIC_VIDEO.name}", flush=True)
    print("[PREVIEW] Production DB/API/Redis/FCM are not used.", flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[PREVIEW] stopped", flush=True)
    finally:
        with state_lock:
            stop_event.set()
        server.server_close()
