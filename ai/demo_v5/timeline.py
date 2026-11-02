"""Opt-in source adapter: keep teammate capture/sampling/detection code unchanged."""
from dataclasses import dataclass
from math import isfinite
from uuid import uuid4
import cv2
from ai.contracts import Frame


@dataclass(frozen=True)
class TimelineFrame(Frame):
    media_time_sec: float
    source_epoch: str
    media_name: str


class TimelineSource:
    def __init__(self, source):
        self.source = source
        self.epoch = ''
        self.last_pts = -1.0

    def __getattr__(self, name):
        return getattr(self.source, name)

    def open(self):
        self.source.open()
        self.epoch = uuid4().hex
        self.last_pts = -1.0

    def read(self):
        frame = self.source.read()
        if frame is None:
            return None
        # Read the decoder position immediately after that exact frame is read.
        # Unsupported/non-monotonic PTS => no overlay; never estimate from wall time.
        try:
            pts = float(self.source.cap.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            if not isfinite(pts) or pts < 0 or pts <= self.last_pts:
                return frame
            self.last_pts = pts
            from pathlib import Path
            return TimelineFrame(frame.cctv_id, frame.captured_at, frame.image,
                                 pts, self.epoch, Path(self.source.stream_url).name)
        except (AttributeError, TypeError, ValueError, OverflowError):
            return frame


def attach_timeline(runtime):
    """Wrap only the existing DEMO source factory before runtime threads start."""
    manager = runtime._capture_manager
    original = manager._worker_factory

    def factory(cctv):
        worker = original(cctv)
        if str(cctv.get('provider', '')).upper() == 'DEMO' and worker.source is not None:
            worker.source = TimelineSource(worker.source)
        return worker
    manager._worker_factory = factory
