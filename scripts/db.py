"""Windows CMD/Linux 공통 Docker DB 검사·백업 도우미.

DB 스키마 변경은 Atlas를 통해 수행한다.

사용 예:
  .venv\\Scripts\\python scripts\\db.py tables
  .venv\\Scripts\\python scripts\\db.py verify
  .venv\\Scripts\\python scripts\\db.py backup

Migration:
  .venv\\Scripts\\python scripts\\atlas_db.py status
  .venv\\Scripts\\python scripts\\atlas_db.py diff change_name
  .venv\\Scripts\\python scripts\\atlas_db.py apply
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run_inside(
    command: str,
    **kwargs,
) -> subprocess.CompletedProcess:
    """
    Docker Compose의 PostgreSQL 컨테이너 안에서
    명령을 실행한다.

    컨테이너의 POSTGRES_* 환경변수를 사용하므로
    DB 이름과 사용자명을 코드에 중복 저장하지 않는다.
    """

    return subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            command,
        ],
        cwd=ROOT,
        check=True,
        **kwargs,
    )


def backup() -> Path:
    """
    현재 PostgreSQL DB의 pg_dump 백업을 생성하고,
    pg_restore --list로 백업 파일을 검증한다.
    """

    folder = (
        ROOT
        / "database"
        / "backups"
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    target = (
        folder
        / (
            "before_migration_"
            + datetime.now().strftime(
                "%Y%m%d_%H%M%S_%f"
            )
            + ".dump"
        )
    )

    try:
        with target.open(
            "xb"
        ) as stream:

            run_inside(
                (
                    'pg_dump '
                    '-U "$POSTGRES_USER" '
                    '-d "$POSTGRES_DB" '
                    "-Fc"
                ),
                stdout=stream,
            )

        if not target.stat().st_size:
            raise RuntimeError(
                "Empty backup"
            )

        with target.open(
            "rb"
        ) as stream:

            run_inside(
                "pg_restore --list",
                stdin=stream,
                stdout=subprocess.DEVNULL,
            )

    except Exception:

        print(
            (
                "BACKUP FAILED. "
                "No migration was started. "
                "Keep any partial file "
                "for inspection."
            ),
            file=sys.stderr,
        )

        raise

    print(
        "BACKUP OK:",
        target,
        flush=True,
    )

    return target


def show_tables() -> None:
    """현재 DB의 테이블 목록을 출력한다."""

    run_inside(
        (
            'psql -X '
            '-v ON_ERROR_STOP=1 '
            '-U "$POSTGRES_USER" '
            '-d "$POSTGRES_DB" '
            '-c "\\dt"'
        )
    )


def verify_schema() -> None:
    """
    tests/database_contract.sql을 이용해
    현재 DB 스키마 계약을 검증한다.
    """

    run_inside(
        (
            'psql -X '
            '-v ON_ERROR_STOP=1 '
            '-U "$POSTGRES_USER" '
            '-d "$POSTGRES_DB" '
            '-f /opt/octv/tests/'
            "database_contract.sql"
        )
    )

    print(
        "SCHEMA OK: "
        "database contract passed."
    )


def main() -> int:

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "action",
        choices=[
            "tables",
            "verify",
            "backup",
        ],
    )

    args = parser.parse_args()

    try:

        if args.action == "tables":
            show_tables()

        elif args.action == "verify":
            verify_schema()

        elif args.action == "backup":
            backup()

        return 0

    except (
        subprocess.CalledProcessError,
        OSError,
        RuntimeError,
    ):

        print(
            (
                "DB TASK FAILED. "
                "Check Docker logs and "
                "the message above. "
                "Do not delete the volume."
            ),
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )