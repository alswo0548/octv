"""OCTV의 Worker 실행 전 설정과 Redis 연결을 읽기 전용으로 점검합니다.

실행: python scripts/check_runtime_connections.py

1. 현재 CMD 설정과 backend/.env를 읽은 뒤의 설정 상태를 구분합니다.
2. Worker와 같은 get_runtime_config() 호출로 JSON 설정을 확인합니다.
3. 기존 알림 Repository의 Redis 연결 함수로 PING과 지정 큐의 건수만 읽습니다.

Worker/Beat/Task는 시작하지 않습니다. DB·외부 API·FCM은 호출하지 않습니다.
.env와 기존 CMD는 변경하지 않으며, 설정은 이 Python 프로세스에서만 로딩합니다.
URL·비밀키·작업 본문·오류 원문은 출력하지 않습니다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def environment_status() -> dict:
    """실제 값 대신 설정 여부와 0/1 스위치의 상태만 반환합니다."""
    def switch(name: str) -> str:
        value = os.environ.get(name)
        if value is None:
            return "MISSING"
        if value == "1":
            return "ON"
        if value == "0":
            return "OFF"
        return "INVALID"

    return {
        "redis_url_configured": bool(os.environ.get("OCTV_REDIS_URL", "").strip()),
        "runtime_path_in_process": bool(os.environ.get("OCTV_RUNTIME_CONFIG", "").strip()),
        "decision_switch": switch("OCTV_DECISION_ENABLED"),
        "push_switch": switch("OCTV_PUSH_ENABLED"),
        "push_recovery_switch": switch("OCTV_PUSH_RECOVERY_ENABLED"),
    }


def queue_counts(client) -> dict:
    """현재 OCTV의 기본 Redis transport에 맞춰 건수만 조회합니다."""
    # 현재 workers.py는 visibility_timeout만 설정합니다. 큐 접두사 재정의는 없습니다.
    # Channel 인스턴스는 만들지 않고 설치된 Kombu의 기본 키 규칙만 읽습니다.
    from kombu.transport.redis import Channel

    steps = tuple(Channel.priority_steps)
    prefix = Channel.global_keyprefix
    separator = Channel.sep
    queues = ("analysis", "notifications", "celery")
    if not steps or 0 not in steps or any(type(step) is not int or step < 0 for step in steps):
        raise ValueError("UNSUPPORTED_PRIORITY_STEPS")
    if not isinstance(prefix, str) or not isinstance(separator, str):
        raise ValueError("UNSUPPORTED_QUEUE_KEY_CONFIG")

    # transaction=False: MULTI/EXEC 없이 조회 명령만 한 번에 보냅니다.
    with client.pipeline(transaction=False) as pipe:
        for queue in queues:
            for priority in steps:
                key = prefix + queue
                if priority:
                    key += separator + str(priority)
                pipe.llen(key)
        pipe.hlen(prefix + Channel.unacked_key)
        pipe.zcard(prefix + Channel.unacked_index_key)
        counts = pipe.execute()

    if len(counts) != len(queues) * len(steps) + 2:
        raise ValueError("UNEXPECTED_QUEUE_COUNT_RESPONSE")
    width = len(steps)
    return {
        "status": "OK",
        "ready": {
            queue: sum(counts[index * width:(index + 1) * width])
            for index, queue in enumerate(queues)
        },
        # 이 두 숫자는 선택한 Redis DB 공용 기록이며, 현재 실행 중 작업 수가 아닙니다.
        "unacked_hash_entries": counts[-2],
        "unacked_index_entries": counts[-1],
    }


def main() -> int:
    report = {"current_cmd": environment_status()}
    if not (ROOT / "backend" / "app" / "workers.py").is_file():
        report["project"] = "PROJECT_ROOT_NOT_FOUND"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    sys.path.insert(0, str(ROOT))

    try:
        from dotenv import load_dotenv

        # 기존 API의 backend .env 로딩처럼, 이미 있는 프로세스 환경변수가 우선합니다.
        backend_env = ROOT / "backend" / ".env"
        report["backend_env_file_exists"] = backend_env.is_file()
        load_dotenv(dotenv_path=backend_env, override=False)
        report["with_backend_env"] = environment_status()
    except Exception as exc:
        report["settings"] = {"status": "FAILED", "error_type": type(exc).__name__}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    ok = True
    try:
        from ai.config import get_runtime_config

        # --config를 직접 주지 않아도 Worker가 실행 설정을 찾는지 확인합니다.
        config = get_runtime_config()
        report["worker_runtime_config"] = {
            "status": "OK",
            "context_transport": config["context_transport"],
            "route_key_configured": bool(config["route_api_key"]),
        }
    except Exception as exc:
        ok = False
        report["worker_runtime_config"] = {
            "status": "NOT_READY", "error_type": type(exc).__name__,
        }

    try:
        from backend.app.notifications.repository import _redis_client

        # 기존 프로젝트의 URL 처리와 3초 연결/응답 제한을 그대로 사용합니다.
        with _redis_client() as client:
            connected = client.ping() is True
            report["python_redis_ping"] = "OK" if connected else "FAILED"
            if not connected:
                ok = False
            else:
                try:
                    report["queue_counts"] = queue_counts(client)
                except Exception as exc:
                    ok = False
                    report["queue_counts"] = {
                        "status": "FAILED", "error_type": type(exc).__name__,
                    }
    except Exception as exc:
        ok = False
        report["python_redis_ping"] = {
            "status": "FAILED", "error_type": type(exc).__name__,
        }

    report["worker_started_by_this_check"] = False
    report["analysis_or_push_executed_by_this_check"] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
