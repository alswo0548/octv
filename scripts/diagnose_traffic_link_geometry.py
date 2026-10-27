"""일반 사건 CCTV 반경 250m ITS 도로 형상/링크 ID 일치 여부 (읽기 전용).

실행: .venv\\Scripts\\python -X utf8 -m scripts.diagnose_traffic_link_geometry --incident-id 2136
DB/Redis 변경 없음. ITS 승인 키는 출력하거나 저장하지 않습니다.
별도 공개 공간참고자료(2024-12)의 링크 위치는 CCTV 촬영 방향 및 통제 사실을 입증하지 않습니다.
"""
from __future__ import annotations

import argparse
import json
import os


def diagnose(incident_id: int):
    from backend.app.cctvs.repository import get_cctv
    from backend.app.db.session import get_connection
    from backend.app.incidents.repository import find_detail
    from backend.app.integrations import auto_match_providers as provider
    from backend.app.integrations.traffic_geometry_probe import (
        query_spatial_link_candidates, compare_with_its)
    report = {"mode": "ROAD_LINK_SPATIAL_READ_ONLY", "incident_id": incident_id}
    with get_connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        incident = find_detail(conn, incident_id)
        if incident is None:
            conn.rollback()
            return {**report, "status": "INCIDENT_NOT_FOUND"}
        cctv = get_cctv(conn, int(incident["cctv_id"]))
        conn.rollback()
    if not cctv:
        return {**report, "status": "CCTV_NOT_FOUND"}
    report["cctv_id"] = int(cctv["id"])
    source = query_spatial_link_candidates(cctv["latitude"], cctv["longitude"])
    report["spatial"] = {key: value for key, value in source.items() if key != "links"}
    key = os.getenv("TRAFFIC_API_KEY", "")
    if not key:
        report["link_comparison"] = {"status": "ITS_KEY_MISSING", "camera_direction_verified": False}
        return report
    lat, lon = float(cctv["latitude"]), float(cctv["longitude"])
    payload = provider._safe_get_json(provider.ITS_TRAFFIC_URL, {
        "apiKey": key, "type": "all", "drcType": "all", "getType": "json",
        "minX": lon - 0.015, "maxX": lon + 0.015,
        "minY": lat - 0.015, "maxY": lat + 0.015,
    }, timeout_seconds=8.0)
    rows = provider._traffic_records(payload)
    if rows is None:
        report["link_comparison"] = {"status": "ITS_RESPONSE_UNAVAILABLE", "camera_direction_verified": False}
    else:
        report["link_comparison"] = compare_with_its(source, rows)
    return report


def main():
    from backend.app.config import load_environment
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incident-id", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.incident_id <= 0:
            raise ValueError("positive incident ID required")
        print(json.dumps(diagnose(args.incident_id), ensure_ascii=False, indent=2))
    except Exception as e:
        # No secrets or HTTP request details are echoed.
        print(json.dumps({"mode": "ROAD_LINK_SPATIAL_READ_ONLY",
                          "status": "PROBE_FAILED", "error_type": type(e).__name__}))


if __name__ == "__main__":
    main()
