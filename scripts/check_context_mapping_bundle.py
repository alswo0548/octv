"""수위·교통 자동 매핑과 MCP Context를 한 번에 확인 (원본 DB 읽기 전용).

사용 예:
  .venv\\Scripts\\python -X utf8 -m scripts.check_context_mapping_bundle --cctv-id 3
  .venv\\Scripts\\python -X utf8 -m scripts.check_context_mapping_bundle --cctv-id 3 --incident-id 123

첫 실행: 감시 중 CCTV에 한해 기존 Celery prewarm 기능을 재사용해 Redis 후보
캐시가 준비됐는지 확인. 외부 제공기관은 기존 캐시를 우선 재사용합니다.
--incident-id를 준 경우만 실제 MCP 도구를 호출합니다(분석 DB 저장 없음).
개인 키·API URL·원시 응답은 출력하지 않습니다.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging


def _load_cctv(cctv_id: int):
    from backend.app.cctvs.repository import get_cctv
    from backend.app.db.session import get_connection
    with get_connection() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        row = get_cctv(connection, cctv_id)
        connection.rollback()
    return dict(row) if row else None


def _incident_for(incident_id: int):
    from backend.app.incidents.repository import find_detail
    from backend.app.db.session import get_connection
    with get_connection() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        incident = find_detail(connection, incident_id)
        connection.rollback()
    return dict(incident) if incident else None


def inspect(cctv_id: int, incident_id: int | None = None) -> dict:
    from ai.config import get_runtime_config
    from backend.app.integrations import cctv_mapping as cm

    report = {"mode": "READ_ONLY_OR_CACHE_PREWARM",
              "cctv_id": cctv_id,
              "warning": "주변 관측소·ITS 도로 후보는 CCTV 침수/통제 확정 증거가 아닙니다."}
    row = _load_cctv(cctv_id)
    if not row:
        return {**report, "status": "CCTV_NOT_FOUND"}
    report["monitored"] = bool(row.get("is_monitored"))
    report["auto_mapping_enabled"] = cm.auto_mapping_enabled()
    # DB는 SELECT 전용, Redis 매핑 캐시 외에는 쓰지 않습니다.
    report["prewarm"] = cm.prepare_monitored_cctv(cctv_id)
    cache = cm.get_cached_mapping(row)
    if cache is None:
        report["mapping_cache"] = "NOT_READY_OR_REDIS_UNAVAILABLE"
    else:
        report["mapping_cache"] = "READY"
    query_input = {**row, "cctv_id": cctv_id, "cctv_name": row.get("name")}
    refs = cm.mapping_reference_for(query_input)
    report["mapping_references"] = refs
    try:
        config = get_runtime_config()
        query = config["query_factory"](query_input, datetime.now(timezone.utc))
        report["prepared_requests"] = {
            "weather": "MAPPED" if query["weather"].get("mapped") else "NO_MAPPING",
            "water": "MAPPED" if query["water_level"].get("mapped") else "NO_MAPPING",
            "traffic_nearby_events": (
                "ENABLED_NEAR_CCTV" if query.get("traffic_nearby_events", {}).get("mapped")
                else "NO_MAPPING"
            ),
            "traffic_verified_fields": sorted(
                field for field, value in query["traffic"].items()
                if isinstance(value, dict) and value.get("mapped") is True
            ),
        }
    except Exception as error:
        # 예외 본문은 요청 URL/인증값을 포함할 수 있어 기록하지 않습니다.
        report["prepared_requests"] = {"status": "CONFIG_OR_QUERY_ERROR",
                                       "error_type": type(error).__name__}

    if incident_id is None:
        report["mcp"] = "SKIPPED_NO_INCIDENT_ID"
        return report
    incident = _incident_for(incident_id)
    if incident is None or incident.get("cctv_id") != cctv_id:
        report["mcp"] = "INCIDENT_NOT_FOUND_OR_WRONG_CCTV"
        return report
    try:
        from ai.mcp.client import collect_via_mcp
        context = asyncio.run(collect_via_mcp(incident_id))
        fields = (
            "water_level_m", "water_risk_level", "traffic_level",
            "traffic_volume_level", "traffic_control", "blocked_lane_count",
            "water_station_mapping", "traffic_link_mapping",
            "traffic_nearby_events",
        )
        report["mcp"] = {
            "status": "CONTEXT_RECEIVED",
            "incident_id": context.incident_id,
            "measurement_statuses": {
                key: context.measurements.get(key, {}).get("status", "NOT_PRESENT")
                for key in fields
            },
        }
    except Exception as error:
        report["mcp"] = {"status": "CONTEXT_FAILED", "error_type": type(error).__name__}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cctv-id", type=int, required=True)
    parser.add_argument("--incident-id", type=int)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    from backend.app.config import load_environment
    load_environment()
    try:
        result = inspect(args.cctv_id, args.incident_id)
    except Exception as error:
        result = {"status": "LOCAL_CHECK_ERROR", "error_type": type(error).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
