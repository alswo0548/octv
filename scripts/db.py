"""Windows CMD/Linux 공통 Docker DB 검사·백업·변경 도우미. Python 표준 라이브러리만 사용."""

import argparse
from datetime import datetime
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run_inside(command, **kwargs):
    # Docker 컨테이너 환경변수를 사용하므로 사용자명/DB명을 명령마다 바꿀 필요가 없습니다.
    return subprocess.run(['docker', 'compose', 'exec', '-T', 'db', 'sh', '-c', command],
                          cwd=ROOT, check=True, **kwargs)


def backup():
    folder = ROOT / 'database/backups'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ('before_003_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.dump')
    try:
        with target.open('xb') as stream:
            run_inside('pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc', stdout=stream)
        if not target.stat().st_size:
            raise RuntimeError('Empty backup')
        with target.open('rb') as stream:
            run_inside('pg_restore --list', stdin=stream, stdout=subprocess.DEVNULL)
    except Exception:
        print('BACKUP FAILED. No migration was started. Keep any partial file for inspection.', file=sys.stderr)
        raise
    print('BACKUP OK:', target, flush=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['tables', 'verify', 'backup', 'migrate'])
    args = parser.parse_args()
    try:
        if args.action == 'migrate':
            try:
                run_inside('psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                           '-f /opt/octv/tests/database_contract.sql', capture_output=True)
            except subprocess.CalledProcessError:
                pass  # A supported older schema is validated transactionally by 003.
            else:
                print('ALREADY CURRENT: schema and all UNIQUE rules match. No migration needed.')
                return 0
        if args.action in ('backup', 'migrate'):
            backup()
        if args.action == 'migrate':
            run_inside('psql -X -v ON_ERROR_STOP=1 -v backup_confirmed=1 '
                       '-U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                       '-f /opt/octv/database/migrations/003_final_erd_uniques.sql')
            print('MIGRATION OK. Keep the backup; removed columns are recoverable from it.')
        elif args.action == 'tables':
            run_inside('psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\\dt"')
        elif args.action == 'verify':
            run_inside('psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                       '-f /opt/octv/tests/database_contract.sql')
            print('SCHEMA OK: matches the supplied ERD.')
        return 0
    except (subprocess.CalledProcessError, OSError, RuntimeError):
        print('DB TASK FAILED. Check Docker logs and the message above. Do not delete the volume.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
