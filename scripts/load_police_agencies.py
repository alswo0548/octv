from pathlib import Path
import time

import requests
from dotenv import dotenv_values
from pyproj import Transformer
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

SERVICE_KEY = env.get("SAFETY_DATA_SERVICE_KEY")

if not SERVICE_KEY:
    raise ValueError(
        "backend/.env에 SAFETY_DATA_SERVICE_KEY가 없습니다."
    )


API_URL = (
    "https://www.safetydata.go.kr/"
    "V2/api/DSSP-IF-00080"
)


# ============================================================
# 좌표 변환
#
# API X/Y:
# EPSG:3857 Web Mercator
#
# -> WGS84 위경도
# ============================================================

TRANSFORMER = Transformer.from_crs(
    "EPSG:3857",
    "EPSG:4326",
    always_xy=True,
)


TARGET_SIDO = {
    "11": "서울특별시",
    "41": "경기도",
}


# ============================================================
# region 예외 매핑
#
# region_code는 기관 선택 등에 사용할 소속/관할 지역을 기준으로 함.
#
# 실제 위치는 latitude / longitude로 별도 보관.
# ============================================================

REGION_OVERRIDES = {
    # 서울강서경찰서는 현재 API 주소가 양천구로 잡혀 있음
    "서울강서경찰서": "11500",

    # 화성시는 API가 기존 상위 코드 41590을 반환
    "화성서부경찰서": "41591",   # 화성시 만세구
    "화성동탄경찰서": "41597",   # 화성시 동탄구
}


# ============================================================
# 공통 문자열 정리
# ============================================================

def clean_text(value) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


# ============================================================
# 응답에서 경찰 POI 행 찾기
# ============================================================

def find_police_items(value) -> list[dict]:
    result = []

    if isinstance(value, dict):
        if (
            "POLSTN_NM" in value
            and "FCLT_TYPE" in value
        ):
            result.append(value)

        for child in value.values():
            result.extend(
                find_police_items(child)
            )

    elif isinstance(value, list):
        for child in value:
            result.extend(
                find_police_items(child)
            )

    return result


# ============================================================
# API 한 페이지 조회
# ============================================================

def fetch_page(
    page_no: int,
    num_of_rows: int = 1000,
) -> dict:

    params = {
        "serviceKey": SERVICE_KEY,
        "returnType": "json",
        "pageNo": page_no,
        "numOfRows": num_of_rows,
    }

    max_retries = 5

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                API_URL,
                params=params,
                timeout=(10, 60),
            )

            response.raise_for_status()

            return response.json()

        except (RequestException, ValueError):
            if attempt == max_retries:
                raise RuntimeError(
                    f"{page_no}페이지 경찰 API 호출에 "
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
        "경찰 API 호출에 실패했습니다."
    )


# ============================================================
# 전체 경찰 POI 조회
# ============================================================

def fetch_all_items() -> list[dict]:
    page_no = 1
    num_of_rows = 1000

    all_items = []

    while True:
        data = fetch_page(
            page_no,
            num_of_rows,
        )

        items = find_police_items(
            data
        )

        total_count = int(
            data.get("totalCount", 0)
        )

        all_items.extend(items)

        print(
            f"  {page_no}페이지 완료 "
            f"({len(all_items)}/{total_count})"
        )

        if len(all_items) >= total_count:
            break

        if not items:
            raise RuntimeError(
                "전체 데이터를 가져오기 전에 "
                "빈 페이지가 반환되었습니다."
            )

        page_no += 1

        time.sleep(0.3)

    return all_items


# ============================================================
# 서울·경기 경찰서만 추출
# ============================================================

def extract_police_stations(
    items: list[dict],
) -> list[dict]:

    stations = []

    for item in items:
        sido_code = str(
            item.get(
                "STDG_CTPV_CD",
                "",
            )
        ).strip()

        if sido_code not in TARGET_SIDO:
            continue

        facility_type = str(
            item.get(
                "FCLT_TYPE",
                "",
            )
        ).strip()

        if facility_type != "경찰서":
            continue

        name = clean_text(
            item.get(
                "FCLT_GVMNFC_NM"
            )
        )

        if not name:
            raise RuntimeError(
                "경찰서명이 없는 데이터가 있습니다."
            )

        address = (
            clean_text(
                item.get(
                    "ROAD_NM_ADDR"
                )
            )
            or clean_text(
                item.get(
                    "ADDR"
                )
            )
        )

        if not address:
            raise RuntimeError(
                f"{name}의 주소가 없습니다."
            )

        x_value = clean_text(
            item.get(
                "XMAP_CRTS"
            )
        )

        y_value = clean_text(
            item.get(
                "YMAP_CRTS"
            )
        )

        if not x_value or not y_value:
            raise RuntimeError(
                f"{name}의 좌표가 없습니다."
            )

        longitude, latitude = (
            TRANSFORMER.transform(
                float(x_value),
                float(y_value),
            )
        )

        # 좌표 변환이 잘못됐을 경우 적재 방지
        if not (
            33.0 <= latitude <= 39.5
            and 124.0 <= longitude <= 132.0
        ):
            raise RuntimeError(
                f"{name}의 변환 좌표가 비정상입니다: "
                f"{latitude}, {longitude}"
            )

        api_region_code = str(
            item.get(
                "STDG_SGG_CD",
                "",
            )
        ).strip()

        stations.append(
            {
                "name": name,
                "sido_code": sido_code,
                "sido_name": TARGET_SIDO[
                    sido_code
                ],
                "api_region_code":
                    api_region_code,
                "address": address,
                "phone": clean_text(
                    item.get(
                        "TELNO"
                    )
                ),
                "latitude": round(
                    latitude,
                    7,
                ),
                "longitude": round(
                    longitude,
                    7,
                ),
            }
        )

    names = [
        station["name"]
        for station in stations
    ]

    if len(names) != len(set(names)):
        raise RuntimeError(
            "경찰서명 중복 데이터가 있습니다."
        )

    return stations


# ============================================================
# DB region 읽기
# ============================================================

def load_regions(
    connection,
) -> tuple[
    dict[str, dict],
    dict[str, list[dict]],
]:

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                region_code,
                sido_name,
                sigungu_name
            FROM region
            WHERE sido_name IN (
                '서울특별시',
                '경기도'
            )
            ORDER BY
                sido_name,
                length(sigungu_name) DESC,
                sigungu_name
            """
        )

        rows = cursor.fetchall()

    by_code = {
        row["region_code"]: row
        for row in rows
    }

    by_sido = {
        "서울특별시": [],
        "경기도": [],
    }

    for row in rows:
        by_sido[
            row["sido_name"]
        ].append(row)

    return (
        by_code,
        by_sido,
    )


# ============================================================
# 주소 표기 정규화
# ============================================================

def normalize_address(
    address: str,
) -> str:

    value = address.strip()

    if value.startswith(
        "서울시 "
    ):
        value = (
            "서울특별시 "
            + value[len("서울시 "):]
        )

    elif value.startswith(
        "서울 "
    ):
        value = (
            "서울특별시 "
            + value[len("서울 "):]
        )

    elif value.startswith(
        "경기 "
    ):
        value = (
            "경기도 "
            + value[len("경기 "):]
        )

    return value


# ============================================================
# 경찰서 -> region_code 결정
# ============================================================

def match_region(
    station: dict,
    regions_by_code: dict[str, dict],
    regions_by_sido: dict[str, list[dict]],
) -> tuple[str, str, str]:

    name = station["name"]

    # --------------------------------------------------------
    # 1. 명시적 예외
    # --------------------------------------------------------

    override_code = (
        REGION_OVERRIDES.get(
            name
        )
    )

    if override_code:
        region = regions_by_code.get(
            override_code
        )

        if region is None:
            raise RuntimeError(
                f"{name} 예외 region_code가 "
                f"DB에 없습니다: {override_code}"
            )

        return (
            override_code,
            region["sigungu_name"],
            "OVERRIDE",
        )


    # --------------------------------------------------------
    # 2. API 시군구코드가 현재 region에 존재하면 사용
    # --------------------------------------------------------

    api_code = station[
        "api_region_code"
    ]

    region = regions_by_code.get(
        api_code
    )

    if (
        region is not None
        and region["sido_name"]
        == station["sido_name"]
    ):
        return (
            api_code,
            region["sigungu_name"],
            "API_CODE",
        )


    # --------------------------------------------------------
    # 3. API 코드가 상위 시 코드 등이라면 주소로 세부 지역 검색
    #
    # 예:
    # 41190 + 부천시 원미구 주소
    # -> 41192
    # --------------------------------------------------------

    address = normalize_address(
        station["address"]
    )

    candidates = regions_by_sido[
        station["sido_name"]
    ]

    for region in candidates:
        sigungu_name = region[
            "sigungu_name"
        ]

        if sigungu_name in address:
            return (
                region["region_code"],
                sigungu_name,
                "ADDRESS",
            )


    raise RuntimeError(
        f"{name}의 region을 매칭하지 못했습니다.\n"
        f"API 코드: {api_code}\n"
        f"주소: {station['address']}"
    )


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
              AND agency_type = 'POLICE'
            """,
            (name,),
        )

        return cursor.fetchone()


# ============================================================
# INSERT
# ============================================================

def insert_agency(
    connection,
    station: dict,
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
                'POLICE',
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                station["name"],
                station["address"],
                station["latitude"],
                station["longitude"],
                station["phone"],
                station["region_code"],
            ),
        )


# ============================================================
# UPDATE
# ============================================================

def update_agency(
    connection,
    agency_id: int,
    station: dict,
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
                station["address"],
                station["latitude"],
                station["longitude"],
                station["phone"],
                station["region_code"],
                agency_id,
            ),
        )


# ============================================================
# DB 검증
# ============================================================

def verify_police_agencies() -> None:

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    r.sido_name,
                    COUNT(*) AS count
                FROM agencies a
                JOIN region r
                  ON r.region_code = a.region_code
                WHERE a.agency_type = 'POLICE'
                  AND r.sido_name IN (
                      '서울특별시',
                      '경기도'
                  )
                GROUP BY r.sido_name
                ORDER BY r.sido_name
                """
            )

            counts = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS count
                FROM agencies
                WHERE agency_type = 'POLICE'
                """
            )

            total = cursor.fetchone()[
                "count"
            ]

    print()
    print("=" * 70)
    print("POLICE 기관 DB 적재 결과")
    print("=" * 70)

    for row in counts:
        print(
            f'{row["sido_name"]:<8}'
            f' : {row["count"]}개'
        )

    print(
        f"전체       : {total}개"
    )

    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # 1. 전체 API 조회
    # --------------------------------------------------------

    print(
        "[1] 경찰 POI 전체 조회"
    )

    items = fetch_all_items()

    print(
        f"  전체 POI: "
        f"{len(items)}개"
    )


    # --------------------------------------------------------
    # 2. 서울·경기 경찰서만 추출
    # --------------------------------------------------------

    print()
    print(
        "[2] 서울·경기 경찰서 추출"
    )

    stations = (
        extract_police_stations(
            items
        )
    )

    seoul_count = sum(
        1
        for station in stations
        if station["sido_code"] == "11"
    )

    gyeonggi_count = sum(
        1
        for station in stations
        if station["sido_code"] == "41"
    )

    print(
        f"  서울: {seoul_count}개"
    )

    print(
        f"  경기: {gyeonggi_count}개"
    )

    print(
        f"  전체: {len(stations)}개"
    )


    if (
        seoul_count != 31
        or gyeonggi_count != 44
        or len(stations) != 75
    ):
        raise RuntimeError(
            "예상 경찰서 수와 일치하지 않습니다."
        )


    # --------------------------------------------------------
    # 3. region 매칭
    # --------------------------------------------------------

    print()
    print(
        "[3] region_code 매칭"
    )

    with get_connection() as connection:

        (
            regions_by_code,
            regions_by_sido,
        ) = load_regions(
            connection
        )


        for station in stations:

            (
                region_code,
                sigungu_name,
                match_method,
            ) = match_region(
                station,
                regions_by_code,
                regions_by_sido,
            )

            station[
                "region_code"
            ] = region_code

            station[
                "sigungu_name"
            ] = sigungu_name

            station[
                "match_method"
            ] = match_method


        print(
            f"  {len(stations)}개 "
            f"전체 매칭 완료"
        )


        # ----------------------------------------------------
        # 특수/주소 기반 매핑 확인
        # ----------------------------------------------------

        print()
        print(
            "[특수 매핑 확인]"
        )

        for station in stations:

            if (
                station[
                    "match_method"
                ]
                != "API_CODE"
            ):
                print(
                    f'  {station["name"]}'
                    f' | API={station["api_region_code"]}'
                    f' → DB={station["region_code"]}'
                    f' {station["sigungu_name"]}'
                    f' | {station["match_method"]}'
                )


        # ----------------------------------------------------
        # 4. DB 저장
        # ----------------------------------------------------

        print()
        print(
            "[4] DB 적재"
        )

        inserted = 0
        updated = 0

        for station in stations:

            existing = (
                find_existing_agency(
                    connection,
                    station["name"],
                )
            )

            if existing is None:

                insert_agency(
                    connection,
                    station,
                )

                inserted += 1

            else:

                update_agency(
                    connection,
                    existing["id"],
                    station,
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


    # --------------------------------------------------------
    # 5. 최종 검증
    # --------------------------------------------------------

    verify_police_agencies()


if __name__ == "__main__":
    main()