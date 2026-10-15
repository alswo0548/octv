"""실제 TCP DB 연결과 현재 스키마 계약을 읽기 전용으로 확인한다."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


def main() -> int:

    try:
        from backend.app.db.session import (
            get_connection,
        )

        with get_connection() as connection:

            connection.execute(
                "SET TRANSACTION READ ONLY"
            )

            row = connection.execute(
                """
                SELECT
                    current_database() AS db,
                    current_user AS usr,
                    current_setting(
                        'server_version'
                    ) AS version,
                    1 AS ok
                """
            ).fetchone()

            contract_path = (
                ROOT
                / "tests"
                / "database_contract.sql"
            )

            connection.execute(
                contract_path.read_text(
                    encoding="utf-8"
                )
            )

            print(
                "DB OK: "
                f"database={row['db']}, "
                f"user={row['usr']}, "
                f"PostgreSQL={row['version']}"
            )

            print(
                "SCHEMA OK: "
                "database_contract.sql passed."
            )

        return 0

    except Exception as exc:

        # 접속 문자열이나 비밀번호가 예외 메시지에
        # 포함될 수 있으므로 원문은 출력하지 않는다.
        print(
            (
                "DB CHECK FAILED "
                f"({type(exc).__name__})."
            ),
            file=sys.stderr,
        )

        print(
            (
                "Check Docker status, "
                "root .env, "
                "backend DATABASE_URL override "
                "and Atlas migration status."
            ),
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )