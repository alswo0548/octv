"""동일 사건 중복 판별 작업 위치."""

from ..contracts import IncidentCandidate


def find_existing(
    candidate: IncidentCandidate, recent_incidents: list[dict]
) -> int | None:
    # TODO: CCTV·유형·위치·시간창을 비교하여 신규/갱신을 구분하세요. dedup_key 규칙을 DB 담당자와 합의하세요.
    raise NotImplementedError("동일 사건 중복 판별 구현 예정")
