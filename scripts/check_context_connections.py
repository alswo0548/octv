"""CCTV 한 대의 기상·수위 후보·교통 응답을 각각 한 번만 조회합니다.

DB는 읽기 전용이며 사건·설정·추천·알림을 생성하거나 변경하지 않습니다.
업무 코드·메시지는 인증값을 가린 뒤 표시하며, 공개 필드만 결과로 남깁니다.
요청 URL·전체 응답·예외 원문은 출력하지 않습니다.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from math import isfinite
import os
from pathlib import Path
import sys
from urllib.parse import quote, quote_plus, unquote, unquote_plus

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SECRETS = ()
WATER_FIELDS = {'wlobscd', 'obsnm', 'wlobsnm', 'lat', 'lon', 'wrnwl', 'almwl', 'srswl'}
TRAFFIC_FIELDS = {'eventid', 'eventtype', 'eventdetailtype', 'linkid', 'roadname',
                  'roaddrctype', 'lanesblocktype', 'lanesblocked', 'coordx', 'coordy',
                  'startdate', 'enddate', 'createddate', 'speed', 'traveltime', 'roadrank',
                  'drctype', 'routeno', 'roadno', 'linkno', 'startnodeid', 'endnodeid'}


def secret_variants(values):
    decoded = {v for raw in values for v in (raw, raw.strip()) if v}
    for _ in range(2):
        decoded.update(v for raw in tuple(decoded) for text in (unquote(raw), unquote_plus(raw))
                       for v in (text, text.strip()) if v)
    return tuple({v for text in decoded for v in (text, quote(text, safe=''), quote_plus(text))})


def safe(value):
    """허용 필드에도 인증값이나 URL이 반사되어 있으면 통째로 가립니다."""
    if isinstance(value, dict):
        return {safe(str(k)): safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(v) for v in value]
    if isinstance(value, str):
        decoded = (value, unquote(value), unquote_plus(value))
        if any('://' in text or any(secret in text for secret in SECRETS) for text in decoded):
            return '[REDACTED]'
        return value[:180]
    return None if isinstance(value, float) and not isfinite(value) else value


def structure(value, depth=0):
    if isinstance(value, dict) and depth < 3:
        return {str(k): structure(v, depth + 1) for k, v in list(value.items())[:16]}
    if isinstance(value, list):
        return {'list_count': len(value), 'item_type': type(value[0]).__name__ if value else None}
    return type(value).__name__


def api_status(payload):
    """허용된 업무 코드·메시지만 보존하며 성공 여부는 추정하지 않습니다."""
    if not isinstance(payload, dict):
        return {}
    response = payload.get('response')
    response = response if isinstance(response, dict) else {}
    scopes = (('', payload, ('code', 'message')),
              ('header.', payload.get('header'), ('resultCode', 'resultMsg')),
              ('response.header.', response.get('header'), ('resultCode', 'resultMsg')))
    return {prefix + key: node[key] for prefix, node, keys in scopes if isinstance(node, dict)
            for key in keys if key in node and (node[key] is None or isinstance(node[key], (str, int, float, bool)))}


def records(value, fields):
    if isinstance(value, dict):
        public = {str(k).lower(): v for k, v in value.items() if str(k).lower() in fields
                  and (v is None or isinstance(v, (str, int, float, bool)))}
        if public:
            yield public
        else:
            for item in value.values():
                yield from records(item, fields)
    elif isinstance(value, list):
        for item in value:
            yield from records(item, fields)


def request_once(url, params=None, headers=None):
    """재시도·리다이렉트 없이 HTTPS 요청 한 번만 수행합니다."""
    import httpx
    result = {}
    try:
        if not url.startswith('https://'):
            return {'status': 'HTTPS_REQUIRED'}, None
        with httpx.Client(timeout=12.0, follow_redirects=False) as client:
            response = client.get(url, params=params or {}, headers=headers or {})
        result = {'status': 'HTTP_RESPONSE' if 200 <= response.status_code < 300 else 'HTTP_ERROR',
                  'http_status': response.status_code}
        try:
            payload = response.json()
            result['structure'] = structure(payload)
            result['api_status'] = api_status(payload)
        except ValueError:
            return {**result, 'json_status': 'NON_JSON'}, None
        if not 200 <= response.status_code < 300:
            return {**result, 'status': 'HTTP_ERROR'}, None
        return result, payload
    except Exception as exc:
        kind = 'TIMEOUT' if isinstance(exc, httpx.TimeoutException) else 'REQUEST_ERROR'
        return {**result, 'status': kind, 'error_type': type(exc).__name__}, None


def read_cctv(cctv_id):
    import psycopg
    from psycopg.rows import dict_row
    from backend.app.config import database_connect_kwargs
    with psycopg.connect(**database_connect_kwargs(), row_factory=dict_row) as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        row = connection.execute(
            'SELECT id, external_cctv_id, name, provider, latitude, longitude, region_code '
            'FROM cctvs WHERE id = %s', (cctv_id,),
        ).fetchone()
        connection.rollback()
    if not row or row['provider'] != 'UTIC':
        raise ValueError('CCTV_NOT_FOUND_OR_NOT_UTIC')
    lat, lon = float(row['latitude']), float(row['longitude'])
    if not (isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('INVALID_COORDINATES')
    return {**row, 'latitude': lat, 'longitude': lon}


def check_weather(cctv):
    from ai.config import get_runtime_config
    from backend.app.integrations.weather import parse_rainfall, parse_wind
    from backend.app.integrations.normalization import measurement
    now = datetime.now(timezone.utc)
    query = get_runtime_config()['query_factory']({**cctv, 'cctv_id': cctv['id']}, now)['weather']
    if not query.get('mapped'):
        return {'status': 'NO_MAPPING'}
    result, payload = request_once(query['url'], query['params'], query.get('headers'))
    if payload is not None:
        result['observations'] = {}
        for field, parser, unit in (('rainfall_mm', parse_rainfall, 'mm'), ('wind_speed_mps', parse_wind, 'm/s')):
            try:
                value, at = parser(payload)
                result['observations'][field] = measurement(value, at, 'KMA_ULTRA_NCST', unit, now, query['max_age_sec'])
            except Exception as exc:
                result['observations'][field] = {'status': 'PARSE_ERROR', 'error_type': type(exc).__name__}
    return result


def main():
    global SECRETS
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cctv-id', type=int, required=True)
    parser.add_argument('--skip-weather', action='store_true', help='이미 확인한 기상 API 조회를 건너뜁니다.')
    parser.add_argument('--skip-events', action='store_true', help='이미 확인한 교통 돌발정보 조회를 건너뜁니다.')
    args = parser.parse_args()
    from backend.app.config import load_environment
    load_environment()
    sensitive = [v for k, v in os.environ.items() if v and (
        k.endswith('_KEY') or any(word in k for word in ('PASSWORD', 'SECRET', 'TOKEN')) or k == 'DATABASE_URL')]
    SECRETS = secret_variants(sensitive)
    output = {'mode': 'READ_ONLY_DIAGNOSTIC', 'note': '후보 조회이며 자동 매핑·위험 판단·통제 없음 판정은 수행하지 않습니다.'}
    cctv = None
    try:
        cctv = read_cctv(args.cctv_id)
        output['cctv'] = cctv
        output['weather'] = {'status': 'SKIPPED_BY_OPTION'} if args.skip_weather else check_weather(cctv)
    except Exception as exc:
        output['weather' if cctv else 'cctv'] = {'status': 'ERROR', 'error_type': type(exc).__name__}

    # 수위 관측소 두 곳은 후보 정보만 표시하며 CCTV의 관측소로 확정하지 않습니다.
    key = os.getenv('WATER_LEVEL_API_KEY', '').strip()
    result, payload = request_once(f'https://api.hrfco.go.kr/{quote(key, safe="")}/waterlevel/info.json') if key else ({'status': 'MISSING_KEY'}, None)
    result['mapping_verified'] = False
    result['candidates'] = [r for r in records(payload, WATER_FIELDS) if str(r.get('wlobscd', '')).strip() in ('1101641', '1101645')]
    output['water_level_candidates'] = result

    # 두 ITS 서비스는 각각 한 번만 호출합니다. 빈 결과를 정상 통제 상태로 바꾸지 않습니다.
    key = os.getenv('TRAFFIC_API_KEY', '').strip()
    for name, endpoint in (('traffic_events', 'eventInfo'), ('traffic_links', 'trafficInfo')):
        if endpoint == 'eventInfo' and args.skip_events:
            output[name] = {'status': 'SKIPPED_BY_OPTION', 'mapping_verified': False}
            continue
        if not cctv or not key:
            output[name] = {'status': 'MISSING_CCTV_OR_KEY', 'mapping_verified': False}
            continue
        lat, lon = cctv['latitude'], cctv['longitude']
        params = {'apiKey': key, 'type': 'ex', 'getType': 'json', 'minX': lon - 0.02,
                  'maxX': lon + 0.02, 'minY': lat - 0.02, 'maxY': lat + 0.02}
        if endpoint == 'eventInfo':
            params['eventType'] = 'all'
        else:
            # 소통정보의 공식 방향 조건을 명시합니다. 양방향 후보 조회이며 실제 방향 매핑은 별도입니다.
            params['drcType'] = 'all'
        result, payload = request_once(f'https://openapi.its.go.kr:9443/{endpoint}', params)
        rows = list(records(payload, TRAFFIC_FIELDS))
        output[name] = {**result, 'mapping_verified': False, 'record_count': len(rows), 'records': rows[:8]}
    return output


if __name__ == '__main__':
    try:
        report = main()
    except Exception as exc:
        report = {'status': 'ERROR', 'error_type': type(exc).__name__}
    print(json.dumps(safe(report), ensure_ascii=False, indent=2, default=str))
