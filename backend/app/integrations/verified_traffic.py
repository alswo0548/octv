"""Operator-reviewed directed ITS links; speed is context only, never a Rule grade."""
from datetime import datetime, timedelta, timezone
from math import isfinite
import json

from .auto_match_providers import ITS_TRAFFIC_URL, _traffic_records, _field, _safe_get_json
from .normalization import measurement


def reviewed_query(incident, review, now, environment):
    off = {'mapped': False, 'now': now}
    if str(environment.get('OCTV_VERIFIED_TRAFFIC_ENABLED', '0')) != '1':
        return off
    try:
        if not isinstance(review, dict) or review.get('road_direction_verified') is not True:
            return off
        if any(not str(review.get(k) or '').strip() for k in
               ('reviewed_by', 'evidence', 'direction', 'reviewed_at')):
            return off
        reviewed_at = datetime.fromisoformat(review['reviewed_at'])
        if reviewed_at.tzinfo is None or reviewed_at > now:
            return off
        link = str(review['link_id'])
        if not (link.isascii() and link.isdecimal() and 5 <= len(link) <= 15):
            return off
        lat, lon = float(incident['latitude']), float(incident['longitude'])
        if not all(map(isfinite, (lat, lon))) or not (-90 < lat < 90 and -180 <= lon <= 180):
            return off
        if not all(isfinite(float(review[k])) for k in ('latitude', 'longitude')):
            return off
        # Camera identity/location changes require a fresh operator review.
        if (int(review['cctv_id']) != int(incident['cctv_id'])
                or abs(float(review['latitude']) - lat) > 1e-7
                or abs(float(review['longitude']) - lon) > 1e-7
                or str(review['provider']) != str(incident.get('provider', 'UTIC'))
                or str(review['camera_name']) != str(incident.get('cctv_name') or incident.get('name') or '')):
            return off
        key = str(environment.get('TRAFFIC_API_KEY', '')).strip()
        if not key:
            return off
        return {'mapped': True, 'now': now, 'link_id': link, 'latitude': lat,
                'longitude': lon, 'api_key': key}
    except (KeyError, TypeError, ValueError, OverflowError):
        return off


def fetch_speed(query):
    now = query['now']
    empty = {'value': None, 'observed_at': None, 'source': 'ITS_REVIEWED_LINK',
             'unit': 'km/h', 'status': 'NO_MAPPING'}
    if not query.get('mapped'):
        return empty
    link = query['link_id']
    cache_key = f'octv:context:its:reviewed_speed:v1:{link}'
    try:
        from .cctv_mapping import _redis
        client = _redis()
        cached = json.loads(client.get(cache_key) or 'null')
    except Exception:
        client, cached = None, None
    try:
        if not isinstance(cached, dict):
            lat, lon = query['latitude'], query['longitude']
            payload = _safe_get_json(ITS_TRAFFIC_URL, {
                'apiKey': query['api_key'], 'type': 'all', 'drcType': 'all', 'getType': 'json',
                'minX': lon - .015, 'maxX': lon + .015,
                'minY': lat - .015, 'maxY': lat + .015,
            })
            rows = _traffic_records(payload)
            if rows is None:
                return {**empty, 'status': 'ERROR'}
            matches = [r for r in rows if isinstance(r, dict)
                       and str(_field(r, 'linkid', 'roadsectionid')) == link]
            if len(matches) != 1:
                return {**empty, 'status': 'NO_DATA' if not matches else 'INVALID'}
            row = matches[0]
            value = float(_field(row, 'speed'))
            at = datetime.strptime(str(_field(row, 'createddate')), '%Y%m%d%H%M%S').replace(
                tzinfo=timezone(timedelta(hours=9)))
            cached = {'value': value, 'observed_at': at.isoformat()}
        value, at = float(cached['value']), datetime.fromisoformat(cached['observed_at'])
        result = measurement(value, at, empty['source'], 'km/h', now, 600)
        if result['status'] == 'OK' and client is not None:
            try:
                # Do not extend cache TTL on reads.
                client.set(cache_key, json.dumps(cached), ex=60, nx=True)
            except Exception:
                pass
        return {**result, 'link_id': link, 'road_direction_verified': True,
                'rule_eligible': False}
    except (ValueError, KeyError, TypeError, OverflowError):
        return {**empty, 'status': 'INVALID'}
