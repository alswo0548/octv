from pathlib import Path
import time

import requests
from dotenv import dotenv_values
from requests.exceptions import RequestException

from backend.app.db.session import get_connection


# ============================================================
# 환경 설정
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

env = dotenv_values(
    ROOT / "backend" / ".env",
    interpolate=False,
)

SERVICE_KEY = env.get("GYEONGGI_DATA_KEY")

if not SERVICE_KEY:
    raise ValueError(
        "backend/.env에 GYEONGGI_DATA_KEY가 없습니다."
    )


API_URL = (
    "https://openapi.gg.go.kr/GovernmentOffice"
)


# ============================================================
# API 기관명 예외
# ============================================================

OFFICE_NAME_OVERRIDES = {
    "남양주시": "남양주시청 제1청사",
}


# ============================================================
# API에 아직 없거나 최신 행정구역이 반영되지 않은 기관
#
# 주소/전화:
# 각 지자체 공식 홈페이지 기준
#
# 위경도:
# 해당 청사 주소의 최신 위치정보 기준
# ============================================================

FALLBACK_AGENCIES = {
    "41220": {
        "name": "평택시청",
        "address": "경기도 평택시 경기대로 245",
        "phone": "031-8024-5000",
        "latitude": 36.9926161,
        "longitude": 127.1137306,
    },

    "41370": {
        "name": "오산시청",
        "address": "경기도 오산시 성호대로 141",
        "phone": "031-8036-8036",
        "latitude": 37.1488789,
        "longitude": 127.0772833,
    },

    "41591": {
        "name": "만세구청",
        "address": "경기도 화성시 만세구 향남읍 향남로 470",
        "phone": "1577-4200",
        "latitude": 37.1374711,
        "longitude": 126.9246650,
    },

    "41593": {
        "name": "효행구청",
        "address": "경기도 화성시 효행구 봉담읍 최루백로 165",
        "phone": "1577-4200",
        "latitude": 37.2091946,
        "longitude": 126.9592549,
    },

    "41595": {
        "name": "병점구청",
        "address": "경기도 화성시 병점구 병점3로 23",
        "phone": "1577-4200",
        "latitude": 37.2087900,
        "longitude": 127.0359900,
    },

    "41597": {
        "name": "동탄구청",
        "address": "경기도 화성시 동탄구 동탄역로 122",
        "phone": "1577-4200",
        "latitude": 37.1972636,
        "longitude": 127.0968547,
    },
}


# ============================================================
# API 한 페이지 조회
# ============================================================

def fetch_page(
    page_no: int,
    page_size: int = 100,
) -> dict:

    params = {
        "KEY": SERVICE_KEY,
        "Type": "json",
        "pIndex": page_no,
        "pSize": page_size,
    }

    max_retries = 5

    for attempt in range(
        1,
        max_retries + 1,
    ):
        try:
            response = requests.get(
                API_URL,
                params=params,
                timeout=(10, 60),
            )

            response.raise_for_status()

            return response.json()

        except (
            RequestException,
            ValueError,
        ):
            if attempt == max_retries:
                raise RuntimeError(
                    f"{page_no}페이지 경기데이터 API 호출에 "
                    f"{max_retries}회 연속 실패했습니다."
                ) from None

            wait_seconds = attempt * 2

            print(
                f"  {page_no}페이지 연결 실패 "
                f"({attempt}/{max_retries}) "
                f"→ {wait_seconds}초 후 재시도"
            )

            time.sleep(wait_seconds)

    raise RuntimeError(
        "경기도 청사 API 호출에 실패했습니다."
    )


# ============================================================
# API 응답 추출
# ============================================================

def extract_response(
    data: dict,
) -> tuple[int, list[dict]]:

    dataset = data.get(
        "GovernmentOffice"
    )

    if not dataset:
        raise RuntimeError(
            "응답에 GovernmentOffice 데이터가 없습니다."
        )

    total_count = None
    rows = []

    for item in dataset:

        if "head" in item:

            for head_item in item["head"]:

                if (
                    "list_total_count"
                    in head_item
                ):
                    total_count = int(
                        head_item[
                            "list_total_count"
                        ]
                    )

                if "RESULT" in head_item:

                    result = (
                        head_item[
                            "RESULT"
                        ]
                    )

                    code = result.get(
                        "CODE"
                    )

                    message = result.get(
                        "MESSAGE"
                    )

                    if code != "INFO-000":
                        raise RuntimeError(
                            "경기데이터 API 오류: "
                            f"{code} / {message}"
                        )

        if "row" in item:

            rows.extend(
                item["row"]
            )

    if total_count is None:
        raise RuntimeError(
            "전체 데이터 개수를 확인하지 못했습니다."
        )

    return (
        total_count,
        rows,
    )


# ============================================================
# 전체 API 데이터 조회
# ============================================================

def fetch_all_rows() -> list[dict]:

    page_no = 1
    page_size = 100

    all_rows = []

    while True:

        data = fetch_page(
            page_no,
            page_size,
        )

        (
            total_count,
            rows,
        ) = extract_response(
            data
        )

        all_rows.extend(
            rows
        )

        print(
            f"  {page_no}페이지 완료 "
            f"({len(all_rows)}/{total_count})"
        )

        if len(all_rows) >= total_count:
            break

        if not rows:
            raise RuntimeError(
                "전체 데이터를 가져오기 전에 "
                "빈 페이지가 반환되었습니다."
            )

        page_no += 1

        time.sleep(0.3)

    return all_rows


# ============================================================
# 경기도 region 조회
# ============================================================

def load_gyeonggi_regions(
    connection,
) -> list[dict]:

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                region_code,
                sido_name,
                sigungu_name
            FROM region
            WHERE sido_name = '경기도'
            ORDER BY region_code
            """
        )

        return cursor.fetchall()


# ============================================================
# region -> 예상 청사명
# ============================================================

def expected_office_name(
    sigungu_name: str,
) -> str:

    override = (
        OFFICE_NAME_OVERRIDES.get(
            sigungu_name
        )
    )

    if override:
        return override


    parts = sigungu_name.split()


    # 수원시 장안구
    # -> 장안구청
    if (
        len(parts) >= 2
        and parts[-1].endswith("구")
    ):
        return (
            f"{parts[-1]}청"
        )


    # 의정부시
    # -> 의정부시청
    if sigungu_name.endswith("시"):
        return (
            f"{sigungu_name}청"
        )


    # 연천군
    # -> 연천군청
    if sigungu_name.endswith("군"):
        return (
            f"{sigungu_name}청"
        )


    raise RuntimeError(
        "기관명을 만들 수 없는 지역입니다: "
        f"{sigungu_name}"
    )


# ============================================================
# API 데이터 -> agency 데이터
# ============================================================

def build_api_agency(
    region: dict,
    row: dict,
) -> dict:

    latitude_value = row.get(
        "REFINE_WGS84_LAT"
    )

    longitude_value = row.get(
        "REFINE_WGS84_LOGT"
    )


    if (
        latitude_value is None
        or longitude_value is None
        or str(latitude_value).strip() == ""
        or str(longitude_value).strip() == ""
    ):
        raise RuntimeError(
            f'{row.get("DIV_NM")}의 좌표가 없습니다.'
        )


    address = (
        row.get(
            "REFINE_ROADNM_ADDR"
        )
        or row.get(
            "REFINE_LOTNO_ADDR"
        )
    )


    if not address:
        raise RuntimeError(
            f'{row.get("DIV_NM")}의 주소가 없습니다.'
        )


    phone = row.get(
        "TELNO_GUID"
    )

    if phone is not None:
        phone = str(
            phone
        ).strip()

        if not phone:
            phone = None


    return {
        "name": str(
            row["DIV_NM"]
        ).strip(),

        "agency_type":
            "LOCAL_GOVERNMENT",

        "address":
            str(address).strip(),

        "latitude":
            round(
                float(latitude_value),
                7,
            ),

        "longitude":
            round(
                float(longitude_value),
                7,
            ),

        "phone":
            phone,

        "region_code":
            region["region_code"],

        "sigungu_name":
            region["sigungu_name"],

        "source":
            "GYEONGGI_API",
    }


# ============================================================
# fallback 데이터 -> agency 데이터
# ============================================================

def build_fallback_agency(
    region: dict,
    fallback: dict,
) -> dict:

    return {
        "name":
            fallback["name"],

        "agency_type":
            "LOCAL_GOVERNMENT",

        "address":
            fallback["address"],

        "latitude":
            fallback["latitude"],

        "longitude":
            fallback["longitude"],

        "phone":
            fallback["phone"],

        "region_code":
            region["region_code"],

        "sigungu_name":
            region["sigungu_name"],

        "source":
            "FALLBACK",
    }


# ============================================================
# 전체 경기 기관 생성
# ============================================================

def build_agencies(
    regions: list[dict],
    api_rows: list[dict],
) -> list[dict]:

    rows_by_name = {}

    for row in api_rows:

        name = str(
            row.get(
                "DIV_NM",
                "",
            )
        ).strip()

        if not name:
            continue

        rows_by_name.setdefault(
            name,
            [],
        ).append(row)


    agencies = []


    for region in regions:

        region_code = (
            region["region_code"]
        )


        # ----------------------------------------------------
        # 1. 최신자료 fallback
        # ----------------------------------------------------

        fallback = (
            FALLBACK_AGENCIES.get(
                region_code
            )
        )

        if fallback:

            agency = (
                build_fallback_agency(
                    region,
                    fallback,
                )
            )

            agencies.append(
                agency
            )

            continue


        # ----------------------------------------------------
        # 2. 경기데이터 API
        # ----------------------------------------------------

        office_name = (
            expected_office_name(
                region[
                    "sigungu_name"
                ]
            )
        )

        candidates = (
            rows_by_name.get(
                office_name,
                [],
            )
        )


        if len(candidates) == 0:
            raise RuntimeError(
                f"기관을 찾지 못했습니다: "
                f"{region_code} / "
                f'{region["sigungu_name"]} / '
                f"{office_name}"
            )


        if len(candidates) > 1:
            raise RuntimeError(
                f"{office_name}이 "
                f"{len(candidates)}개 존재합니다."
            )


        agency = build_api_agency(
            region,
            candidates[0],
        )

        agencies.append(
            agency
        )


    return agencies


# ============================================================
# 기존 기관 조회
# ============================================================

def find_existing_agency(
    connection,
    name: str,
) -> dict | None:

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                id,
                name
            FROM agencies
            WHERE name = %s
              AND agency_type = 'LOCAL_GOVERNMENT'
            """,
            (name,),
        )

        return cursor.fetchone()


# ============================================================
# INSERT
# ============================================================

def insert_agency(
    connection,
    agency: dict,
) -> None:

    with connection.cursor() as cursor:

        cursor.execute(
            """
            INSERT INTO agencies (
                name,
                agency_type,
                address,
                latitude,
                longitude,
                phone,
                region_code
            )
            VALUES (
                %s,
                'LOCAL_GOVERNMENT',
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                agency["name"],
                agency["address"],
                agency["latitude"],
                agency["longitude"],
                agency["phone"],
                agency["region_code"],
            ),
        )


# ============================================================
# UPDATE
# ============================================================

def update_agency(
    connection,
    agency_id: int,
    agency: dict,
) -> None:

    with connection.cursor() as cursor:

        cursor.execute(
            """
            UPDATE agencies
            SET
                address = %s,
                latitude = %s,
                longitude = %s,
                phone = %s,
                region_code = %s
            WHERE id = %s
            """,
            (
                agency["address"],
                agency["latitude"],
                agency["longitude"],
                agency["phone"],
                agency["region_code"],
                agency_id,
            ),
        )


# ============================================================
# 최종 검증
# ============================================================

def verify_gyeonggi() -> None:

    with get_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS count
                FROM agencies a
                JOIN region r
                  ON r.region_code = a.region_code
                WHERE
                    a.agency_type = 'LOCAL_GOVERNMENT'
                    AND r.sido_name = '경기도'
                """
            )

            count = (
                cursor.fetchone()[
                    "count"
                ]
            )


            cursor.execute(
                """
                SELECT
                    a.name,
                    a.region_code,
                    r.sigungu_name,
                    a.address,
                    a.latitude,
                    a.longitude,
                    a.phone
                FROM agencies a
                JOIN region r
                  ON r.region_code = a.region_code
                WHERE
                    a.agency_type = 'LOCAL_GOVERNMENT'
                    AND r.sido_name = '경기도'
                ORDER BY a.region_code
                """
            )

            rows = cursor.fetchall()


    print()
    print("=" * 110)
    print(
        "경기도 LOCAL_GOVERNMENT DB 확인"
    )
    print("=" * 110)


    for row in rows:

        print(
            f'{row["region_code"]}'
            f' | {row["sigungu_name"]:<12}'
            f' | {row["name"]:<15}'
            f' | {row["latitude"]}'
            f' | {row["longitude"]}'
            f' | {row["phone"]}'
        )


    print()
    print(
        f"경기도 LOCAL_GOVERNMENT 기관 수: "
        f"{count}"
    )

    print("=" * 110)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "[1] 경기도 청사 API 전체 조회"
    )

    api_rows = (
        fetch_all_rows()
    )

    print(
        f"  전체 데이터: "
        f"{len(api_rows)}개"
    )


    print()
    print(
        "[2] 경기도 region 조회"
    )


    with get_connection() as connection:

        regions = (
            load_gyeonggi_regions(
                connection
            )
        )


    print(
        f"  경기도 region: "
        f"{len(regions)}개"
    )


    if len(regions) != 47:
        raise RuntimeError(
            "경기도 region 수가 "
            f"47개가 아닙니다: "
            f"{len(regions)}개"
        )


    print()
    print(
        "[3] LOCAL_GOVERNMENT 데이터 생성"
    )


    agencies = build_agencies(
        regions,
        api_rows,
    )


    if len(agencies) != 47:
        raise RuntimeError(
            "경기도 LOCAL_GOVERNMENT가 "
            f"47개가 아닙니다: "
            f"{len(agencies)}개"
        )


    print(
        f"  전체 {len(agencies)}개 생성 완료"
    )


    # --------------------------------------------------------
    # fallback 확인
    # --------------------------------------------------------

    print()
    print(
        "[보완 데이터 확인]"
    )


    for agency in agencies:

        if (
            agency["source"]
            == "FALLBACK"
        ):
            print(
                f'  {agency["region_code"]}'
                f' | {agency["sigungu_name"]}'
                f' | {agency["name"]}'
                f' | {agency["address"]}'
                f' | {agency["latitude"]}'
                f' | {agency["longitude"]}'
            )


    # --------------------------------------------------------
    # DB 적재
    # --------------------------------------------------------

    print()
    print(
        "[4] DB 적재"
    )


    inserted = 0
    updated = 0


    with get_connection() as connection:

        for agency in agencies:

            existing = (
                find_existing_agency(
                    connection,
                    agency["name"],
                )
            )


            if existing is None:

                insert_agency(
                    connection,
                    agency,
                )

                inserted += 1


            else:

                update_agency(
                    connection,
                    existing["id"],
                    agency,
                )

                updated += 1


    print(
        f"  신규 INSERT: "
        f"{inserted}개"
    )

    print(
        f"  기존 UPDATE: "
        f"{updated}개"
    )


    verify_gyeonggi()


if __name__ == "__main__":
    main()