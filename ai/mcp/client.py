
"""
OCTV MCP 서버의 도구를 호출하는 클라이언트 파일

- backend/app/integrations/context.py 의 
        collect_context() 함수로 사건의 외부 데이터를 수집하고 통합

- ai/mcp/tools.py 의 
        query_context() MCP에서 사용할 조회 함수

- ai/mcp/server.py 의
        create_server() 함수로 조회 함수를 MCP 도구로 등록

- 현재 파일의 collect_via_mcp() 에서 MCP 도구를 실제로 호출하고 결과를 받는다.

주요 기능
1. 기존 MCP 서버와 클라이언트 연결
2. 최종적으로 ContextSnapshot 객체로 복원하여 반환

※ 실제 외부 API 호출은 MCP 서버 내부에서 수행
※ 현재는 단일 Python 환경에서 in-memory 방식으로 연결
"""

from datetime import datetime
from fastmcp import Client
from ai.contracts import ContextSnapshot
from .server import create_server


# MCP 서버를 통해 사건의 외부 상황 정보를 수집하는 비동기 함수
async def collect_via_mcp(incident_id):

    """
    in-memory 방식이므로 별도 서버 프로세스 없이 연결
    여기서 in-memory 방식은 MCP 서버와 클라이언트를 
    하나의 Python 프로그램 안에서 간편하게 연결하는 방식
    """
    async with Client(
        create_server()
    ) as client:

        # MCP 서버에 등록된 도구 호출
        result = await client.call_tool(
            'get_incident_context',                 # 도구 이름
            {
                'incident_id': incident_id          # 외부 정보를 조회할 사건 ID
            }
        )

    data = result.data

    # MCP에서 받은 데이터를 ContextSnapshot으로 복원
    return ContextSnapshot(

        data['incident_id'],

        # ISO 8601 (날짜와 시간을 일정한 규칙에 따라 표현하는 국제 표준 형식) 문자열을 datetime 객체로 변환
        datetime.fromisoformat(
            data['captured_at']
        ),

        data['measurements'],           # 강수량·수위·교통 등 통합 외부 데이터

        tuple(
            data['sources']
        )
    )
