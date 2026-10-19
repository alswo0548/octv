"""
운영 통계: 한국 날짜의 포함 구간을 UTC 반열린 구간으로 바꿔 조회합니다.
저장된 confidence 분포는 정확도·mAP가 아니며 기존 테이블만 읽습니다.
"""

from datetime import datetime, time, timedelta, timezone
from ..db.session import get_connection
from . import repository, schemas


def get_stats(filters: schemas.StatsFilters):
    # 기간·지역·CCTV 필터를 모든 분포에 공통 적용하고 빈 날짜도 0건으로 반환합니다.
    kst = timezone(timedelta(hours=9))
    query = filters.model_dump()
    query["start_utc"] = datetime.combine(filters.start, time.min, kst).astimezone(timezone.utc).replace(tzinfo=None)
    query["end_utc"] = datetime.combine(filters.end + timedelta(days=1), time.min, kst).astimezone(timezone.utc).replace(tzinfo=None)
    with get_connection() as connection:
        row = repository.aggregate_incidents(connection, query)
    return schemas.StatsResponse(**row, filters=filters)
