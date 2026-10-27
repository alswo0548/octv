"""일반 사건 자동 매핑 진단: 기본 모드는 DB·Redis 읽기 전용.

실행: .venv\\Scripts\\python -X utf8 -m scripts.diagnose_general_incident_mapping --incident-no OCTV_P2_2136_damage
--live: MCP 외부 API를 한 번 조회하며 DB 저장은 하지 않습니다. Redis 짧은 관측 캐시는 갱신될 수 있습니다.
출력에는 인증키, 요청 URL, 관측 원문/수치가 포함되지 않습니다.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

FIELDS = (
    "rainfall_mm", "wind_speed_mps", "water_level_m", "water_risk_level",
    "traffic_nearby_events", "traffic_control", "blocked_lane_count",
    "water_station_mapping", "traffic_link_mapping",
)


def inspect(incident_id: int | None = None, *, incident_no: str | None = None, live: bool = False) -> dict:
    from ai.config import get_runtime_config
    from backend.app.cctvs.repository import get_cctv
    from backend.app.db.session import get_connection
    from backend.app.incidents.repository import find_detail
    from backend.app.integrations import cctv_mapping

    report: dict = {"mode": "LIVE_MCP_READ_ONLY" if live else "LOCAL_READ_ONLY"}
    with get_connection() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        if incident_id is None:
            found = connection.execute(
                "SELECT id FROM incidents WHERE incident_no = %s LIMIT 1", (incident_no,)
            ).fetchone()
            if found is None:
                connection.rollback()
                return {**report, "status": "INCIDENT_NOT_FOUND"}
            incident_id = int(found["id"])
        report["incident_id"] = incident_id
        incident = find_detail(connection, incident_id)
        if incident is None:
            connection.rollback()
            return {**report, "status": "INCIDENT_NOT_FOUND"}
        incident = dict(incident)
        cctv = get_cctv(connection, int(incident["cctv_id"]))
        assessment = connection.execute(
            "SELECT risk_breakdown_json FROM incident_assessments "
            "WHERE incident_id = %s ORDER BY id DESC LIMIT 1", (incident_id,),
        ).fetchone()
        connection.rollback()

    if cctv is None:
        return {**report, "status": "CCTV_NOT_FOUND"}
    cctv = dict(cctv)
    report["cctv_id"] = int(incident["cctv_id"])
    report["monitored"] = bool(cctv.get("is_monitored"))
    report["auto_mapping_enabled"] = cctv_mapping.auto_mapping_enabled()
    cached = cctv_mapping.get_cached_mapping(cctv)
    report["mapping_cache"] = "READY" if cached is not None else "NOT_READY_OR_REDIS_UNAVAILABLE"
    if cached:
        report["mapping"] = {
            "weather": "GRID_READY",
            "water": str((cached.get("water_level") or {}).get("status") or "NO_MAPPING"),
            "water_reason": str((cached.get("water_level") or {}).get("reason") or "")[:70],
            "traffic": str((cached.get("traffic") or {}).get("status") or "NO_MAPPING"),
            "traffic_reason": str((cached.get("traffic") or {}).get("reason") or "")[:70],
        }
    try:
        query = get_runtime_config()["query_factory"](incident, datetime.now(timezone.utc))
        report["prepared_requests"] = {
            "weather": bool(query["weather"].get("mapped")),
            "water": bool(query["water_level"].get("mapped")),
            "nearby_traffic_events": bool(query["traffic_nearby_events"].get("mapped")),
            "traffic_verified_fields": sorted(
                name for name, spec in query["traffic"].items()
                if isinstance(spec, dict) and spec.get("mapped") is True
            ),
        }
    except Exception as exc:
        report["prepared_requests"] = {"error_type": type(exc).__name__}

    snapshot = (assessment or {}).get("risk_breakdown_json") or {}
    snapshot = snapshot.get("context_snapshot") if isinstance(snapshot, dict) else None
    report["saved_context"] = (
        {"status": "FOUND", "measurements": {
            key: str((snapshot.get("measurements", {}).get(key) or {}).get("status") or "NOT_RECORDED")
            for key in FIELDS
        }} if isinstance(snapshot, dict) and isinstance(snapshot.get("measurements"), dict)
        else {"status": "NOT_RECORDED"}
    )
    if live:
        import asyncio
        try:
            from ai.mcp.client import collect_via_mcp
            data = asyncio.run(collect_via_mcp(incident_id))
            report["live_mcp"] = {
                "status": "CONTEXT_RECEIVED",
                "measurements": {key: str(data.measurements.get(key, {}).get("status") or "NOT_RECORDED")
                                 for key in FIELDS},
            }
        except Exception as exc:
            report["live_mcp"] = {"status": "FAILED", "error_type": type(exc).__name__}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--incident-id", type=int)
    group.add_argument("--incident-no", type=str)
    parser.add_argument("--live", action="store_true", help="MCP 외부 API 한 번 조회 (DB 저장 없음)")
    args = parser.parse_args()
    from backend.app.config import load_environment
    load_environment()
    logging.disable(logging.CRITICAL)
    try:
        if args.incident_id is not None and args.incident_id < 1:
            raise ValueError("invalid ID")
        if args.incident_no is not None and (not args.incident_no.strip() or len(args.incident_no) > 80):
            raise ValueError("invalid incident number")
        report = inspect(args.incident_id, incident_no=args.incident_no, live=args.live)
    except Exception as exc:
        report = {"status": "LOCAL_CHECK_ERROR", "error_type": type(exc).__name__}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
