"""05번 실행 환경 확인 또는 기존 사건의 판단 미리보기.

python scripts/check_langgraph.py
python scripts/check_langgraph.py --incident-id 31
python scripts/check_langgraph.py --incident-id 31 --save

--save를 명시한 마지막 명령만 판단 결과를 DB에 저장합니다.
미리보기도 실제 외부 API를 호출하므로 요청 쿼터가 사용될 수 있습니다.
인증키·API 요청 URL·원문 오류는 출력하지 않습니다.
"""

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# 수집·계산 결과만 반환하여 파이프라인 마지막 DB 저장 노드를 대체합니다.
def preview_result(state):
    assessment = state['assessment']
    return {
        'status': 'PREVIEW_NOT_SAVED',
        'incident_id': state['incident_id'],
        'risk_score': assessment['risk_score'],
        'risk_level': assessment['risk_level'],
        'priority': assessment['priority'],
        'missing_fields': assessment['risk_breakdown']['missing'],
        'measurement_statuses': {
            name: item.get('status')
            for name, item in state['context'].measurements.items()
        },
        'route_fetch_statuses': {
            str(agency_id): info['status']
            for agency_id, info in state['route_fetches'].items()
        },
        'agencies': [
            {
                'agency_id': row['agency_id'],
                'rank': row['recommendation_rank'],
                'score': row['recommendation_score'],
                'access_status': row['score_breakdown_json']['access_status'],
            }
            for row in state['recommendations']
        ],
    }


# 기본 실행은 패키지·설정 확인뿐이며, 사건 ID를 주어야 실제 조회를 시작합니다.
def main() -> int:
    parser = argparse.ArgumentParser(description='OCTV LangGraph 실행 확인')
    parser.add_argument('--config', help='실행 설정 JSON 경로; 생략 시 환경변수 사용')
    parser.add_argument('--incident-id', type=int, help='이미 저장된 테스트 사건 ID')
    parser.add_argument('--save', action='store_true', help='판단 결과를 실제 DB에 저장')
    args = parser.parse_args()
    if args.save and args.incident_id is None:
        parser.error('--save에는 --incident-id가 필요합니다.')
    versions = {}
    for package in ('langgraph', 'fastmcp', 'psycopg', 'httpx', 'python-dotenv', 'shapely'):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = 'MISSING'
    print(json.dumps({'python': sys.version.split()[0], 'packages': versions}, indent=2))
    if 'MISSING' in versions.values():
        print('누락된 기존 의존성이 있습니다. 프로젝트 requirements와 설치 환경을 확인하세요.')
        return 1
    try:
        from ai.config import get_runtime_config
        config = get_runtime_config(args.config)
        print('실행 설정 검증 완료. Context 방식:', config['context_transport'])
        print('경로 인증키 설정 여부:', bool(config['route_api_key']))
        if args.incident_id is None:
            print('환경 확인만 완료했습니다. API 호출·DB 저장은 실행하지 않았습니다.')
            return 0
        if not args.save:
            config['save_analysis'] = preview_result
        from ai.orchestration.pipeline import run_pipeline
        result = run_pipeline(args.incident_id, config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        # 응답 원문과 인증키를 포함할 수 있는 str(exc)나 traceback은 출력하지 않습니다.
        print('실행 중단:', type(exc).__name__)
        print('설정값·관측소 매핑·DB·외부 API 상태를 확인하세요. 통과로 처리하지 않습니다.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
