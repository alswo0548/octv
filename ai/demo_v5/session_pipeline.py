"""Isolated v5 session adapter. Original temporal rules and UTIC pipeline unchanged."""
from datetime import timezone
from zoneinfo import ZoneInfo
from hashlib import sha256

from backend.app.db.session import get_connection
from ai.detection.incident_pipeline import IncidentPipeline, IncidentPipelineResult


def active_session(cctv_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT w.issued_at FROM cctvs c JOIN weather_alerts w
              ON w.external_alert_id = 'DEMO:main_demo:' || c.external_cctv_id
            WHERE c.id=%s AND c.provider='DEMO'
              AND c.external_cctv_id = ANY(%s)
              AND c.is_monitored AND w.status='ACTIVE'
            ORDER BY w.issued_at DESC LIMIT 1
        """, (cctv_id, ['DEMO-N001','DEMO-N002','DEMO-N003'])).fetchone()
    if not row:
        return None
    issued = row['issued_at']
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=ZoneInfo('Asia/Seoul'))
    return issued.astimezone(timezone.utc)


class SessionPipeline:
    def __init__(self, original, demo_ids, session_reader=active_session, factory=IncidentPipeline):
        self.original = original
        self.demo_ids = frozenset(demo_ids)
        self.session_reader = session_reader
        self.factory = factory
        self.sessions = {}

    def handle_result(self, frame, detections, performance=None):
        if frame.cctv_id not in self.demo_ids:
            return self.original.handle_result(frame=frame, detections=detections, performance=performance)
        started = self.session_reader(frame.cctv_id)
        captured = frame.captured_at
        if captured.tzinfo is None:
            # Frame contract requires absolute timestamps; never guess timezone.
            return IncidentPipelineResult(had_error=True)
        if started is None or captured < started:
            self.sessions.pop(frame.cctv_id, None)
            return IncidentPipelineResult()
        current = self.sessions.get(frame.cctv_id)
        if current is None or current[0] != started:
            token = sha256(started.isoformat().encode()).hexdigest()[:20]
            def register(payload):
                # Reject late registrations after stop or a newer start.
                if self.session_reader(frame.cctv_id) != started:
                    raise RuntimeError('Demo session ended before registration')
                return self.original._register_fn({**payload, 'dedup_key': f"v5:{token}:{payload['dedup_key']}"})
            pipeline = self.factory(config=self.original._config, register_fn=register)
            self.sessions[frame.cctv_id] = (started, pipeline)
        return self.sessions[frame.cctv_id][1].handle_result(frame=frame, detections=detections, performance=performance)
