# 2026년 10월 2일 개발 기반 정비

## 기준과 보존

실제 첨부 OCTV(1).zip과 OCTV 기획문서(3).zip을 사용했습니다. 요청문 안의 과거 ZIP 이름 대신 현재 첨부 내용을 확인했습니다.
새 첨부 최종 ERD를 대조하고 UNIQUE 표시를 더한 database/ERD.png 및 ERD.svg를 작성했습니다. 원본은 database/reference/ERD_2026-10-02.png입니다. WEB/MOBILE 소스·자산, shared, AI 학습 설정, Ultralytics/settings.json, 의존성 버전과 실행 명령은 유지했습니다.
학습 데이터·가중치는 원래 ZIP에 없으며 datasets/, weights/, runs/ 등 개인 학습 경로를 유지합니다. 클래스 ID와 학습 설정은 변경하지 않았습니다.

## 코드와 ERD 일치 변경

| 항목 | 반영 |
|---|---|
| route_evaluations | 최신 ERD에 없어 제거. 규칙 버전·생성시각·기관추천 관계를 route_candidates에 반영 |
| route_candidates | 개별 점수 5개 컬럼 제거, score_breakdown_json NULL 허용, 기관추천 FK 직접 연결 |
| notifications | route_evaluation_id 대신 agency_recommendation_id FK. 나머지 현재 정의 유지 |
| incidents | detection_duration_sec 제거, 상태 DETECTED/CONFIRMED/SENT/RESOLVED/FALSE_POSITIVE |
| cctvs | 감시 모드 BASE/ALERT/VERIFY/POST_ALERT/OFF. 기존 의미를 ERD에 맞게 주석 정리 |
| incident_agency_recommendations | recommended_at 제거. RECOMMENDED/DELIVERED/COMPLETED |
| weather_alerts / incident_contexts | raw_data_json / raw_context_json 제거. captured_at NOT NULL 유지 |
| agencies | phone NULL 허용 |

이는 첨부 ERD에 맞춘 변경이며 임의 재설계가 아닙니다. 14개 → 13개 테이블, 134개 → 123개 컬럼, 20개 → 19개 FK입니다.
서비스 재난 유형은 기존 VARCHAR(50)을 유지했습니다. 수집 중인 3개 학습 클래스만으로 서비스 유형을 제한하지 않았습니다.
ERD의 DATETIME은 PostgreSQL TIMESTAMP WITHOUT TIME ZONE으로, AUTO_INCREMENT는 IDENTITY로 표현했습니다.

명백한 오류: 추천기관 agency_id의 BIGIBT → PostgreSQL에서 실행 불가 → 참조 대상 agencies.id와 같은 BIGINT로 수정.
새 테이블·컬럼은 추가하지 않았습니다. 사용자 요청에 따라 UNIQUE 규칙 7개를 추가했습니다. 상세 조합과 범위는 ERD_UNIQUES.md에 있습니다.

## 자료 간 충돌과 미정 사항

- 새 ERD의 FALSE_POSITIVE를 사건 ENUM과 API 응답 형식에 반영했습니다. 오탐 판정 업무 처리는 후속 구현 대상입니다.
- 새 ERD의 COMPLETED를 기관추천 ENUM에 반영했습니다. 기관별 완료 처리와 사건 RESOLVED 전환 로직은 후속 구현 대상입니다.
- 기존 UI 목업의 동작은 그대로입니다. 화면상 동작을 실제 DB 처리로 설명하지 않습니다.
- 아키텍처 그림에는 RDBMS MySQL 및 Redis/Celery/MediaMTX가 있으나 이번 명시 요청에 따라 PostgreSQL만 구성했습니다. 추가 서비스를 설치하지 않았습니다.
- 현재 서비스는 flood / fallen_tree / severe_road_damage / road_obstacle 네 유형을 사용합니다. 모델 내부 클래스와 ID는 가중치 적용 전에 별도로 확인합니다.
- 최신 ERD의 is_monitored는 기본 감시 대상 여부이고 monitored_mode는 현재 감시 상태입니다. 기존 문서의 둘을 같은 ON/OFF로 다루던 설명은 수정했습니다. 특보 중 수동 OFF 허용·재활성화 제외 등 운영 정책은 별도 확인 사항이며 이번에 구현하지 않았습니다.

## 실행 가능 부분과 미구현 부분

실행 가능한 코드: PostgreSQL 초기화·변경 SQL, dotenv 설정 읽기, psycopg 공통 연결/트랜잭션, 실제 접속 검사 스크립트, 백업·변경 실행 도우미.
실행 검증한 범위와 환경에서 실행하지 못한 부분은 VALIDATION.md에 구분했습니다.
백엔드 업무 API·repository, 인증, CCTV Worker, 외부 API, AI 추론·판단, 알림은 골격입니다. 업무 API는 501 응답을 유지합니다.
기관 전달 요청 초안은 삭제된 route_evaluation_id 대신 route_candidate_id로 경로 후보를 식별하도록 맞췄습니다. 실제 저장 계약은 미구현입니다.

## GitHub와 기존 DB에 반영

이번 변경은 원본 ZIP과 동일한 GitHub main 커밋 88a108a8503841de43811360b5ca956f97ebbb30에서 시작했습니다.
작업 브랜치의 PR을 main에 병합한 뒤 GITHUB_DB_APPLY.md 순서대로 각 PC에서 갱신합니다.
미커밋 파일, 개인 .env, .venv, node_modules, 학습 데이터·가중치는 별도로 보존합니다.

`python scripts/db.py migrate`가 현재 구조를 검사하고, 이미 최신이면 아무 변경 없이 끝납니다.
기존 14개 또는 직전 13개 테이블 DB는 검증된 전체 백업 후 003_final_erd_uniques.sql 하나로 갱신합니다.
001·002를 먼저 실행하지 마세요. 002는 직전 배포 이력을 재현할 수 있도록 당시 ENUM과 계약 검사를 고정했습니다.
003은 원래 FALSE_POSITIVE 상태를 보존합니다. 중복 데이터, NULL 수집시각, 알림/기관 연결 불일치는 중단·전체 rollback합니다.
삭제되는 옛 컬럼·JSON은 .dump 백업에서 복구할 수 있습니다. 데이터 자동 삭제·중복 병합·시각 추정은 하지 않습니다.

후속 작업은 이 수정본과 해당 PR을 기준으로 이어갑니다.
