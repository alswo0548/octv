"""CCTV별 수위 관측소 *지리 후보* 검토 (DB 읽기 전용, API 목록 최대 1회).

실행: .venv\\Scripts\\python -X utf8 -m scripts.check_cctv_water_candidates --cctv-id 3
기상/ITS/실시간 수위/사건 생성/DB 쓰기를 실행하지 않습니다.
Redis에 6시간 이내 공식 관측소 목록 캐시가 있으면 재사용합니다.
관측소와 CCTV가 지리적으로 가까워도 하천 영향 관계는 검증되지 않은 상태입니다.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from math import isfinite

from backend.app.integrations.auto_match_providers import (
    _canonical_station, _read_station_catalog, choose_water_station, distance_m,
)
from scripts import check_context_connections as diag


def build_report(cctv: dict, rows: list, max_km: float = 15.0, limit: int = 5) -> dict:
    """공식 제원 좌표만으로 가장 가까운 관측소 후보를 출력; 위험도 연결은 하지 않음."""
    distances = []
    valid_stations = 0
    for raw in rows:
        station = _canonical_station(raw)
        if station is None:
            continue
        valid_stations += 1
        dist = distance_m(cctv.get('latitude'), cctv.get('longitude'),
                          station['latitude'], station['longitude'])
        if dist is None:
            continue
        distances.append({
            'station_id': station['station_id'],
            'station_name': station['name'],
            'river': station['river'],
            'distance_m': round(dist),
            'within_search_radius': dist <= max_km * 1000,
            'official_thresholds_available': station['thresholds_available'],
            'same_river_or_flood_impact_verified': False,
        })
    distances.sort(key=lambda item: (item['distance_m'], item['station_id']))
    nearby = [item for item in distances if item['within_search_radius']][:limit]
    match = choose_water_station(cctv, rows)
    return {
        'status': ('OFFICIAL_GEO_CANDIDATES_UNVERIFIED' if nearby
                   else 'NO_STATION_WITHIN_SEARCH_RADIUS' if valid_stations
                   else 'STATION_COORDINATES_UNAVAILABLE'),
        'cctv_id': cctv.get('id'),
        'official_coordinate_station_count': valid_stations,
        'search_radius_km': max_km,
        'nearby_candidates': nearby,
        'nearest_station_any_distance': distances[:1],
        'existing_auto_mapping_status': match['status'],
        'water_risk_mapping_confirmed': match['status'] == 'VERIFIED_EXACT_COLOCATION',
        'note': '거리/하천명만으로 CCTV 침수 영향권·관측소 관계를 확정하지 않습니다.',
    }


def inspect(cctv_id: int, key: str, redis_client=None) -> dict:
    if not key:
        return {'status': 'MISSING_WATER_LEVEL_API_KEY'}
    # 기존 읽기 전용 진단에서 사용하던 DB 조회를 그대로 활용합니다.
    cctv = diag.read_cctv(cctv_id)
    rows, source_status = _read_station_catalog(redis_client, key)
    if rows is None:
        return {'status': source_status, 'cctv_id': cctv_id}
    result = build_report(cctv, rows)
    result['catalog_source'] = source_status
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cctv-id', type=int, required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    from backend.app.config import load_environment
    load_environment()
    secrets = [v for k, v in os.environ.items() if v and (
        k.endswith('_KEY') or any(word in k for word in ('PASSWORD', 'SECRET', 'TOKEN'))
        or k == 'DATABASE_URL')]
    diag.SECRETS = diag.secret_variants(secrets)
    # Redis 연결 장애는 DB 및 API를 실패시키지 않습니다. 기존 6시간 캐시 재사용.
    client = None
    try:
        from backend.app.integrations.cctv_mapping import _redis
        client = _redis()
    except Exception:
        pass
    try:
        report = inspect(args.cctv_id, os.getenv('WATER_LEVEL_API_KEY', '').strip(), client)
    except Exception as exc:
        # 예외 메시지에 키/URL 등이 포함될 수 있어 유형만 출력합니다.
        report = {'status': 'LOCAL_DIAGNOSTIC_ERROR', 'error_type': type(exc).__name__}
    print(json.dumps(diag.safe(report), ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
