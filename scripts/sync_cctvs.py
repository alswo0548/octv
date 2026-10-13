"""OCTV CCTV 기준정보 동기화 스크립트."""

from pathlib import Path
import os

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]

ENV_PATH = (
    ROOT
    / ".env"
)


# ============================================================
# CCTV 기준 데이터
#
# 실제 HLS Stream URL / Stream ID는 저장하지 않는다.
# external_cctv_id를 이용해 연결 시점에 UTIC에서 다시 조회한다.
# ============================================================

CCTV_DATA = [
    {
        "external_cctv_id": "E910012",
        "name": "[경부선][서울]경부동탄터널(서울)-입구",
        "provider": "UTIC",
        "address": None,
        "latitude": 37.1824818,
        "longitude": 127.0958378,
        "stream_url": None,
        "is_monitored": True,
        "connection_status": "DISCONNECTED",
        "video_quality_status": "UNAVAILABLE",
        "analysis_status": "STOPPED",
        "last_frame_at": None,
        "region_code": None,
        "monitored_mode": "BASE",
    },
]


def load_database_config() -> dict:
    """
    루트 .env에서 PostgreSQL 접속 설정을 읽는다.
    """

    load_dotenv(
        dotenv_path=ENV_PATH
    )

    db_name = os.getenv("POSTGRES_DB")
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_port = os.getenv("POSTGRES_PORT")

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
        raise RuntimeError(
            ".env에 다음 PostgreSQL 설정이 없습니다: "
            + ", ".join(missing)
        )

    return {
        "host": "127.0.0.1",
        "port": int(db_port),
        "dbname": db_name,
        "user": db_user,
        "password": db_password,
    }


def upsert_cctv(
    connection: psycopg.Connection,
    cctv: dict,
) -> int:
    """
    provider + external_cctv_id 기준으로 CCTV 정보를 upsert한다.

    이미 존재하면 기준정보만 갱신한다.

    connection_status, video_quality_status,
    analysis_status, last_frame_at 같은 런타임 상태값은
    기존 CCTV가 존재할 경우 덮어쓰지 않는다.
    """

    query = """
        INSERT INTO cctvs (
            external_cctv_id,
            name,
            provider,
            address,
            latitude,
            longitude,
            stream_url,
            is_monitored,
            connection_status,
            video_quality_status,
            analysis_status,
            last_frame_at,
            region_code,
            monitored_mode
        )
        VALUES (
            %(external_cctv_id)s,
            %(name)s,
            %(provider)s,
            %(address)s,
            %(latitude)s,
            %(longitude)s,
            %(stream_url)s,
            %(is_monitored)s,
            %(connection_status)s,
            %(video_quality_status)s,
            %(analysis_status)s,
            %(last_frame_at)s,
            %(region_code)s,
            %(monitored_mode)s
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
            stream_url = EXCLUDED.stream_url,
            region_code = EXCLUDED.region_code
        RETURNING id;
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query,
            cctv,
        )

        row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                "CCTV 저장 후 id를 반환받지 못했습니다."
            )

        return row[0]


def print_saved_cctvs(
    connection: psycopg.Connection,
) -> None:
    """
    현재 등록된 UTIC CCTV를 출력한다.
    """

    query = """
        SELECT
            id,
            external_cctv_id,
            name,
            provider,
            latitude,
            longitude,
            stream_url,
            is_monitored,
            connection_status,
            video_quality_status,
            analysis_status,
            last_frame_at,
            region_code,
            monitored_mode
        FROM cctvs
        WHERE provider = 'UTIC'
        ORDER BY id;
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query
        )

        rows = cursor.fetchall()

    print()
    print("=" * 70)
    print("UTIC CCTV")
    print("=" * 70)

    if not rows:
        print(
            "등록된 UTIC CCTV가 없습니다."
        )
        return

    for row in rows:

        (
            cctv_id,
            external_cctv_id,
            name,
            provider,
            latitude,
            longitude,
            stream_url,
            is_monitored,
            connection_status,
            video_quality_status,
            analysis_status,
            last_frame_at,
            region_code,
            monitored_mode,
        ) = row

        print()
        print(
            f"id                   : {cctv_id}"
        )
        print(
            f"external_cctv_id     : {external_cctv_id}"
        )
        print(
            f"name                 : {name}"
        )
        print(
            f"provider             : {provider}"
        )
        print(
            f"latitude             : {latitude}"
        )
        print(
            f"longitude            : {longitude}"
        )
        print(
            f"stream_url           : {stream_url}"
        )
        print(
            f"is_monitored         : {is_monitored}"
        )
        print(
            f"connection_status    : {connection_status}"
        )
        print(
            f"video_quality_status : {video_quality_status}"
        )
        print(
            f"analysis_status      : {analysis_status}"
        )
        print(
            f"last_frame_at        : {last_frame_at}"
        )
        print(
            f"region_code          : {region_code}"
        )
        print(
            f"monitored_mode       : {monitored_mode}"
        )


def main() -> None:

    database_config = load_database_config()

    print("=" * 70)
    print("OCTV CCTV REFERENCE DATA SYNC")
    print("=" * 70)

    with psycopg.connect(
        **database_config
    ) as connection:

        try:

            for cctv in CCTV_DATA:

                cctv_id = upsert_cctv(
                    connection,
                    cctv,
                )

                print(
                    "[UPSERT] "
                    f"id={cctv_id} "
                    f"/ provider={cctv['provider']} "
                    f"/ external_cctv_id="
                    f"{cctv['external_cctv_id']}"
                )

            connection.commit()

        except Exception:
            connection.rollback()
            raise

        print_saved_cctvs(
            connection
        )

    print()
    print(
        "[SUCCESS] CCTV 기준정보 동기화 완료"
    )


if __name__ == "__main__":
    main()