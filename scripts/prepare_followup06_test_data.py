r"""후속06의 실제 로그인·기관 전달·지원요청 검증에 사용할 개발 DB 자료를 준비합니다.

흐름: 읽기 전용 사전 확인 → 비밀번호 입력 → 검증용 10행 INSERT → COMMIT.
기존 get_connection과 회원가입 비밀번호 검증을 재사용합니다.
기존 행의 UPDATE/DELETE, 스키마 변경, Worker·외부 API·FCM 호출은 없습니다.
지원요청은 만들지 않습니다. 이후 실제 API로 등록해야 저장 검증이 됩니다.

Windows CMD, 프로젝트 루트:
    python scripts\prepare_followup06_test_data.py --apply

--apply가 없으면 사전 확인과 추가 예정 건수만 표시합니다.
자료는 웹·모바일 검증에 재사용하도록 COMMIT 후 남습니다.
실패하면 해당 트랜잭션은 rollback되지만 자동 증가 ID는 소모될 수 있습니다.
"""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import sys
import warnings


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TAG = "OCTV_FOLLOWUP06_TEST"
INCIDENT_NO = "OCTV-F06-TEST-001"
EMAILS = (
    "octv06.admin@example.com",
    "octv06.agency.a@example.com",
    "octv06.agency.b@example.com",
)
PLANNED_ROWS = {
    "region": 1,
    "agencies": 2,
    "users": 3,
    "cctvs": 1,
    "incidents": 1,
    "incident_agency_recommendations": 2,
    "incident_support_requests": 0,
}


class PreparationStopped(Exception):
    """오류 본문 대신 아래에 정의한 고정 코드만 출력합니다."""


def require_local_development_db(connection):
    # 이번에 사용자가 확인한 로컬 octv_dev에서만 테스트 자료를 추가합니다.
    if (
        connection.info.host not in {"127.0.0.1", "localhost", "::1"}
        or connection.info.dbname != "octv_dev"
    ):
        raise PreparationStopped("EXPECTED_LOCAL_OCTV_DEV")


def require_unused_markers(connection):
    # 재실행·이름 충돌이면 중단합니다. 기존 계정의 비밀번호나 역할을 덮지 않습니다.
    row = connection.execute(
        """
        SELECT
          EXISTS (SELECT 1 FROM users WHERE lower(btrim(email)) = ANY(%s))
          OR EXISTS (SELECT 1 FROM region WHERE region_code = %s)
          OR EXISTS (SELECT 1 FROM cctvs WHERE provider = %s)
          OR EXISTS (SELECT 1 FROM incidents
                     WHERE incident_no = %s OR model_version = %s)
          AS marker_exists
        """,
        (list(EMAILS), TAG, TAG, INCIDENT_NO, TAG),
    ).fetchone()
    if row["marker_exists"]:
        raise PreparationStopped("TEST_MARKER_EXISTS_NO_ROWS_ADDED")


def read_password():
    from backend.app.auth.schemas import SignupRequest
    from pydantic import ValidationError

    print("Password: 8-10 characters, letters + digits + special character, no spaces.")
    # 입력이 화면에 표시되는 getpass 대체 동작은 사용하지 않습니다.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Test password (hidden): ")
        repeated = getpass.getpass("Repeat password (hidden): ")
    if password != repeated:
        raise PreparationStopped("PASSWORD_CONFIRMATION_MISMATCH")
    try:
        SignupRequest(
            email=EMAILS[1], password=password, name="OCTV06 TEST",
            role="AGENCY_STAFF", agency_id=1,
        )
    except ValidationError:
        # ValidationError 전체에는 입력값이 들어갈 수 있으므로 출력하지 않습니다.
        raise PreparationStopped("PASSWORD_POLICY_REJECTED") from None
    return password


def insert_fixture(connection, password_hash):
    from psycopg.types.json import Json

    connection.execute(
        "INSERT INTO region (region_code, sido_name, sigungu_name) VALUES (%s, %s, %s)",
        (TAG, "OCTV 테스트", "후속06 검증용"),
    )
    agency_ids = []
    for label, agency_type in (("A", "FIRE"), ("B", "ROAD_MANAGEMENT")):
        agency_ids.append(connection.execute(
            """
            INSERT INTO agencies
              (name, agency_type, latitude, longitude, region_code)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (f"[OCTV06 테스트] {label}기관", agency_type, 37.5, 127.0, TAG),
        ).fetchone()["id"])

    users = {}
    specs = (
        ("admin", EMAILS[0], "CONTROL_ADMIN", None),
        ("agency_a", EMAILS[1], "AGENCY_STAFF", agency_ids[0]),
        ("agency_b", EMAILS[2], "RESPONDER", agency_ids[1]),
    )
    for label, email, role, agency_id in specs:
        user_id = connection.execute(
            """
            INSERT INTO users
              (email, password_hash, name, role, is_active, agency_id, notification_enabled)
            VALUES (%s, %s, %s, %s, TRUE, %s, TRUE) RETURNING id
            """,
            (email, password_hash, f"[OCTV06 테스트] {label}", role, agency_id),
        ).fetchone()["id"]
        users[label] = {"id": user_id, "role": role, "agency_id": agency_id}

    # 영상 URL·감시 설정이 없는 테스트 CCTV이며 실제 탐지를 실행하지 않습니다.
    cctv_id = connection.execute(
        """
        INSERT INTO cctvs
          (external_cctv_id, name, provider, latitude, longitude, region_code, is_monitored)
        VALUES (%s, %s, %s, %s, %s, %s, FALSE) RETURNING id
        """,
        (TAG, "[OCTV06 테스트] 영상 없는 검증용 CCTV", TAG, 37.5, 127.0, TAG),
    ).fetchone()["id"]

    # CONFIRMED와 추천 2건은 검증의 시작 조건입니다. 실제 분석 결과로 취급하지 않습니다.
    incident_id = connection.execute(
        """
        INSERT INTO incidents
          (incident_no, cctv_id, hazard_type, confidence, model_version,
           detection_bbox_json, dedup_key, status, detected_at, last_detected_at)
        VALUES (%s, %s, 'road_obstacle', 0.9, %s, %s, %s, 'CONFIRMED',
                CURRENT_TIMESTAMP AT TIME ZONE 'UTC',
                CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
        RETURNING id
        """,
        (INCIDENT_NO, cctv_id, TAG, Json({"test_fixture": True}), TAG),
    ).fetchone()["id"]

    for rank, agency_id in enumerate(agency_ids, start=1):
        connection.execute(
            """
            INSERT INTO incident_agency_recommendations
              (recommendation_rank, recommendation_score, score_breakdown_json,
               rule_version, recommendation_status, incident_id, agency_id)
            VALUES (%s, 0, %s, %s, 'RECOMMENDED', %s, %s)
            """,
            (rank, Json({"test_fixture": True}), TAG, incident_id, agency_id),
        )
    return {"incident_id": incident_id, "incident_no": INCIDENT_NO, "users": users}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="검증용 10행을 실제 저장")
    args = parser.parse_args()
    stage = "IMPORT"
    try:
        import bcrypt
        from backend.app.config import jwt_secret
        from backend.app.db.session import get_connection

        stage = "READ_ONLY_PREFLIGHT"
        with get_connection() as connection:
            require_local_development_db(connection)
            connection.execute("SET TRANSACTION READ ONLY")
            require_unused_markers(connection)
        try:
            jwt_secret()
            jwt_ready = True
        except ValueError:
            jwt_ready = False
        print("JWT_SECRET_CONFIGURED =", jwt_ready)
        print("PLANNED_ROWS =", json.dumps(PLANNED_ROWS))
        if not args.apply:
            print("READ_ONLY_DONE: add --apply to prepare the test data.")
            return 0

        stage = "PASSWORD"
        password = read_password()
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        del password
        stage = "INSERT_TRANSACTION"
        with get_connection() as connection:
            require_local_development_db(connection)
            connection.execute("SET LOCAL lock_timeout = '5s'")
            connection.execute("SET LOCAL statement_timeout = '15s'")
            require_unused_markers(connection)
            result = insert_fixture(connection, password_hash)
        del password_hash
        print("TEST_DATA_COMMITTED")
        print(json.dumps(result, indent=2))
        print("NEXT: actual login -> agency delivery -> support request POST/GET.")
        return 0
    except PreparationStopped as exc:
        print("STOPPED:", str(exc))
        return 2
    except (KeyboardInterrupt, EOFError):
        print("CANCELLED: check the test marker before retrying.")
        return 2
    except Exception as exc:
        # 접속 문자열·SQL 본문·입력값이 포함될 수 있는 예외 메시지를 출력하지 않습니다.
        print("PREPARATION_FAILED:", stage, type(exc).__name__)
        print("Do not repeat automatically; paste these status lines for review.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
