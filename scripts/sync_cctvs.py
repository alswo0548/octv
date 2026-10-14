"""OCTV UTIC CCTV 기준정보 동기화 스크립트."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
import requests
from dotenv import load_dotenv
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry


# ============================================================
# 경로
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

ROOT_ENV_PATH = ROOT / ".env"
BACKEND_ENV_PATH = ROOT / "backend" / ".env"

DEFAULT_CCTV_FILE = (
    ROOT
    / "data"
    / "OpenDataCCTV.xlsx"
)


# ============================================================
# 상수
# ============================================================

VWORLD_API_URL = "https://api.vworld.kr/req/data"

VWORLD_DATASET = "LT_C_ADSIGG_INFO"

TARGET_SIDO_CODES = {
    "11": "서울특별시",
    "41": "경기도",
}

PROVIDER = "UTIC"

TEST_CCTV_ID = "E910012"


# ============================================================
# 지역 Polygon
# ============================================================

@dataclass
class RegionPolygon:
    region_code: str
    region_name: str
    geometry: BaseGeometry

    @property
    def bounds(
        self,
    ) -> tuple[float, float, float, float]:
        return self.geometry.bounds

    def contains_point(
        self,
        longitude: float,
        latitude: float,
    ) -> bool:

        min_x, min_y, max_x, max_y = self.bounds

        # 먼저 bounding box로 빠르게 제외
        if not (
            min_x <= longitude <= max_x
            and min_y <= latitude <= max_y
        ):
            return False

        point = Point(
            longitude,
            latitude,
        )

        # 경계선 위의 좌표도 포함
        return self.geometry.covers(point)


# ============================================================
# 환경변수
# ============================================================

def load_environment() -> dict[str, Any]:
    """
    backend/.env에서
    PostgreSQL / VWorld 설정을 읽는다.
    """

    if ROOT_ENV_PATH.exists():
        load_dotenv(
            dotenv_path=ROOT_ENV_PATH
        )

    if BACKEND_ENV_PATH.exists():
        load_dotenv(
            dotenv_path=BACKEND_ENV_PATH,
            override=True,
        )

    if (
        not ROOT_ENV_PATH.exists()
        and not BACKEND_ENV_PATH.exists()
    ):
        raise FileNotFoundError(
            ".env 파일을 찾을 수 없습니다.\n"
            f"- {ROOT_ENV_PATH}\n"
            f"- {BACKEND_ENV_PATH}"
        )

    db_name = os.getenv("POSTGRES_DB")
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_port = os.getenv("POSTGRES_PORT")

    vworld_api_key = os.getenv("VWORLD_API_KEY")

    # VWorld Key 발급 시 특정 도메인을 등록했다면
    # .env에 VWORLD_DOMAIN을 추가해서 사용할 수 있다.
    vworld_domain = os.getenv("VWORLD_DOMAIN")

    missing = []

    if not db_name:
        missing.append("POSTGRES_DB")

    if not db_user:
        missing.append("POSTGRES_USER")

    if not db_password:
        missing.append("POSTGRES_PASSWORD")

    if not db_port:
        missing.append("POSTGRES_PORT")

    if not vworld_api_key:
        missing.append("VWORLD_API_KEY")

    if missing:
        raise RuntimeError(
            ".env에 다음 설정이 없습니다: "
            + ", ".join(missing)
        )

    return {
        "database": {
            "host": "127.0.0.1",
            "port": int(db_port),
            "dbname": db_name,
            "user": db_user,
            "password": db_password,
        },
        "vworld_api_key": vworld_api_key,
        "vworld_domain": vworld_domain,
    }


# ============================================================
# UTIC Excel
# ============================================================

def load_cctv_excel(
    file_path: Path,
) -> pd.DataFrame:
    """
    UTIC 공식 OpenDataCCTV.xlsx를 읽는다.
    """

    if not file_path.exists():
        raise FileNotFoundError(
            "\nUTIC CCTV 파일을 찾을 수 없습니다.\n"
            f"예상 위치: {file_path}"
        )

    print()
    print("=" * 70)
    print("1. UTIC CCTV 파일 읽기")
    print("=" * 70)

    print(
        f"파일: {file_path}"
    )

    dataframe = pd.read_excel(
        file_path,
        engine="openpyxl",
    )

    # 컬럼명 공백 제거
    dataframe.columns = [
        str(column).strip().upper()
        for column in dataframe.columns
    ]

    required_columns = {
        "CCTVID",
        "CCTVNAME",
        "XCOORD",
        "YCOORD",
    }

    missing_columns = (
        required_columns
        - set(dataframe.columns)
    )

    if missing_columns:
        raise RuntimeError(
            "필수 컬럼이 없습니다: "
            + ", ".join(
                sorted(missing_columns)
            )
        )

    original_count = len(dataframe)

    dataframe = dataframe[
        [
            "CCTVID",
            "CCTVNAME",
            "XCOORD",
            "YCOORD",
        ]
    ].copy()

    dataframe["CCTVID"] = (
        dataframe["CCTVID"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    dataframe["CCTVNAME"] = (
        dataframe["CCTVNAME"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    dataframe["XCOORD"] = pd.to_numeric(
        dataframe["XCOORD"],
        errors="coerce",
    )

    dataframe["YCOORD"] = pd.to_numeric(
        dataframe["YCOORD"],
        errors="coerce",
    )

    # 필수 데이터가 없는 행 제거
    dataframe = dataframe[
        dataframe["CCTVID"] != ""
    ]

    dataframe = dataframe.dropna(
        subset=[
            "XCOORD",
            "YCOORD",
        ]
    )

    # 대한민국 범위를 크게 벗어난 이상 좌표 제거
    dataframe = dataframe[
        dataframe["XCOORD"].between(
            124.0,
            132.0,
        )
        & dataframe["YCOORD"].between(
            33.0,
            39.5,
        )
    ]

    # CCTVID가 중복되어 있으면 마지막 행 사용
    dataframe = dataframe.drop_duplicates(
        subset=["CCTVID"],
        keep="last",
    )

    dataframe = dataframe.reset_index(
        drop=True
    )

    print(
        f"원본 CCTV        : {original_count:,}개"
    )

    print(
        f"유효 CCTV        : {len(dataframe):,}개"
    )

    print(
        "제외 CCTV        : "
        f"{original_count - len(dataframe):,}개"
    )

    return dataframe


# ============================================================
# VWorld
# ============================================================

def request_vworld_regions(
    sido_code: str,
    api_key: str,
    domain: str | None,
) -> list[dict]:
    """
    VWorld에서 특정 시도의 시군구 경계를 가져온다.
    """

    params = {
        "service": "data",
        "version": "2.0",
        "request": "GetFeature",
        "format": "json",
        "size": "1000",
        "page": "1",
        "data": VWORLD_DATASET,
        "geometry": "true",
        "attribute": "true",
        "crs": "EPSG:4326",
        "attrFilter": (
            f"sig_cd:like:{sido_code}"
        ),
        "key": api_key,
    }

    if domain:
        params["domain"] = domain

    response = requests.get(
        VWORLD_API_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    api_response = payload.get(
        "response",
        {}
    )

    status = api_response.get(
        "status"
    )

    if status != "OK":

        error = (
            api_response.get("error")
            or {}
        )

        raise RuntimeError(
            "\nVWorld API 호출에 실패했습니다.\n"
            f"시도 코드: {sido_code}\n"
            f"상태: {status}\n"
            f"오류 코드: {error.get('code')}\n"
            f"오류 내용: {error.get('text')}\n"
            "\n"
            "VWorld Key 발급 시 도메인을 등록했다면 "
            "backend/.env에 다음 값도 추가해 주세요.\n"
            "VWORLD_DOMAIN=등록한도메인"
        )

    result = (
        api_response.get("result")
        or {}
    )

    feature_collection = (
        result.get("featureCollection")
        or {}
    )

    return (
        feature_collection.get("features")
        or []
    )


def load_region_polygons(
    api_key: str,
    domain: str | None,
) -> list[RegionPolygon]:
    """
    서울특별시 + 경기도 시군구 Polygon을 가져온다.
    """

    print()
    print("=" * 70)
    print("2. VWorld 시군구 경계 조회")
    print("=" * 70)

    polygons: list[RegionPolygon] = []

    for (
        sido_code,
        sido_name,
    ) in TARGET_SIDO_CODES.items():

        features = request_vworld_regions(
            sido_code=sido_code,
            api_key=api_key,
            domain=domain,
        )

        print(
            f"{sido_name:<10}: "
            f"{len(features):,}개"
        )

        for feature in features:

            properties = (
                feature.get("properties")
                or {}
            )

            geometry_json = feature.get(
                "geometry"
            )

            if not geometry_json:
                continue

            region_code = str(
                properties.get("sig_cd")
                or ""
            ).strip()

            region_name = str(
                properties.get("sig_kor_nm")
                or ""
            ).strip()

            if not region_code:
                continue

            geometry = shape(
                geometry_json
            )

            if geometry.is_empty:
                continue

            # 간혹 invalid geometry가 있을 경우 보정
            if not geometry.is_valid:
                geometry = geometry.buffer(0)

            polygons.append(
                RegionPolygon(
                    region_code=region_code,
                    region_name=region_name,
                    geometry=geometry,
                )
            )

    if not polygons:
        raise RuntimeError(
            "VWorld에서 서울·경기 시군구 경계를 "
            "가져오지 못했습니다."
        )

    print()
    print(
        f"전체 Polygon     : {len(polygons):,}개"
    )

    return polygons


# ============================================================
# Point-in-Polygon
# ============================================================

def find_region(
    longitude: float,
    latitude: float,
    polygons: list[RegionPolygon],
) -> RegionPolygon | None:

    for region in polygons:

        if region.contains_point(
            longitude,
            latitude,
        ):
            return region

    return None


def match_cctvs_to_regions(
    dataframe: pd.DataFrame,
    polygons: list[RegionPolygon],
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    CCTV 좌표를 시군구 Polygon과 매칭한다.

    반환:
        matched
        unmatched
    """

    print()
    print("=" * 70)
    print("3. CCTV 좌표 → 시군구 매칭")
    print("=" * 70)

    result_rows = []

    total = len(dataframe)

    for index, row in enumerate(
        dataframe.itertuples(index=False),
        start=1,
    ):

        longitude = float(
            row.XCOORD
        )

        latitude = float(
            row.YCOORD
        )

        region = find_region(
            longitude=longitude,
            latitude=latitude,
            polygons=polygons,
        )

        result_rows.append(
            {
                "CCTVID": row.CCTVID,
                "CCTVNAME": row.CCTVNAME,
                "XCOORD": longitude,
                "YCOORD": latitude,
                "REGION_CODE": (
                    region.region_code
                    if region
                    else None
                ),
                "REGION_NAME": (
                    region.region_name
                    if region
                    else None
                ),
            }
        )

        if (
            index % 1000 == 0
            or index == total
        ):
            print(
                "\r"
                f"처리 중           : "
                f"{index:,}/{total:,}",
                end="",
                flush=True,
            )

    print()

    result = pd.DataFrame(
        result_rows
    )

    matched = result[
        result["REGION_CODE"].notna()
    ].copy()

    unmatched = result[
        result["REGION_CODE"].isna()
    ].copy()

    seoul_count = (
        matched["REGION_CODE"]
        .astype(str)
        .str.startswith("11")
        .sum()
    )

    gyeonggi_count = (
        matched["REGION_CODE"]
        .astype(str)
        .str.startswith("41")
        .sum()
    )

    print()
    print(
        f"서울특별시        : {seoul_count:,}개"
    )

    print(
        f"경기도            : {gyeonggi_count:,}개"
    )

    print(
        f"서울·경기 합계    : {len(matched):,}개"
    )

    print(
        "서울·경기 외      : "
        f"{len(unmatched):,}개"
    )

    return (
        matched,
        unmatched,
    )


# ============================================================
# 테스트 CCTV 출력
# ============================================================

def print_test_cctv(
    dataframe: pd.DataFrame,
) -> None:
    """
    E910012 지역 판정 결과를 출력한다.
    """

    target = dataframe[
        dataframe["CCTVID"]
        == TEST_CCTV_ID
    ]

    print()
    print("=" * 70)
    print(f"검증 CCTV: {TEST_CCTV_ID}")
    print("=" * 70)

    if target.empty:
        print(
            "서울·경기 매칭 결과에서 "
            f"{TEST_CCTV_ID}를 찾지 못했습니다."
        )
        return

    row = target.iloc[0]

    print(
        f"CCTV ID           : {row['CCTVID']}"
    )

    print(
        f"이름              : {row['CCTVNAME']}"
    )

    print(
        f"위도              : {row['YCOORD']}"
    )

    print(
        f"경도              : {row['XCOORD']}"
    )

    print(
        f"시군구            : {row['REGION_NAME']}"
    )

    print(
        f"region_code       : {row['REGION_CODE']}"
    )


# ============================================================
# DB region 검증
# ============================================================

def load_database_region_codes(
    connection: psycopg.Connection,
) -> dict[str, tuple[str, str]]:
    """
    DB region 테이블에서
    서울/경기 region_code를 읽는다.
    """

    query = """
        SELECT
            region_code,
            sido_name,
            sigungu_name
        FROM region
        WHERE region_code LIKE '11%%'
           OR region_code LIKE '41%%'
        ORDER BY region_code;
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query
        )

        rows = cursor.fetchall()

    return {
        str(region_code): (
            sido_name,
            sigungu_name,
        )
        for (
            region_code,
            sido_name,
            sigungu_name,
        ) in rows
    }


def filter_valid_regions(
    connection: psycopg.Connection,
    dataframe: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    VWorld에서 얻은 region_code가
    실제 DB region 테이블에도 존재하는지 확인한다.
    """

    print()
    print("=" * 70)
    print("4. DB region 코드 검증")
    print("=" * 70)

    database_regions = (
        load_database_region_codes(
            connection
        )
    )

    print(
        "DB 서울·경기 region: "
        f"{len(database_regions):,}개"
    )

    valid_mask = (
        dataframe["REGION_CODE"]
        .astype(str)
        .isin(
            database_regions.keys()
        )
    )

    valid = dataframe[
        valid_mask
    ].copy()

    invalid = dataframe[
        ~valid_mask
    ].copy()

    print(
        f"DB 매칭 성공       : {len(valid):,}개"
    )

    print(
        f"DB region 불일치  : {len(invalid):,}개"
    )

    if not invalid.empty:

        invalid_codes = (
            invalid[
                [
                    "REGION_CODE",
                    "REGION_NAME",
                ]
            ]
            .drop_duplicates()
            .sort_values(
                "REGION_CODE"
            )
        )

        print()
        print(
            "[경고] VWorld에는 있지만 "
            "region 테이블에는 없는 코드"
        )

        for row in (
            invalid_codes
            .itertuples(index=False)
        ):

            print(
                f"  - "
                f"{row.REGION_CODE} "
                f"/ {row.REGION_NAME}"
            )

    return (
        valid,
        invalid,
    )


# ============================================================
# CCTV dict 생성
# ============================================================

def build_cctv_records(
    dataframe: pd.DataFrame,
) -> list[dict]:
    """
    DataFrame → cctvs UPSERT용 dict 변환
    """

    records = []

    for row in dataframe.itertuples(
        index=False
    ):

        records.append(
            {
                "external_cctv_id": (
                    str(
                        row.CCTVID
                    ).strip()
                ),
                "name": (
                    str(
                        row.CCTVNAME
                    ).strip()
                ),
                "provider": PROVIDER,
                "address": None,
                "latitude": float(
                    row.YCOORD
                ),
                "longitude": float(
                    row.XCOORD
                ),
                "stream_url": None,

                # 신규 CCTV 기본값
                "is_monitored": False,
                "connection_status": (
                    "DISCONNECTED"
                ),
                "video_quality_status": (
                    "UNAVAILABLE"
                ),
                "analysis_status": (
                    "STOPPED"
                ),
                "last_frame_at": None,
                "region_code": str(
                    row.REGION_CODE
                ),
                "monitored_mode": "BASE",
            }
        )

    return records


# ============================================================
# 기존/신규 개수 계산
# ============================================================

def get_existing_cctv_ids(
    connection: psycopg.Connection,
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

        rows = cursor.fetchall()

    return {
        str(row[0])
        for row in rows
    }


def print_sync_plan(
    connection: psycopg.Connection,
    records: list[dict],
) -> tuple[int, int]:

    existing_ids = (
        get_existing_cctv_ids(
            connection
        )
    )

    insert_count = 0
    update_count = 0

    for cctv in records:

        if (
            cctv["external_cctv_id"]
            in existing_ids
        ):
            update_count += 1

        else:
            insert_count += 1

    print()
    print("=" * 70)
    print("5. CCTV 동기화 계획")
    print("=" * 70)

    print(
        f"동기화 대상       : {len(records):,}개"
    )

    print(
        f"신규 INSERT       : {insert_count:,}개"
    )

    print(
        f"기존 UPDATE       : {update_count:,}개"
    )

    return (
        insert_count,
        update_count,
    )


# ============================================================
# UPSERT
# ============================================================

def upsert_cctvs(
    connection: psycopg.Connection,
    records: list[dict],
) -> None:
    """
    provider + external_cctv_id 기준 UPSERT.

    신규:
        모든 초기값 저장.

    기존:
        name
        latitude
        longitude
        region_code

    만 갱신한다.

    런타임 상태는 절대로 덮어쓰지 않는다.
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
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            region_code = EXCLUDED.region_code;
    """

    with connection.cursor() as cursor:

        cursor.executemany(
            query,
            records,
        )


# ============================================================
# 저장 결과 확인
# ============================================================

def print_database_summary(
    connection: psycopg.Connection,
) -> None:

    query = """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (
                WHERE region_code LIKE '11%%'
            ) AS seoul,
            COUNT(*) FILTER (
                WHERE region_code LIKE '41%%'
            ) AS gyeonggi,
            COUNT(*) FILTER (
                WHERE is_monitored = TRUE
            ) AS monitored
        FROM cctvs
        WHERE provider = 'UTIC';
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query
        )

        row = cursor.fetchone()

    if row is None:
        return

    (
        total,
        seoul,
        gyeonggi,
        monitored,
    ) = row

    print()
    print("=" * 70)
    print("DB 저장 결과")
    print("=" * 70)

    print(
        f"UTIC 전체         : {total:,}개"
    )

    print(
        f"서울              : {seoul:,}개"
    )

    print(
        f"경기              : {gyeonggi:,}개"
    )

    print(
        f"현재 감시 중      : {monitored:,}개"
    )


def print_database_test_cctv(
    connection: psycopg.Connection,
) -> None:

    query = """
        SELECT
            id,
            external_cctv_id,
            name,
            latitude,
            longitude,
            region_code,
            is_monitored,
            monitored_mode,
            connection_status,
            video_quality_status,
            analysis_status
        FROM cctvs
        WHERE provider = 'UTIC'
          AND external_cctv_id = %s;
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query,
            (TEST_CCTV_ID,),
        )

        row = cursor.fetchone()

    print()
    print("=" * 70)
    print(f"DB 검증 CCTV: {TEST_CCTV_ID}")
    print("=" * 70)

    if row is None:
        print(
            "DB에서 CCTV를 찾지 못했습니다."
        )
        return

    (
        cctv_id,
        external_cctv_id,
        name,
        latitude,
        longitude,
        region_code,
        is_monitored,
        monitored_mode,
        connection_status,
        video_quality_status,
        analysis_status,
    ) = row

    print(
        f"id                 : {cctv_id}"
    )

    print(
        f"external_cctv_id   : {external_cctv_id}"
    )

    print(
        f"name               : {name}"
    )

    print(
        f"latitude           : {latitude}"
    )

    print(
        f"longitude          : {longitude}"
    )

    print(
        f"region_code        : {region_code}"
    )

    print(
        f"is_monitored       : {is_monitored}"
    )

    print(
        f"monitored_mode     : {monitored_mode}"
    )

    print(
        f"connection_status  : {connection_status}"
    )

    print(
        "video_quality_status: "
        f"{video_quality_status}"
    )

    print(
        f"analysis_status    : {analysis_status}"
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "UTIC CCTV를 서울·경기 시군구와 "
            "매칭하여 cctvs 테이블에 동기화합니다."
        )
    )

    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_CCTV_FILE,
        help=(
            "UTIC OpenDataCCTV.xlsx 경로"
        ),
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "실제로 DB에 INSERT/UPDATE 합니다. "
            "옵션이 없으면 DRY-RUN입니다."
        ),
    )

    args = parser.parse_args()

    print()
    print("=" * 70)
    print("OCTV UTIC CCTV REFERENCE DATA SYNC")
    print("=" * 70)

    print(
        "실행 모드         : "
        + (
            "APPLY"
            if args.apply
            else "DRY-RUN"
        )
    )

    environment = load_environment()

    dataframe = load_cctv_excel(
        args.file.resolve()
    )

    polygons = load_region_polygons(
        api_key=environment[
            "vworld_api_key"
        ],
        domain=environment[
            "vworld_domain"
        ],
    )

    (
        matched_dataframe,
        unmatched_dataframe,
    ) = match_cctvs_to_regions(
        dataframe=dataframe,
        polygons=polygons,
    )

    # VWorld 좌표 판정 결과부터 확인
    print_test_cctv(
        matched_dataframe
    )

    database_config = (
        environment["database"]
    )

    with psycopg.connect(
        **database_config
    ) as connection:

        (
            valid_dataframe,
            invalid_dataframe,
        ) = filter_valid_regions(
            connection=connection,
            dataframe=matched_dataframe,
        )

        records = build_cctv_records(
            valid_dataframe
        )

        print_sync_plan(
            connection=connection,
            records=records,
        )

        # --------------------------------------------
        # DRY-RUN
        # --------------------------------------------

        if not args.apply:

            connection.rollback()

            print()
            print("=" * 70)
            print("DRY-RUN 완료")
            print("=" * 70)

            print(
                "DB는 변경되지 않았습니다."
            )

            print()
            print(
                "위 결과가 정상이라면 다음 명령으로 "
                "실제 반영하세요."
            )

            print()
            print(
                ".venv\\Scripts\\python "
                "scripts\\sync_cctvs.py "
                "--apply"
            )

            return

        # --------------------------------------------
        # APPLY
        # --------------------------------------------

        try:

            print()
            print("=" * 70)
            print("6. DB UPSERT")
            print("=" * 70)

            upsert_cctvs(
                connection=connection,
                records=records,
            )

            connection.commit()

            print(
                f"[SUCCESS] {len(records):,}개 "
                "CCTV 동기화 완료"
            )

        except Exception:

            connection.rollback()
            raise

        print_database_summary(
            connection
        )

        print_database_test_cctv(
            connection
        )

    print()
    print("=" * 70)
    print("CCTV 기준정보 동기화 완료")
    print("=" * 70)


if __name__ == "__main__":
    main()