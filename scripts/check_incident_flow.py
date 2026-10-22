"""설정 존재 여부와 한 사건의 저장 상태만 조회. 큐 발행/외부 API/데이터 변경 없음.

python scripts/check_incident_flow.py
python scripts/check_incident_flow.py --incident-id 31
기본 실행은 설정 검사만 합니다. ID를 지정해야 PostgreSQL·Redis에 접속합니다.
인증값, 토큰, 요청 URL, 예외 원문 및 Redis 전체 상태는 출력하지 않습니다.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PUSH_STATES = {
    "READY", "WAITING", "SENDING", "FINISHED", "SKIPPED", "EXHAUSTED",
    "EXPIRED", "CONFIG_ERROR",
}
DEVICE_STATES = {"ACCEPTED", "RETRY", "UNREGISTERED", "PERMANENT_ERROR", "CONFIG_ERROR", "CHANGED"}


def summarize_push(raw):
    """알림 기록의 허용된 상태와 개수만 반환. 임의 문자열은 그대로 출력하지 않음."""
    if raw is None:
        return {"status": "NO_REDIS_RECORD"}
    try:
        state = json.loads(raw)
        if not isinstance(state, dict) or state.get("version") != 1:
            raise ValueError
        status = state.get("status")
        attempts = state.get("attempts", 0)
        results = state.get("results", {})
        if status not in PUSH_STATES or type(attempts) is not int or attempts < 0:
            raise ValueError
        if not isinstance(results, dict):
            raise ValueError
        counts = {name: 0 for name in sorted(DEVICE_STATES)}
        for item in results.values():
            if not isinstance(item, dict) or item.get("status") not in DEVICE_STATES:
                raise ValueError
            counts[item["status"]] += 1
        return {"status": status, "attempts": attempts, "device_counts": counts}
    except (ValueError, TypeError):
        return {"status": "INVALID_REDIS_RECORD"}


def check_settings():
    from backend.app.config import load_environment
    load_environment()
    output = {
        "mode": "SETTINGS_ONLY",
        "enabled": {key: os.environ.get(key, "0") == "1" for key in (
            "OCTV_DECISION_ENABLED", "OCTV_AUTO_MAPPING_ENABLED",
            "OCTV_PUSH_ENABLED", "OCTV_PUSH_RECOVERY_ENABLED",
        )},
        "configured": {key: bool(os.environ.get(key, "").strip()) for key in (
            "OCTV_REDIS_URL", "OCTV_RUNTIME_CONFIG", "OCTV_FIREBASE_PROJECT_ID",
            "GOOGLE_APPLICATION_CREDENTIALS", "OCTV_PUSH_START_AT",
        )},
    }
    try:
        from ai.config import get_runtime_config
        config = get_runtime_config()
        output["runtime"] = {"status": "VALID", "transport": config["context_transport"]}
    except Exception:
        output["runtime"] = {"status": "NOT_READY"}
    # 미설정 ADC는 실행 환경의 서비스 계정을 사용할 수도 있으므로 실패로 단정하지 않습니다.
    return output


def read_incident(incident_id):
    from backend.app.db.session import get_connection
    with get_connection() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '5000ms'")
        row = connection.execute("""
            SELECT i.id, i.status,
              (SELECT count(*) FROM incident_contexts c WHERE c.incident_id=i.id) AS contexts,
              (SELECT count(*) FROM incident_assessments a WHERE a.incident_id=i.id) AS assessments,
              (SELECT count(*) FROM notifications n WHERE n.incidents_id=i.id) AS notifications
            FROM incidents i WHERE i.id=%s
        """, (incident_id,)).fetchone()
        if row is None:
            return {"status": "NOT_FOUND"}
        agencies = connection.execute("""
            SELECT agency_id, recommendation_status FROM incident_agency_recommendations
            WHERE incident_id=%s ORDER BY agency_id
        """, (incident_id,)).fetchall()
        notifications = connection.execute("""
            SELECT id, agency_id, user_id, (read_at IS NOT NULL) AS is_read
            FROM notifications WHERE incidents_id=%s ORDER BY id LIMIT 100
        """, (incident_id,)).fetchall()
    return {"status": "READ", "incident": row, "agencies": agencies,
            "notifications": notifications, "notification_limit": 100}


def read_redis(incident_id, notification_ids):
    import redis
    with redis.Redis.from_url(os.environ["OCTV_REDIS_URL"], decode_responses=True,
                             socket_connect_timeout=3, socket_timeout=3) as client:
        return {
            "status": "READ",
            "analysis_lock_ttl": client.ttl(f"octv:analysis:incident:{incident_id}"),
            "notifications": [{
                "id": nid,
                "lock_ttl": client.ttl(f"octv:push:lock:v1:{nid}"),
                **summarize_push(client.get(f"octv:push:state:v1:{nid}")),
            } for nid in notification_ids],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incident-id", type=int)
    args = parser.parse_args()
    if args.incident_id is not None and not 0 < args.incident_id <= 9223372036854775807:
        parser.error("incident-id는 양의 DB 정수 ID여야 합니다.")
    try:
        output = check_settings()
    except Exception:
        print(json.dumps({"status": "SETTINGS_OR_DEPENDENCY_UNAVAILABLE"}))
        return 1
    failed = output["runtime"]["status"] != "VALID"
    if args.incident_id is not None:
        output["mode"] = "READ_ONLY_INCIDENT"
        try:
            output["db"] = read_incident(args.incident_id)
            failed |= output["db"]["status"] != "READ"
        except Exception:
            output["db"] = {"status": "UNAVAILABLE"}
            failed = True
        try:
            ids = [row["id"] for row in output["db"].get("notifications", [])]
            output["redis"] = read_redis(args.incident_id, ids)
        except Exception:
            output["redis"] = {"status": "UNAVAILABLE"}
            failed = True
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
