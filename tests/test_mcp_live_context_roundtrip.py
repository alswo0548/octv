"""Real in-memory MCP transport; DB/provider boundaries replaced with fixtures."""
import asyncio
from contextlib import nullcontext
from datetime import datetime, timezone
from unittest.mock import patch

from ai.config import runtime_config_scope
from ai.mcp.client import collect_via_mcp
from backend.app.integrations import context


def test_context_survives_real_mcp_roundtrip():
    now = datetime.now(timezone.utc)
    item = {'value': 32, 'status': 'OK', 'source': 'ITS_REVIEWED_LINK',
            'unit': 'km/h', 'observed_at': now.isoformat(), 'rule_eligible': False}
    with patch.object(context, 'get_connection', return_value=nullcontext(None)), \
         patch.object(context, 'find_detail', return_value={'id': 7}), \
         patch.object(context.weather, 'fetch_observations', return_value={'rainfall_mm': {**item, 'value': 2}}), \
         patch.object(context.water_level, 'fetch_data', return_value={**item, 'value': 1}), \
         patch.object(context.water_level, 'classify_risk_level', return_value={**item, 'value': 'NORMAL'}), \
         patch.object(context.traffic, 'fetch_rule_data', return_value={}), \
         patch.object(context, 'nearby_event_measurement', return_value={**item, 'status': 'NO_MAPPING'}), \
         patch.object(context.places, 'fetch_data', return_value={}), \
         patch('backend.app.integrations.verified_traffic.fetch_speed', return_value=item), \
         runtime_config_scope({'query_factory': lambda incident, at: {}}):
        snapshot = asyncio.run(collect_via_mcp(7))
    assert snapshot.incident_id == 7
    assert snapshot.measurements['traffic_speed_kmh'] == item
    assert snapshot.measurements['rainfall_mm']['value'] == 2
    assert snapshot.measurements['water_risk_level']['value'] == 'NORMAL'
    assert 'ITS_REVIEWED_LINK' in snapshot.sources
