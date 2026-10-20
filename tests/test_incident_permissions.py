"""기존 auth와 사건·기관 API 연결을 검증합니다. DB 연결·조회 결과만 Mock으로 대체합니다.
실행: python -m unittest discover -s tests -p test_incident_permissions.py -v
"""

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import unittest
from unittest.mock import MagicMock, patch

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation

from backend.app.main import app
from backend.app import dependencies
from backend.app.auth import repository as auth_repository, service as auth_service
from backend.app.agencies import repository as agency_repository, service as agency_service
from backend.app.incidents import repository as incident_repository, service as incident_service


TEST_SECRET = "test-only-octv-secret-do-not-use-in-a-server-0123456789"
TEST_PASSWORD = "Octv123!"


class IncidentPermissionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = bcrypt.hashpw(
            TEST_PASSWORD.encode(), bcrypt.gensalt()
        ).decode()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"JWT_SECRET": TEST_SECRET}))
        self.stack.enter_context(
            patch("psycopg.connect", side_effect=AssertionError("실제 DB 연결 금지"))
        )
        self.connection = MagicMock()
        self.connection.execute.return_value.fetchone.return_value = None
        for module in (dependencies, auth_service, incident_service, agency_service):
            mocked = self.stack.enter_context(patch.object(module, "get_connection"))
            mocked.return_value.__enter__.return_value = self.connection
        self.user = {
            "id": 9,
            "email": "member@example.com",
            "name": "테스트 사용자",
            "password_hash": self.password_hash,
            "role": "RESPONDER",
            "agency_id": 7,
            "notification_enabled": True,
            "is_active": True,
        }
        self.find_email = self.stack.enter_context(patch.object(
            auth_repository, "find_user_by_email", side_effect=lambda c, e: self.user
        ))
        self.find_id = self.stack.enter_context(patch.object(
            auth_repository, "find_user_by_id", side_effect=lambda c, i: self.user
        ))
        self.client = self.stack.enter_context(TestClient(app))

    def headers(self, **changes):
        now = datetime.now(timezone.utc)
        claims = {"sub": "9", "iat": now, "exp": now + timedelta(minutes=60)}
        claims.update(changes)
        token = jwt.encode(claims, TEST_SECRET, algorithm="HS256")
        return {"Authorization": "Bearer " + token}

    def incident(self):
        return {
            "id": 31,
            "incident_no": "OCTV-test",
            "cctv_id": 1,
            "cctv_name": "테스트 CCTV",
            "provider": "UTIC",
            "address": "서울특별시 강남구 테헤란로 629",
            "hazard_type": "FLOOD",
            "status": "DETECTED",
            "confidence": Decimal("0.9"),
            "detected_at": datetime(2026, 1, 1),
            "last_detected_at": datetime(2026, 1, 1),
            "latitude": Decimal("37.5"),
            "longitude": Decimal("127.0"),
            "region_code": None,
            "representative_image_updated_at": None,
            "detection_bbox_json": {},
        }

    def test_existing_login_token_and_me(self):
        response = self.client.post("/api/auth/login", json={
            "email": " MEMBER@EXAMPLE.COM ", "password": TEST_PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.find_email.call_args.args[1], "member@example.com")
        body = response.json()
        self.assertNotIn("password_hash", body["user"])
        claims = jwt.decode(body["access_token"], TEST_SECRET, algorithms=["HS256"])
        self.assertEqual(claims["exp"] - claims["iat"], 3600)
        result = self.client.get("/api/auth/me", headers={
            "Authorization": "Bearer " + body["access_token"],
        })
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["id"], 9)
        self.assertNotIn("password_hash", result.json())

    def test_existing_oauth_token_works_for_incidents(self):
        result = self.client.post("/api/auth/token", data={
            "username": "member@example.com", "password": TEST_PASSWORD,
        })
        self.assertEqual(result.status_code, 200)
        with patch.object(incident_repository, "list_incidents", return_value={
            "items": [], "total": 0, "page": 1, "page_size": 5,
        }) as query:
            response = self.client.get("/api/incidents", headers={
                "Authorization": "Bearer " + result.json()["access_token"],
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(query.call_args.args[1]["agency_id"], 7)

    def test_existing_wrong_password_and_inactive_account(self):
        body = {"email": "member@example.com", "password": "Wrong123!"}
        self.assertEqual(self.client.post("/api/auth/login", json=body).status_code, 401)
        self.user["is_active"] = False
        body["password"] = TEST_PASSWORD
        self.assertEqual(self.client.post("/api/auth/login", json=body).status_code, 403)
        self.assertEqual(
            self.client.get("/api/incidents", headers=self.headers()).status_code, 403
        )

    def test_missing_invalid_and_expired_tokens(self):
        invalid_headers = [
            {},
            {"Authorization": "Bearer invalid"},
            self.headers(exp=datetime.now(timezone.utc) - timedelta(seconds=1)),
            self.headers(sub="not-an-id"),
        ]
        for path in ("/api/incidents", "/api/incidents/31"):
            for headers in invalid_headers:
                with self.subTest(path=path, headers_present=bool(headers)):
                    self.assertEqual(self.client.get(path, headers=headers).status_code, 401)

    def test_deleted_user_is_unauthorized(self):
        self.find_id.side_effect = None
        self.find_id.return_value = None
        self.assertEqual(
            self.client.get("/api/incidents", headers=self.headers()).status_code, 401
        )

    def test_signup_sidos(self):
        with patch.object(
            auth_repository,
            "list_signup_sidos",
            return_value=[
                {
                    "sido_name":
                        "경기도"
                },
                {
                    "sido_name":
                        "서울특별시"
                },
            ],
        ) as query:

            response = self.client.get(
                "/api/auth/signup/sidos"
            )

            self.assertEqual(
                response.status_code,
                200,
            )

            self.assertEqual(
                response.json(),
                [
                    {
                        "sido_name":
                            "경기도"
                    },
                    {
                        "sido_name":
                            "서울특별시"
                    },
                ],
            )

            query.assert_called_once_with(
                self.connection
            )


    def test_signup_sigungus(self):
        with patch.object(
            auth_repository,
            "list_signup_sigungus",
            return_value=[
                {
                    "region_code":
                        "11680",
                    "sigungu_name":
                        "강남구",
                },
            ],
        ) as query:

            response = self.client.get(
                "/api/auth/signup/sigungus",
                params={
                    "sido_name":
                        "서울특별시"
                },
            )

            self.assertEqual(
                response.status_code,
                200,
            )

            self.assertEqual(
                response.json(),
                [
                    {
                        "region_code":
                            "11680",
                        "sigungu_name":
                            "강남구",
                    },
                ],
            )

            query.assert_called_once_with(
                self.connection,
                "서울특별시",
            )

        response = self.client.get(
            "/api/auth/signup/sigungus",
            params={
                "sido_name": ""
            },
        )

        self.assertEqual(
            response.status_code,
            400,
        )


    def test_signup_agencies(self):
        with patch.object(
            auth_repository,
            "list_signup_agencies",
            return_value=[
                {
                    "id": 4,
                    "name":
                        "강남소방서",
                    "agency_type":
                        "FIRE",
                    "address":
                        "서울특별시 강남구 테헤란로 629 (삼성동)",
                    "region_code":
                        "11680",
                },
            ],
        ) as query:

            response = self.client.get(
                "/api/auth/signup/agencies",
                params={
                    "region_code":
                        "11680",
                    "agency_type":
                        "FIRE",
                },
            )

            self.assertEqual(
                response.status_code,
                200,
            )

            body = response.json()

            self.assertEqual(
                body[0]["name"],
                "강남소방서",
            )

            self.assertEqual(
                body[0]["agency_type"],
                "FIRE",
            )

            self.assertEqual(
                body[0]["region_code"],
                "11680",
            )

            self.assertIsNotNone(
                body[0]["address"]
            )

            query.assert_called_once_with(
                self.connection,
                "11680",
                "FIRE",
            )

        response = self.client.get(
            "/api/auth/signup/agencies",
            params={
                "region_code":
                    "11680",
                "agency_type":
                    "INVALID",
            },
        )

        self.assertEqual(
            response.status_code,
            422,
        )



    def test_existing_signup_rules_and_password_hash(self):
        body = {
            "email": "NEW@EXAMPLE.COM", "password": TEST_PASSWORD,
            "name": " 사용자 ", "role": "RESPONDER", "agency_id": 7,
        }
        self.find_email.side_effect = None
        self.find_email.return_value = None
        with patch.object(auth_repository, "agency_exists", return_value=True), \
                patch.object(auth_repository, "insert_user", return_value=self.user) as insert:
            response = self.client.post("/api/auth/signup", json=body)
            self.assertEqual(response.status_code, 201)
            values = insert.call_args.args[1]
            self.assertEqual(values["email"], "new@example.com")
            self.assertEqual(values["name"], "사용자")
            self.assertTrue(bcrypt.checkpw(
                TEST_PASSWORD.encode(), values["password_hash"].encode()
            ))
            for changes in (
                {"role": "CONTROL_ADMIN"}, {"password": "short"},
                {"password": "Octv123456!"}, {"agency_id": 0}, {"name": "   "},
            ):
                with self.subTest(changes=changes):
                    self.assertEqual(
                        self.client.post("/api/auth/signup", json=body | changes).status_code,
                        422,
                    )
            self.assertEqual(insert.call_count, 1)

    def test_existing_duplicate_and_unknown_agency_errors(self):
        body = {
            "email": "new@example.com", "password": TEST_PASSWORD,
            "name": "사용자", "role": "RESPONDER", "agency_id": 7,
        }
        self.assertEqual(self.client.post("/api/auth/signup", json=body).status_code, 409)
        self.find_email.side_effect = None
        self.find_email.return_value = None
        with patch.object(auth_repository, "agency_exists", return_value=False):
            self.assertEqual(self.client.post("/api/auth/signup", json=body).status_code, 400)
        with patch.object(auth_repository, "agency_exists", return_value=True), \
                patch.object(auth_repository, "insert_user", side_effect=UniqueViolation()):
            self.assertEqual(self.client.post("/api/auth/signup", json=body).status_code, 409)

    def test_existing_admin_dependency(self):
        test_app = FastAPI()

        @test_app.get("/admin")
        def admin(user=Depends(dependencies.require_control_admin)):
            return {"id": user["id"]}

        with TestClient(test_app) as client:
            self.assertEqual(client.get("/admin").status_code, 401)
            self.assertEqual(client.get("/admin", headers=self.headers()).status_code, 403)
            self.user["role"] = "CONTROL_ADMIN"
            self.assertEqual(client.get("/admin", headers=self.headers()).status_code, 200)

    def test_list_scope_uses_current_user_for_both_roles(self):
        headers = self.headers()
        with patch.object(incident_repository, "list_incidents", return_value={
            "items": [], "total": 0, "page": 1, "page_size": 5,
        }) as query:
            for role, agency_id in (("RESPONDER", 7), ("AGENCY_STAFF", 8)):
                self.user.update(role=role, agency_id=agency_id)
                result = self.client.get(
                    "/api/incidents?agency_id=999&active_only=true", headers=headers
                )
                self.assertEqual(result.status_code, 200)
                self.assertEqual(query.call_args.args[1]["agency_id"], agency_id)
                self.assertTrue(query.call_args.args[1]["agency_active_only"])
            self.user.update(role="CONTROL_ADMIN", agency_id=None)
            self.client.get("/api/incidents", headers=headers)
            self.assertNotIn("agency_id", query.call_args.args[1])

    def test_service_does_not_trust_supplied_agency_filter(self):
        filters = {"agency_id": 999, "agency_active_only": True}
        with patch.object(incident_repository, "list_incidents", return_value={
            "items": [], "total": 0, "page": 1, "page_size": 5,
        }) as query:
            incident_service.list_incidents(filters=filters, user=self.user)
            self.assertEqual(query.call_args.args[1]["agency_id"], 7)
            self.assertFalse(query.call_args.args[1]["agency_active_only"])
            self.assertEqual(filters, {"agency_id": 999, "agency_active_only": True})

    def test_detail_denied_before_reading_incident(self):
        with patch.object(incident_repository, "find_detail") as detail:
            result = self.client.get("/api/incidents/31", headers=self.headers())
            self.assertEqual(result.status_code, 404)
            detail.assert_not_called()
            sql, params = self.connection.execute.call_args.args
            self.assertEqual(params, (31, 7))
            self.assertIn("'DELIVERED', 'COMPLETED'", sql)

    def test_detail_allowed_for_own_agency(self):
        self.connection.execute.return_value.fetchone.return_value = {"id": 1}

        recommendations = {
            "incident_id": 31,
            "incident_status": "DETECTED",
            "items": [],
        }

        with (
            patch.object(
                incident_repository,
                "find_detail",
                return_value=self.incident(),
            ),
            patch.object(
                agency_repository,
                "list_recommendations",
                return_value=recommendations,
            ),
        ):
            response = self.client.get(
                "/api/incidents/31",
                headers=self.headers(),
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            response.json()["id"],
            31,
        )
        self.assertEqual(
            response.json()["analysis_status"],
            "PENDING",
        )

        self.assertEqual(
            response.json()["provider"],
            "UTIC",
        )

        self.assertEqual(
            response.json()["address"],
            "서울특별시 강남구 테헤란로 629",
        )

    def test_admin_detail_and_missing_incident(self):
        self.user.update(
            role="CONTROL_ADMIN",
            agency_id=None,
        )

        recommendations = {
            "incident_id": 31,
            "incident_status": "DETECTED",
            "items": [],
        }

        with (
            patch.object(
                incident_repository,
                "find_detail",
                return_value=self.incident(),
            ) as detail,
            patch.object(
                agency_repository,
                "list_recommendations",
                return_value=recommendations,
            ) as recommendation_query,
        ):
            self.assertEqual(
                self.client.get(
                    "/api/incidents/31",
                    headers=self.headers(),
                ).status_code,
                200,
            )

            self.connection.execute.assert_not_called()

            recommendation_query.assert_called_once_with(
                self.connection,
                31,
                agency_id=None,
            )

            detail.return_value = None

            self.assertEqual(
                self.client.get(
                    "/api/incidents/999",
                    headers=self.headers(),
                ).status_code,
                404,
            )

    def test_user_without_agency_cannot_read_detail(self):
        self.user["agency_id"] = None
        with patch.object(incident_repository, "find_detail") as detail:
            self.assertEqual(
                self.client.get("/api/incidents/31", headers=self.headers()).status_code, 404
            )
            detail.assert_not_called()
            self.connection.execute.assert_not_called()
        self.assertEqual(incident_repository.agency_filter({"agency_id": None}), ("FALSE", []))

    def test_list_count_and_page_share_scope(self):
        self.connection.execute.side_effect = [
            MagicMock(**{"fetchone.return_value": {"n": 3}}),
            MagicMock(**{"fetchall.return_value": []}),
        ]
        result = incident_repository.list_incidents(
            self.connection, {"agency_id": 7, "q": "OCTV"}, 9, 5
        )
        self.assertEqual(result, {"items": [], "total": 3, "page": 9, "page_size": 5})
        count, page = self.connection.execute.call_args_list
        for call in (count, page):
            self.assertIn("ar.agency_id = %s", call.args[0])
            self.assertIn("'DELIVERED', 'COMPLETED'", call.args[0])
        self.assertEqual(count.args[1], ["%OCTV%", "%OCTV%", "%OCTV%", 7])
        self.assertEqual(page.args[1], ["%OCTV%", "%OCTV%", "%OCTV%", 7, 5, 40])

    def test_active_scope_and_existing_search_parameters(self):
        active, params = incident_repository.agency_filter({
            "agency_id": 7, "agency_active_only": True,
        })
        self.assertIn("= 'DELIVERED'", active)
        self.assertNotIn("COMPLETED", active)
        self.assertEqual(params, [7])
        start, end = datetime(2026, 1, 1), datetime(2026, 1, 2)
        where, values = incident_repository.incident_where({
            "status": "SENT", "hazard_type": "FLOOD", "priority": "P1",
            "region_code": "11000", "cctv_id": 1, "start": start, "end": end,
            "q": "road", "confirmed_only": True, "active_only": True,
        })
        self.assertEqual(values, ["SENT", "FLOOD", "P1", "11000", 1, start, end, "%road%", "%road%", "%road%"])
        self.assertIn("c.address ILIKE %s", where)
        self.assertIn("i.detected_at >= %s", where)
        self.assertIn("i.detected_at < %s", where)

    def test_existing_query_validation(self):
        for query in ("page=0", "page_size=101", "status=UNKNOWN", "start=2026-01-01T00:00:00"):
            with self.subTest(query=query):
                self.assertEqual(
                    self.client.get("/api/incidents?" + query, headers=self.headers()).status_code,
                    422,
                )


    def test_responder_completes_delivery_and_incident_stays_sent(self):
        with (
            patch.object(
                agency_repository,
                "complete_delivery",
                return_value={
                    "agency_recommendation_id": 12,
                    "agency_id": 7,
                    "recommendation_status": "COMPLETED",
                },
            ) as complete,
            patch.object(
                incident_repository,
                "resolve_if_all_deliveries_completed",
                return_value={
                    "id": 31,
                    "status": "SENT",
                },
            ) as resolve,
        ):
            response = self.client.patch(
                "/api/agencies/incidents/31/complete",
                headers=self.headers(),
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json(),
            {
                "incident_id": 31,
                "agency_id": 7,
                "agency_recommendation_id": 12,
                "recommendation_status": "COMPLETED",
                "incident_status": "SENT",
            },
        )

        complete.assert_called_once_with(
            self.connection,
            31,
            7,
        )

        resolve.assert_called_once_with(
            self.connection,
            31,
        )


    def test_last_responder_completion_resolves_incident(self):
        with (
            patch.object(
                agency_repository,
                "complete_delivery",
                return_value={
                    "agency_recommendation_id": 12,
                    "agency_id": 7,
                    "recommendation_status": "COMPLETED",
                },
            ),
            patch.object(
                incident_repository,
                "resolve_if_all_deliveries_completed",
                return_value={
                    "id": 31,
                    "status": "RESOLVED",
                },
            ),
        ):
            response = self.client.patch(
                "/api/agencies/incidents/31/complete",
                headers=self.headers(),
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json()["recommendation_status"],
            "COMPLETED",
        )

        self.assertEqual(
            response.json()["incident_status"],
            "RESOLVED",
        )


    def test_agency_staff_cannot_complete_delivery(self):
        self.user["role"] = "AGENCY_STAFF"

        with (
            patch.object(
                agency_repository,
                "complete_delivery",
            ) as complete,
            patch.object(
                incident_repository,
                "resolve_if_all_deliveries_completed",
            ) as resolve,
        ):
            response = self.client.patch(
                "/api/agencies/incidents/31/complete",
                headers=self.headers(),
            )

        self.assertEqual(
            response.status_code,
            403,
        )

        complete.assert_not_called()
        resolve.assert_not_called()


    def test_internal_service_requires_user(self):
        for action in (
            lambda: incident_service.list_incidents(),
            lambda: incident_service.get_incident(31, None),
        ):
            with self.assertRaises(HTTPException) as error:
                action()
            self.assertEqual(error.exception.status_code, 401)

    def test_public_agency_fields_and_query_order(self):
        self.connection.execute.return_value.fetchall.return_value = [{
            "id": 7, "name": "테스트 기관", "agency_type": "FIRE", "phone": "private",
        }]
        response = self.client.get("/api/agencies")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"id": 7, "name": "테스트 기관", "agency_type": "FIRE"}])
        sql, params = self.connection.execute.call_args.args
        self.assertIn("ORDER BY name, id", sql)
        self.assertEqual(params, [])
        agency_repository.list_agencies(self.connection, "11000")
        self.assertEqual(self.connection.execute.call_args.args[1], ["11000"])

    def test_existing_detection_time_and_serialization(self):
        when = datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9)))
        candidate = {"confidence": "0.9", "detected_at": when}
        with patch.object(incident_repository, "save_detection", return_value={"id": 31}) as save:
            self.assertEqual(incident_service.register_detection(candidate), {"id": 31})
            self.assertEqual(save.call_args.args[1]["detected_at"], datetime(2026, 1, 1))
            self.assertEqual(candidate["detected_at"], when)
        with self.assertRaises(ValueError):
            incident_service.utc_naive(datetime(2026, 1, 1))
        row = self.incident()
        result = incident_service.serialize_incident(row)
        self.assertEqual(result["detected_at"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(result["confidence"], 0.9)
        self.assertIsNone(row["detected_at"].tzinfo)


if __name__ == "__main__":
    unittest.main()
