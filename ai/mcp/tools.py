"""MCP 도구와 외부 어댑터 연결 작업 위치."""

from ..contracts import ContextSnapshot


def query_context(incident_id: int) -> ContextSnapshot:
    # TODO: backend/app/integrations의 조회 어댑터를 연결하고 단위·출처·수집 시각을 함께 반환하세요. 동일 API 연동을 중복
    # 작성하지 마세요.
    raise NotImplementedError("MCP 도구와 외부 어댑터 연결 구현 예정")
