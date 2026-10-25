"""Demo CCTV 수집·사건 상태 읽기 전용 진단. 조회 외 DB/Runtime 변경 없음."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from backend.app.config import load_environment
from backend.app.db.session import get_connection
from backend.app.demo.service import get_demo_status


def main() -> None:
    load_environment()
    try:
        state = get_demo_status()
        print("[DEMO STATUS] active=", state.active,
              "CCTV=", f"{state.active_cctv_count}/{state.case_count}",
              "ACTIVE_ALERTS=", state.active_alert_count)
    except Exception as exc:
        print("[DEMO STATUS ERROR]", type(exc).__name__, str(exc))

    with get_connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute(
            "SELECT id, external_cctv_id, is_monitored, monitored_mode, "
            "connection_status, analysis_status, last_frame_at, stream_url IS NOT NULL AS video_set "
            "FROM cctvs WHERE provider='DEMO' ORDER BY external_cctv_id"
        ).fetchall()
        events = conn.execute(
            "SELECT c.external_cctv_id, i.id, i.hazard_type, i.confidence, "
            "i.model_version, i.status, i.detected_at "
            "FROM incidents i JOIN cctvs c ON c.id=i.cctv_id "
            "WHERE c.provider='DEMO' ORDER BY i.id DESC LIMIT 15"
        ).fetchall()

    print("\n[DEMO CCTV / DB 수집 상태]")
    for row in rows:
        print(f"{row['external_cctv_id']} / DB_ID={row['id']} / "
              f"ON={row['is_monitored']} / mode={row['monitored_mode']} / "
              f"capture={row['connection_status']} / YOLO={row['analysis_status']} / "
              f"last_frame={row['last_frame_at']} / video_set={row['video_set']}")
    print("\n[최근 DEMO Incident, 최근 15건 (DB UTC 기준)]")
    for row in events:
        print(f"{row['external_cctv_id']} / incident={row['id']} / "
              f"{row['hazard_type']} / conf={row['confidence']} / "
              f"status={row['status']} / model={row['model_version']} / "
              f"detected_at={row['detected_at']}")
    if not events:
        print("DEMO INCIDENT: 0건 (현재 DB에 DEMO 제공자의 Incident 없음)")
    if rows and all(not r['is_monitored'] for r in rows):
        print("\n[힌트] 현재 Demo CCTV가 모두 OFF입니다. 웹 영상 재생과 YOLO는 별개입니다.")
        print("시연 시작 → Runtime 창에서 [DEMO SOURCE], [YOLO WORKER] cctv=4/5/6, [TEMPORAL] 확인")
    elif rows and any(r['analysis_status'] != 'RUNNING' for r in rows if r['is_monitored']):
        print("\n[힌트] 감시 ON인데 YOLO가 RUNNING이 아닌 CCTV가 있습니다. Runtime 로그 확인이 필요합니다.")
    else:
        print("\n[힌트] YOLO RUNNING이어도 VERIFY 3회/15초 및 IoU 조건을 통과해야 Incident가 생성됩니다.")
    print("진단 종료: DB 조회만 수행, 변경 없음")


if __name__ == '__main__':
    main()
