# 개발 기준

이번 단계는 구조·DB·실행 준비까지입니다. 전체 개발 시나리오와 후속 구현은 다음 요청에서 이어갑니다.

## 현재 확인할 기준

- DB 기준은 database/ERD.png입니다. 기능별 정의는 backend/app/각기능/sql/에 있습니다.
- PostgreSQL과 psycopg + SQL을 유지합니다. 인증·API 업무 처리와 AI 함수는 아직 골격입니다.
- 공통 연결·트랜잭션은 backend/app/db/session.py이며 설정은 backend/app/config.py가 읽습니다.
- 기존 WEB/MOBILE 목업과 자산은 보존했습니다. UI 문자열 ID·백분율을 DB BIGINT·0~1 confidence로 그대로 저장하지 않습니다.
- 데이터·모델·학습 설정은 개인 작업을 유지합니다. ZIP에 미포함되어도 삭제 대상으로 취급하지 않습니다.
- 자료 간 상태값·완료 처리 충돌은 CHANGES.md에 정리했습니다. 기존 문서의 오래된 정책을 확정 기준으로 다시 적용하지 않습니다.

## 읽을 문서

STRUCTURE.md는 수정 위치, DATABASE.md는 Docker·DB 명령, CHANGES.md는 반영 기준과 미정 사항,
VALIDATION.md는 실제 실행 결과와 미검증 범위입니다. 요약 Word 문서는 같은 docs/에 있습니다.
