from pathlib import Path
import json
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

SERVICE_KEY = env.get(
    "SAFETY_DATA_COMMON_POI_KEY"
)

if not SERVICE_KEY:
    raise ValueError(
        "backend/.env에 "
        "SAFETY_DATA_COMMON_POI_KEY가 없습니다."
    )


API_URL = (
    "https://www.safetydata.go.kr/"
    "V2/api/DSSP-IF-00079"
)


CACHE_PATH = (
    ROOT
    / "database"
    / "reference"
    / "common_poi"
    / "common_poi_cache.json"
)


# ============================================================
# 공통POI 좌표
#
# X/Y = EPSG:3857
# -> WGS84
# ============================================================

TRANSFORMER = Transformer.from_crs(
    "EPSG:3857",
    "EPSG:4326",
    always_xy=True,
)


# ============================================================
# 공통POI에 없는 서울 8개 구청
#
# 주소/전화번호:
# 각 자치구 공식 홈페이지 기준
#
# 좌표:
# 현행 도로명주소 위치 기준
# ============================================================

FALLBACK_AGENCIES = {

    "11230": {
        "name": "동대문구청",
        "address": "서울특별시 동대문구 천호대로 145",
        "phone": "02-2127-4114",
        "latitude": 37.5743694,
        "longitude": 127.0397079,
    },

    "11260": {
        "name": "중랑구청",
        "address": "서울특별시 중랑구 봉화산로 179",
        "phone": "02-2094-0114",
        "latitude": 37.6062618,
        "longitude": 127.0930485,
    },

    "11290": {
        "name": "성북구청",
        "address": "서울특별시 성북구 보문로 168",
        "phone": "02-2241-3114",
        "latitude": 37.5894563,
        "longitude": 127.0168496,
    },

    "11305": {
        "name": "강북구청",
        "address": "서울특별시 강북구 덕릉로 138",
        "phone": "02-901-6114",
        "latitude": 37.6349246,
        "longitude": 127.0290954,
    },

    "11320": {
        "name": "도봉구청",
        "address": "서울특별시 도봉구 마들로 656",
        "phone": "02-2091-2120",
        "latitude": 37.6687017,
        "longitude": 127.0470068,
    },

    "11350": {
        "name": "노원구청",
        "address": "서울특별시 노원구 노해로 437",
        "phone": "02-2116-3114",
        "latitude": 37.6536180,
        "longitude": 127.0567027,
    },

    "11380": {
        "name": "은평구청",
        "address": "서울특별시 은평구 은평로 195",
        "phone": "02-351-6114",
        "latitude": 37.6021756,
        "longitude": 126.9293379,
    },

    "11410": {
        "name": "서대문구청",
        "address": "서울특별시 서대문구 연희로 248",
        "phone": "02-330-1114",
        "latitude": 37.5792073,
        "longitude": 126.9362844,
    },
}


# ============================================================
# 문자열 정리
# ============================================================

def clean_text(value) -> str | None:

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


# ============================================================
# 공통POI 행 추출
# ============================================================

def find_poi_items(value) -> list[dict]:

    result = []

    if isinstance(value, dict):

        if (
            "FCLT_GVMNFC_NM" in value
            and "STDG_CTPV_CD" in value
        ):
            result.append(value)

        for child in value.values():
            result.extend(
                find_poi_items(child)
            )

    elif isinstance(value, list):

        for child in value:
            result.extend(
                find_poi_items(child)
            )

    return result


# ============================================================
# API 한 페이지
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
                    f"{page_no}페이지 공통POI API 호출에 "
                    f"{max_retries}회 연속 실패했습니다."
                ) from None

            wait_seconds = (
                attempt * 2
            )

            print(
                f"  {page_no}페이지 연결 실패 "
                f"({attempt}/{max_retries}) "
                f"→ {wait_seconds}초 후 재시도"
            )

            time.sleep(
                wait_seconds
            )

    raise RuntimeError(
        "공통POI API 호출에 실패했습니다."
    )


# ============================================================
# 전체 POI
#
# 캐시가 있으면 캐시 사용
# ============================================================

def load_all_poi() -> list[dict]:

    if CACHE_PATH.exists():

        print(
            "  저장된 공통POI 캐시를 사용합니다."
        )

        with CACHE_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:

            items = json.load(
                file
            )

        print(
            f"  캐시 데이터: "
            f"{len(items)}개"
        )

        return items


    print(
        "  캐시가 없어 API 전체 조회를 시작합니다."
    )

    page_no = 1
    num_of_rows = 1000

    all_items = []

    while True:

        data = fetch_page(
            page_no,
            num_of_rows,
        )

        items = find_poi_items(
            data
        )

        total_count = int(
            data.get(
                "totalCount",
                0,
            )
        )

        if total_count <= 0:

            raise RuntimeError(
                "totalCount를 확인할 수 없습니다."
            )


        all_items.extend(
            items
        )

        print(
            f"  {page_no}페이지 완료 "
            f"({len(all_items)}/{total_count})"
        )


        if len(all_items) >= total_count:
            break


        if not items:

            raise RuntimeError(
                "전체 조회 전에 "
                "빈 페이지가 반환되었습니다."
            )


        page_no += 1

        time.sleep(0.3)


    CACHE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with CACHE_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            all_items,
            file,
            ensure_ascii=False,
        )

    print(
        f"  캐시 저장 완료: "
        f"{CACHE_PATH}"
    )

    return all_items


# ============================================================
# 서울 region
# ============================================================

def load_seoul_regions(
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
            WHERE sido_name = '서울특별시'
            ORDER BY region_code
            """
        )

        return cursor.fetchall()


# ============================================================
# 서울 자치단체 POI 인덱스
# ============================================================

def build_poi_index(
    items: list[dict],
) -> dict:

    index = {}


    for item in items:

        sido_code = str(
            item.get(
                "STDG_CTPV_CD",
                "",
            )
        ).strip()

        if sido_code != "11":
            continue


        facility_type = str(
            item.get(
                "FCLT_TYPE",
                "",
            )
        ).strip()

        if facility_type != "자치단체":
            continue


        region_code = str(
            item.get(
                "STDG_SGG_CD",
                "",
            )
        ).strip()


        name = clean_text(
            item.get(
                "FCLT_GVMNFC_NM"
            )
        )

        if not region_code or not name:
            continue


        key = (
            region_code,
            name,
        )


        index.setdefault(
            key,
            [],
        ).append(
            item
        )


    return index


# ============================================================
# API POI -> agency
# ============================================================

def build_api_agency(
    region: dict,
    item: dict,
) -> dict:

    name = clean_text(
        item.get(
            "FCLT_GVMNFC_NM"
        )
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


    if not name:
        raise RuntimeError(
            "구청명이 없습니다."
        )


    if not address:
        raise RuntimeError(
            f"{name} 주소가 없습니다."
        )


    if not x_value or not y_value:

        raise RuntimeError(
            f"{name} 좌표가 없습니다."
        )


    longitude, latitude = (
        TRANSFORMER.transform(
            float(x_value),
            float(y_value),
        )
    )


    if not (
        37.0 <= latitude <= 38.0
        and
        126.5 <= longitude <= 127.5
    ):
        raise RuntimeError(
            f"{name} 좌표가 비정상입니다: "
            f"{latitude}, {longitude}"
        )


    return {
        "name":
            name,

        "address":
            address,

        "phone":
            clean_text(
                item.get(
                    "TELNO"
                )
            ),

        "latitude":
            round(
                latitude,
                7,
            ),

        "longitude":
            round(
                longitude,
                7,
            ),

        "region_code":
            region["region_code"],

        "sigungu_name":
            region["sigungu_name"],

        "source":
            "COMMON_POI",
    }


# ============================================================
# fallback -> agency
# ============================================================

def build_fallback_agency(
    region: dict,
    fallback: dict,
) -> dict:

    return {
        "name":
            fallback["name"],

        "address":
            fallback["address"],

        "phone":
            fallback["phone"],

        "latitude":
            fallback["latitude"],

        "longitude":
            fallback["longitude"],

        "region_code":
            region["region_code"],

        "sigungu_name":
            region["sigungu_name"],

        "source":
            "FALLBACK",
    }


# ============================================================
# 서울 25개 기관 구성
# ============================================================

def build_agencies(
    regions: list[dict],
    poi_index: dict,
) -> list[dict]:

    agencies = []


    for region in regions:

        region_code = (
            region["region_code"]
        )


        # ----------------------------------------------------
        # 공통POI에 없는 8개
        # ----------------------------------------------------

        fallback = (
            FALLBACK_AGENCIES.get(
                region_code
            )
        )

        if fallback:

            agencies.append(
                build_fallback_agency(
                    region,
                    fallback,
                )
            )

            continue


        # ----------------------------------------------------
        # 나머지 17개
        # ----------------------------------------------------

        expected_name = (
            f'{region["sigungu_name"]}청'
        )


        candidates = (
            poi_index.get(
                (
                    region_code,
                    expected_name,
                ),
                [],
            )
        )


        if len(candidates) == 0:

            raise RuntimeError(
                f"구청을 찾지 못했습니다: "
                f"{region_code} / "
                f'{region["sigungu_name"]} / '
                f"{expected_name}"
            )


        if len(candidates) > 1:

            raise RuntimeError(
                f"{expected_name}이 "
                f"{len(candidates)}개 존재합니다."
            )


        agencies.append(
            build_api_agency(
                region,
                candidates[0],
            )
        )


    return agencies


# ============================================================
# 기존 기관
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
# 검증
# ============================================================

def verify() -> None:

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
                    AND r.sido_name = '서울특별시'
                """
            )

            seoul_count = (
                cursor.fetchone()[
                    "count"
                ]
            )


            cursor.execute(
                """
                SELECT
                    COUNT(*) AS count
                FROM agencies
                WHERE agency_type = 'LOCAL_GOVERNMENT'
                """
            )

            total_count = (
                cursor.fetchone()[
                    "count"
                ]
            )


            cursor.execute(
                """
                SELECT
                    a.region_code,
                    r.sigungu_name,
                    a.name,
                    a.latitude,
                    a.longitude,
                    a.phone
                FROM agencies a
                JOIN region r
                  ON r.region_code = a.region_code
                WHERE
                    a.agency_type = 'LOCAL_GOVERNMENT'
                    AND r.sido_name = '서울특별시'
                ORDER BY a.region_code
                """
            )

            rows = cursor.fetchall()


    print()
    print("=" * 105)
    print(
        "서울 LOCAL_GOVERNMENT DB 확인"
    )
    print("=" * 105)


    for row in rows:

        print(
            f'{row["region_code"]}'
            f' | {row["sigungu_name"]:<8}'
            f' | {row["name"]:<12}'
            f' | {row["latitude"]}'
            f' | {row["longitude"]}'
            f' | {row["phone"]}'
        )


    print()
    print(
        f"서울 LOCAL_GOVERNMENT : "
        f"{seoul_count}개"
    )

    print(
        f"전체 LOCAL_GOVERNMENT : "
        f"{total_count}개"
    )

    print("=" * 105)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "[1] 공통POI 데이터 준비"
    )

    items = load_all_poi()


    print()
    print(
        "[2] 서울 region 조회"
    )


    with get_connection() as connection:

        regions = (
            load_seoul_regions(
                connection
            )
        )


    print(
        f"  서울 region: "
        f"{len(regions)}개"
    )


    if len(regions) != 25:

        raise RuntimeError(
            "서울 region 수가 "
            f"25개가 아닙니다: "
            f"{len(regions)}개"
        )


    print()
    print(
        "[3] 서울 LOCAL_GOVERNMENT 생성"
    )


    poi_index = (
        build_poi_index(
            items
        )
    )


    agencies = (
        build_agencies(
            regions,
            poi_index,
        )
    )


    if len(agencies) != 25:

        raise RuntimeError(
            "서울 LOCAL_GOVERNMENT가 "
            f"25개가 아닙니다: "
            f"{len(agencies)}개"
        )


    api_count = sum(
        1
        for agency in agencies
        if agency["source"] == "COMMON_POI"
    )

    fallback_count = sum(
        1
        for agency in agencies
        if agency["source"] == "FALLBACK"
    )


    print(
        f"  공통POI : "
        f"{api_count}개"
    )

    print(
        f"  보완자료 : "
        f"{fallback_count}개"
    )

    print(
        f"  전체     : "
        f"{len(agencies)}개"
    )


    print()
    print(
        "[보완 데이터 확인]"
    )


    for agency in agencies:

        if agency["source"] == "FALLBACK":

            print(
                f'  {agency["region_code"]}'
                f' | {agency["sigungu_name"]}'
                f' | {agency["name"]}'
                f' | {agency["address"]}'
                f' | {agency["latitude"]}'
                f' | {agency["longitude"]}'
            )


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


    verify()


if __name__ == "__main__":
    main()