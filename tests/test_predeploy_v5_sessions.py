import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from ai.demo_v5.session_pipeline import SessionPipeline


class FakePipeline:
    def __init__(self, config=None, register_fn=None):
        self._config = config
        self._register_fn = register_fn or (lambda p: p)
        self.calls = []
    def handle_result(self, **kwargs):
        self.calls.append(kwargs)
        return self._register_fn({'dedup_key': 'cctv:4:hazard:flood'})


class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        self.session = self.now
        self.original = FakePipeline()
        self.adapter = SessionPipeline(self.original, [4], lambda _: self.session, FakePipeline)
    def frame(self, id=4, offset=1):
        return SimpleNamespace(cctv_id=id, captured_at=self.now+timedelta(seconds=offset))
    def test_utc_untouched(self):
        result = self.adapter.handle_result(self.frame(3), [])
        self.assertEqual(result['dedup_key'], 'cctv:4:hazard:flood')
        self.assertEqual(len(self.original.calls), 1)
    def test_restarts_have_new_dedup_and_verifier(self):
        one = self.adapter.handle_result(self.frame(), [])
        same = self.adapter.handle_result(self.frame(offset=2), [])
        self.assertEqual(one, same)
        old = self.adapter.sessions[4][1]
        self.session = self.now+timedelta(seconds=10)
        new = self.adapter.handle_result(self.frame(offset=11), [])
        self.assertNotEqual(one, new)
        self.assertIsNot(old, self.adapter.sessions[4][1])
    def test_stopped_or_stale_frame_does_not_register(self):
        self.adapter.handle_result(self.frame(), [])
        self.session = None
        self.assertFalse(self.adapter.handle_result(self.frame(), []).had_error)
        self.assertNotIn(4, self.adapter.sessions)
        self.session = self.now+timedelta(seconds=10)
        self.assertFalse(self.adapter.handle_result(self.frame(), []).had_error)
        self.assertNotIn(4, self.adapter.sessions)
    def test_delayed_registration_after_stop_is_rejected(self):
        self.adapter.handle_result(self.frame(), [])
        register = self.adapter.sessions[4][1]._register_fn
        self.session = None
        with self.assertRaises(RuntimeError): register({'dedup_key':'old'})
    def test_naive_frame_is_not_guessed(self):
        frame = SimpleNamespace(cctv_id=4, captured_at=self.now.replace(tzinfo=None))
        self.assertTrue(self.adapter.handle_result(frame, []).had_error)
