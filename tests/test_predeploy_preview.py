import json
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import numpy as np
from ai.contracts import Frame, Detection
from ai.demo_v5.telemetry import publish, observing_detector

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.frame = Frame(4, datetime.now(timezone.utc), np.zeros((40,80,3),dtype=np.uint8))
        self.detections = [Detection('flood',.8,(1,2,30,20),'approved')]
    def test_exact_frame_and_actual_boxes_are_one_snapshot(self):
        with patch('ai.demo_v5.telemetry.client') as client:
            publish(self.frame,self.detections)
            args = client.return_value.setex.call_args.args
            self.assertEqual(args[:2], ('octv:v5:preview:4',30))
            payload = json.loads(args[2])
            self.assertEqual((payload['width'],payload['height']),(80,40))
            self.assertEqual(payload['detections'][0]['bbox'],[1,2,30,20])
    def test_preview_failure_does_not_change_inference(self):
        with patch('ai.demo_v5.telemetry.client',side_effect=RuntimeError('offline')):
            result = observing_detector(lambda _: self.detections)(self.frame)
            self.assertIs(result,self.detections)
    def test_empty_predictions_are_not_invented(self):
        with patch('ai.demo_v5.telemetry.client') as client:
            publish(self.frame,[])
            self.assertEqual(json.loads(client.return_value.setex.call_args.args[2])['detections'],[])
