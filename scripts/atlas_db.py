r"""OCTV SQL -> Atlas migration helper (Windows CMD / Python 3.12).

Original feature SQL is preserved. Changes are generated from database/schema.sql
and applied as versioned migrations (Atlas CLI is a separate prerequisite).

Run from the repository root:
  .venv\Scripts\python scripts\atlas_db.py init-create  # one teammate, once
  .venv\Scripts\python scripts\atlas_db.py init-mark    # each existing 003 DB, once
  .venv\Scripts\python scripts\atlas_db.py diff change_name
  .venv\Scripts\python scripts\atlas_db.py apply
  .venv\Scripts\python scripts\atlas_db.py adopt-manual  # only already manually updated DB
  .venv\Scripts\python scripts\atlas_db.py status
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import quote, urlencode

ROOT = Path(__file__).resolve().parents[1]
# Direct invocation: python scripts\\atlas_db.py; make backend package importable.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "database" / "schema.sql"
OUTPUT = ROOT / "database" / ".atlas_generated" / "schema.sql"
MIGRATIONS = ROOT / "database" / "atlas_migrations"
ATLAS_CONFIG = ROOT / "atlas.hcl"
BASELINE_PATTERN = re.compile(r"^[0-9]+_baseline\.sql$")
LABEL_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,60}$")


def expand_psql_file(file: Path, stack: tuple[Path, ...] = (), root: bool = False) -> str:
    """Expand OCTV's psql \\ir includes, leaving pure PostgreSQL DDL for Atlas."""
    file = file.resolve()
    if not file.is_relative_to(ROOT) or not file.exists():
        raise ValueError("SQL include is missing or points outside the OCTV project")
    if file in stack:
        raise ValueError("SQL include cycle detected")
    chunks: list[str] = []
    for line in file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("\\ir "):
            relative = stripped[4:].strip().strip("'\"")
            included = (file.parent / relative).resolve()
            chunks.append(f"-- Begin: {included.relative_to(ROOT).as_posix()}")
            chunks.append(expand_psql_file(included, stack + (file,)))
            chunks.append(f"-- End: {included.relative_to(ROOT).as_posix()}")
        elif root and stripped in {
            r"\set ON_ERROR_STOP on", "BEGIN;", "COMMIT;",
            "SET LOCAL search_path TO public;",
        }:
            continue  # Atlas schema state is declarative, not a psql transaction.
        elif stripped.startswith("\\"):
            raise ValueError(f"Unsupported psql instruction in {file.name}")
        else:
            chunks.append(line)
    return "\n".join(chunks) + "\n"


def render() -> Path:
    sql = expand_psql_file(SOURCE, root=True)
    if "\\ir " in sql or "\\set " in sql:
        raise ValueError("Unexpanded psql meta-command")
    if sql.count("CREATE TABLE ") < 13:
        raise ValueError("SQL source appears incomplete; no Atlas operation was run")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("-- Generated from database/schema.sql. DO NOT EDIT.\n" + sql,
                      encoding="utf-8", newline="\n")
    return OUTPUT


def database_url() -> str:
    """Reuse OCTV's already-defined Python DB connection settings."""
    try:
        from backend.app.config import database_connect_kwargs
        from psycopg.conninfo import conninfo_to_dict
    except ImportError as exc:
        raise ValueError("Backend packages missing: install backend\\requirements.txt") from exc
    conn_kwargs = database_connect_kwargs()
    if conn_kwargs.get("conninfo"):
        values = conninfo_to_dict(conn_kwargs["conninfo"])
    else:
        values = dict(conn_kwargs)
    host = str(values.get("host") or "127.0.0.1")
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("This helper supports the local OCTV DB only")
    try:
        port = int(values.get("port") or 5432)
    except (ValueError, TypeError) as exc:
        raise ValueError("Bad DB port") from exc
    if not 1 <= port <= 65535:
        raise ValueError("Bad DB port")
    user = str(values.get("user") or "")
    password = str(values.get("password") or "")
    dbname = str(values.get("dbname") or "")
    if not user or not password or not dbname:
        raise ValueError("Check root .env or backend DATABASE_URL: DB name/user/password missing")
    # OCTV's backup helper dumps the Docker Compose db, not an arbitrary DATABASE_URL.
    from dotenv import dotenv_values
    local_values = dotenv_values(ROOT / ".env", interpolate=False)
    def expected(key: str, default: str) -> str:
        return str(os.getenv(key) or local_values.get(key) or default)
    if (dbname != expected("POSTGRES_DB", "octv_dev") or
            user != expected("POSTGRES_USER", "octv_dev") or
            str(port) != expected("POSTGRES_PORT", "5432")):
        raise ValueError("Backend DB and Compose DB do not match; stop before backup/migration")
    return (f"postgres://{quote(user, safe='')}:{quote(password, safe='')}@"
            f"{host}:{port}/{quote(dbname, safe='')}?"
            f"{urlencode({'search_path':'public', 'sslmode':'disable'})}")


def run_atlas(*args: str, capture_output: bool = False) -> subprocess.CompletedProcess:
    if not shutil.which("atlas"):
        raise ValueError("Atlas not installed: see docs/ATLAS_SQL_AUTOMATION.md")
    env = os.environ.copy()
    env["OCTV_ATLAS_DB_URL"] = database_url()
    return subprocess.run(["atlas", *args, "--env", "local"],
                          cwd=ROOT, env=env, check=True,
                          capture_output=capture_output, text=capture_output)


def check_legacy_baseline() -> None:
    print("Verifying the existing 003 DB structure...", flush=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "db.py"), "verify"],
                   cwd=ROOT, check=True)


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS.glob("*.sql")) if MIGRATIONS.exists() else []


def baseline_file() -> Path:
    files = [p for p in migration_files() if BASELINE_PATTERN.fullmatch(p.name)]
    if len(files) != 1:
        raise ValueError("Exactly one generated *_baseline.sql is required")
    return files[0]


def init_create() -> None:
    # Run on a branch based on the last shared 003 schema, before teammate's PR.
    check_legacy_baseline()
    if migration_files() or (MIGRATIONS / "atlas.sum").exists():
        raise ValueError("Atlas migrations already exist; do not create another baseline")
    render()
    MIGRATIONS.mkdir(parents=True, exist_ok=True)
    run_atlas("migrate", "diff", "baseline")
    name = baseline_file().name
    print(f"BASELINE GENERATED: {name}")
    print("Commit database/atlas_migrations/*.sql and atlas.sum in the setup PR.")


def init_mark() -> None:
    # Only for an EXISTING and VERIFIED 003 DB (not for an empty DB).
    check_legacy_baseline()
    render()
    if len(migration_files()) != 1:
        raise ValueError("Mark baseline before new migrations are added; stop for review")
    version = baseline_file().name.split("_", 1)[0]
    print(f"Marking existing DB as already at baseline {version}; no schema DDL is executed.")
    run_atlas("migrate", "apply", "--baseline", version)
    run_atlas("migrate", "status")


def diff(label: str) -> None:
    if not LABEL_PATTERN.fullmatch(label):
        raise ValueError("Use an English lowercase label: e.g. modify_agency_phone")
    baseline_file()
    render()
    run_atlas("migrate", "diff", label)
    print("Review generated SQL before applying, especially DROP/RENAME/ALTER TYPE.")
    print("Commit the SQL file AND atlas.sum after successful tests.")


def apply() -> None:
    baseline_file()
    render()
    print("--- Planned DB changes (dry run) ---", flush=True)
    run_atlas("migrate", "apply", "--dry-run")
    confirm = input("Review the changes. Type APPLY to back up and execute: ").strip()
    if confirm != "APPLY":
        print("Cancelled. Database was not changed.")
        return
    # The existing OCTV backup helper takes a verified pg_dump before every change.
    subprocess.run([sys.executable, str(ROOT / "scripts" / "db.py"), "backup"],
                   cwd=ROOT, check=True)
    run_atlas("migrate", "apply")
    run_atlas("migrate", "status")


def adopt_manual() -> None:
    """Safely adopt ONE migration already reflected in this developer's DB.

    This one-time command is only for a team member who manually applied
    a schema change before Atlas was installed. Never execute its DDL twice.
    """
    from backend.app.config import database_connect_kwargs
    try:
        import psycopg
    except ImportError as exc:
        raise ValueError("Install backend\\requirements.txt first") from exc

    baseline = baseline_file()
    files = migration_files()
    if len(files) != 2 or files[0] != baseline:
        raise ValueError("Manual adoption expects baseline + exactly ONE new migration. Stop and review.")

    # Do not adjust a database that Atlas has already started tracking.
    with psycopg.connect(**database_connect_kwargs()) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.atlas_schema_revisions')")
            if cursor.fetchone()[0] is not None:
                raise ValueError("Atlas revision table exists. Do not adopt again; use status.")

    render()
    print("Checking whether LIVE Docker DB matches the updated SQL definitions...", flush=True)
    result = run_atlas("schema", "apply", "--dry-run", capture_output=True)
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    # Atlas' documented zero-diff message is 'Schemas are synced, no changes to be made'.
    # Do not rely on exit code alone: dry-run succeeds when it produces a change plan.
    match = re.search(r"schema(?:s)?\s+(?:is|are)\s+synced\s*,?\s*no changes to be made", output, re.I)
    if not match:
        print("STOP: Atlas did not confirm a zero difference between DB and SQL definitions.", flush=True)
        print("Review the dry-run plan with the team before proceeding. No revision was marked.", flush=True)
        raise ValueError("DB != SQL schema. Do not mark any migration version.")

    latest = files[1].name.split("_", 1)[0]
    print("LIVE DB and SQL are in sync. One manual change is already present.")
    print(f"The existing DB can be marked through Atlas version {latest} without running schema DDL.")
    confirm = input("Type MARK_ALREADY_APPLIED to back up and record it (or Enter to stop): ").strip()
    if confirm != "MARK_ALREADY_APPLIED":
        print("Cancelled. Database history was not changed.")
        return
    subprocess.run([sys.executable, str(ROOT / "scripts" / "db.py"), "backup"],
                   cwd=ROOT, check=True)
    # Atlas baseline marks versions through latest without executing the SQL statements.
    run_atlas("migrate", "apply", "--baseline", latest)
    run_atlas("migrate", "status")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("render", "init-create", "init-mark", "apply", "adopt-manual", "status"):
        sub.add_parser(action)
    command = sub.add_parser("diff")
    command.add_argument("label")
    args = parser.parse_args()
    try:
        if not ATLAS_CONFIG.is_file():
            raise ValueError("atlas.hcl is missing in OCTV root")
        if args.action == "render":
            print("SCHEMA GENERATED:", render().relative_to(ROOT))
        elif args.action == "init-create":
            init_create()
        elif args.action == "init-mark":
            init_mark()
        elif args.action == "diff":
            diff(args.label)
        elif args.action == "adopt-manual":
            adopt_manual()
        elif args.action == "apply":
            apply()
        elif args.action == "status":
            baseline_file()
            render()
            run_atlas("migrate", "status")
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        # The underlying process may include a credential in its error text.
        print(f"STOP: {type(exc).__name__}. Review the preceding message; no DB reset.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
