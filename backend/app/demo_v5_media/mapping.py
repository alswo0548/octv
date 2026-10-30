"""v5-only Demo mapping preparation. Never writes to OCTV's SQL tables.

Explicitly scoped to the three approved DEMO identities. Existing start,
incident, temporal, detection, rules and notification code are untouched.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.app.db.session import get_connection
from backend.app.integrations.cctv_mapping import (
    auto_mapping_enabled, get_cached_mapping, kma_grid, prepare_cached_mapping,
)
from .scenario_risk import _SCENARIOS

DEMO_IDENTIFIERS = ('DEMO-N001', 'DEMO-N002', 'DEMO-N003')
WATER_READY = frozenset({
    'VERIFIED_EXACT_COLOCATION', 'NEARBY_STATION_WITH_THRESHOLDS',
    'NEARBY_STATION_NO_THRESHOLDS',
})

# Presentation-only water levels. These are NOT measurements, official station
# matches, official thresholds, or inputs to real-world LangGraph risk rules.
_EXAMPLE_WATER_LEVEL_M = {
    'DEMO-N001': 2.4,
    'DEMO-N002': 0.9,
    'DEMO-N003': 0.6,
}


def demo_preview_for_camera(identifier: str, latitude, longitude) -> dict | None:
    """Explicitly simulated mapping for the three approved DEMO scenarios.

    Weather grid coordinates are calculated from the registered CCTV location;
    every rainfall/water/traffic number is an illustrative scenario value.
    Never create fictitious official station IDs or road link identifiers.
    """
    if identifier not in DEMO_IDENTIFIERS or identifier not in _SCENARIOS:
        return None
    try:
        nx, ny = kma_grid(latitude, longitude)
        if not 1 <= nx <= 149 or not 1 <= ny <= 253:
            return None
    except (ValueError, TypeError, OverflowError):
        return None
    scenario = _SCENARIOS[identifier]
    return {
        'source': 'DEMO_SIMULATION',
        'label': '시연용 가상 매핑 · 실제 관측값/도로 통제 정보 아님',
        'external_cctv_id': identifier,
        'weather_grid': {'nx': nx, 'ny': ny},
        'rainfall_mm': scenario.get('rainfall_mm', 0.0),
        'water_level_m': _EXAMPLE_WATER_LEVEL_M[identifier],
        'water_risk_level': scenario.get('water_risk_level', 'NORMAL'),
        'blocked_lane_count': scenario.get('blocked_lane_count', 0),
    }


def demo_preview_for_incident(incident: dict) -> dict | None:
    """Display only for a DB-assessed, explicitly simulated DEMO incident."""
    if incident.get('provider') != 'DEMO':
        return None
    risk = incident.get('risk_breakdown_json')
    if not isinstance(risk, dict):
        return None
    demo = risk.get('demo_simulation')
    if (not isinstance(demo, dict)
            or demo.get('enabled') is not True
            or demo.get('score_source') != 'DEMO_SIMULATION'):
        return None
    identifier = demo.get('external_cctv_id')
    if identifier not in DEMO_IDENTIFIERS:
        return None
    return demo_preview_for_camera(identifier,
                                   incident.get('latitude'),
                                   incident.get('longitude'))


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
    real_water_status = str(water.get('status') or 'CACHE_NOT_READY')
    real_traffic_status = str(traffic.get('status') or 'CACHE_NOT_READY')
    identifier = cctv['external_cctv_id']
    demo = (
        demo_preview_for_camera(identifier, cctv['latitude'], cctv['longitude'])
        if auto_mapping_enabled() else None
    )
    # Show a safe fallback even when Redis has no prepared mapping. The
    # simulated preview is a separate field and never becomes a real match.
    water_official = real_water_status in WATER_READY
    return {
        'external_cctv_id': identifier,
        'cache_ready': cached is not None,
        'preparation': preparation,
        'weather_grid_ready': (cached is not None or demo is not None),
        'weather_grid': (cached.get('weather_grid') if cached else
                         demo['weather_grid'] if demo else None),
        'water_status': (real_water_status if water_official else
                         'DEMO_SIMULATION' if demo else real_water_status),
        'water_reason': str(water.get('reason') or real_water_status)[:80],
        'water_mapped': water_official,
        'traffic_status': ('DEMO_SIMULATION' if demo else real_traffic_status),
        'traffic_reason': str(traffic.get('reason') or real_traffic_status)[:80],
        'traffic_rule_mapped': False,
        'demo_mapping': demo,
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
