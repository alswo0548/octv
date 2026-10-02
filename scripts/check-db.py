"""실제 TCP DB 연결과 최신 구조를 읽기 전용으로 확인합니다. 프로젝트 루트에서 실행."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    try:
        from backend.app.db.session import get_connection
        with get_connection() as connection:
            connection.execute('SET TRANSACTION READ ONLY')
            row = connection.execute(
                "SELECT current_database() AS db, current_user AS usr, "
                "current_setting('server_version') AS version, 1 AS ok"
            ).fetchone()
            connection.execute((ROOT / 'tests/database_contract.sql').read_text(encoding='utf-8'))
            print(f"DB OK: database={row['db']}, user={row['usr']}, PostgreSQL={row['version']}")
            print('SCHEMA OK: 13 tables; columns, ENUMs, PKs, FKs and 7 UNIQUE rules match the supplied ERD.')
        return 0
    except Exception as exc:
        # DSN/접속 문자열/비밀번호가 예외에 포함될 수 있어 원문을 출력하지 않습니다.
        print(f'DB CHECK FAILED ({type(exc).__name__}).', file=sys.stderr)
        print('Check Docker status, root .env, backend DATABASE_URL override and migrations.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
