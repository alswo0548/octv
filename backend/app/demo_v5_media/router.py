"""Demo MP4 playback only; does NOT create or simulate detections or incidents.

A short-lived bearer capability lets a native HTML <video> use HTTP Range
without putting a login JWT into the video URL. Use only on trusted demo LAN.
"""
from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from backend.app.db.session import get_connection
from backend.app.dependencies import require_control_admin

router = APIRouter(prefix="/api/demo/v5", tags=["Demo v5 playback"])
ROOT = Path(__file__).resolve().parents[3]
DEMO_FILES = {
    "DEMO-N001": "N001_demo.mp4",
    "DEMO-N002": "N002_demo.mp4",
    "DEMO-N003": "N003_demo.mp4",
}
TOKEN_TTL_SEC = 900
_tickets: dict[str, tuple[int, float]] = {}
_lock = Lock()


def _file_for_active_demo(cctv_id: int) -> Path:
    with get_connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        row = conn.execute(
            "SELECT provider, external_cctv_id, stream_url, is_monitored "
            "FROM cctvs WHERE id=%s", (cctv_id,),
        ).fetchone()
    if row is None or row["provider"] != "DEMO":
        raise HTTPException(404, "Demo CCTV를 찾지 못했습니다.")
    expected = DEMO_FILES.get(str(row["external_cctv_id"]))
    if not expected:
        raise HTTPException(404, "지원하지 않는 Demo CCTV입니다.")
    if not row["is_monitored"] or row["stream_url"] != expected:
        raise HTTPException(409, "해당 Demo CCTV가 시작되지 않았습니다.")
    video_dir = Path(os.getenv("OCTV_DEMO_VIDEO_DIR", "demo/videos"))
    if not video_dir.is_absolute():
        video_dir = ROOT / video_dir
    video_dir = video_dir.resolve()
    target = (video_dir / expected).resolve()
    if not target.is_relative_to(video_dir) or not target.is_file():
        raise HTTPException(404, "Demo 영상이 없습니다.")
    return target


@router.post("/playback/{cctv_id}")
def grant_playback(cctv_id: int, request: Request, _admin=Depends(require_control_admin)):
    _file_for_active_demo(cctv_id)
    now = time.monotonic()
    token = secrets.token_urlsafe(32)
    with _lock:
        stale = [k for k, (_, exp) in _tickets.items() if exp < now]
        for key in stale:
            _tickets.pop(key, None)
        _tickets[token] = (cctv_id, now + TOKEN_TTL_SEC)
    url = request.url_for("watch_demo_video", cctv_id=cctv_id)
    return {"url": f"{url}?token={token}", "expires_in": TOKEN_TTL_SEC}


@router.get("/watch/{cctv_id}", name="watch_demo_video")
def watch_demo_video(cctv_id: int, token: str):
    with _lock:
        ticket = _tickets.get(token)
    if ticket is None or ticket[0] != cctv_id or time.monotonic() >= ticket[1]:
        raise HTTPException(403, "재생 권한이 만료됐습니다. 다시 연결해주세요.")
    target = _file_for_active_demo(cctv_id)
    return FileResponse(target, media_type="video/mp4", headers={"Cache-Control": "no-store"})


@router.get("/n001-overlay/{cctv_id}")
def n001_visual_overlay(cctv_id: int, _admin=Depends(require_control_admin)):
    """Precomputed visual-only N001 rectangles (never incident decisions)."""
    source = _file_for_active_demo(cctv_id)
    if source.name != "N001_demo.mp4":
        raise HTTPException(404, "N001 전용 영상 시각화입니다.")
    from .n001_overlay import read_n001_overlay
    return read_n001_overlay(source)


@router.get("/sync")
def demo_synchronized_start(_admin=Depends(require_control_admin)):
    """Shared scenario timeline for the approved active Demo cameras.

    Demo start stores a KST-naive weather_alerts.issued_at in the DB. We attach
    Asia/Seoul here, so all browser players use one absolute timestamp and late
    selections jump to the correct playback offset. Read only; no fake events.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from backend.app.demo.service import get_demo_status

    status = get_demo_status()
    if not status.active:
        return {"active": False, "started_at": None}
    with get_connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        row = conn.execute(
            "SELECT MIN(issued_at) AS issued_at, COUNT(*) AS count "
            "FROM weather_alerts WHERE status='ACTIVE' "
            "AND external_alert_id LIKE %s",
            ("DEMO:main_demo:%",),
        ).fetchone()
    if not row or row["count"] != status.case_count or not isinstance(row["issued_at"], datetime):
        return {"active": False, "started_at": None}
    issued = row["issued_at"]
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return {"active": True, "started_at": issued.isoformat()}


@router.get("/mapping-status")
def demo_mapping_status(_admin=Depends(require_control_admin)):
    """Inspect safe cached mapping reasons; no network/provider calls or DB changes."""
    from .mapping import mapping_status
    try:
        return mapping_status()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/prepare-mapping")
def demo_prepare_mapping(_admin=Depends(require_control_admin)):
    """Prewarm only approved DEMO mapping into Redis before demo/start.

    Failure never changes the original start endpoint or reinterprets absent
    water/traffic mappings as valid real-world measurements.
    """
    from .mapping import prepare_mapping
    try:
        return prepare_mapping()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/archive-scope")
def demo_archive_scope(_admin=Depends(require_control_admin)):
    """Presentation archive only: no DELETE/UPDATE and no change to FCM history."""
    with get_connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute("""
            SELECT i.id FROM incidents i JOIN cctvs c ON c.id=i.cctv_id
            WHERE c.provider='DEMO' AND c.external_cctv_id = ANY(%s)
              AND NOT EXISTS (
                SELECT 1 FROM weather_alerts w
                WHERE w.external_alert_id='DEMO:main_demo:' || c.external_cctv_id
                  AND w.status='ACTIVE' AND c.is_monitored
                  AND i.detected_at >= ((w.issued_at AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'UTC')
              )
        """, (list(DEMO_FILES),)).fetchall()
    return {"archived_ids": [row['id'] for row in rows]}


@router.get("/preview/{cctv_id}")
def inference_preview(cctv_id: int, _admin=Depends(require_control_admin)):
    import json
    from ai.demo_v5.telemetry import client
    with get_connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        camera = conn.execute('SELECT is_monitored, provider FROM cctvs WHERE id=%s', (cctv_id,)).fetchone()
    if camera is None:
        raise HTTPException(404, 'CCTV 없음')
    if not camera['is_monitored']:
        return {'state': 'OFF', 'frame': None}
    try:
        value = client().get(f'octv:v5:preview:{cctv_id}')
    except Exception:
        raise HTTPException(503, '추론 프레임 조회 연결 실패') from None
    frame = json.loads(value) if value else None
    if frame and camera['provider'] == 'DEMO':
        from datetime import datetime
        from ai.demo_v5.session_pipeline import active_session
        started = active_session(cctv_id)
        if started is None or datetime.fromisoformat(frame['captured_at']) < started:
            frame = None
    return {'state': 'READY' if frame else 'NO_RECENT_FRAME', 'frame': frame}


@router.post("/incidents/{incident_id}/explain")
def explain_incident_v5(incident_id: int, _admin=Depends(require_control_admin)):
    """LLM is opt-in per click, does not change incidents or make decisions."""
    from backend.app.incidents.repository import find_detail
    from .llm_explanation import explain
    with get_connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        incident = find_detail(conn, incident_id)
    if incident is None:
        raise HTTPException(404, '사건이 없습니다.')
    return explain(incident)
