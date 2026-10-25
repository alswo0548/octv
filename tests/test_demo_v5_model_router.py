"""No DB, no YOLO models, and no side effects."""
import unittest
from datetime import datetime

import numpy as np

from ai.contracts import Detection, Frame
from ai.demo_v5.model_router import APPROVED_ROUTES, DemoModelRouter


class DummyDetector:
    def __init__(self, values):
        self.values = values
        self.calls = 0

    def detect(self, frame):
        self.calls += 1
        return self.values


class RouterTests(unittest.TestCase):
    def test_real_traffic_camera_preserves_default_detector(self):
        real = Detection("flood", .51, (1, 2, 3, 4), "base.pt")
        base = DummyDetector([real])
        special = DummyDetector([])
        router = DemoModelRouter(base, {4: (APPROVED_ROUTES[0], special)})
        frame = Frame(3, datetime.now(), np.zeros((10, 10, 3), dtype=np.uint8))
        self.assertEqual(router.detect(frame), [real]); self.assertEqual(base.calls, 1)
        self.assertEqual(special.calls, 0)

    def test_demo_requires_real_model_hit_correct_class_and_entry_threshold(self):
        base = DummyDetector([])
        detections = [
            Detection("flood", .79, (1, 2, 3, 4), "N052.pt"),
            Detection("flood", .82, (1, 2, 3, 4), "N052.pt"),
            Detection("road_obstacle", .99, (1, 2, 3, 4), "N052.pt"),
        ]
        demo = DummyDetector(detections)
        router = DemoModelRouter(base, {4: (APPROVED_ROUTES[0], demo)})
        frame = Frame(4, datetime.now(), np.zeros((10, 10, 3), dtype=np.uint8))
        self.assertEqual(router.detect(frame), [detections[1]])
        self.assertEqual(base.calls, 0); self.assertEqual(demo.calls, 1)

    def test_no_fake_detection_when_model_returns_empty(self):
        router = DemoModelRouter(DummyDetector([]), {6: (APPROVED_ROUTES[2], DummyDetector([]))})
        self.assertEqual(router.detect(Frame(6, datetime.now(), np.zeros((10, 10, 3)))), [])


if __name__ == "__main__":
    unittest.main()
