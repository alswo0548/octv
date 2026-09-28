"""탐지 이후 처리 흐름 작업 위치."""

from ..contracts import IncidentCandidate


def run_pipeline(candidate: IncidentCandidate) -> dict:
    # TODO: 시간 검증/중복 확인 → 사건 등록 → 상황 수집 → 위험도 → 기관 → 경로 순으로 연결하세요. 실패 재시도·중복 저장 방지를
    # 설계하세요. 전송과 감시 OFF는 자동 실행하지 마세요.
    raise NotImplementedError("탐지 이후 처리 흐름 구현 예정")
