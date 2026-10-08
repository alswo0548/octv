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

SERVICE_KEY = env.get("DATA_GO_KR_SERVICE_KEY")

if not SERVICE_KEY:
    raise ValueError(
        "backend/.env에 DATA_GO_KR_SERVICE_KEY가 없습니다."
    )


API_URL = (
    "https://apis.data.go.kr/1741000/"
    "StanReginCd/getStanReginCdList"
)


TARGETS = {
    "11": "서울특별시",
    "41": "경기도",
}


def fetch_regions(sido_name: str) -> list[dict]:
    page_no = 1
    num_of_rows = 500
    all_rows = []

    while True:
        params = {
            "ServiceKey": SERVICE_KEY,
            "pageNo": page_no,
            "numOfRows": num_of_rows,
            "type": "json",
            "locatadd_nm": sido_name,
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
                        f"{sido_name} {page_no}페이지 API 호출에 "
                        f"{max_retries}회 연속 실패했습니다."
                    ) from None

                wait_seconds = attempt * 2

                print(
                    f"  {page_no}페이지 연결 실패 "
                    f"({attempt}/{max_retries}) "
                    f"→ {wait_seconds}초 후 재시도"
                )

                time.sleep(wait_seconds)

        api_data = data["StanReginCd"]

        head = api_data[0]["head"]

        total_count = int(
            head[0]["totalCount"]
        )

        rows = api_data[1].get(
            "row",
            [],
        )

        all_rows.extend(rows)

        print(
            f"  {page_no}페이지 완료 "
            f"({len(all_rows)}/{total_count})"
        )

        if len(all_rows) >= total_count:
            break

        page_no += 1

        time.sleep(0.3)

    return all_rows


def extract_sigungu(
    rows: list[dict],
) -> list[dict]:
    regions = {}

    for row in rows:
        sido_cd = row["sido_cd"]
        sgg_cd = row["sgg_cd"]
        umd_cd = row["umd_cd"]
        ri_cd = row["ri_cd"]

        # 서울·경기만
        if sido_cd not in TARGETS:
            continue

        # 시도 자체 제외
        if sgg_cd == "000":
            continue

        # 읍면동 제외
        if umd_cd != "000":
            continue

        # 리 단위 제외
        if ri_cd != "00":
            continue

        sido_name = TARGETS[sido_cd]

        full_name = row[
            "locatadd_nm"
        ]

        sigungu_name = (
            full_name
            .removeprefix(
                sido_name
            )
            .strip()
        )

        region_code = (
            f"{sido_cd}{sgg_cd}"
        )

        regions[
            region_code
        ] = {
            "region_code":
                region_code,
            "sido_name":
                sido_name,
            "sigungu_name":
                sigungu_name,
        }

    candidates = list(
        regions.values()
    )

    # 하위 구가 있는 상위 시는 제외
    #
    # 수원시        X
    # 수원시 장안구 O
    # 수원시 권선구 O
    #
    # 의정부시      O
    leaf_regions = []

    for region in candidates:
        sido_name = region[
            "sido_name"
        ]

        sigungu_name = region[
            "sigungu_name"
        ]

        has_child = any(
            (
                other["sido_name"]
                == sido_name
            )
            and (
                other["sigungu_name"]
                .startswith(
                    sigungu_name + " "
                )
            )
            for other
            in candidates
            if (
                other["region_code"]
                != region["region_code"]
            )
        )

        if not has_child:
            leaf_regions.append(
                region
            )

    return sorted(
        leaf_regions,
        key=lambda x: (
            x["sido_name"],
            x["region_code"],
        ),
    )


def save_regions(
    regions: list[dict],
) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO region (
                    region_code,
                    sido_name,
                    sigungu_name,
                    weather_region_code
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    NULL
                )
                ON CONFLICT (region_code)
                DO UPDATE SET
                    sido_name = EXCLUDED.sido_name,
                    sigungu_name = EXCLUDED.sigungu_name
                """,
                [
                    (
                        region[
                            "region_code"
                        ],
                        region[
                            "sido_name"
                        ],
                        region[
                            "sigungu_name"
                        ],
                    )
                    for region
                    in regions
                ],
            )


def verify_regions() -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    sido_name,
                    COUNT(*) AS count
                FROM region
                WHERE sido_name IN (
                    '서울특별시',
                    '경기도'
                )
                GROUP BY sido_name
                ORDER BY sido_name
                """
            )

            rows = cursor.fetchall()

    print()
    print("=" * 70)
    print("DB 적재 결과")
    print("=" * 70)

    total = 0

    for row in rows:
        print(
            f'{row["sido_name"]} : '
            f'{row["count"]}'
        )

        total += row["count"]

    print(f"전체 : {total}")
    print("=" * 70)


def main():
    all_rows = []

    for sido_name in (
        TARGETS.values()
    ):
        print(
            f"[조회] {sido_name}"
        )

        rows = fetch_regions(
            sido_name
        )

        print(
            f"  원본 행 수: "
            f"{len(rows)}"
        )

        all_rows.extend(
            rows
        )

    regions = extract_sigungu(
        all_rows
    )

    print()
    print("=" * 70)
    print("DB 적재 대상")
    print("=" * 70)

    for region in regions:
        print(
            f'{region["region_code"]}'
            f' | '
            f'{region["sido_name"]}'
            f' | '
            f'{region["sigungu_name"]}'
        )

    print()
    print(f"총 {len(regions)}개")

    if len(regions) != 72:
        raise RuntimeError(
            "예상한 지역 수 72개와 일치하지 않습니다. "
            "DB 적재를 중단합니다."
        )

    print()
    print("[DB] region 테이블 적재 시작")

    save_regions(
        regions
    )

    print("[DB] region 테이블 적재 완료")

    verify_regions()


if __name__ == "__main__":
    main()