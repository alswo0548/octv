"""
기상청 초단기실황 API 데이터 처리

주요 기능
1. 기상청 API 응답에서 강수량(RN1) 데이터 추출 후 최신 관측값 선택 [RN1: 1시간 강수량(mm)]
2. 추출한 강수량은 float 로 변환하여 관측시간을 UTC로 반환한다.
3. normalization.py 에서 만든 measurement()로 데이터 유효성 검사 진행
"""

from datetime import datetime, timezone, timedelta
from .normalization import fetch_metric

KST = timezone(timedelta(hours=9))

# 기상청 API를 호출하고 강수량 데이터를 검증하는 함수
def fetch_data(query: dict) -> dict:
    return fetch_metric(
        query,
        parse_rainfall,
        'KMA_ULTRA_NCST',
        'mm'
    )

# 기상청 API 응답에서 강수량을 추출
def parse_rainfall(payload):
    response = payload["response"]

    if str(response["header"]["resultCode"]) != "00": # "00"은 정상적으로 응답했다는 의미
        raise ValueError("기상 API 업무 오류")

    # 응답 데이터에서 실제 관측 목록을 가져옴. 관측 목록이 없으면 빈 리스트를 사용
    items = response["body"].get(
        "items", {}
    ).get("item", [])

    if isinstance(items, dict):
        items = [items]

    # 여러 관측 항목 중 가장 최신 데이터의 RN1(1시간 강수량)만 선택
    rows = [
        x for x in items
        if x.get("category") == "RN1"
    ]

    if not rows:
        return None, None

    row = max(
        rows,
        key=lambda x: (
            x["baseDate"],
            x["baseTime"]
        )
    )

    value = float(row["obsrValue"])

    if value < 0:
        return None, None

    at = datetime.strptime(
        row["baseDate"] + row["baseTime"],
        "%Y%m%d%H%M"
    ).replace(tzinfo=KST)

    return value, at.astimezone(timezone.utc)
