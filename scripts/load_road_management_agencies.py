from pathlib import Path
from urllib.parse import quote
import re
import tempfile
import warnings
import zipfile

import requests
import shapefile

from dotenv import dotenv_values
from pyproj import Transformer
from shapely import transform as shapely_transform
from shapely.geometry import shape
from shapely.validation import make_valid

from backend.app.db.session import get_connection


# ============================================================
# 기본 경로
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

REFERENCE_DIR = (
    ROOT
    / "database"
    / "reference"
    / "road_management"
    / "seoul"
)

ROAD_BOUNDARY_ZIP = (
    REFERENCE_DIR
    / "TL_BSBND_A.zip"
)

DISTRICT_BOUNDARY_ZIP = (
    REFERENCE_DIR
    / "서울시 상권분석서비스(영역-자치구).zip"
)


# ============================================================
# 환경변수
# ============================================================

env = dotenv_values(
    ROOT / "backend" / ".env",
    interpolate=False,
)

SEOUL_OPENAPI_KEY = env.get(
    "SEOUL_OPENAPI_KEY"
)

KAKAO_REST_API_KEY = env.get(
    "KAKAO_REST_API_KEY"
)

if not SEOUL_OPENAPI_KEY:
    raise ValueError(
        "backend/.env에 SEOUL_OPENAPI_KEY가 없습니다."
    )

if not KAKAO_REST_API_KEY:
    raise ValueError(
        "backend/.env에 KAKAO_REST_API_KEY가 없습니다."
    )


# ============================================================
# API 설정
# ============================================================

SEOUL_API_BASE = (
    "http://openapi.seoul.go.kr:8088"
)

ROAD_BOUNDARY_SERVICE = (
    "tlBsbndA"
)

ORGANIZATION_SERVICE = (
    "SeoulOrganizationService"
)

KAKAO_ADDRESS_API = (
    "https://dapi.kakao.com/"
    "v2/local/search/address.json"
)


# ============================================================
# 공간정보 설정
# ============================================================

ROAD_CRS = "EPSG:5186"
DISTRICT_CRS = "EPSG:5181"

MIN_INTERSECTION_RATIO = 0.01

transformer = Transformer.from_crs(
    ROAD_CRS,
    DISTRICT_CRS,
    always_xy=True,
)


# ============================================================
# 서울시 API
# 도로사업소 6개 이름 조회
# ============================================================

def fetch_road_office_names() -> list[str]:

    url = (
        f"{SEOUL_API_BASE}/"
        f"{SEOUL_OPENAPI_KEY}/json/"
        f"{ROAD_BOUNDARY_SERVICE}/1/100/"
    )

    response = requests.get(
        url,
        timeout=(10, 30),
    )

    response.raise_for_status()

    data = response.json()

    service_data = data.get(
        ROAD_BOUNDARY_SERVICE
    )

    if not service_data:
        raise RuntimeError(
            "도로사업소 경계 API 응답이 없습니다."
        )

    result = service_data.get(
        "RESULT",
        {},
    )

    if result.get("CODE") != "INFO-000":
        raise RuntimeError(
            "도로사업소 API 호출 실패: "
            f'{result.get("CODE")} / '
            f'{result.get("MESSAGE")}'
        )

    names = sorted({
        row["ROAD_MNG_NO"].strip()
        for row
        in service_data.get("row", [])
        if row.get("ROAD_MNG_NO")
    })

    if len(names) != 6:
        raise RuntimeError(
            "서울 도로사업소가 "
            f"6개가 아닙니다: {len(names)}개"
        )

    return names


# ============================================================
# 서울시 조직도 API
# ============================================================

def fetch_organization_rows(
    office_name: str,
) -> list[dict]:

    encoded_name = quote(
        office_name,
        safe="",
    )

    url = (
        f"{SEOUL_API_BASE}/"
        f"{SEOUL_OPENAPI_KEY}/json/"
        f"{ORGANIZATION_SERVICE}/"
        f"1/200/"
        f"{encoded_name}/"
    )

    response = requests.get(
        url,
        timeout=(10, 30),
    )

    response.raise_for_status()

    data = response.json()

    service_data = data.get(
        ORGANIZATION_SERVICE
    )

    if not service_data:
        return []

    result = service_data.get(
        "RESULT",
        {},
    )

    if result.get("CODE") == "INFO-200":
        return []

    if result.get("CODE") != "INFO-000":
        raise RuntimeError(
            f"{office_name} 조직도 조회 실패: "
            f'{result.get("CODE")} / '
            f'{result.get("MESSAGE")}'
        )

    return service_data.get(
        "row",
        [],
    )


# ============================================================
# 사업소 주소 선택
# ============================================================

def select_address(
    office_name: str,
    rows: list[dict],
) -> str:

    expected_department = (
        f"서울특별시 도로사업소 {office_name}"
    )

    # 가장 신뢰할 수 있는 사업소 자체 행
    for row in rows:

        department = str(
            row.get(
                "FULL_DEPTNAME",
                "",
            )
        ).strip()

        location = str(
            row.get(
                "DEPT_LOC",
                "",
            )
        ).strip()

        if (
            department == expected_department
            and location
        ):
            return location

    # fallback
    for row in rows:

        location = str(
            row.get(
                "DEPT_LOC",
                "",
            )
        ).strip()

        if location:
            return location

    raise RuntimeError(
        f"{office_name} 주소를 찾지 못했습니다."
    )


# ============================================================
# 사업소 전화번호 선택
# ============================================================

def select_phone(
    office_name: str,
    rows: list[dict],
) -> tuple[str, str]:

    expected_department = (
        f"서울특별시 도로사업소 {office_name}"
    )

    # --------------------------------------------------------
    # 1순위:
    # 사업소 자체 행이며
    # 실제 도로사업소 총괄 업무인 경우
    # --------------------------------------------------------

    for row in rows:

        department = str(
            row.get(
                "FULL_DEPTNAME",
                "",
            )
        ).strip()

        phone = str(
            row.get(
                "OFFI_TEL_NUM",
                "",
            )
        ).strip()

        work = str(
            row.get(
                "ASSIGN_WORK",
                "",
            )
        ).strip()

        if (
            department == expected_department
            and phone
            and "총괄" in work
            and (
                office_name in work
                or "도로사업소" in work
            )
        ):
            return (
                phone,
                "사업소장/사업소 총괄",
            )

    # --------------------------------------------------------
    # 2순위:
    # 관리단속과 서무 총괄
    #
    # 남부도로사업소 원본 데이터 오류 등을 처리
    # --------------------------------------------------------

    management_department = (
        f"{expected_department} 관리단속과"
    )

    for row in rows:

        department = str(
            row.get(
                "FULL_DEPTNAME",
                "",
            )
        ).strip()

        phone = str(
            row.get(
                "OFFI_TEL_NUM",
                "",
            )
        ).strip()

        work = str(
            row.get(
                "ASSIGN_WORK",
                "",
            )
        ).strip()

        if (
            department == management_department
            and phone
            and "서무" in work
            and "총괄" in work
        ):
            return (
                phone,
                "관리단속과 서무 총괄 fallback",
            )

    raise RuntimeError(
        f"{office_name}의 적절한 "
        "전화번호를 찾지 못했습니다."
    )


# ============================================================
# 조직도 주소 정리
# ============================================================

def clean_address(
    address: str,
) -> str:

    # 우편번호 제거
    address = re.sub(
        r"^\(\d{5}\)\s*",
        "",
        address,
    )

    # (대치동), (상암동) 등의 부가정보 제거
    address = re.sub(
        r"\s*\([^)]*\)\s*.*$",
        "",
        address,
    )

    # 층 정보 제거
    address = re.sub(
        r",\s*\d+층.*$",
        "",
        address,
    )

    return address.strip()


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
            f"Kakao 주소 검색 실패: {address}"
        )

    result = documents[0]

    road_address = result.get(
        "road_address"
    )

    if not road_address:
        raise RuntimeError(
            f"도로명주소 결과 없음: {address}"
        )

    normalized_address = str(
        road_address["address_name"]
    ).strip()

    # Kakao:
    # 서울 강남구 ...
    #
    # DB 저장:
    # 서울특별시 강남구 ...
    if normalized_address.startswith(
        "서울 "
    ):
        normalized_address = (
            "서울특별시 "
            + normalized_address[3:]
        )

    return {
        "address": normalized_address,
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
# ZIP 압축 해제
# ============================================================

def extract_zip(
    zip_path: Path,
    temp_root: Path,
    folder_name: str,
) -> Path:

    if not zip_path.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: "
            f"{zip_path}"
        )

    destination = (
        temp_root
        / folder_name
    )

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(
        zip_path,
        "r",
    ) as archive:

        archive.extractall(
            destination
        )

    return destination


# ============================================================
# SHP 파일 찾기
# ============================================================

def find_shp_file(
    directory: Path,
) -> Path:

    shp_files = list(
        directory.rglob("*.shp")
    )

    if len(shp_files) != 1:
        raise RuntimeError(
            f"{directory}의 SHP 파일이 "
            f"정확히 1개가 아닙니다: "
            f"{len(shp_files)}개"
        )

    return shp_files[0]


# ============================================================
# 도로사업소 경계 읽기
# ============================================================

def load_road_boundaries(
    shp_path: Path,
) -> list[dict]:

    boundaries = []

    # 실제 DBF는 CP949지만
    # CPG에는 UTF-8이 기록되어 있어
    # pyshp warning이 발생한다.
    # 해당 warning만 의도적으로 숨긴다.
    with warnings.catch_warnings():

        warnings.filterwarnings(
            "ignore",
            message=(
                r"Specified encoding: cp949 "
                r"different to encoding read "
                r"from \.cpg file:.*"
            ),
        )

        with shapefile.Reader(
            str(shp_path),
            encoding="cp949",
        ) as reader:

            for shape_record in (
                reader.iterShapeRecords()
            ):

                record = (
                    shape_record.record.as_dict()
                )

                geometry = shape(
                    shape_record
                    .shape
                    .__geo_interface__
                )

                if not geometry.is_valid:
                    geometry = make_valid(
                        geometry
                    )

                # EPSG:5186 → EPSG:5181
                geometry = shapely_transform(
                    geometry,
                    transformer.transform,
                    interleaved=False,
                )

                boundaries.append(
                    {
                        "code": str(
                            record["BSCODE"]
                        ).strip(),

                        "name": str(
                            record["BSNAME"]
                        ).strip(),

                        "geometry": geometry,
                    }
                )

    return boundaries


# ============================================================
# 서울 자치구 경계 읽기
# ============================================================

def load_district_boundaries(
    shp_path: Path,
) -> list[dict]:

    districts = []

    with shapefile.Reader(
        str(shp_path),
        encoding="utf-8",
    ) as reader:

        for shape_record in (
            reader.iterShapeRecords()
        ):

            record = (
                shape_record.record.as_dict()
            )

            geometry = shape(
                shape_record
                .shape
                .__geo_interface__
            )

            if not geometry.is_valid:
                geometry = make_valid(
                    geometry
                )

            districts.append(
                {
                    "region_code": str(
                        record["SIGNGU_CD"]
                    ).strip(),

                    "sigungu_name": str(
                        record["SIGNGU_NM"]
                    ).strip(),

                    "geometry": geometry,
                }
            )

    return districts


# ============================================================
# service_region_codes 자동 계산
# ============================================================

def calculate_service_regions(
    road_boundaries: list[dict],
    districts: list[dict],
) -> dict[str, list[str]]:

    service_regions = {
        road["name"]: []
        for road in road_boundaries
    }

    covered_regions = set()

    for district in districts:

        district_geometry = (
            district["geometry"]
        )

        district_area = (
            district_geometry.area
        )

        if district_area <= 0:
            raise RuntimeError(
                f'{district["sigungu_name"]} '
                "면적이 0 이하입니다."
            )

        accepted_count = 0

        for road in road_boundaries:

            intersection = (
                district_geometry.intersection(
                    road["geometry"]
                )
            )

            if intersection.is_empty:
                continue

            ratio = (
                intersection.area
                / district_area
            )

            if (
                ratio
                < MIN_INTERSECTION_RATIO
            ):
                continue

            service_regions[
                road["name"]
            ].append(
                district[
                    "region_code"
                ]
            )

            accepted_count += 1

        if accepted_count == 0:
            raise RuntimeError(
                f'{district["sigungu_name"]}에 '
                "연결된 도로사업소가 없습니다."
            )

        covered_regions.add(
            district["region_code"]
        )

    for office_name in (
        service_regions
    ):

        service_regions[
            office_name
        ] = sorted(
            set(
                service_regions[
                    office_name
                ]
            )
        )

    if len(covered_regions) != 25:
        raise RuntimeError(
            "서울 25개 자치구가 모두 "
            "도로사업소와 연결되지 않았습니다."
        )

    return service_regions


# ============================================================
# SHP 기반 관할지역 생성
# ============================================================

def build_service_regions(
) -> dict[str, list[str]]:

    with tempfile.TemporaryDirectory() as temp:

        temp_root = Path(temp)

        road_dir = extract_zip(
            ROAD_BOUNDARY_ZIP,
            temp_root,
            "road",
        )

        district_dir = extract_zip(
            DISTRICT_BOUNDARY_ZIP,
            temp_root,
            "district",
        )

        road_shp = find_shp_file(
            road_dir
        )

        district_shp = find_shp_file(
            district_dir
        )

        road_boundaries = (
            load_road_boundaries(
                road_shp
            )
        )

        districts = (
            load_district_boundaries(
                district_shp
            )
        )

        if len(road_boundaries) != 6:
            raise RuntimeError(
                "도로사업소 경계가 "
                f"6개가 아닙니다: "
                f"{len(road_boundaries)}개"
            )

        if len(districts) != 25:
            raise RuntimeError(
                "서울 자치구 경계가 "
                f"25개가 아닙니다: "
                f"{len(districts)}개"
            )

        return calculate_service_regions(
            road_boundaries,
            districts,
        )


# ============================================================
# DB에서 서울 region_code 찾기
# ============================================================

def find_region_code(
    connection,
    sigungu_name: str,
) -> str:

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT region_code
            FROM region
            WHERE sigungu_name = %s
              AND region_code LIKE '11%%'
            ORDER BY region_code
            """,
            (
                sigungu_name,
            ),
        )

        rows = cursor.fetchall()

    if len(rows) != 1:
        raise RuntimeError(
            f"{sigungu_name}에 해당하는 "
            "서울 region_code를 "
            f"정확히 찾지 못했습니다: "
            f"{len(rows)}개"
        )

    return rows[0]["region_code"]


# ============================================================
# 최종 기관 데이터 생성
# ============================================================

def build_agency_data(
    office_names: list[str],
    service_regions: dict[
        str,
        list[str],
    ],
) -> list[dict]:

    agencies = []

    with get_connection() as connection:

        for office_name in office_names:

            rows = (
                fetch_organization_rows(
                    office_name
                )
            )

            if not rows:
                raise RuntimeError(
                    f"{office_name} 조직도 "
                    "데이터가 없습니다."
                )

            raw_address = (
                select_address(
                    office_name,
                    rows,
                )
            )

            cleaned_address = (
                clean_address(
                    raw_address
                )
            )

            phone, phone_source = (
                select_phone(
                    office_name,
                    rows,
                )
            )

            location = (
                geocode_address(
                    cleaned_address
                )
            )

            region_code = (
                find_region_code(
                    connection,
                    location[
                        "sigungu_name"
                    ],
                )
            )

            service_region_codes = (
                service_regions.get(
                    office_name
                )
            )

            if not service_region_codes:
                raise RuntimeError(
                    f"{office_name}의 "
                    "service_region_codes가 "
                    "없습니다."
                )

            agencies.append(
                {
                    "name": office_name,

                    "address": (
                        location[
                            "address"
                        ]
                    ),

                    "phone": phone,

                    "phone_source": (
                        phone_source
                    ),

                    "latitude": (
                        location[
                            "latitude"
                        ]
                    ),

                    "longitude": (
                        location[
                            "longitude"
                        ]
                    ),

                    "region_code": (
                        region_code
                    ),

                    "service_region_codes": (
                        service_region_codes
                    ),
                }
            )

    return agencies


# ============================================================
# 기존 ROAD_MANAGEMENT 검색
# ============================================================

def find_existing_agency(
    connection,
    name: str,
) -> dict | None:

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT id, name
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
            f"{name} ROAD_MANAGEMENT "
            "기관이 DB에 중복되어 있습니다."
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
# DB 적재
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
# 최종 DB 검증
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
                    a.latitude,
                    a.longitude,
                    a.phone,
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
    print("ROAD_MANAGEMENT DB 확인")
    print("=" * 120)

    for row in rows:

        print()

        print(
            f'[{row["name"]}]'
        )

        print(
            f'  주소: {row["address"]}'
        )

        print(
            f'  전화: {row["phone"]}'
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
    print("agencies 전체 현황")
    print("=" * 70)

    total = 0

    for row in counts:

        print(
            f'{row["agency_type"]:<20}'
            f' : {row["count"]}개'
        )

        total += row["count"]

    print(
        f'{"TOTAL":<20}'
        f' : {total}개'
    )

    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "[1] 서울 도로사업소 API 조회"
    )

    office_names = (
        fetch_road_office_names()
    )

    for office_name in office_names:
        print(
            f"  - {office_name}"
        )


    print()
    print(
        "[2] SHP 기반 관할지역 자동 계산"
    )

    service_regions = (
        build_service_regions()
    )

    for office_name in sorted(
        service_regions
    ):

        print(
            f"  {office_name}: "
            f"{service_regions[office_name]}"
        )


    print()
    print(
        "[3] 조직도 + Kakao + region DB 조회"
    )

    agencies = (
        build_agency_data(
            office_names,
            service_regions,
        )
    )

    for agency in agencies:

        print()
        print(
            f'  [{agency["name"]}]'
        )

        print(
            f'    주소: '
            f'{agency["address"]}'
        )

        print(
            f'    전화: '
            f'{agency["phone"]}'
        )

        print(
            f'    전화 선택: '
            f'{agency["phone_source"]}'
        )

        print(
            f'    region_code: '
            f'{agency["region_code"]}'
        )

        print(
            f'    service_region_codes: '
            f'{agency["service_region_codes"]}'
        )

        print(
            f'    좌표: '
            f'{agency["latitude"]}, '
            f'{agency["longitude"]}'
        )


    print()
    print(
        "[4] agencies DB 적재"
    )

    inserted, updated = (
        save_agencies(
            agencies
        )
    )

    print(
        f"  신규 INSERT: {inserted}개"
    )

    print(
        f"  기존 UPDATE: {updated}개"
    )


    print()
    print(
        "[5] 최종 DB 검증"
    )

    verify_database()


if __name__ == "__main__":
    main()