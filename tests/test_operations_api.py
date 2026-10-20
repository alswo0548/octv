"""운영 API의 JWT·입력값·설정 저장 계약을 검사합니다. 외부 DB·키 없이 실행합니다."""
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app import dependencies
from backend.app.settings import router as settings_router, service as settings_service, schemas as settings_schemas
from backend.app.stats import router as stats_router, service as stats_service, schemas as stats_schemas
from backend.app.cctvs import (
    repository as cctv_repository,
    router as cctv_router,
    service as cctv_service,
)

SECRET = "operations-unit-test-only-secret-32-characters"
VALUES = dict(base_analysis_interval_sec=10, alert_analysis_interval_sec=5, verify_analysis_interval_sec=1,
    candidate_confidence_threshold=Decimal("0.35"), candidate_min_detection_count=3, temporal_validation_sec=5,
    incident_confidence_threshold=Decimal("0.7"), reconnect_interval_sec=3, max_reconnect_attempts=5, quality_threshold=Decimal("0.6"))

class OperationsApiTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("psycopg.connect", side_effect=AssertionError("real database forbidden")))
        self.stack.enter_context(patch("backend.app.dependencies.jwt_secret", return_value=SECRET))
        self.user = {"id": 42, "role": "CONTROL_ADMIN", "agency_id": None, "is_active": True, "notification_enabled": True}
        self.stack.enter_context(patch("backend.app.auth.repository.find_user_by_id", return_value=self.user))
        self.conn = MagicMock(); self.conn.__enter__.return_value = self.conn
        for target in ("backend.app.dependencies", "backend.app.settings.service", "backend.app.stats.service", "backend.app.cctvs.service"):
            self.stack.enter_context(patch(target + ".get_connection", return_value=self.conn))
        self.row = {**VALUES, "id": 1, "updated_by": None, "updated_at": datetime(2026, 10, 19, 15, 0)}
        self.read = self.stack.enter_context(patch("backend.app.settings.repository.get_monitoring_settings", side_effect=lambda *a, **k: dict(self.row)))
        def save(conn, sid, values, uid):
            self.row.update(values, updated_by=uid, updated_at=datetime(2026, 10, 19, 16, 0,),)
            return {"id": sid,}
        self.save = self.stack.enter_context(patch("backend.app.settings.repository.save_monitoring_settings", side_effect=save))
        self.aggregate = self.stack.enter_context(patch("backend.app.stats.repository.aggregate_incidents", return_value={
            "total_incident_count": 0, "confirmed_incident_count": 0, "average_confidence": None,
            "by_status": {}, "by_hazard": {}, "by_risk": {}, "by_priority": {}, "confidence_distribution": {},
            "daily": [{"day": "2026-10-20", "count": 0}], "hourly": [{"hour": h, "count": 0} for h in range(24)],
        }))
        app = FastAPI()
        for router in (settings_router.router, stats_router.router, cctv_router.router): app.include_router(router, prefix="/api")
        self.client = TestClient(app); self.addCleanup(self.client.close)

    def headers(self, **claims):
        return {"Authorization": "Bearer " + jwt.encode({"sub": "42", "exp": datetime.now(timezone.utc) + timedelta(minutes=5), **claims}, SECRET, algorithm=dependencies.JWT_ALGORITHM)}

    def body(self, **changes):
        return settings_schemas.MonitoringSettingsRequest(**VALUES).model_dump(mode="json") | changes

    def test_anonymous_settings_stats_and_cctv_requests_are_401(self):
        for path, method, body in (("/api/settings/monitoring", "GET", None), ("/api/settings/monitoring", "PUT", self.body()),
            ("/api/stats", "GET",  None), ("/api/cctvs", "GET", None), ("/api/cctvs/1/stream", "POST", None), ("/api/cctvs/1/reconnect", "POST", None),
            ("/api/cctvs/1/monitoring", "PATCH", {"enabled": True})):
            with self.subTest(path=path, method=method):
                self.assertEqual(self.client.request(method, path, json=body).status_code, 401)
        self.read.assert_not_called(); self.save.assert_not_called(); self.aggregate.assert_not_called()

    def test_field_roles_cannot_use_admin_operations(self):
        for role in ("AGENCY_STAFF", "RESPONDER"):
            self.user.update(role=role, agency_id=7)
            for path in ("/api/settings/monitoring", "/api/stats", "/api/cctvs", "/api/cctvs/1"):
                with self.subTest(role=role, path=path): self.assertEqual(self.client.get(path, headers=self.headers()).status_code, 403)
            self.assertEqual(self.client.put("/api/settings/monitoring", headers=self.headers(), json=self.body()).status_code, 403)
            self.assertEqual(self.client.post("/api/cctvs/1/stream", headers=self.headers()).status_code, 403)
            self.assertEqual(self.client.post("/api/cctvs/1/reconnect", headers=self.headers()).status_code, 403)
            self.assertEqual(self.client.patch("/api/cctvs/1/monitoring", headers=self.headers(), json={"enabled": False}).status_code, 403)
        self.save.assert_not_called()

    def test_expired_and_inactive_sessions_are_rejected(self):
        self.assertEqual(self.client.get("/api/stats", headers=self.headers(exp=0)).status_code, 401)
        self.user["is_active"] = False
        self.assertEqual(self.client.get("/api/settings/monitoring", headers=self.headers()).status_code, 403)

    def test_settings_save_requery_actor_and_explicit_utc(self):
        response = self.client.put("/api/settings/monitoring", headers=self.headers(role="RESPONDER", id=999), json=self.body(base_analysis_interval_sec=12))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["base_analysis_interval_sec"], 12)
        self.assertEqual(response.json()["updated_by"], 42)
        self.assertTrue(response.json()["updated_at"].endswith("Z"))
        self.assertEqual(self.read.call_args_list[0].kwargs, {"for_update": True})
        again = self.client.get("/api/settings/monitoring", headers=self.headers()).json()
        self.assertEqual(again["base_analysis_interval_sec"], 12)
        self.assertEqual(again["application"]["temporal_validation_sec"]["mode"], "RESTART_REQUIRED")
        self.assertEqual(again["application"]["reconnect_interval_sec"]["mode"], "RESTART_REQUIRED")

    def test_incident_fields_are_saved_and_require_restart(self):
        for name in (settings_service.INCIDENT_RESTART_FIELDS):
            if "threshold" in name:
                value = (float(VALUES[name]) + 0.01)
            else:
                value = (int(VALUES[name]) + 1)

            with self.subTest(name=name):
                response = (self.client.put("/api/settings/monitoring", headers=self.headers(), json=self.body(**{name: value,}),))
                self.assertEqual(response.status_code, 200, response.text,)
                actual_value = (response.json()[name])
                if "threshold" in name:
                    self.assertEqual(Decimal(str(actual_value)), Decimal(str(value)))

                else:
                    self.assertEqual(actual_value, value)

                self.assertEqual(response.json()["application"][name]["mode"], "RESTART_REQUIRED",)

        self.assertEqual(self.save.call_count, len(settings_service.INCIDENT_RESTART_FIELDS))

    def test_invalid_settings_are_422_without_storage(self):
        for value in (0, -1, 1.5, True, "5", 2147483648):
            with self.subTest(value=value): self.assertEqual(self.client.put("/api/settings/monitoring", headers=self.headers(), json=self.body(base_analysis_interval_sec=value)).status_code, 422)
        for value in (-0.1, 1.1, "NaN", "Infinity", "0.12345"):
            with self.subTest(value=value): self.assertEqual(self.client.put("/api/settings/monitoring", headers=self.headers(), json=self.body(quality_threshold=value)).status_code, 422)
        self.save.assert_not_called()

    def test_actor_and_extra_fields_cannot_be_forged(self):
        for name in ("updated_by", "updated_at", "id", "rule_version"):
            self.assertEqual(self.client.put("/api/settings/monitoring", headers=self.headers(), json=self.body(**{name: 9})).status_code, 422)
        self.save.assert_not_called()

    def test_empty_settings_are_not_inserted(self):
        self.read.side_effect = None; self.read.return_value = None
        self.assertEqual(self.client.get("/api/settings/monitoring", headers=self.headers()).status_code, 409)
        self.assertEqual(self.client.put("/api/settings/monitoring", headers=self.headers(), json=self.body()).status_code, 409)
        self.save.assert_not_called()

    def test_personal_push_setting_stays_separate(self):
        self.user.update(role="RESPONDER", agency_id=7)
        response = self.client.get("/api/settings/me/notifications", headers=self.headers())
        self.assertEqual(response.json(), {"enabled": True})
        with patch("backend.app.settings.repository.set_notification_enabled", return_value={"notification_enabled": False}) as save:
            response = self.client.patch("/api/settings/me/notifications", headers=self.headers(), json={"enabled": False})
            self.assertEqual(response.json(), {"enabled": False}); save.assert_called_once_with(self.conn, 42, False)
        self.save.assert_not_called()

    def test_korean_day_boundaries_and_filters(self):
        response = self.client.get("/api/stats?start=2026-10-20&end=2026-10-20&region_code=R1&cctv_id=7&confirmed_only=false", headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        filters = self.aggregate.call_args.args[1]
        self.assertEqual(filters["start_utc"], datetime(2026, 10, 19, 15))
        self.assertEqual(filters["end_utc"], datetime(2026, 10, 20, 15))
        self.assertEqual((filters["region_code"], filters["cctv_id"], filters["confirmed_only"]), ("R1", 7, False))
        self.assertEqual(response.json()["average_confidence"], None)
        self.assertEqual(len(response.json()["hourly"]), 24)

    def test_invalid_period_and_cctv_are_422(self):
        for params in ("start=2026-10-21&end=2026-10-20", "start=2020-01-01&end=2026-01-01", "cctv_id=0", "cctv_id=bad", "start=0001-01-01&end=0001-01-01", "start=9999-12-31&end=9999-12-31"):
            with self.subTest(params=params): self.assertEqual(self.client.get("/api/stats?" + params, headers=self.headers()).status_code, 422)
        self.aggregate.assert_not_called()

    def test_default_stats_scope_is_confirmed_only(self):
        self.assertEqual(self.client.get("/api/stats", headers=self.headers()).status_code, 200)
        self.assertTrue(self.aggregate.call_args.args[1]["confirmed_only"])

    def test_unmonitored_stream_rejected_without_external_call(self):
        with patch("backend.app.cctvs.repository.get_cctv", return_value={"is_monitored": False}), patch("backend.app.cctvs.streaming.prepare_cctv_stream") as prepare:
            self.assertEqual(self.client.post("/api/cctvs/1/stream", headers=self.headers()).status_code, 409)
            prepare.assert_not_called()

    def test_stream_preparation_success_and_external_failure(self):
        import requests
        with patch("backend.app.cctvs.repository.get_cctv", return_value={"is_monitored": True, "provider": "UTIC", "external_cctv_id": "TEST"}), patch("backend.app.cctvs.streaming.prepare_cctv_stream", return_value={"cctv_id": 1, "path": "test", "playback_url": "http://localhost:8889/test", "whep_url": "http://localhost:8889/test/whep"}) as prepare:
            self.assertEqual(self.client.post("/api/cctvs/1/stream", headers=self.headers()).status_code, 200)
            prepare.side_effect = requests.ConnectionError("TEST_ONLY")
            self.assertEqual(self.client.post("/api/cctvs/1/stream", headers=self.headers()).status_code, 502)


    def test_reconnect_missing_cctv_is_404(self):
        with (
            patch(
                "backend.app.cctvs."
                "repository.get_cctv",
                return_value=None,
            ) as get_cctv,
            patch(
                "backend.app.cctvs."
                "reconnect_signal."
                "publish_reconnect_request"
            ) as publish,
        ):

            response = (
                self.client.post(
                    "/api/cctvs/1/reconnect",
                    headers=self.headers(),
                )
            )

        self.assertEqual(
            response.status_code,
            404,
            response.text,
        )

        self.assertEqual(
            response.json(),
            {
                "detail":
                    "CCTV를 찾을 수 없습니다.",
            },
        )

        get_cctv.assert_called_once_with(
            self.conn,
            1,
        )

        publish.assert_not_called()

    def test_unmonitored_reconnect_is_409(
        self,
    ):
        with (
            patch(
                "backend.app.cctvs."
                "repository.get_cctv",
                return_value={
                    "id": 1,
                    "is_monitored": False,
                    "provider": "UTIC",
                },
            ),
            patch(
                "backend.app.cctvs."
                "reconnect_signal."
                "publish_reconnect_request"
            ) as publish,
        ):

            response = (
                self.client.post(
                    "/api/cctvs/1/reconnect",
                    headers=self.headers(),
                )
            )

        self.assertEqual(
            response.status_code,
            409,
            response.text,
        )

        self.assertEqual(
            response.json(),
            {
                "detail":
                    "현재 감시 중인 CCTV가 "
                    "아니므로 재연결할 수 없습니다.",
            },
        )

        publish.assert_not_called()

    def test_unsupported_provider_reconnect_is_409(
        self,
    ):
        with (
            patch(
                "backend.app.cctvs."
                "repository.get_cctv",
                return_value={
                    "id": 1,
                    "is_monitored": True,
                    "provider": "OTHER",
                },
            ),
            patch(
                "backend.app.cctvs."
                "reconnect_signal."
                "publish_reconnect_request"
            ) as publish,
        ):

            response = (
                self.client.post(
                    "/api/cctvs/1/reconnect",
                    headers=self.headers(),
                )
            )

        self.assertEqual(
            response.status_code,
            409,
            response.text,
        )

        self.assertEqual(
            response.json(),
            {
                "detail":
                    "현재 수동 재연결을 지원하지 "
                    "않는 CCTV입니다.",
            },
        )

        publish.assert_not_called()

    def test_manual_reconnect_is_accepted(
        self,
    ):
        with (
            patch(
                "backend.app.cctvs."
                "repository.get_cctv",
                return_value={
                    "id": 1,
                    "is_monitored": True,
                    "provider": "UTIC",
                },
            ) as get_cctv,
            patch(
                "backend.app.cctvs."
                "reconnect_signal."
                "publish_reconnect_request"
            ) as publish,
        ):

            response = (
                self.client.post(
                    "/api/cctvs/1/reconnect",
                    headers=self.headers(),
                )
            )

        self.assertEqual(
            response.status_code,
            202,
            response.text,
        )

        self.assertEqual(
            response.json(),
            {
                "cctv_id": 1,
                "status": "ACCEPTED",
            },
        )

        get_cctv.assert_called_once_with(
            self.conn,
            1,
        )

        publish.assert_called_once_with(
            self.conn,
            1,
        )

    def test_alert_and_verify_monitoring_off_are_409(
        self,
    ):
        """
        시스템이 강제로 유지해야 하는 감시 상태에서는
        관리자가 수동으로 CCTV 감시를 종료할 수 없다.

        ALERT  + OFF -> 409
        VERIFY + OFF -> 409
        """

        cases = (
            (
                "ALERT",
                "기상특보 감시 중인 CCTV는 "
                "수동으로 감시를 종료할 수 없습니다.",
            ),
            (
                "VERIFY",
                "위험상황 검증 중인 CCTV는 "
                "수동으로 감시를 종료할 수 없습니다.",
            ),
        )

        for (
            mode,
            expected_detail,
        ) in cases:

            with self.subTest(
                mode=mode
            ):

                error = (
                    cctv_repository
                    .MonitoringChangeBlockedError(
                        mode
                    )
                )

                with (
                    patch.object(
                        cctv_repository,
                        "update_monitoring",
                        side_effect=error,
                    ) as update_monitoring,
                    patch(
                        "backend.app.cctvs."
                        "streaming.remove_cctv_stream"
                    ) as remove_stream,
                ):

                    response = (
                        self.client.patch(
                            "/api/cctvs/1/monitoring",
                            headers=self.headers(),
                            json={
                                "enabled": False,
                            },
                        )
                    )

                self.assertEqual(
                    response.status_code,
                    409,
                    response.text,
                )

                self.assertEqual(
                    response.json(),
                    {
                        "detail":
                            expected_detail,
                    },
                )

                update_monitoring.assert_called_once_with(
                    self.conn,
                    cctv_id=1,
                    enabled=False,
                )

                # OFF 자체가 실패했으므로
                # MediaMTX stream도 제거하면 안 된다.
                remove_stream.assert_not_called()

    def test_cctv_last_frame_utc_is_explicit(self):
        from backend.app.cctvs.schemas import CctvResponse
        data = dict(id=1, external_cctv_id="T", name="TEST", provider="UTIC", latitude=37, longitude=127, is_monitored=True, connection_status="CONNECTED", last_frame_at=datetime(2026, 10, 19, 15))
        self.assertEqual(CctvResponse(**data).last_frame_at.utcoffset(), timedelta(0))

if __name__ == "__main__": unittest.main()
