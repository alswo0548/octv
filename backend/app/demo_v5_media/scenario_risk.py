"""Explicitly simulated risk assessment for approved v5 DEMO incidents only.

Original Rule, original real Context, non-DEMO incidents and historical assessments
remain unchanged. Synthetic inputs are never reported as observed API values.
"""
from datetime import datetime, timezone

from ai.contracts import ContextSnapshot
from ai.risk_priority.rules import assess

_SCENARIOS = {
    'DEMO-N001': {'blocked_lane_count': 2, 'water_risk_level': 'WARNING',
                  'rainfall_mm': 30.0, 'traffic_volume_level': 'MEDIUM',
                  'nearby_hospital_distance_m': 250.0},   # 85 / P1
    'DEMO-N002': {'blocked_lane_count': 0, 'water_risk_level': 'NORMAL',
                  'rainfall_mm': 10.0, 'nearby_hospital_distance_m': 300.0},  # 55 / P2
    'DEMO-N003': {'blocked_lane_count': 0, 'rainfall_mm': 0.0,
                  'wind_speed_mps': 0.0, 'nearby_hospital_distance_m': 2000.0,
                  'nearby_school_distance_m': 2000.0},   # 40 / P2
}
_EXPECTED = {'DEMO-N001': 85.0, 'DEMO-N002': 55.0, 'DEMO-N003': 40.0}


def _approved_camera(incident: dict) -> str | None:
    if incident.get('provider') != 'DEMO':
        return None
    if not str(incident.get('dedup_key') or '').startswith('v5:'):
        return None
    # Independent SQL read validates provider AND external identifier;
    # never trust incident.cctv_name or hard-code mutable DB IDs.
    from backend.app.db.session import get_connection
    with get_connection() as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        row = conn.execute("""
            SELECT external_cctv_id FROM cctvs WHERE id=%s AND provider='DEMO'
              AND external_cctv_id = ANY(%s)
        """, (incident['cctv_id'], list(_SCENARIOS))).fetchone()
    if not row:
        return None
    return row['external_cctv_id']


def scenario_assessor(snapshot: ContextSnapshot, policy: dict, incident: dict) -> dict:
    """Simulated score for opted-in DEMO; real context is retained and stored."""
    camera = _approved_camera(incident)
    if camera is None:
        return assess(snapshot, policy)
    from backend.app.demo_v5_media.session_check import active_v5_incident
    if not active_v5_incident(incident):
        return assess(snapshot, policy)
    # Assess a separate *hypothetical* context. The real ContextSnapshot is
    # untouched and still saved in incident_contexts/risk_breakdown_json.
    measurements = {
        field: {'value': value, 'status': 'OK', 'source': 'DEMO_SIMULATION',
                'observed_at': snapshot.captured_at, 'unit': 'scenario_only'}
        for field, value in _SCENARIOS[camera].items()
    }
    hypothetical = ContextSnapshot(snapshot.incident_id, snapshot.captured_at,
                                   measurements, ('DEMO_SIMULATION',))
    result = assess(hypothetical, policy)
    if result['risk_score'] != _EXPECTED[camera]:
        raise ValueError('승인 DEMO 가상 시나리오 점수 검증 실패')
    actual = assess(snapshot, policy)
    result['risk_breakdown']['demo_simulation'] = {
        'enabled': True,
        'label': '시연 전용 가상 위험도 (실제 관측/운영 판단 아님)',
        'external_cctv_id': camera,
        'score_source': 'DEMO_SIMULATION',
        'inputs': measurements,
        'actual_context_preserved': True,
        'actual_risk_score': actual['risk_score'],
        'actual_priority': actual['priority'],
        'actual_missing': actual['risk_breakdown']['missing'],
    }
    result['rule_version'] = policy['version'] + ':DEMO_SIMULATION_V1'
    return result
