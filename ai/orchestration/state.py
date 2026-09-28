"""처리 단계 공통 상태 작업 위치."""

from ..contracts import IncidentCandidate


def create_state(candidate: IncidentCandidate) -> dict:
    # TODO: 후보, 외부 상황, 위험도, 기관, 경로, 오류 상태를 정의하세요. LangGraph 사용 시 TypedDict 등 명시적 상태 계약으로
    # 발전시키세요.
    raise NotImplementedError("처리 단계 공통 상태 구현 예정")
