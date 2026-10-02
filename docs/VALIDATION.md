# 검증 결과

검증일: 2026-10-02. 사용자 PC와 기존 개인 DB는 건드리지 않았습니다.

## 실제 실행한 검사

| 항목 | 결과 |
|---|---|
| npm ci | 기존 package-lock으로 설치 성공, 프로젝트 의존성 파일 변경 없음 |
| npm run typecheck | WEB/MOBILE TypeScript 통과 |
| npm run format:check | 기존 UI 형식 검사 통과 |
| npm run build:web | Vite 빌드 성공 |
| npm run build:mobile:web | Expo 웹 export 성공, 이미지·영상 자산 포함 |
| Python compileall | backend, ai, scripts 컴파일 성공 |
| 백엔드 unittest | 10개 통과: 실제 HTTP 기동·501·API 목록·환경설정 우선순위·특수문자 비밀번호·최신 DB 재실행·백업 실패 시 차단·백업 선행 |
| pip check | backend/requirements.txt 설치 후 충돌 없음 |
| 새 DB 생성 | PGlite 0.5.8의 PostgreSQL 18.3 WASM 엔진에서 전체 SQL 실행 성공 |
| ERD 구조 | 13개 테이블, 123개 컬럼, 19개 FK, PK·자료형·NULL·IDENTITY·ENUM 10종·UNIQUE 7개 정의 검사 통과 |
| 기존 DB 변경 | 원본 14개 및 직전 13개 테이블 정의에 검증 데이터를 넣고 003 실행 성공 |
| 신규 UNIQUE 동작 | 7개 규칙의 중복 INSERT/재개 UPDATE 거절, 종결 후 재발·다른 CCTV/유형·다른 지역·다른 사용자·반복 평가 허용 |
| 관계·값 보존 | 후보 ID·거리·규칙 버전·생성시각, 알림의 기관추천 FK 이전, FALSE_POSITIVE 보존, COMPLETED 저장 확인 |
| 변경 중단 | 중복 이메일·NULL 수집시각·알림 관계 오류 시 중단·전체 rollback 확인 |
| 재적용 | db.py가 현재 계약 통과 시 백업/마이그레이션을 실행하지 않는 테스트 통과 |
| Python 실제 연결 | 임시 PGlite TCP 서버에 psycopg 연결, check-db.py에서 SELECT 및 읽기 전용 구조 검사 성공 |
| 원본 보존 | frontend, shared, ai, Ultralytics 설정, 의존성·버전 파일 93개를 바이트 비교해 동일함 확인 |

SQL 검증의 범위: psql의 상대 include를 파일 기준으로 펼쳐 WASM PostgreSQL에서 실행했습니다.
Docker의 초기화 훅이나 psql 백업 가드 자체를 실행한 결과는 아닙니다.
Python 연결은 실제 TCP 프로토콜로 테스트했으나 대상은 Docker PostgreSQL 17이 아닌 WASM PostgreSQL 18.3입니다.
PGlite는 검증 환경에만 설치했으며 프로젝트 실행 방식·의존성에는 추가하지 않았습니다.

Word 검수: 폴더 안내 2쪽, Docker DB 가이드 3쪽. 모든 최종 페이지를 렌더링해 한글·표·명령어 잘림이 없는지 확인했습니다.

## 정적 검토

- 최신 ERD 이미지의 테이블·컬럼·상태·PK/FK와 SQL 대조.
- Compose YAML 해석, 모든 바인드 마운트 원본 경로 존재 확인.
- 초기화의 SQL 18개 파일 호출 경로 및 중복 없음 확인.
- database/schema/ 옛 경로 제거, 관련 Python 참조·README·문서·CI 경로 갱신.
- 초기화 진입점만 docker-entrypoint-initdb.d에 노출, 마이그레이션 자동 실행 방지.
- 프로젝트명 octv와 postgres_data 볼륨 유지, 외부 바인딩 127.0.0.1 유지.
- db.py의 전체 백업 → 백업 목록 검사 → 변경 실행 순서, 실패 시 중단 경로 검토.

## 이 환경에서 실행하지 못한 항목

- Docker/Compose 명령과 postgres:17.11-bookworm 이미지의 실제 기동·마운트·초기화 훅.
- Windows Docker Desktop·WSL 2·각 PC의 포트 및 볼륨 보존 동작.
- Docker 안의 pg_dump/pg_restore 백업·복구 명령, psql 메타명령 실행.
- 실제 PostgreSQL 17 서버를 대상으로 한 Python 접속. PR의 database 작업에서 신규 생성·psql 백업 가드·2종 기존 DB 갱신·rollback을 실행하도록 연결했습니다. 실제 원격 결과는 PR Checks를 기준으로 확인합니다.
- Windows UI 직접 조작, 휴대폰 네이티브 실행과 GPU/학습 환경. 이번에 학습 환경을 변경하지 않았습니다.

이 검증으로 업무 기능·인증·AI·알림이 완성됐다고 판단하지 않습니다. 기존 501 골격을 유지합니다.
각 PC에서 Docker_DB_세팅가이드의 config → up → ps/logs → tables → verify → check-db 순서로 마무리하세요.
기존 DB에는 verify 결과를 먼저 보고 백업을 거쳐 migrate를 사용합니다.
