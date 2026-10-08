from pathlib import Path
import time

import requests
from dotenv import dotenv_values
from requests.exceptions import RequestException

from backend.app.db.session import get_connection


ROOT = Path(__file__).resolve().parents[1]

env = dotenv_values(
    ROOT / "backend" / ".env",
    interpolate=False,
)

KMA_API_KEY = env.get("KMA_API_KEY")

if not KMA_API_KEY:
    raise ValueError(
        "backend/.env에 KMA_API_KEY가 없습니다."
    )


API_URL = (
    "https://apihub.kma.go.kr/api/typ02/openApi/"
    "WethrBasicInfoService/getWrnZoneCd"
)


# ============================================================
# 서울 특보권역
# ============================================================

SEOUL_ZONE_BY_DISTRICT = {
    # 서울동남권
    "강동구": "서울동남권",
    "송파구": "서울동남권",
    "강남구": "서울동남권",
    "서초구": "서울동남권",

    # 서울동북권
    "도봉구": "서울동북권",
    "노원구": "서울동북권",
    "강북구": "서울동북권",
    "성북구": "서울동북권",
    "동대문구": "서울동북권",
    "중랑구": "서울동북권",
    "성동구": "서울동북권",
    "광진구": "서울동북권",

    # 서울서남권
    "강서구": "서울서남권",
    "양천구": "서울서남권",
    "구로구": "서울서남권",
    "영등포구": "서울서남권",
    "동작구": "서울서남권",
    "관악구": "서울서남권",
    "금천구": "서울서남권",

    # 서울서북권
    "은평구": "서울서북권",
    "종로구": "서울서북권",
    "마포구": "서울서북권",
    "서대문구": "서울서북권",
    "중구": "서울서북권",
    "용산구": "서울서북권",
}


def find_zone_items(value) -> list[dict]:
    result = []

    if isinstance(value, dict):
        if (
            "warningAreaCode" in value
            and "korName" in value
        ):
            result.append(value)

        for child in value.values():
            result.extend(
                find_zone_items(child)
            )

    elif isinstance(value, list):
        for child in value:
            result.extend(
                find_zone_items(child)
            )

    return result


def fetch_weather_zones() -> dict[str, str]:
    params = {
        "pageNo": 1,
        "numOfRows": 1000,
        "dataType": "JSON",
        "korName": "",
        "authKey": KMA_API_KEY,
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

            data = response.json()

            break

        except RequestException:
            if attempt == max_retries:
                raise RuntimeError(
                    "기상청 특보구역 API 호출에 "
                    f"{max_retries}회 연속 실패했습니다."
                ) from None

            wait_seconds = attempt * 2

            print(
                f"API 연결 실패 "
                f"({attempt}/{max_retries}) "
                f"→ {wait_seconds}초 후 재시도"
            )

            time.sleep(wait_seconds)

    items = find_zone_items(data)

    zones = {}

    for item in items:
        code = str(
            item["warningAreaCode"]
        ).strip()

        name = str(
            item["korName"]
        ).strip()

        zones[name] = code

    if not zones:
        raise RuntimeError(
            "기상청 특보구역 데이터를 찾지 못했습니다."
        )

    return zones


def require_zone(
    zones: dict[str, str],
    zone_name: str,
) -> str:
    code = zones.get(zone_name)

    if code is None:
        raise RuntimeError(
            f"기상청 특보구역을 찾지 못했습니다: "
            f"{zone_name}"
        )

    return code


def get_base_sigungu(
    sigungu_name: str,
) -> str:
    """
    DB:
        수원시 장안구
        성남시 분당구
        고양시 일산동구

    기상청:
        수원시
        성남시
        고양시

    따라서 첫 번째 이름이 '시'로 끝나는 경우
    상위 시 이름을 사용한다.
    """

    parts = sigungu_name.split()

    if (
        len(parts) >= 2
        and parts[0].endswith("시")
    ):
        return parts[0]

    return sigungu_name


def build_weather_codes(
    region: dict,
    zones: dict[str, str],
) -> list[str]:
    sido_name = region["sido_name"]
    sigungu_name = region["sigungu_name"]

    codes = []


    # ========================================================
    # 서울특별시
    # ========================================================

    if sido_name == "서울특별시":
        # 서울 전체
        codes.append(
            require_zone(
                zones,
                "서울특별시",
            )
        )

        zone_name = SEOUL_ZONE_BY_DISTRICT.get(
            sigungu_name
        )

        if zone_name is None:
            raise RuntimeError(
                f"서울 특보권역 매핑이 없습니다: "
                f"{sigungu_name}"
            )

        codes.append(
            require_zone(
                zones,
                zone_name,
            )
        )


    # ========================================================
    # 경기도
    # ========================================================

    elif sido_name == "경기도":
        base_name = get_base_sigungu(
            sigungu_name
        )

        # 기본적으로 시군 전체 코드 추가
        codes.append(
            require_zone(
                zones,
                base_name,
            )
        )


        # ----------------------------------------------------
        # 파주시
        # ----------------------------------------------------

        if base_name == "파주시":
            codes.extend(
                [
                    require_zone(
                        zones,
                        "파주시동북부",
                    ),
                    require_zone(
                        zones,
                        "파주시서북부",
                    ),
                    require_zone(
                        zones,
                        "파주시남부",
                    ),
                ]
            )


        # ----------------------------------------------------
        # 여주시
        # ----------------------------------------------------

        elif base_name == "여주시":
            codes.extend(
                [
                    require_zone(
                        zones,
                        "여주시동남부",
                    ),
                    require_zone(
                        zones,
                        "여주시서부",
                    ),
                ]
            )


        # ----------------------------------------------------
        # 양평군
        # ----------------------------------------------------

        elif base_name == "양평군":
            codes.extend(
                [
                    require_zone(
                        zones,
                        "양평군동부",
                    ),
                    require_zone(
                        zones,
                        "양평군서부",
                    ),
                ]
            )


        # ----------------------------------------------------
        # 용인시
        # ----------------------------------------------------

        elif base_name == "용인시":

            # 기흥구 / 수지구
            if (
                sigungu_name
                in (
                    "용인시 기흥구",
                    "용인시 수지구",
                )
            ):
                codes.append(
                    require_zone(
                        zones,
                        "용인시서북부",
                    )
                )

            # 처인구는 하나의 구 안에서
            # 동북부와 남부로 다시 나뉨
            elif (
                sigungu_name
                == "용인시 처인구"
            ):
                codes.extend(
                    [
                        require_zone(
                            zones,
                            "용인시동북부",
                        ),
                        require_zone(
                            zones,
                            "용인시남부",
                        ),
                    ]
                )

            else:
                raise RuntimeError(
                    f"용인시 구 매핑을 찾지 못했습니다: "
                    f"{sigungu_name}"
                )

    else:
        raise RuntimeError(
            f"지원하지 않는 시도입니다: "
            f"{sido_name}"
        )


    # 혹시 중복 코드가 생기더라도 제거
    return list(
        dict.fromkeys(codes)
    )


def load_regions() -> list[dict]:
    with get_connection() as connection:
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
                    region_code
                """
            )

            return cursor.fetchall()


def save_weather_codes(
    mappings: list[dict],
) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                UPDATE region
                SET weather_region_code = %s
                WHERE region_code = %s
                """,
                [
                    (
                        mapping[
                            "weather_region_code"
                        ],
                        mapping[
                            "region_code"
                        ],
                    )
                    for mapping in mappings
                ],
            )


def verify() -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_count,
                    COUNT(*) FILTER (
                        WHERE weather_region_code IS NOT NULL
                    ) AS mapped_count,
                    COUNT(*) FILTER (
                        WHERE weather_region_code IS NULL
                    ) AS unmapped_count
                FROM region
                WHERE sido_name IN (
                    '서울특별시',
                    '경기도'
                )
                """
            )

            result = cursor.fetchone()

    print()
    print("=" * 70)
    print("DB 기상특보 코드 적재 결과")
    print("=" * 70)

    print(
        f'전체 지역     : '
        f'{result["total_count"]}'
    )

    print(
        f'매핑 완료     : '
        f'{result["mapped_count"]}'
    )

    print(
        f'미매핑 지역   : '
        f'{result["unmapped_count"]}'
    )

    print("=" * 70)


def main():
    print("[1] 기상청 특보구역 조회")

    zones = fetch_weather_zones()

    print(
        f"  특보구역 {len(zones)}개 조회 완료"
    )

    print()
    print("[2] DB 지역 조회")

    regions = load_regions()

    print(
        f"  region {len(regions)}개 조회 완료"
    )

    if len(regions) != 72:
        raise RuntimeError(
            f"region이 72개가 아닙니다. "
            f"현재: {len(regions)}개"
        )


    print()
    print("[3] 기상특보 코드 매핑")

    mappings = []

    for region in regions:
        codes = build_weather_codes(
            region,
            zones,
        )

        mappings.append(
            {
                "region_code":
                    region["region_code"],

                "weather_region_code":
                    codes,
            }
        )


    # 특수 매핑만 눈으로 확인
    print()
    print("[특수 매핑 확인]")

    special_names = (
        "강남구",
        "종로구",
        "파주시",
        "여주시",
        "양평군",
        "용인시 처인구",
        "용인시 기흥구",
        "용인시 수지구",
    )

    for region, mapping in zip(
        regions,
        mappings,
    ):
        if (
            region["sigungu_name"]
            in special_names
        ):
            print(
                f'{region["region_code"]}'
                f' | '
                f'{region["sigungu_name"]}'
                f' | '
                f'{mapping["weather_region_code"]}'
            )


    print()
    print("[4] DB 적재 시작")

    save_weather_codes(
        mappings
    )

    print("[4] DB 적재 완료")

    verify()


if __name__ == "__main__":
    main()