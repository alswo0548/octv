from pathlib import Path

import requests
from dotenv import dotenv_values

from backend.app.db.session import get_connection


# ============================================================
# 기본 경로 / 환경변수
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

env = dotenv_values(
    ROOT / "backend" / ".env",
    interpolate=False,
)

KAKAO_REST_API_KEY = env.get(
    "KAKAO_REST_API_KEY"
)

if not KAKAO_REST_API_KEY:
    raise ValueError(
        "backend/.env에 "
        "KAKAO_REST_API_KEY가 없습니다."
    )


KAKAO_ADDRESS_API = (
    "https://dapi.kakao.com/"
    "v2/local/search/address.json"
)


# ============================================================
# 경기도 건설본부 기관 기본정보
#
# 공식 API/다운로드 데이터로 얻지 못한 최소 기준값
# ============================================================

OFFICES = [
    {
        "name": "경기도건설본부 도로건설과",
        "division": "남부",

        "address": (
            "경기도 수원시 권선구 "
            "칠보로1번길 20"
        ),

        # 도로 유지보수 업무 연락처
        "phone": "031-8008-5883",
    },

    {
        "name": "경기도건설본부 북부도로과",
        "division": "북부",

        "address": (
            "경기도 의정부시 "
            "범골로 138"
        ),

        # 도로 유지보수 업무 연락처
        "phone": "031-8008-8309",
    },
]


# ============================================================
# 경기도 건설본부 공식 관리구역
#
# region_code 자체는 하드코딩하지 않는다.
# 아래 시·군명을 region DB에서 자동 확장한다.
# ============================================================

SERVICE_AREAS = {

    "남부": [
        "용인시",
        "양평군",
        "여주시",
        "광주시",
        "이천시",
        "안성시",
        "화성시",
        "평택시",
        "김포시",
    ],

    "북부": [
        "파주시",
        "양주시",
        "포천시",
        "가평군",
        "남양주시",
        "연천군",
    ],
}


# ============================================================
# 시도명 정규화
#
# Kakao:
#   경기
#
# 우리 DB:
#   경기도
# ============================================================

def normalize_sido_name(
    sido_name: str,
) -> str:

    aliases = {
        "서울": "서울특별시",
        "경기": "경기도",
    }

    return aliases.get(
        sido_name,
        sido_name,
    )


# ============================================================
# Kakao 주소 → 좌표
# ============================================================

def geocode_address(
    address: str,
) -> dict:

    response = requests.get(
        KAKAO_ADDRESS_API,
        headers={
            "Authorization": (
                f"KakaoAK "
                f"{KAKAO_REST_API_KEY}"
            )
        },
        params={
            "query": address,
        },
        timeout=(10, 30),
    )

    response.raise_for_status()

    data = response.json()

    documents = data.get(
        "documents",
        [],
    )

    if not documents:
        raise RuntimeError(
            f"Kakao 주소 검색 실패: "
            f"{address}"
        )

    result = documents[0]

    road_address = result.get(
        "road_address"
    )

    if not road_address:
        raise RuntimeError(
            f"도로명주소 결과 없음: "
            f"{address}"
        )


    normalized_address = str(
        road_address[
            "address_name"
        ]
    ).strip()


    # Kakao 주소 표기를 DB 표기에 맞춤
    if normalized_address.startswith(
        "경기 "
    ):
        normalized_address = (
            "경기도 "
            + normalized_address[3:]
        )

    elif normalized_address.startswith(
        "서울 "
    ):
        normalized_address = (
            "서울특별시 "
            + normalized_address[3:]
        )


    raw_sido_name = str(
        road_address[
            "region_1depth_name"
        ]
    ).strip()


    return {
        "address": normalized_address,

        "sido_name": (
            normalize_sido_name(
                raw_sido_name
            )
        ),

        "sigungu_name": str(
            road_address[
                "region_2depth_name"
            ]
        ).strip(),

        "latitude": float(
            result["y"]
        ),

        "longitude": float(
            result["x"]
        ),
    }


# ============================================================
# 경기도 region 전체 조회
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
# 기관 청사 위치 region 매칭
# ============================================================

def find_office_region(
    connection,
    sido_name: str,
    sigungu_name: str,
) -> dict:

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                region_code,
                sido_name,
                sigungu_name
            FROM region
            WHERE sido_name = %s
              AND sigungu_name = %s
            ORDER BY region_code
            """,
            (
                sido_name,
                sigungu_name,
            ),
        )

        rows = cursor.fetchall()


    if len(rows) != 1:

        raise RuntimeError(
            "기관 위치 region 매칭 실패: "
            f"{sido_name} / "
            f"{sigungu_name} "
            f"→ {len(rows)}개"
        )


    return rows[0]


# ============================================================
# 관리 대상 시·군 → 실제 region 자동 확장
#
# 예:
#
# 용인시
# → 용인시 처인구
# → 용인시 기흥구
# → 용인시 수지구
#
# 화성시
# → 화성시 만세구
# → 화성시 효행구
# → 화성시 병점구
# → 화성시 동탄구
# ============================================================

def find_matching_regions(
    target_name: str,
    regions: list[dict],
) -> list[dict]:

    target_name = (
        target_name.strip()
    )

    matched = []


    for region in regions:

        sigungu_name = str(
            region["sigungu_name"]
        ).strip()


        # 정확한 시·군
        if sigungu_name == target_name:

            matched.append(
                region
            )

            continue


        # 일반구가 존재하는 도시
        if sigungu_name.startswith(
            target_name + " "
        ):

            matched.append(
                region
            )


    return matched


# ============================================================
# 남부 / 북부 service_region_codes 생성
# ============================================================

def build_service_regions(
    regions: list[dict],
) -> dict[str, list[str]]:

    result = {}


    for division, target_names in (
        SERVICE_AREAS.items()
    ):

        codes = []


        for target_name in target_names:

            matched = (
                find_matching_regions(
                    target_name,
                    regions,
                )
            )


            if not matched:

                raise RuntimeError(
                    f"{division} 관리구역 "
                    f"'{target_name}'에 해당하는 "
                    "region을 찾지 못했습니다."
                )


            for region in matched:

                codes.append(
                    region["region_code"]
                )


        result[division] = sorted(
            set(codes)
        )


    # --------------------------------------------------------
    # 남부 / 북부 중복 검사
    # --------------------------------------------------------

    south_codes = set(
        result["남부"]
    )

    north_codes = set(
        result["북부"]
    )

    overlap = (
        south_codes
        & north_codes
    )


    if overlap:

        raise RuntimeError(
            "남부/북부 service_region_codes가 "
            f"중복됩니다: {sorted(overlap)}"
        )


    return result


# ============================================================
# 최종 기관 데이터 생성
# ============================================================

def build_agency_data() -> list[dict]:

    agencies = []


    with get_connection() as connection:

        regions = (
            load_gyeonggi_regions(
                connection
            )
        )


        if len(regions) != 47:

            raise RuntimeError(
                "경기도 region 수가 "
                f"47개가 아닙니다: "
                f"{len(regions)}개"
            )


        service_regions = (
            build_service_regions(
                regions
            )
        )


        for office in OFFICES:

            location = (
                geocode_address(
                    office["address"]
                )
            )


            office_region = (
                find_office_region(
                    connection,
                    location[
                        "sido_name"
                    ],
                    location[
                        "sigungu_name"
                    ],
                )
            )


            division = (
                office["division"]
            )

            service_region_codes = (
                service_regions[
                    division
                ]
            )


            agencies.append(
                {
                    "name": (
                        office["name"]
                    ),

                    "address": (
                        location["address"]
                    ),

                    "phone": (
                        office["phone"]
                    ),

                    "latitude": (
                        location["latitude"]
                    ),

                    "longitude": (
                        location["longitude"]
                    ),

                    "region_code": (
                        office_region[
                            "region_code"
                        ]
                    ),

                    "service_region_codes": (
                        service_region_codes
                    ),

                    "division": (
                        division
                    ),
                }
            )


    return agencies


# ============================================================
# 기존 ROAD_MANAGEMENT 확인
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
              AND agency_type = 'ROAD_MANAGEMENT'
            ORDER BY id
            """,
            (
                name,
            ),
        )

        rows = cursor.fetchall()


    if len(rows) > 1:

        raise RuntimeError(
            f"{name} 기관이 "
            "중복되어 있습니다."
        )


    if not rows:
        return None


    return rows[0]


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
                region_code,
                service_region_codes
            )
            VALUES (
                %s,
                'ROAD_MANAGEMENT',
                %s,
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
                agency[
                    "service_region_codes"
                ],
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
                region_code = %s,
                service_region_codes = %s
            WHERE id = %s
            """,
            (
                agency["address"],
                agency["latitude"],
                agency["longitude"],
                agency["phone"],
                agency["region_code"],
                agency[
                    "service_region_codes"
                ],
                agency_id,
            ),
        )


# ============================================================
# DB 저장
# ============================================================

def save_agencies(
    agencies: list[dict],
) -> tuple[int, int]:

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


    return (
        inserted,
        updated,
    )


# ============================================================
# 최종 DB 확인
# ============================================================

def verify_database() -> None:

    with get_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    a.id,
                    a.name,
                    a.address,
                    a.phone,
                    a.latitude,
                    a.longitude,
                    a.region_code,
                    r.sigungu_name,
                    a.service_region_codes
                FROM agencies a
                JOIN region r
                  ON r.region_code = a.region_code
                WHERE
                    a.agency_type = 'ROAD_MANAGEMENT'
                ORDER BY a.name
                """
            )

            rows = cursor.fetchall()


            cursor.execute(
                """
                SELECT
                    agency_type,
                    COUNT(*) AS count
                FROM agencies
                GROUP BY agency_type
                ORDER BY agency_type
                """
            )

            counts = cursor.fetchall()


    print()
    print("=" * 120)
    print(
        "ROAD_MANAGEMENT DB 확인"
    )
    print("=" * 120)


    for row in rows:

        print()

        print(
            f'[{row["name"]}]'
        )

        print(
            f'  주소: '
            f'{row["address"]}'
        )

        print(
            f'  전화: '
            f'{row["phone"]}'
        )

        print(
            f'  위치 region: '
            f'{row["region_code"]} '
            f'{row["sigungu_name"]}'
        )

        print(
            f'  관할 regions: '
            f'{row["service_region_codes"]}'
        )

        print(
            f'  좌표: '
            f'{row["latitude"]}, '
            f'{row["longitude"]}'
        )


    print()
    print("=" * 70)
    print(
        "agencies 전체 현황"
    )
    print("=" * 70)


    total = 0


    for row in counts:

        print(
            f'{row["agency_type"]:<20}'
            f' : '
            f'{row["count"]}개'
        )

        total += row[
            "count"
        ]


    print(
        f'{"TOTAL":<20}'
        f' : '
        f'{total}개'
    )

    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "[1] 경기도 ROAD_MANAGEMENT "
        "데이터 자동 생성"
    )


    agencies = (
        build_agency_data()
    )


    for agency in agencies:

        print()
        print(
            f'[{agency["name"]}]'
        )

        print(
            f'  담당: '
            f'{agency["division"]}'
        )

        print(
            f'  주소: '
            f'{agency["address"]}'
        )

        print(
            f'  전화: '
            f'{agency["phone"]}'
        )

        print(
            f'  region_code: '
            f'{agency["region_code"]}'
        )

        print(
            f'  service_region_codes: '
            f'{agency["service_region_codes"]}'
        )

        print(
            f'  service region 수: '
            f'{len(agency["service_region_codes"])}'
        )

        print(
            f'  좌표: '
            f'{agency["latitude"]}, '
            f'{agency["longitude"]}'
        )


    print()
    print(
        "[2] agencies DB 적재"
    )


    inserted, updated = (
        save_agencies(
            agencies
        )
    )


    print(
        f"  신규 INSERT: "
        f"{inserted}개"
    )

    print(
        f"  기존 UPDATE: "
        f"{updated}개"
    )


    print()
    print(
        "[3] 최종 DB 검증"
    )


    verify_database()


if __name__ == "__main__":
    main()