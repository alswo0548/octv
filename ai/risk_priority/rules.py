"""위험도·우선순위 산정 작업 위치."""

from ..contracts import ContextSnapshot, Assessment


def assess(context: ContextSnapshot) -> Assessment:
    # TODO: 유형별 규칙, 점수 근거, P1/P2/P3 및 rule_version을 구현하세요. 확정되지 않은 가중치는 임의 결정하지 마세요.
    raise NotImplementedError("위험도·우선순위 산정 구현 예정")
