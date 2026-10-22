r"""기존 감시 ON CCTV를 포함하여 자동 매핑 캐시를 한 번 준비합니다.

프로젝트 루트에서:
  .venv\Scripts\python -m scripts.prewarm_cctv_context_mapping --cctv-id 3
  .venv\Scripts\python -m scripts.prewarm_cctv_context_mapping --all-monitored

API 요청·DB 변경·사건/알림 생성 없음. Redis 매핑 키만 생성합니다.
"""

import argparse

from backend.app.config import load_environment
from backend.app.integrations.cctv_mapping import (
    auto_mapping_enabled,
    prepare_all_monitored,
    prepare_monitored_cctv,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cctv-id", type=int)
    group.add_argument("--all-monitored", action="store_true")
    args = parser.parse_args()
    load_environment()
    if not auto_mapping_enabled():
        raise SystemExit("OCTV_AUTO_MAPPING_ENABLED=1 설정 후 실행하세요.")
    if args.cctv_id is not None:
        status = prepare_monitored_cctv(args.cctv_id)
        print(f"cctv_id={args.cctv_id} status={status}")
    else:
        print("monitored_cache_status=", prepare_all_monitored())


if __name__ == "__main__":
    main()
