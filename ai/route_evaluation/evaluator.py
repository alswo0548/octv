"""기관별 A/B/C 경로 평가 작업 위치."""

from ..contracts import ContextSnapshot


def evaluate(context: ContextSnapshot, candidates: list[dict]) -> list[dict]:
    # TODO: 교통·통제·위험·접근성·거리 점수와 제외 사유를 구현하세요. 경로 3개와 제외된 후보 정보도 보존하세요.
    raise NotImplementedError("기관별 A/B/C 경로 평가 구현 예정")
