"""OCTV Demo CCTV 기준정보 동기화 스크립트."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv


# ============================================================
# 경로
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

ROOT_ENV_PATH = ROOT / ".env"
BACKEND_ENV_PATH = ROOT / "backend" / ".env"

DEFAULT_CONFIG_PATH = ROOT / "demo" / "cctvs.json"

PROVIDER = "DEMO"


# ============================================================
# 환경변수
# ============================================================


def load_environment() -> dict[str, Any]:
    if ROOT_ENV_PATH.exists():
        load_dotenv(dotenv_path=ROOT_ENV_PATH)

    if BACKEND_ENV_PATH.exists():
        load_dotenv(
            dotenv_path=BACKEND_ENV_PATH,
            override=True,
        )

    database_url = os.getenv("DATABASE_URL")

    if database_url:
        return {
            "database_url": database_url,
        }

    db_name = os.getenv("POSTGRES_DB")
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_port = os.getenv("POSTGRES_PORT")
    db_host = os.getenv(
        "POSTGRES_HOST",
        "127.0.0.1",
    )

    missing = []

    if not db_name:
        missing.append("POSTGRES_DB")

    if not db_user:
        missing.append("POSTGRES_USER")

    if not db_password:
        missing.append("POSTGRES_PASSWORD")

    if not db_port:
        missing.append("POSTGRES_PORT")

    if missing:
        raise RuntimeError(".env에 DB 설정이 없습니다: " + ", ".join(missing))

    database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    return {
        "database_url": database_url,
    }


# ============================================================
# Demo CCTV 설정
# ============================================================


def load_demo_cctvs(
    config_path: Path,
) -> list[dict[str, Any]]:
    if not config_path.exists():
        raise FileNotFoundError(f"Demo CCTV 설정 파일을 찾을 수 없습니다.\n경로: {config_path}")

    with config_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    cctvs = payload.get("cctvs")

    if not isinstance(
        cctvs,
        list,
    ):
        raise RuntimeError("demo/cctvs.json의 'cctvs'는 배열이어야 합니다.")

    return cctvs


# ============================================================
# 설정 검증
# ============================================================


def validate_records(
    records: list[dict[str, Any]],
) -> None:
    required_fields = {
        "external_cctv_id",
        "name",
        "latitude",
        "longitude",
        "region_code",
    }

    seen_ids: set[str] = set()

    for index, record in enumerate(
        records,
        start=1,
    ):
        missing = [
            field
            for field in required_fields
            if record.get(field)
            in (
                None,
                "",
            )
        ]

        if missing:
            raise RuntimeError(f"Demo CCTV #{index} 필수값 누락: " + ", ".join(sorted(missing)))

        external_cctv_id = str(record["external_cctv_id"]).strip()

        if external_cctv_id in seen_ids:
            raise RuntimeError(f"external_cctv_id가 중복되었습니다: {external_cctv_id}")

        seen_ids.add(external_cctv_id)

        latitude = float(record["latitude"])
        longitude = float(record["longitude"])

        if not (33.0 <= latitude <= 39.5):
            raise RuntimeError(f"비정상 위도입니다: {external_cctv_id} / {latitude}")

        if not (124.0 <= longitude <= 132.0):
            raise RuntimeError(f"비정상 경도입니다: {external_cctv_id} / {longitude}")


# ============================================================
# DB 검증
# ============================================================


def validate_regions(
    connection,
    records: list[dict[str, Any]],
) -> None:
    if not records:
        return

    region_codes = sorted({str(record["region_code"]).strip() for record in records})

    query = """
        SELECT region_code
        FROM region
        WHERE region_code =
              ANY(%s::varchar[]);
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (region_codes,),
        )

        existing = {str(row["region_code"]) for row in cursor.fetchall()}

    missing = set(region_codes) - existing

    if missing:
        raise RuntimeError(
            "DB region 테이블에 없는 region_code가 있습니다: " + ", ".join(sorted(missing))
        )


# ============================================================
# 기존 CCTV 조회
# ============================================================


def load_existing_ids(
    connection,
) -> set[str]:
    query = """
        SELECT external_cctv_id
        FROM cctvs
        WHERE provider = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (PROVIDER,),
        )

        return {str(row["external_cctv_id"]) for row in cursor.fetchall()}


# ============================================================
# UPSERT
# ============================================================


def upsert_demo_cctvs(
    connection,
    records: list[dict[str, Any]],
) -> None:
    if not records:
        return

    query = """
        INSERT INTO cctvs (
            external_cctv_id,
            name,
            provider,
            address,
            latitude,
            longitude,
            region_code
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        ON CONFLICT (
            provider,
            external_cctv_id
        )
        DO UPDATE SET
            name = EXCLUDED.name,
            address = EXCLUDED.address,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            region_code = EXCLUDED.region_code;
    """

    params = []

    for record in records:
        params.append(
            (
                str(record["external_cctv_id"]).strip(),
                str(record["name"]).strip(),
                PROVIDER,
                (str(record["address"]).strip() if record.get("address") else None),
                float(record["latitude"]),
                float(record["longitude"]),
                str(record["region_code"]).strip(),
            )
        )

    with connection.cursor() as cursor:
        cursor.executemany(
            query,
            params,
        )


# ============================================================
# 실행
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(description=("OCTV Demo CCTV 기준정보 동기화"))

    parser.add_argument(
        "--apply",
        action="store_true",
        help=("실제 DB에 Demo CCTV를 INSERT/UPDATE"),
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=("Demo CCTV JSON 경로"),
    )

    args = parser.parse_args()

    print()
    print("=" * 70)
    print("OCTV DEMO CCTV REFERENCE DATA SYNC")
    print("=" * 70)

    print("실행 모드         : " + ("APPLY" if args.apply else "DRY-RUN"))

    config_path = args.config.resolve()

    print(f"설정 파일         : {config_path}")

    records = load_demo_cctvs(config_path)

    print(f"Demo CCTV         : {len(records):,}개")

    if not records:
        print()
        print("Demo CCTV가 아직 설정되지 않았습니다.")
        print("demo/cctvs.json에 CCTV를 추가한 뒤 다시 실행하세요.")
        return

    validate_records(records)

    environment = load_environment()

    with psycopg.connect(
        environment["database_url"],
        row_factory=dict_row,
    ) as connection:
        validate_regions(
            connection,
            records,
        )

        existing_ids = load_existing_ids(connection)

        insert_count = sum(
            1 for record in records if str(record["external_cctv_id"]).strip() not in existing_ids
        )

        update_count = len(records) - insert_count

        print()
        print("=" * 70)
        print("동기화 계획")
        print("=" * 70)

        print(f"동기화 대상       : {len(records):,}개")

        print(f"신규 INSERT       : {insert_count:,}개")

        print(f"기존 UPDATE       : {update_count:,}개")

        if not args.apply:
            connection.rollback()

            print()
            print("=" * 70)
            print("DRY-RUN 완료")
            print("=" * 70)
            print("DB는 변경되지 않았습니다.")
            print()
            print("실제 반영:")
            print(".venv\\Scripts\\python scripts\\sync_demo_cctvs.py --apply")

            return

        upsert_demo_cctvs(
            connection,
            records,
        )

        connection.commit()

    print()
    print("=" * 70)
    print("APPLY 완료")
    print("=" * 70)

    print(f"Demo CCTV {len(records):,}개 동기화 완료")


if __name__ == "__main__":
    main()
