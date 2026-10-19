r"""검증 사건 3번의 실제 기관 전달·지원요청 저장·기관별 조회를 확인합니다.

읽기 확인: python scripts\check_followup06_support_flow.py --inspect
실제 실행: python scripts\check_followup06_support_flow.py --apply

실행 전 서버의 분석·Push·Push recovery 스위치를 모두 0으로 유지합니다.
API로 테스트 사건을 SENT, 추천 두 건을 DELIVERED로 변경하고
DB 알림 2건과 지원요청 2건을 저장합니다. SQL은 읽기 전용 검증에만 사용합니다.
기존 COMPLETED 값·DB 구조·프로그램 코드·패키지는 변경하지 않습니다.
반복 POST를 막는 로컬 실행 표시를 남기며 자동 재전송이나 자동 삭제를 하지 않습니다.
비밀번호·JWT·응답 본문·예외 원문은 출력하거나 파일에 저장하지 않습니다.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import getpass
from pathlib import Path
import sys
import warnings

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from check_followup06_login import BASE_URL, EXPECTED, CheckFailed, check_identity
from prepare_followup06_test_data import TAG, require_local_development_db

INCIDENT_ID = 3
SUPPORT = "/api/support-requests/incidents/3"
RECOMMENDATIONS = "/api/agencies/incidents/3/recommendations"
DELIVERIES = "/api/agencies/incidents/3/deliveries"
RUN_MARKER = ROOT / "local_data" / "followup06_support_incident_3.started"
BODIES = {
    "agency_a": {"support_type": "EQUIPMENT", "request_content": "[OCTV06 TEST A] support request"},
    "agency_b": {"support_type": "TRAFFIC_CONTROL", "request_content": "[OCTV06 TEST B] support request"},
}


def need(condition, code):
    if not condition:
        raise CheckFailed(code)


def read_db():
    """API와 별도의 PostgreSQL 연결로 테스트 사건의 저장 결과를 읽습니다."""
    from backend.app.db.session import get_connection

    with get_connection() as c:
        require_local_development_db(c)
        c.execute("SET TRANSACTION READ ONLY")
        c.execute("SET LOCAL statement_timeout = '15s'")
        incident = c.execute(
            """SELECT i.id, i.incident_no, i.model_version, i.status, c.provider
               FROM incidents i JOIN cctvs c ON c.id = i.cctv_id WHERE i.id = %s""",
            (INCIDENT_ID,),
        ).fetchone()
        need(incident is not None and incident["model_version"] == TAG
             and incident["provider"] == TAG and incident["incident_no"] == "OCTV-F06-TEST-001",
             "EXPECTED_TEST_INCIDENT_REQUIRED")
        recs = c.execute(
            """SELECT id, agency_id, recommendation_status, rule_version
               FROM incident_agency_recommendations WHERE incident_id = %s ORDER BY agency_id""",
            (INCIDENT_ID,),
        ).fetchall()
        need(len(recs) == 2 and [r["agency_id"] for r in recs] == [1, 2]
             and all(r["rule_version"] == TAG for r in recs), "EXPECTED_TEST_RECOMMENDATIONS_REQUIRED")
        field_users = c.execute(
            """SELECT id, agency_id FROM users WHERE agency_id IN (1, 2)
               AND is_active AND role IN ('AGENCY_STAFF', 'RESPONDER') ORDER BY id"""
        ).fetchall()
        need(field_users == [{"id": 2, "agency_id": 1}, {"id": 3, "agency_id": 2}],
             "EXPECTED_TWO_FIELD_USERS_REQUIRED")
        requests = c.execute(
            """SELECT id, incident_id, responder_id, agency_id, support_type,
                      request_content, created_at FROM incident_support_requests
               WHERE incident_id = %s ORDER BY agency_id, id""", (INCIDENT_ID,),
        ).fetchall()
        notifications = c.execute(
            """SELECT id, incidents_id, agency_id, user_id, agency_recommendation_id,
                      created_at, read_at FROM notifications
               WHERE incidents_id = %s ORDER BY agency_id, id""", (INCIDENT_ID,),
        ).fetchall()
    return {"incident": incident, "recs": recs, "requests": requests, "notifications": notifications}


def print_state(state):
    print("DB_STATE: incident_id=3 status=" + state["incident"]["status"])
    print("DB_COUNTS: support_requests=" + str(len(state["requests"]))
          + " notifications=" + str(len(state["notifications"])))
    for rec in state["recs"]:
        print(f"AGENCY_STATE: agency_id={rec['agency_id']} status={rec['recommendation_status']}")


def check_request(row, label):
    body = BODIES[label]
    user_id, agency_id = (2, 1) if label == "agency_a" else (3, 2)
    need(isinstance(row, dict), "REQUEST_OBJECT_REQUIRED")
    need(type(row.get("id")) is int and row["id"] > 0
         and type(row.get("incident_id")) is int and row["incident_id"] == INCIDENT_ID
         and type(row.get("responder_id")) is int and row["responder_id"] == user_id
         and type(row.get("agency_id")) is int and row["agency_id"] == agency_id
         and row.get("support_type") == body["support_type"]
         and row.get("request_content") == body["request_content"], "REQUEST_IDENTITY_OR_CONTENT_MISMATCH")
    stamp = row.get("created_at")
    if isinstance(stamp, str):
        stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    need(isinstance(stamp, datetime) and stamp.tzinfo is not None
         and stamp.utcoffset() == timedelta(0), "REQUEST_TIMESTAMP_NOT_EXPLICIT_UTC")
    need(abs(datetime.now(timezone.utc) - stamp) < timedelta(minutes=5), "REQUEST_TIME_OUTSIDE_TEST_WINDOW")
    return stamp


class Flow:
    def __init__(self, client):
        self.client = client
        self.tokens = {}
        self.stage = "START"

    def call(self, label, method, path, account=None, body=None, expected=200):
        self.stage = label
        headers = {} if account is None else {"Authorization": "Bearer " + self.tokens[account]}
        response = self.client.request(method, path, headers=headers, json=body)
        need(response.status_code == expected, f"HTTP_{response.status_code}_EXPECTED_{expected}")
        # 거부 응답은 본문을 출력하거나 해석하지 않고 예상 HTTP 상태만 확인합니다.
        return None if expected not in (200, 201) else response.json()

    def passed(self, label):
        print("PASS: " + label, flush=True)

    def login(self, password):
        for label, email, user_id, role, agency_id in EXPECTED:
            result = self.call(label + " LOGIN", "POST", "/api/auth/login",
                               body={"email": email, "password": password})
            need(isinstance(result, dict), "LOGIN_OBJECT_REQUIRED")
            check_identity(result.get("user"), email, user_id, role, agency_id)
            token = result.get("access_token")
            need(isinstance(token, str) and token.strip() and result.get("token_type") == "bearer",
                 "BEARER_TOKEN_REQUIRED")
            self.tokens[label] = token

    def check_recommendations(self, account, expected_agencies, status):
        result = self.call(account + " RECOMMENDATIONS", "GET", RECOMMENDATIONS, account)
        need(isinstance(result, dict) and result.get("incident_id") == INCIDENT_ID
             and result.get("incident_status") == status, "RECOMMENDATION_INCIDENT_MISMATCH")
        rows = result.get("items")
        need(isinstance(rows, list) and len(rows) == len(expected_agencies), "RECOMMENDATION_COUNT_MISMATCH")
        need({r["agency_id"]: r["recommendation_status"] for r in rows} == expected_agencies,
             "RECOMMENDATION_SCOPE_MISMATCH")
        need(all(r["routes"] == [] for r in rows), "EXPECTED_NO_ROUTE_FIXTURE")
        return rows

    def deliver(self, agency_id, recommendation_id, duplicate=False):
        result = self.call("DELIVER_" + str(agency_id), "POST", DELIVERIES, "admin",
                           {"selections": [{"agency_id": agency_id}]})
        need(isinstance(result, dict), "DELIVERY_OBJECT_REQUIRED")
        items = result.get("items")
        expected_count = 0 if duplicate else 1
        need(result.get("incident_id") == INCIDENT_ID and result.get("incident_status") == "SENT"
             and result.get("created_notification_count") == expected_count
             and result.get("push_status") == ("NO_NEW_NOTIFICATIONS" if duplicate else "DISABLED")
             and isinstance(items, list) and len(items) == 1, "DELIVERY_RESULT_OR_PUSH_SWITCH_MISMATCH")
        item = items[0]
        need(item.get("agency_id") == agency_id and item.get("agency_recommendation_id") == recommendation_id
             and item.get("status") == "DELIVERED" and item.get("newly_delivered") is (not duplicate)
             and item.get("created_notification_count") == expected_count, "DELIVERY_ITEM_MISMATCH")
        self.passed(f"agency_id={agency_id} {'repeat delivery' if duplicate else 'delivery'} notifications_created={expected_count}")

    def create_request(self, label):
        body = dict(BODIES[label])
        body["request_content"] = "  " + body["request_content"] + "  "
        row = self.call(label + " SUPPORT_POST", "POST", SUPPORT, label, body, expected=201)
        check_request(row, label)
        self.passed(f"{label} SUPPORT_POST HTTP_201 request_id={row['id']}")
        return row

    def check_scope(self, account, expected_rows):
        rows = self.call(account + " SUPPORT_GET", "GET", SUPPORT, account)
        need(isinstance(rows, list) and len(rows) == len(expected_rows), "SUPPORT_SCOPE_COUNT_MISMATCH")
        need({row["id"] for row in rows} == {row["id"] for row in expected_rows.values()}, "SUPPORT_SCOPE_IDS_MISMATCH")
        by_id = {row["id"]: label for label, row in expected_rows.items()}
        for row in rows:
            check_request(row, by_id[row["id"]])
        self.passed(f"{account} SUPPORT_GET visible_requests={len(rows)}")

    def run(self, initial):
        self.check_recommendations("admin", {1: "RECOMMENDED", 2: "RECOMMENDED"}, "CONFIRMED")
        self.check_scope("admin", {})
        for account in ("agency_a", "agency_b"):
            self.call(account + " BEFORE_DELIVERY", "GET", SUPPORT, account, expected=404)
        self.passed("both agencies BEFORE_DELIVERY HTTP_404")

        self.stage = "ONCE_ONLY_GUARD"
        RUN_MARKER.parent.mkdir(parents=True, exist_ok=True)
        # x는 이미 파일이 있으면 실패합니다. 동시 실행과 재실행의 중복 POST를 막습니다.
        with RUN_MARKER.open("x", encoding="utf-8") as marker:
            marker.write("STARTED: incident=3; inspect DB before any further write.\n")

        self.call("ADMIN_CREATE_DENIED", "POST", SUPPORT, "admin", BODIES["agency_a"], expected=403)
        self.passed("admin SUPPORT_POST HTTP_403")
        rec_ids = {r["agency_id"]: r["id"] for r in initial["recs"]}
        self.deliver(1, rec_ids[1])
        # 최초 전달 성공을 확인한 뒤 같은 기관을 다시 전달하여 중복 알림 방지를 검사합니다.
        self.deliver(1, rec_ids[1], duplicate=True)
        created = {"agency_a": self.create_request("agency_a")}
        self.call("AGENCY_B_STILL_UNDELIVERED", "GET", SUPPORT, "agency_b", expected=404)
        self.passed("agency_b AFTER_A_REQUEST HTTP_404")
        self.deliver(2, rec_ids[2])
        created["agency_b"] = self.create_request("agency_b")

        self.check_scope("admin", created)
        for account, agency_id in (("agency_a", 1), ("agency_b", 2)):
            self.check_scope(account, {account: created[account]})
            self.check_recommendations(account, {agency_id: "DELIVERED"}, "SENT")
        self.check_recommendations("admin", {1: "DELIVERED", 2: "DELIVERED"}, "SENT")
        self.passed("recommendations: admin=2 agencies; each field user=own agency")

        self.stage = "POSTGRES_COMMIT_VERIFICATION"
        final = read_db()
        need(final["incident"]["status"] == "SENT"
             and all(r["recommendation_status"] == "DELIVERED" for r in final["recs"]), "DB_DELIVERY_STATE_MISMATCH")
        need(len(final["requests"]) == 2, "DB_REQUEST_COUNT_MISMATCH")
        for stored in final["requests"]:
            label = "agency_a" if stored["agency_id"] == 1 else "agency_b"
            api_row = created[label]
            need(stored["id"] == api_row["id"] and stored["created_at"].tzinfo is None, "DB_REQUEST_OR_TIMESTAMP_MISMATCH")
            normalized = {**stored, "created_at": stored["created_at"].replace(tzinfo=timezone.utc)}
            need(check_request(normalized, label) == check_request(api_row, label), "DB_API_TIME_MISMATCH")
        notes = final["notifications"]
        need(len(notes) == 2 and {(n["agency_id"], n["user_id"]) for n in notes} == {(1, 2), (2, 3)},
             "DB_NOTIFICATION_SCOPE_MISMATCH")
        need(all(n["incidents_id"] == INCIDENT_ID and n["agency_recommendation_id"] == rec_ids[n["agency_id"]]
                 and n["read_at"] is None for n in notes), "DB_NOTIFICATION_LINK_MISMATCH")
        for account, user_id in (("agency_a", 2), ("agency_b", 3)):
            api_notes = self.call(account + " NOTIFICATIONS", "GET", "/api/notifications", account)
            need(isinstance(api_notes, list), "NOTIFICATIONS_LIST_REQUIRED")
            selected = [n for n in api_notes if n.get("incident_id") == INCIDENT_ID]
            expected_note = next(n for n in notes if n["user_id"] == user_id)
            need(len(selected) == 1 and selected[0].get("id") == expected_note["id"]
                 and selected[0].get("read_at") is None, "NOTIFICATION_API_SCOPE_MISMATCH")
        self.passed("POSTGRES: support_requests=2 notifications=2; support request API/DB identity and UTC match")
        print("SUPPORT_FLOW_PASSED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    flow = None
    stage = "READ_ONLY_PREFLIGHT"
    try:
        initial = read_db()
        print_state(initial)
        if not args.apply:
            print("READ_ONLY_DONE: no API writes.")
            return 0
        need(not RUN_MARKER.exists(), "ALREADY_STARTED_USE_INSPECT_ONLY")
        need(initial["incident"]["status"] == "CONFIRMED"
             and all(r["recommendation_status"] == "RECOMMENDED" for r in initial["recs"])
             and not initial["requests"] and not initial["notifications"], "FRESH_TEST_DATA_REQUIRED")
        stage = "SERVER_CHECK"
        with httpx.Client(base_url=BASE_URL, timeout=15.0, trust_env=False, follow_redirects=False) as client:
            flow = Flow(client)
            spec = flow.call("SERVER_CHECK", "GET", "/openapi.json")
            need(isinstance(spec, dict) and spec.get("info", {}).get("title", "").startswith("OCTV"),
                 "EXPECTED_OCTV_SERVER_REQUIRED")
            flow.stage = "PASSWORD_INPUT"
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Test password (hidden): ")
            flow.login(password)
            del password
            flow.run(initial)
        return 0
    except (KeyboardInterrupt, EOFError):
        print("CANCELLED: use --inspect; do not repeat POST automatically.")
        return 2
    except Exception as exc:
        safe_error = str(exc) if isinstance(exc, CheckFailed) else type(exc).__name__
        print("STOPPED:", flow.stage if flow else stage, safe_error)
        print("Some API writes may already be committed. Use --inspect and paste status output.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
