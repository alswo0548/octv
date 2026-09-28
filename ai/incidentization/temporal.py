"""시간 연속성 검증 작업 위치."""

from ..contracts import IncidentCandidate


def validate_candidate(history: list[IncidentCandidate]) -> IncidentCandidate | None:
    # TODO: 후보 신뢰도·탐지 횟수·지속시간 기준으로 사건 후보를 검증하세요. 임계값은 설정에서 받으세요.
    raise NotImplementedError("시간 연속성 검증 구현 예정")
