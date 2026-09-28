"""수집 근거만 사용해 설명문을 생성하고 실패/근거 누락을 구분하세요. 감시 OFF·출동 결정을 위임하지 마세요."""

from ..errors import FeatureNotImplemented


def fetch_data(query: dict) -> dict:
    # TODO: 제공자 확정 → 응답 계약 → timeout/재시도/오류 처리 → 값 정규화.
    # 자격증명은 config에서 주입하며 실패를 정상 데이터로 바꾸지 마세요.
    raise FeatureNotImplemented("llm 외부 연동 구현 예정")
