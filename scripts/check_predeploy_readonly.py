"""Read-only local preflight. Never prints keys, changes DB, or sends notifications."""
from pathlib import Path
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parents[1]

def main():
    load_dotenv(ROOT / 'backend/.env')
    load_dotenv(ROOT / '.env')
    for key in ('OCTV_DEMO_ENABLED','OCTV_DECISION_ENABLED'):
        print(f'{key}:', 'ENABLED' if os.getenv(key) == '1' else 'DISABLED')
    print('운영 모델 설정:', bool(os.getenv('OCTV_YOLO_MODEL_PATH')))
    from ai.demo_v5.model_router import validate_approved_files
    try:
        validate_approved_files()
        print('V5 승인 모델/영상 SHA256: PASS')
    except Exception as e:
        print('V5 승인 파일: FAIL', type(e).__name__)
    from backend.app.config import database_connect_kwargs
    import psycopg
    try:
        with psycopg.connect(**{**database_connect_kwargs(), 'connect_timeout': 3}) as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            rows = conn.execute('''SELECT c.id,c.provider,c.external_cctv_id,c.is_monitored,
                c.connection_status,c.analysis_status,
                (SELECT count(*) FROM incidents i WHERE i.cctv_id=c.id) AS incident_count
                FROM cctvs c ORDER BY c.id''').fetchall()
            print('CCTV id/provider/external_id/monitored/connection/analysis/incident_count:')
            for row in rows:
                print(row)
            print('※ TEST 이름은 정리 후보일 뿐입니다. 실제 UTIC·DEMO와 참조를 확인한 뒤 비활성화하세요.')
    except Exception as e:
        print('DB: UNAVAILABLE', type(e).__name__)
    try:
        from ai.demo_v5.telemetry import client
        print('Redis:', 'PASS' if client().ping() else 'FAIL')
    except Exception as e:
        print('Redis: UNAVAILABLE', type(e).__name__)

if __name__ == '__main__': main()
