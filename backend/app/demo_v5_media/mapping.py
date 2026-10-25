"""v5-only Demo mapping preparation. Never writes to OCTV's SQL tables.

Explicitly scoped to the three approved DEMO identities. Existing start,
incident, temporal, detection, rules and notification code are untouched.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.app.db.session import get_connection
from backend.app.integrations.cctv_mapping import (
    auto_mapping_enabled, get_cached_mapping, prepare_cached_mapping,
)

DEMO_IDENTIFIERS = ('DEMO-N001', 'DEMO-N002', 'DEMO-N003')
WATER_READY = frozenset({
    'VERIFIED_EXACT_COLOCATION', 'NEARBY_STATION_WITH_THRESHOLDS',
    'NEARBY_STATION_NO_THRESHOLDS',
})


def _demo_cameras() -> list[dict]:
    with get_connection() as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        rows = conn.execute('''
            SELECT id, provider, external_cctv_id, name, address,
                   latitude, longitude, region_code
            FROM cctvs
            WHERE provider='DEMO' AND external_cctv_id = ANY(%s)
            ORDER BY external_cctv_id
        ''', (list(DEMO_IDENTIFIERS),)).fetchall()
    # No arbitrary CCTV ID can be used to trigger external requests.
    result = [dict(row) for row in rows]
    if sorted(row['external_cctv_id'] for row in result) != list(DEMO_IDENTIFIERS):
        raise ValueError('승인 Demo CCTV 3대가 DB에 모두 등록되어 있어야 합니다.')
    return result


def _one_status(cctv: dict, preparation: str | None = None) -> dict:
    cached = get_cached_mapping(cctv)
    water = cached.get('water_level', {}) if cached else {}
    traffic = cached.get('traffic', {}) if cached else {}
    water_status = str(water.get('status') or 'CACHE_NOT_READY')
    traffic_status = str(traffic.get('status') or 'CACHE_NOT_READY')
    return {
        'external_cctv_id': cctv['external_cctv_id'],
        'cache_ready': cached is not None,
        'preparation': preparation,
        'weather_grid_ready': cached is not None,
        'water_status': water_status,
        'water_reason': str(water.get('reason') or water_status)[:80],
        'water_mapped': water_status in WATER_READY,
        # A traffic link without verified CCTV direction must not affect Rule.
        'traffic_status': traffic_status,
        'traffic_reason': str(traffic.get('reason') or traffic_status)[:80],
        'traffic_rule_mapped': False,
    }


def mapping_status() -> dict:
    cameras = _demo_cameras()
    return {
        'auto_mapping_enabled': auto_mapping_enabled(),
        'items': [_one_status(camera) for camera in cameras],
    }


def prepare_mapping() -> dict:
    cameras = _demo_cameras()
    if not auto_mapping_enabled():
        return {'auto_mapping_enabled': False,
                'items': [_one_status(camera, 'DISABLED') for camera in cameras]}
    # Run independently, not one network timeout per CCTV in series.
    # prepare_cached_mapping only writes a bounded Redis cache; SQL is read-only.
    with ThreadPoolExecutor(max_workers=3) as pool:
        preparations = list(pool.map(prepare_cached_mapping, cameras))
    return {
        'auto_mapping_enabled': True,
        'items': [_one_status(camera, state)
                  for camera, state in zip(cameras, preparations, strict=True)],
    }
