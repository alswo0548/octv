"""공식 수위관측소 지리 후보의 하천명 교차 확인 (읽기 전용 진단).

실행: .venv\\Scripts\\python -X utf8 -m scripts.check_cctv_station_rivers --cctv-id 3
HRFCO 목록은 기존 6시간 Redis 캐시 재사용. 공식 국가가뭄정보포털 지도 API는 최대 1회 호출.
DB 조회 전용. 기상/ITS/수위실측/MCP/사건화/위험 판단은 실행하지 않음.
중요: 하천명 확인은 CCTV 침수 영향권 확정이 아닙니다.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from hashlib import sha256

import httpx

from backend.app.integrations.auto_match_providers import (
    _canonical_station, _name_key, _read_station_catalog, distance_m,
    _parse_station_coordinate,
)
from scripts.check_cctv_water_candidates import build_report
from scripts import check_context_connections as diag

# 공식 국가가뭄정보포털: 공개 수위관측소 GIS 레이어. HRFCO와 소속/대상 범위가
# 다를 수 있으며, 반환 기록이 없다면 미확인으로 처리합니다.
GIS_RIVER_QUERY_URL = (
    'https://www.drought.go.kr/droughtmap/rest/services/'
    'DROUGHTWEATHERFACILITY/MapServer/10/query'
)


def fetch_official_river_metadata(station_ids: list[str], redis_client=None) -> dict:
    """숫자로 검증한 관측소 ID 목록으로 공개 GIS 한 번 조회. 원문 응답 미출력."""
    ids = sorted({str(i) for i in station_ids
                  if str(i).isascii() and str(i).isdigit() and 5 <= len(str(i)) <= 12})[:5]
    if not ids:
        return {'status': 'NO_CANDIDATE_IDS', 'rows': []}
    digest = sha256(','.join(ids).encode('ascii')).hexdigest()
    cache_key = 'octv:context:official_gis:rivers:v1:' + digest
    if redis_client is not None:
        try:
            cached = json.loads(redis_client.get(cache_key) or 'null')
            if (isinstance(cached, dict) and cached.get('status') == 'OFFICIAL_GIS_RESPONSE_RECEIVED'
                    and isinstance(cached.get('rows'), list) and len(cached['rows']) <= 50):
                return {**cached, 'metadata_catalog_source': 'GIS_CACHED'}
        except (TypeError, ValueError, OSError):
            pass
        except Exception:
            pass  # Redis 연결 장애 시 진단은 직접 조회 가능
    params = {
        'where': f'WLOBSCD IN ({",".join(ids)})',
        'outFields': 'WLOBSCD,OBSNM,RIVNM,LAT,LON',
        'returnGeometry': 'false',
        'f': 'json',
    }
    try:
        with httpx.Client(timeout=7.0, follow_redirects=False) as client:
            response = client.get(GIS_RIVER_QUERY_URL, params=params)
        if response.status_code != 200 or len(response.content) > 500_000:
            return {'status': 'OFFICIAL_GIS_HTTP_UNAVAILABLE', 'rows': [],
                    'http_status': response.status_code}
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError, OSError):
        return {'status': 'OFFICIAL_GIS_REQUEST_FAILED', 'rows': []}
    if not isinstance(payload, dict) or isinstance(payload.get('error'), dict):
        return {'status': 'OFFICIAL_GIS_SCHEMA_OR_PROVIDER_ERROR', 'rows': []}
    features = payload.get('features')
    if not isinstance(features, list) or len(features) > 50:
        return {'status': 'OFFICIAL_GIS_SCHEMA_OR_PROVIDER_ERROR', 'rows': []}
    rows = []
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get('attributes'), dict):
            continue
        a = feature['attributes']
        code = str(a.get('WLOBSCD') or '').strip()
        if code not in ids:
            continue
        rows.append({
            'station_id': code,
            'station_name': str(a.get('OBSNM') or '').strip()[:70],
            'river': str(a.get('RIVNM') or '').strip()[:70],
            'latitude': _parse_station_coordinate(a.get('LAT'), latitude=True),
            'longitude': _parse_station_coordinate(a.get('LON'), latitude=False),
        })
    result = {'status': 'OFFICIAL_GIS_RESPONSE_RECEIVED', 'rows': rows}
    if redis_client is not None:
        try:
            redis_client.set(cache_key, json.dumps(result, ensure_ascii=False), ex=86400 if rows else 3600)
        except Exception:
            pass
    return {**result, 'metadata_catalog_source': 'GIS_FRESH'}


def add_river_evidence(geo_report: dict, station_rows: list,
                       official_meta: dict) -> dict:
    """관측소 동일성을 세 가지(코드/이름/좌표)로 확인한 뒤 하천명만 표기."""
    output = {**geo_report}
    candidates = [dict(item) for item in geo_report.get('nearby_candidates', [])]
    output['nearby_candidates'] = candidates
    output['river_metadata_source'] = 'NATIONAL_DROUGHT_PORTAL_OFFICIAL_GIS'
    output['river_metadata_status'] = official_meta['status']
    output['river_metadata_catalog_source'] = official_meta.get('metadata_catalog_source', 'GIS_UNAVAILABLE')
    output['water_risk_mapping_confirmed'] = False
    output['cctv_flood_impact_verified'] = False
    output['note'] = ('관측소 코드·이름·좌표가 일치하면 하천명만 확인합니다. '
                      '하천명/거리만으로 CCTV 침수 영향권 또는 위험도를 판단하지 않습니다.')
    by_id = {}
    for raw in station_rows:
        parsed = _canonical_station(raw)
        if parsed is not None:
            by_id[parsed['station_id']] = parsed
    gis_by_id = {}
    for row in official_meta.get('rows', []):
        if isinstance(row, dict):
            gis_by_id.setdefault(row.get('station_id'), []).append(row)
    matches = 0
    for candidate in candidates:
        candidate['confirmed_river_name'] = None
        candidate['river_name_evidence'] = 'NOT_VERIFIED'
        candidate['same_river_or_flood_impact_verified'] = False
        if official_meta['status'] != 'OFFICIAL_GIS_RESPONSE_RECEIVED':
            candidate['river_name_evidence'] = 'PROVIDER_UNAVAILABLE'
            continue
        station = by_id.get(candidate['station_id'])
        features = gis_by_id.get(candidate['station_id'], [])
        if not features:
            candidate['river_name_evidence'] = 'NOT_IN_SECONDARY_OFFICIAL_CATALOG'
            continue
        if len(features) != 1:
            candidate['river_name_evidence'] = 'DUPLICATE_OFFICIAL_RECORDS'
            continue
        feature = features[0]
        if station is None or not feature['river']:
            candidate['river_name_evidence'] = 'IDENTITY_OR_RIVER_MISSING'
            continue
        if not _name_key(station['name']) or _name_key(station['name']) != _name_key(feature['station_name']):
            candidate['river_name_evidence'] = 'STATION_NAME_MISMATCH'
            continue
        separation_m = distance_m(station['latitude'], station['longitude'],
                                  feature['latitude'], feature['longitude'])
        if separation_m is None or separation_m > 500:
            candidate['river_name_evidence'] = 'STATION_COORDINATE_MISMATCH'
            continue
        candidate['confirmed_river_name'] = feature['river']
        candidate['river_name_evidence'] = 'OFFICIAL_ID_NAME_COORDINATES_MATCH'
        matches += 1
    output['river_names_verified_count'] = matches
    return output


def inspect(cctv_id: int, water_api_key: str, redis_client=None) -> dict:
    """DB는 SELECT만, 외부기관은 HRFCO 목록 0~1회 + GIS 1회만 조회."""
    if not water_api_key:
        return {'status': 'MISSING_WATER_LEVEL_API_KEY', 'cctv_id': cctv_id}
    cctv = diag.read_cctv(cctv_id)
    catalog, catalog_status = _read_station_catalog(redis_client, water_api_key)
    if catalog is None:
        return {'status': catalog_status, 'cctv_id': cctv_id}
    report = build_report(cctv, catalog)
    report['catalog_source'] = catalog_status
    ids = [c['station_id'] for c in report.get('nearby_candidates', [])]
    official = fetch_official_river_metadata(ids, redis_client)
    return add_river_evidence(report, catalog, official)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cctv-id', type=int, required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    from backend.app.config import load_environment
    load_environment()
    secret_values = [v for k, v in os.environ.items() if v and (
        k.endswith('_KEY') or any(w in k for w in ('PASSWORD', 'SECRET', 'TOKEN'))
        or k == 'DATABASE_URL')]
    diag.SECRETS = diag.secret_variants(secret_values)
    redis_client = None
    try:
        from backend.app.integrations.cctv_mapping import _redis
        redis_client = _redis()
    except Exception:
        pass
    try:
        result = inspect(args.cctv_id, os.getenv('WATER_LEVEL_API_KEY', '').strip(), redis_client)
    except Exception as exc:
        # HTTP 요청의 예외 원문에 인증키가 포함될 수 있으므로 종류만 출력.
        result = {'status': 'LOCAL_DIAGNOSTIC_ERROR', 'error_type': type(exc).__name__}
    print(json.dumps(diag.safe(result), ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
