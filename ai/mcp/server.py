
"""
OCTV 외부 상황 정보 조회용 MCP 서버

주요 기능
1. FastMCP 서버 생성
2. 사건 외부 정보 조회 함수를 MCP 도구로 등록
3. ContextSnapshot을 딕셔너리로 변환
4. 수집 시각을 ISO 8601 문자열로 변환
5. stdio 방식으로 MCP 서버 실행

※ 외부 API 호출 및 위험도 계산은 직접 수행하지 않음
"""

from dataclasses import asdict
from fastmcp import FastMCP
from .tools import query_context

# OCTV MCP 서버를 생성하고 도구를 등록하는 함수
def create_server():
    server = FastMCP("OCTV context")

    # 아래 함수를 MCP 도구로 등록
    # AI 시스템의 MCP 클라이언트가 호출할 수 있는 도구로 등록
    @server.tool()
    def get_incident_context(incident_id: int) -> dict:

        # 사건 ID로 외부 상황 정보 조회
        # ContextSnapshot 객체를 직렬화 가능한 딕셔너리로 변환
        result = asdict(
            query_context(incident_id)
        )

        # UTC 수집 시각을 ISO 8601 문자열로 변환 (JSON으로 전달하기 위한 처리)
        result["captured_at"] = (
            result["captured_at"].isoformat()
        )

        return result

    return server

if __name__ == "__main__":

    # MCP 서버를 생성하고 stdio 통신 방식으로 실행
    create_server().run(
        transport="stdio"
    )
