"""후보 기관 추천 작업 위치."""

from ..contracts import ContextSnapshot


def recommend(context: ContextSnapshot, agencies: list[dict]) -> list[dict]:
    # TODO: 사건 유형·기관 역할·거리·접근성을 기준으로 후보와 점수 근거를 반환하세요. 실제 전달은 관리자 선택 후 백엔드에서 처리합니다.
    raise NotImplementedError("후보 기관 추천 구현 예정")
