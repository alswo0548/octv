"""Dashboard-only read-only MCP refresh of external measurements.

Keeps saved incident assessments immutable. Provider observational caches may be
updated by existing MCP adapters, but incidents, risk rules and DB are untouched.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from threading import Lock
from time import monotonic

# A single per-process cache avoids one full provider fan-out every 60 seconds
# for every browser tab. Never store credentials or a user's authorization here.
_SUCCESS_TTL_SECONDS = 180
_FAILURE_TTL_SECONDS = 45
_MAX_INCIDENTS = 64
_LOCK = Lock()
_CACHE: dict[int, tuple[float, object | None, str, datetime]] = {}


def _query_mcp(incident_id: int):
    from ai.mcp.client import collect_via_mcp
    return asyncio.run(collect_via_mcp(incident_id))


def latest_context(incident_id: int) -> tuple[object | None, str, datetime]:
    """Return snapshot, attempt status and UTC checked-at; failures stay explicit.

    Call this only AFTER the normal Dashboard role-scoped incident access check.
    Cache the failure too, avoiding a retry storm when provider is unavailable.
    """
    now = monotonic()
    with _LOCK:
        existing = _CACHE.get(incident_id)
        if existing is not None:
            stored_at, snapshot, status, checked = existing
            ttl = _SUCCESS_TTL_SECONDS if status == "OK" else _FAILURE_TTL_SECONDS
            if now - stored_at < ttl:
                return snapshot, status, checked
        checked = datetime.now(timezone.utc)
        try:
            snapshot = _query_mcp(incident_id)
            if (
                getattr(snapshot, "incident_id", None) != incident_id
                or not isinstance(getattr(snapshot, "measurements", None), dict)
                or not isinstance(getattr(snapshot, "captured_at", None), datetime)
            ):
                raise ValueError("MCP returned an invalid incident context")
            status = "OK"
        except Exception:
            # Credentials and raw provider payloads must not enter user-facing errors.
            snapshot, status = None, "FAILED"
        if len(_CACHE) >= _MAX_INCIDENTS and incident_id not in _CACHE:
            oldest = min(_CACHE, key=lambda key: _CACHE[key][0])
            del _CACHE[oldest]
        _CACHE[incident_id] = (monotonic(), snapshot, status, checked)
        return snapshot, status, checked


def nearby_reference_count(measurements: dict) -> int | None:
    """Display ITS nearby-event total as reference only, never verified closure."""
    item = measurements.get("traffic_nearby_events")
    if not isinstance(item, dict) or item.get("status") != "REFERENCE_ONLY":
        return None
    value = item.get("value")
    return value if type(value) is int and value >= 0 else None
