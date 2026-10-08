from pathlib import Path
import csv

from openpyxl import load_workbook
from pyproj import Transformer

from backend.app.db.session import get_connection


# ============================================================
# 경로 설정
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

REFERENCE_DIR = (
    ROOT
    / "database"
    / "reference"
    / "fire"
)

FIRE_STATUS_CSV = (
    REFERENCE_DIR
    / "소방청_시도 소방서 현황_20260701.csv"
)

SEOUL_LOCATION_XLSX = (
    REFERENCE_DIR
    / "소방서 안전센터 구조대 위치정보_2025.xlsx"
)

GYEONGGI_FIRE_CSV = (
    REFERENCE_DIR
    / "경기도소방서현황및관할구역현황.csv"
)


# ============================================================
# 서울 좌표 변환
#
# EPSG:5186
#   ↓
# WGS84 (EPSG:4326)
# ============================================================

TRANSFORMER = Transformer.from_crs(
    "EPSG:5186",
    "EPSG:4326",
    always_xy=True,
)


# ============================================================
# 서울 소방청 자료
# ============================================================

def read_seoul_fire_status() -> dict[str, dict]:
    if not FIRE_STATUS_CSV.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: {FIRE_STATUS_CSV}"
        )

    stations = {}

    with FIRE_STATUS_CSV.open(
        "r",
        encoding="cp949",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row["본부명"].strip() != "서울소방재난본부":
                continue

            name = row["소방서"].strip()

            stations[name] = {
                "name": name,
                "address": row["주소"].strip(),
                "phone": row["전화번호"].strip(),
            }

    return stations


# ============================================================
# 서울 위치자료
# ============================================================

def read_seoul_fire_locations() -> dict[str, dict]:
    if not SEOUL_LOCATION_XLSX.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: {SEOUL_LOCATION_XLSX}"
        )

    workbook = load_workbook(
        SEOUL_LOCATION_XLSX,
        read_only=True,
        data_only=True,
    )

    worksheet = workbook.active
    rows = worksheet.iter_rows(values_only=True)

    headers = next(rows)

    column_index = {
        name: index
        for index, name in enumerate(headers)
    }

    required_columns = {
        "서ㆍ센터명",
        "유형구분명",
        "X좌표",
        "Y좌표",
    }

    missing = required_columns - set(column_index)

    if missing:
        workbook.close()

        raise RuntimeError(
            f"서울 위치자료에 필요한 컬럼이 없습니다: "
            f"{sorted(missing)}"
        )

    locations = {}

    for row in rows:
        agency_type = row[
            column_index["유형구분명"]
        ]

        if agency_type is None:
            continue

        if str(agency_type).strip() != "소방서":
            continue

        name = str(
            row[column_index["서ㆍ센터명"]]
        ).strip()

        x_value = row[column_index["X좌표"]]
        y_value = row[column_index["Y좌표"]]

        if x_value is None or y_value is None:
            workbook.close()

            raise RuntimeError(
                f"{name}의 좌표가 없습니다."
            )

        longitude, latitude = TRANSFORMER.transform(
            float(x_value),
            float(y_value),
        )

        locations[name] = {
            "latitude": round(latitude, 7),
            "longitude": round(longitude, 7),
        }

    workbook.close()

    return locations


# ============================================================
# 서울 데이터 결합
# ============================================================

def build_seoul_agencies() -> list[dict]:
    status_data = read_seoul_fire_status()
    location_data = read_seoul_fire_locations()

    status_names = set(status_data)
    location_names = set(location_data)

    if status_names != location_names:
        print(
            "소방청 자료에만 존재:",
            sorted(status_names - location_names),
        )

        print(
            "서울 위치자료에만 존재:",
            sorted(location_names - status_names),
        )

        raise RuntimeError(
            "서울 소방서 두 자료의 기관명이 일치하지 않습니다."
        )

    if len(status_data) != 25:
        raise RuntimeError(
            f"서울 소방서가 25개가 아닙니다: "
            f"{len(status_data)}개"
        )

    agencies = []

    for name in sorted(status_data):
        status = status_data[name]
        location = location_data[name]

        agencies.append(
            {
                "name": name,
                "sido_name": "서울특별시",
                "address": status["address"],
                "phone": status["phone"],
                "latitude": location["latitude"],
                "longitude": location["longitude"],
            }
        )

    return agencies


# ============================================================
# 경기도 소방서 자료
# ============================================================

def read_gyeonggi_agencies() -> list[dict]:
    if not GYEONGGI_FIRE_CSV.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: {GYEONGGI_FIRE_CSV}"
        )

    agencies = []

    with GYEONGGI_FIRE_CSV.open(
        "r",
        encoding="cp949",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        required_columns = {
            "전체기관명",
            "대표전화번호",
            "소재지도로명주소",
            "WGS84위도",
            "WGS84경도",
        }

        missing = (
            required_columns
            - set(reader.fieldnames or [])
        )

        if missing:
            raise RuntimeError(
                f"경기도 소방서 자료에 필요한 컬럼이 없습니다: "
                f"{sorted(missing)}"
            )

        for row in reader:
            name = row[
                "전체기관명"
            ].strip()

            # "경기도 가평소방서"
            #       ↓
            # "가평소방서"
            name = name.removeprefix(
                "경기도 "
            ).strip()

            address = row[
                "소재지도로명주소"
            ].strip()

            phone = row[
                "대표전화번호"
            ].strip()

            latitude = float(
                row["WGS84위도"]
            )

            longitude = float(
                row["WGS84경도"]
            )

            agencies.append(
                {
                    "name": name,
                    "sido_name": "경기도",
                    "address": address,
                    "phone": phone,
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

    if len(agencies) != 36:
        raise RuntimeError(
            f"경기도 소방서가 36개가 아닙니다: "
            f"{len(agencies)}개"
        )

    return agencies


# ============================================================
# region 후보 조회
# ============================================================

def load_region_candidates(
    connection,
    sido_name: str,
) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                region_code,
                sigungu_name
            FROM region
            WHERE sido_name = %s
            ORDER BY
                length(sigungu_name) DESC,
                sigungu_name
            """,
            (sido_name,),
        )

        return cursor.fetchall()


# ============================================================
# 기관 주소 -> region_code 매칭
# ============================================================

def match_region_code(
    address: str,
    sido_name: str,
    candidates: list[dict],
) -> tuple[str, str]:
    """
    주소와 가장 구체적인 region을 매칭한다.

    예:

    경기도 고양시 덕양구 ...
        -> 고양시 덕양구

    경기도 화성시 만세구 ...
        -> 화성시 만세구

    경기도 가평군 ...
        -> 가평군
    """

    for region in candidates:
        sigungu_name = region[
            "sigungu_name"
        ]

        expected_prefix = (
            f"{sido_name} "
            f"{sigungu_name}"
        )

        if address.startswith(
            expected_prefix
        ):
            return (
                region["region_code"],
                sigungu_name,
            )

    raise RuntimeError(
        f"주소와 일치하는 region을 찾지 못했습니다: "
        f"{address}"
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
              AND agency_type = 'FIRE'
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
                'FIRE',
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
# 결과 검증
# ============================================================

def verify_fire_agencies() -> None:
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
                WHERE a.agency_type = 'FIRE'
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
                FROM agencies a
                JOIN region r
                  ON r.region_code = a.region_code
                WHERE a.agency_type = 'FIRE'
                  AND r.sido_name IN (
                      '서울특별시',
                      '경기도'
                  )
                """
            )

            total = cursor.fetchone()["count"]

    print()
    print("=" * 70)
    print("FIRE 기관 DB 적재 결과")
    print("=" * 70)

    for row in counts:
        print(
            f'{row["sido_name"]:<8} : '
            f'{row["count"]}개'
        )

    print(f"전체       : {total}개")
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():
    # --------------------------------------------------------
    # 1. 원본 자료 읽기
    # --------------------------------------------------------

    print("[1] 서울 소방서 자료 읽기")

    seoul_agencies = (
        build_seoul_agencies()
    )

    print(
        f"  서울 소방서: "
        f"{len(seoul_agencies)}개"
    )


    print()
    print("[2] 경기도 소방서 자료 읽기")

    gyeonggi_agencies = (
        read_gyeonggi_agencies()
    )

    print(
        f"  경기도 소방서: "
        f"{len(gyeonggi_agencies)}개"
    )


    agencies = (
        seoul_agencies
        + gyeonggi_agencies
    )

    if len(agencies) != 61:
        raise RuntimeError(
            f"전체 FIRE 기관이 61개가 아닙니다: "
            f"{len(agencies)}개"
        )


    # --------------------------------------------------------
    # 3. region_code 매칭
    # --------------------------------------------------------

    print()
    print("[3] region_code 매칭")

    with get_connection() as connection:
        seoul_regions = (
            load_region_candidates(
                connection,
                "서울특별시",
            )
        )

        gyeonggi_regions = (
            load_region_candidates(
                connection,
                "경기도",
            )
        )

        for agency in agencies:
            if (
                agency["sido_name"]
                == "서울특별시"
            ):
                candidates = (
                    seoul_regions
                )

            else:
                candidates = (
                    gyeonggi_regions
                )

            (
                region_code,
                sigungu_name,
            ) = match_region_code(
                agency["address"],
                agency["sido_name"],
                candidates,
            )

            agency[
                "region_code"
            ] = region_code

            agency[
                "sigungu_name"
            ] = sigungu_name


        print(
            f"  전체 {len(agencies)}개 "
            f"지역 매칭 완료"
        )


        # ----------------------------------------------------
        # 적재 대상 확인
        # ----------------------------------------------------

        print()
        print("[경기도 적재 대상 미리보기]")

        for agency in gyeonggi_agencies:
            print(
                f'  {agency["name"]}'
                f' | {agency["sigungu_name"]}'
                f' | {agency["region_code"]}'
                f' | {agency["latitude"]}'
                f' | {agency["longitude"]}'
            )


        # ----------------------------------------------------
        # 4. DB 저장
        # ----------------------------------------------------

        print()
        print("[4] DB 적재")

        inserted = 0
        updated = 0

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


    # --------------------------------------------------------
    # 5. 확인
    # --------------------------------------------------------

    verify_fire_agencies()


if __name__ == "__main__":
    main()