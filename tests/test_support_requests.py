"""후속-06 지원요청의 인증·권한·입력값·저장 경계를 검사합니다.

실행: python -m unittest tests.test_support_requests -v

실제 Router → JWT 검사 → Service를 실행하고, 사용자 조회와 DB 결과만 대체합니다.
테스트 전용 키를 사용하며 실제 .env, PostgreSQL, Redis, FCM에는 접근하지 않습니다.
Repository 검사는 SQL의 값 전달과 예외 전파만 확인합니다. 실제 SQL 실행 결과,
동시 저장과 PostgreSQL COMMIT·ROLLBACK은 별도 DB 연결 검사에서 확인해야 합니다.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, sentinel

import jwt
import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import dependencies
from backend.app.db import session
from backend.app.support_requests import repository, router, schemas, service


# 실제 서비스의 비밀키가 아닙니다. 생성한 JWT도 출력하지 않습니다.
TEST_JWT_KEY = "octv-support-requests-unit-test-key-never-use-in-production"
INCIDENT_ID = 301
ENDPOINT = f"/api/support-requests/incidents/{INCIDENT_ID}"
BODY = {"support_type": "PERSONNEL", "request_content": "현장 인력 지원 요청"}


def user_row(**changes):
    row = {"id": 101, "role": "RESPONDER", "agency_id": 201, "is_active": True}
    return {**row, **changes}


def request_row(**changes):
    row = {
        "id": 401,
        "incident_id": INCIDENT_ID,
        "responder_id": 101,
        "agency_id": 201,
        **BODY,
        "created_at": datetime(2026, 10, 19, 1, 2, 3),
        "responder_name": "테스트 대원",
        "agency_name": "테스트 기관",
    }
    return {**row, **changes}


class PatchTestCase(unittest.TestCase):
    def replace(self, target, **options):
        # 각 테스트가 끝나면 대체한 함수를 반드시 원래대로 돌려놓습니다.
        replacement = patch(target, **options)
        result = replacement.start()
        self.addCleanup(replacement.stop)
        return result


class SupportRequestApiTests(PatchTestCase):
    def setUp(self):
        # 빠진 mock이 있어도 실제 접속이나 환경설정 읽기로 이어지지 않게 차단합니다.
        self.replace("psycopg.connect", side_effect=AssertionError("실제 DB 접속 금지"))
        self.replace(
            "backend.app.config.jwt_secret",
            side_effect=AssertionError("실제 JWT 설정 읽기 금지"),
        )
        self.replace(
            "backend.app.db.session.database_connect_kwargs",
            side_effect=AssertionError("실제 DB 설정 읽기 금지"),
        )
        self.replace("backend.app.dependencies.jwt_secret", return_value=TEST_JWT_KEY)

        # JWT 해독은 실제 함수로 실행하고, 그 사용자 ID의 DB 조회만 대체합니다.
        self.connection = sentinel.support_connection
        for target in ("backend.app.dependencies", "backend.app.support_requests.service"):
            context = MagicMock()
            context.__enter__.return_value = self.connection
            context.__exit__.return_value = False
            self.replace(f"{target}.get_connection", return_value=context)
        self.user = user_row()
        self.lookup_user = self.replace(
            "backend.app.auth.repository.find_user_by_id", return_value=self.user
        )
        self.scope = self.replace(
            "backend.app.support_requests.repository.find_access_scope",
            return_value={
                "id": INCIDENT_ID,
                "incident_status": "SENT",
                "recommendation_status": "DELIVERED",
            },
        )
        self.list_rows = self.replace(
            "backend.app.support_requests.repository.list_for_incident", return_value=[]
        )
        self.insert = self.replace(
            "backend.app.support_requests.repository.insert_request",
            return_value=request_row(),
        )
        # app.main의 시작 작업 없이 지원요청 라우터만 등록합니다.
        app = FastAPI()
        app.include_router(router.router, prefix="/api")
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def headers(self, **claims):
        payload = {
            "sub": str(self.user["id"]),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            **claims,
        }
        token = jwt.encode(payload, TEST_JWT_KEY, algorithm=dependencies.JWT_ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

    def test_missing_login_is_401_for_read_and_create(self):
        self.assertEqual(self.client.get(ENDPOINT).status_code, 401)
        self.assertEqual(self.client.post(ENDPOINT, json=BODY).status_code, 401)
        self.lookup_user.assert_not_called()
        self.scope.assert_not_called()
        self.insert.assert_not_called()

    def test_invalid_expired_or_wrongly_signed_jwt_is_401(self):
        # unittest의 실패 출력에도 토큰이 포함되지 않도록 이름만 subTest에 넣습니다.
        cases = {
            "malformed": {"Authorization": "Bearer invalid-test-token"},
            "expired": self.headers(exp=datetime.now(timezone.utc) - timedelta(minutes=1)),
            "invalid_subject": self.headers(sub="not-a-user-id"),
            "missing_subject": self.headers(sub=None),
        }
        wrong_signature = jwt.encode(
            {"sub": "101", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            TEST_JWT_KEY + "-different",
            algorithm=dependencies.JWT_ALGORITHM,
        )
        cases["wrong_signature"] = {"Authorization": f"Bearer {wrong_signature}"}
        for name, headers in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.client.get(ENDPOINT, headers=headers).status_code, 401)
        self.lookup_user.assert_not_called()
        self.scope.assert_not_called()

    def test_deleted_user_is_401(self):
        self.lookup_user.return_value = None
        self.assertEqual(self.client.get(ENDPOINT, headers=self.headers()).status_code, 401)
        self.scope.assert_not_called()

    def test_inactive_user_is_403_before_support_queries(self):
        self.user["is_active"] = False
        for method in ("get", "post"):
            with self.subTest(method=method):
                options = {"json": BODY} if method == "post" else {}
                response = self.client.request(method, ENDPOINT, headers=self.headers(), **options)
                self.assertEqual(response.status_code, 403)
        self.scope.assert_not_called()
        self.insert.assert_not_called()

    def test_admin_reads_all_agencies_for_selected_incident(self):
        self.user.update(role="CONTROL_ADMIN", agency_id=None)
        self.list_rows.return_value = [request_row(), request_row(id=402, agency_id=202)]
        response = self.client.get(ENDPOINT, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["agency_id"] for item in response.json()], [201, 202])
        self.scope.assert_called_once_with(self.connection, INCIDENT_ID, None)
        self.list_rows.assert_called_once_with(self.connection, INCIDENT_ID, None)

    def test_field_roles_read_only_their_agency_scope(self):
        for role in ("AGENCY_STAFF", "RESPONDER"):
            for state in ("DELIVERED", "COMPLETED"):
                with self.subTest(role=role, state=state):
                    self.user["role"] = role
                    self.scope.return_value["recommendation_status"] = state
                    response = self.client.get(ENDPOINT, headers=self.headers())
                    self.assertEqual(response.status_code, 200)
                    self.scope.assert_called_with(self.connection, INCIDENT_ID, 201)
                    self.list_rows.assert_called_with(self.connection, INCIDENT_ID, 201)

    def test_missing_agency_is_404(self):
        for agency_id in (None, 0, -1, "201"):
            with self.subTest(agency_id=agency_id):
                self.user["agency_id"] = agency_id
                self.assertEqual(self.client.get(ENDPOINT, headers=self.headers()).status_code, 404)
                response = self.client.post(ENDPOINT, headers=self.headers(), json=BODY)
                self.assertEqual(response.status_code, 404)
        self.scope.assert_not_called()
        self.list_rows.assert_not_called()
        self.insert.assert_not_called()

    def test_missing_or_undelivered_incident_is_404(self):
        # 다른 기관에 전달됐더라도 자기 기관의 전달 행이 없으면 조회할 수 없습니다.
        cases = {
            "missing_incident": None,
            "other_agency_only": {"incident_status": "SENT", "recommendation_status": None},
            "recommended_only": {"incident_status": "SENT", "recommendation_status": "RECOMMENDED"},
        }
        for name, scope in cases.items():
            with self.subTest(case=name):
                self.scope.return_value = scope
                self.assertEqual(self.client.get(ENDPOINT, headers=self.headers()).status_code, 404)
                response = self.client.post(ENDPOINT, headers=self.headers(), json=BODY)
                self.assertEqual(response.status_code, 404)
        self.list_rows.assert_not_called()
        self.insert.assert_not_called()

    def test_admin_cannot_create_even_if_token_claims_field_role(self):
        self.user.update(role="CONTROL_ADMIN", agency_id=None)
        headers = self.headers(role="RESPONDER", agency_id=201)
        self.assertEqual(self.client.post(ENDPOINT, headers=headers, json=BODY).status_code, 403)
        self.insert.assert_not_called()

    def test_unknown_role_is_403_for_read_and_create(self):
        self.user["role"] = "UNSUPPORTED_TEST_ROLE"
        self.assertEqual(self.client.get(ENDPOINT, headers=self.headers()).status_code, 403)
        self.assertEqual(self.client.post(ENDPOINT, headers=self.headers(), json=BODY).status_code, 403)
        self.scope.assert_not_called()
        self.insert.assert_not_called()

    def test_field_roles_create_with_current_db_user_and_normalized_content(self):
        for role in ("AGENCY_STAFF", "RESPONDER"):
            with self.subTest(role=role):
                self.user["role"] = role
                body = {**BODY, "request_content": "  현장 인력 지원 요청\n"}
                # JWT에 임의 기관을 적어도 DB에서 조회한 현재 소속을 사용해야 합니다.
                response = self.client.post(
                    ENDPOINT, headers=self.headers(agency_id=999), json=body
                )
                self.assertEqual(response.status_code, 201)
                self.lookup_user.assert_called_with(self.connection, 101)
                self.insert.assert_called_with(self.connection, INCIDENT_ID, 101, 201, BODY)
                self.assertEqual(response.json()["id"], 401)
                self.assertEqual(response.json()["agency_id"], 201)

    def test_completed_recommendation_or_inactive_incident_rejects_create(self):
        for incident_state, agency_state in (
            ("SENT", "COMPLETED"),
            ("CONFIRMED", "DELIVERED"),
            ("RESOLVED", "DELIVERED"),
        ):
            with self.subTest(incident_state=incident_state, agency_state=agency_state):
                self.scope.return_value.update(
                    incident_status=incident_state, recommendation_status=agency_state
                )
                response = self.client.post(ENDPOINT, headers=self.headers(), json=BODY)
                self.assertEqual(response.status_code, 409)
        self.insert.assert_not_called()

    def test_status_change_before_insert_returns_409_without_retry(self):
        # SQL 조건에 맞는 행이 사라진 결과를 대체하고, Service의 처리를 확인합니다.
        self.insert.return_value = None
        response = self.client.post(ENDPOINT, headers=self.headers(), json=BODY)
        self.assertEqual(response.status_code, 409)
        self.insert.assert_called_once()

    def test_invalid_body_is_422_before_insert(self):
        cases = {
            "empty": {**BODY, "request_content": ""},
            "whitespace": {**BODY, "request_content": " \n\t "},
            "too_long": {**BODY, "request_content": "가" * 2001},
            "null_content": {**BODY, "request_content": None},
            "numeric_content": {**BODY, "request_content": 123},
            "unknown_type": {**BODY, "support_type": "AUTOMATIC_DISPATCH"},
            "missing_type": {"request_content": BODY["request_content"]},
        }
        for name, body in cases.items():
            with self.subTest(case=name):
                response = self.client.post(ENDPOINT, headers=self.headers(), json=body)
                self.assertEqual(response.status_code, 422)
        self.scope.assert_not_called()
        self.insert.assert_not_called()

    def test_forged_identity_and_status_fields_are_422(self):
        for field, value in (
            ("responder_id", 999), ("agency_id", 999), ("incident_id", 999),
            ("created_at", "2026-01-01T00:00:00Z"), ("status", "COMPLETED"),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    ENDPOINT, headers=self.headers(), json={**BODY, field: value}
                )
                self.assertEqual(response.status_code, 422)
        self.insert.assert_not_called()

    def test_declared_support_types_and_2000_characters_are_accepted(self):
        for support_type in ("PERSONNEL", "EQUIPMENT", "TRAFFIC_CONTROL", "OTHER"):
            with self.subTest(support_type=support_type):
                body = {"support_type": support_type, "request_content": "가" * 2000}
                self.insert.return_value = request_row(**body)
                response = self.client.post(ENDPOINT, headers=self.headers(), json=body)
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json()["support_type"], support_type)

    def test_invalid_incident_id_is_422(self):
        for incident_id in ("0", "-1", "9223372036854775808", "sample-incident"):
            with self.subTest(incident_id=incident_id):
                path = f"/api/support-requests/incidents/{incident_id}"
                self.assertEqual(self.client.get(path, headers=self.headers()).status_code, 422)
        self.scope.assert_not_called()

    def test_timestamp_is_explicit_utc_without_mutating_repository_row(self):
        for original in (
            datetime(2026, 10, 19, 1, 2, 3),
            datetime(2026, 10, 19, 10, 2, 3, tzinfo=timezone(timedelta(hours=9))),
        ):
            with self.subTest(has_timezone=original.tzinfo is not None):
                row = request_row(created_at=original)
                self.list_rows.return_value = [row]
                response = self.client.get(ENDPOINT, headers=self.headers())
                self.assertEqual(response.status_code, 200)
                actual = datetime.fromisoformat(response.json()[0]["created_at"])
                self.assertEqual(actual, datetime(2026, 10, 19, 1, 2, 3, tzinfo=timezone.utc))
                self.assertEqual(actual.utcoffset(), timedelta(0))
                self.assertIs(row["created_at"], original)


class SupportRequestRepositoryBoundaryTests(PatchTestCase):
    def setUp(self):
        self.replace("psycopg.connect", side_effect=AssertionError("실제 DB 접속 금지"))

    def test_scope_and_list_pass_incident_and_agency_as_parameters(self):
        connection = MagicMock()
        for agency_id in (None, 201):
            with self.subTest(agency_id=agency_id):
                repository.find_access_scope(connection, INCIDENT_ID, agency_id)
                self.assertEqual(connection.execute.call_args.args[1], (agency_id, INCIDENT_ID))
                repository.list_for_incident(connection, INCIDENT_ID, agency_id)
                expected = (INCIDENT_ID,) if agency_id is None else (INCIDENT_ID, agency_id)
                self.assertEqual(connection.execute.call_args.args[1], expected)

    def test_insert_binds_content_and_identity_then_reads_current_names(self):
        connection = MagicMock()
        stored = request_row()
        content = "장비 요청: '); -- 이 문장도 일반 입력값입니다."
        names = {"responder_name": "현재 작성자 이름", "agency_name": "현재 기관 이름"}
        connection.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=stored)),
            MagicMock(fetchone=MagicMock(return_value=names)),
        ]
        result = repository.insert_request(
            connection, INCIDENT_ID, 101, 201, {**BODY, "request_content": content}
        )
        first, second = connection.execute.call_args_list
        self.assertEqual(first.args[1], ("PERSONNEL", content, 101, INCIDENT_ID, 201))
        self.assertNotIn(content, first.args[0])
        self.assertEqual(second.args[1], (101, 201))
        self.assertEqual(result["responder_name"], names["responder_name"])
        self.assertEqual(result["agency_name"], names["agency_name"])

    def test_empty_conditional_insert_does_not_query_names(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = None
        self.assertIsNone(repository.insert_request(connection, INCIDENT_ID, 101, 201, BODY))
        connection.execute.assert_called_once()

    def test_storage_failure_reaches_psycopg_context_without_retry(self):
        # 실제 Service·Repository·get_connection을 통과하되 psycopg 연결 객체만 대체합니다.
        # __exit__에 예외가 전달되는지 확인하며 실제 DB rollback 성공을 뜻하지는 않습니다.
        self.replace("backend.app.db.session.database_connect_kwargs", return_value={})
        self.replace(
            "backend.app.support_requests.repository.find_access_scope",
            return_value={"incident_status": "SENT", "recommendation_status": "DELIVERED"},
        )
        for fail_at in ("insert", "names"):
            with self.subTest(fail_at=fail_at):
                connection = MagicMock()
                connection.__enter__.return_value = connection
                connection.__exit__.return_value = False
                error = psycopg.OperationalError("대체 저장 오류")
                if fail_at == "insert":
                    connection.execute.side_effect = error
                else:
                    connection.execute.side_effect = [
                        MagicMock(fetchone=MagicMock(return_value=request_row())), error
                    ]
                with patch.object(session.psycopg, "connect", return_value=connection):
                    with self.assertRaises(psycopg.OperationalError) as raised:
                        service.create_support_request(
                            INCIDENT_ID, schemas.SupportRequestCreate(**BODY), user_row()
                        )
                self.assertIs(raised.exception, error)
                self.assertIs(connection.__exit__.call_args.args[0], psycopg.OperationalError)
                self.assertIs(connection.__exit__.call_args.args[1], error)
                self.assertEqual(connection.execute.call_count, 1 if fail_at == "insert" else 2)


if __name__ == "__main__":
    unittest.main()
