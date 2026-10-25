"""Current approved DEMO session guard (SQL read only)."""
from datetime import timezone
from ai.demo_v5.session_pipeline import active_session


def active_v5_incident(incident: dict) -> bool:
    started = active_session(int(incident['cctv_id']))
    if started is None:
        return False
    detected = incident.get('detected_at')
    if detected is None:
        return False
    # Incidents are stored as naive UTC even when DB sessions are in KST.
    if detected.tzinfo is None:
        detected = detected.replace(tzinfo=timezone.utc)
    return detected.astimezone(timezone.utc) >= started
