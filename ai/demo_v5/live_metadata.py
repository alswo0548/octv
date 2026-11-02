"""Bounded asynchronous telemetry. No JPEG, no inference, no incident decisions."""
from collections import deque
from datetime import datetime, timezone
from math import isfinite
from queue import Queue, Full
from threading import Thread
import json
import os

PREFIX = 'octv:v5:boxes:v1:'
MAX_AGE_SEC = 3.0


def enabled():
    return os.getenv('OCTV_LIVE_BBOX_ENABLED', '0').strip() == '1'


def metadata(frame, detections):
    t = getattr(frame, 'media_time_sec', None)
    if t is None or not isfinite(t) or t < 0:
        return None
    height, width = frame.image.shape[:2]
    boxes = []
    for d in detections[:100]:
        bbox = [float(v) for v in d.bbox]
        confidence = float(d.confidence)
        if (len(bbox) == 4 and all(map(isfinite, bbox)) and isfinite(confidence)
                and 0 <= confidence <= 1 and 0 <= bbox[0] < bbox[2] <= width
                and 0 <= bbox[1] < bbox[3] <= height):
            boxes.append({'bbox': bbox, 'confidence': confidence,
                          'hazard_type': d.hazard_type, 'model_version': d.model_version})
    return {'t': t, 'captured_at': frame.captured_at.astimezone(timezone.utc).isoformat(),
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'source_epoch': frame.source_epoch, 'media_name': frame.media_name,
            'width': width, 'height': height, 'boxes': boxes}


class MetadataPublisher:
    def __init__(self):
        self.queue = Queue(maxsize=1)
        self.history = {}
        Thread(target=self._run, daemon=True, name='bbox-metadata').start()

    def submit(self, frame, detections):
        try:
            item = metadata(frame, detections)
            if item is not None:
                self.queue.put_nowait((frame.cctv_id, item))
        except (Full, ValueError, TypeError, AttributeError, OverflowError):
            pass  # Optional telemetry cannot block or fail real detections.

    def _run(self):
        from .telemetry import client
        while True:
            cctv_id, item = self.queue.get()
            try:
                history = self.history.setdefault(cctv_id, deque(maxlen=32))
                if history and history[-1]['source_epoch'] != item['source_epoch']:
                    history.clear()
                history.append(item)
                client().setex(PREFIX + str(cctv_id), 5, json.dumps(list(history), allow_nan=False))
            except Exception:
                pass
            finally:
                self.queue.task_done()


def recent_frames(raw, started, media_name, now=None):
    now = now or datetime.now(timezone.utc)
    if started is None:
        return []
    try:
        rows = json.loads(raw) if raw else []
        if not isinstance(rows, list):
            return []
        result = []
        for row in rows[-32:]:
            captured = datetime.fromisoformat(row['captured_at'])
            age = (now - captured).total_seconds()
            if (row['media_name'] == media_name and captured >= started
                    and 0 <= age <= MAX_AGE_SEC):
                result.append({**row, 'age_sec': age})
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        return []
