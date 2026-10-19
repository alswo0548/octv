"""네 서비스 클래스의 기존 사건화→저장→분석 요청→실제 LangGraph 판단을 Mock I/O로 검증합니다."""
import os
from contextlib import nullcontext, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import Mock, patch
import unittest

import numpy as np
from ai.contracts import Detection, Frame
from ai.detection.incident_pipeline import ALLOWED_HAZARD_TYPES, IncidentPipeline, IncidentPipelineConfig
from ai.risk_priority.rules import RISK_POLICIES, assess
from ai.agency_recommendation.recommender import AGENCY_ROLES
from ai.orchestration.pipeline import run_pipeline
from backend.app.incidents.service import register_detection
from tests.test_langgraph_core import sample_config, sample_context, sample_incident

EXPECTED = {0: "flood", 1: "fallen_tree", 2: "severe_road_damage", 3: "road_obstacle"}

class HazardContractTests(unittest.TestCase):
    def test_active_classes_match_existing_incidentization(self):
        self.assertEqual(ALLOWED_HAZARD_TYPES, frozenset(EXPECTED.values()))
        for hazard in EXPECTED.values():
            self.assertIn(hazard, RISK_POLICIES); self.assertIn(hazard, AGENCY_ROLES)
        self.assertNotIn("sinkhole", ALLOWED_HAZARD_TYPES)
        self.assertNotIn("road_damage", ALLOWED_HAZARD_TYPES)

    def test_four_classes_cross_real_temporal_storage_queue_and_graph_boundaries(self):
        for hazard in EXPECTED.values():
            with self.subTest(hazard=hazard):
                incident = {**sample_incident(), "hazard_type": hazard, "incident_no": "TEST-ONLY"}
                saved = []; snapshots = []
                def save_detection(connection, payload): saved.append(payload); return incident
                config = sample_config(); config["load_incident"] = lambda _: incident
                config["save_analysis"] = lambda state: snapshots.append(state) or {"status":"TEST_SAVED"}
                def dispatch(incident_id, token):
                    self.assertEqual(incident_id, 1); self.assertEqual(token,"TEST-LOCK")
                    self.assertEqual(run_pipeline(incident_id,config)["status"],"TEST_SAVED")
                    return Mock(id="TEST-TASK")
                with patch.dict(os.environ, {"OCTV_DECISION_ENABLED":"1", "OCTV_REDIS_URL":"redis://127.0.0.1:1/0"}), patch("backend.app.incidents.service.get_connection", return_value=nullcontext(object())), patch("backend.app.incidents.repository.save_detection", side_effect=save_detection), patch("backend.app.analysis_requests.get_analysis_input", return_value=incident), patch("backend.app.analysis_requests.acquire_analysis_lock", return_value="TEST-LOCK"), patch("backend.app.workers.analyze_incident.delay", side_effect=dispatch) as delay, redirect_stdout(StringIO()):
                    pipeline = IncidentPipeline(config=IncidentPipelineConfig(), register_fn=register_detection)
                    detection = Detection(hazard_type=hazard, confidence=0.9, bbox=(10,10,80,80), model_version="MOCK-NAMES-ONLY")
                    for second in range(3):
                        pipeline.handle_result(Frame(cctv_id=9, captured_at=datetime(2026,10,20,tzinfo=timezone.utc)+timedelta(seconds=second),image=np.zeros((100,100,3),dtype=np.uint8)), [detection])
                self.assertEqual(len(saved),1)
                self.assertEqual(saved[0]["hazard_type"],hazard)
                self.assertTrue(saved[0]["representative_image"].startswith(b"\xff\xd8"))
                delay.assert_called_once()
                self.assertEqual(len(snapshots),1)
                self.assertEqual(snapshots[0]["incident"]["hazard_type"],hazard)
                self.assertGreater(snapshots[0]["assessment"]["risk_score"],0)
                self.assertTrue(snapshots[0]["recommendations"])

    def test_road_damage_reuses_existing_scores_and_legacy_read_policy(self):
        new = assess(sample_context(), RISK_POLICIES["severe_road_damage"])
        legacy = assess(sample_context(), RISK_POLICIES["sinkhole"])
        self.assertEqual(new, legacy)
        self.assertEqual(new["risk_score"], 90)
        self.assertEqual(new["risk_breakdown"]["base_score"],45)
        self.assertEqual(new["risk_breakdown"]["components"]["closure_confirmed"]["points"],5)
        self.assertEqual(AGENCY_ROLES["severe_road_damage"], AGENCY_ROLES["sinkhole"])

    def test_unconfirmed_road_damage_context_does_not_invent_bonus(self):
        from dataclasses import replace
        context = replace(sample_context(), measurements={})
        result = assess(context, RISK_POLICIES["severe_road_damage"])
        self.assertEqual(result["risk_score"],45)
        self.assertIn("rainfall_mm", result["risk_breakdown"]["missing"])
        self.assertIn("closure_confirmed", result["risk_breakdown"]["missing"])

if __name__ == '__main__': unittest.main()
