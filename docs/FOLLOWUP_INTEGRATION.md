# OCTV 후속 통합 검증

기준: 2026-10-22, `fix/minjae-followup-integration`, 최신 main `15df572`에서 분기.
이 문서는 실행 계획이며 아래 체크박스는 실제 서버·기기에서 확인한 뒤 표시한다.

## 코드 대조 결과

| 분류 | 항목과 근거 | 이번 처리 |
|---|---|---|
| 이미 구현·병합 | 사건 COMMIT 후 `after_incident_committed`, POST analysis, 결과 GET, 7개 LangGraph 노드와 MCP Context | 재구현 없음 |
| 이미 구현·병합 | PR #48 환경 로딩, #50·51 큐·잠금, #52·54·57 매핑·캐시 | 유지 |
| 이미 구현·병합 | PR #60 analysis Worker 명령 오타 수정, #59 팀원 VERIFY 수정 | 최신 main 그대로 보존 |
| 이미 구현·병합 | 기관 전달 트랜잭션, DB 알림 중복 방지, 발송·재시도·Beat 복구, 모바일 세션·터치 연결 | 유지 |
| 실제 누락 | 웹 사건·분석 결과·CCTV·추천 경로·지원요청의 주기적 재조회 | 기존 GET에 조회 폴링 연결 |
| 실행 준비 누락 | 알림 Worker·Beat 전용 Windows 실행 파일 | CMD 2개 추가 |
| 진단 보완 | 같은 사건의 DB 저장 및 Redis 발송 상태 확인 | 읽기 전용 `check_incident_flow.py` 추가 |
| 실환경 확인 | 외부 API·Redis/Celery·DB 동시성·Android·카카오내비 | 아래 순서로 한 번에 확인 |
| 설정·정책 대기 | Firebase·공개 주소·운영 백업·회원가입 승인 정책 | 자동 변경 없음 |
| 모델 대기 | 최종 가중치·독립 Holdout·영상 시연 | 학습·가중치 교체 없음 |

폴링은 성공/실패 응답 완료 후 10초 간격이며 통합관제 외부상황은 60초 간격이다. 숨긴 탭에서는 새 요청을 멈추고 복귀 시 조회한다. 선택 사건·필터를 유지하며 화면/세션 변경 시 요청을 취소한다. 실패를 정상으로 바꾸지 않고 기존 오류 영역을 사용한다. 설정 편집·통계는 기존 단발 조회를 유지한다. 기관 선택 모달의 전송은 자동 반복하지 않는다.

진행 중 작업도 보존한다. `feat/incident-detection-overlay` (`d65f4cc`)는 main보다 1개 커밋 앞서며 같은 사건 화면의 이미지 표시 구간을 수정한다. 이번 조회 훅 구간과 텍스트 병합 충돌이 없음을 확인했으며 해당 변경을 이 PR에 포함하지 않았다. `feature/sy-cctv-context-mapping` (`29b89c9`)는 분기된 이전 `ai/context_resolver.py` 작업으로, 이번 PR에서 가져오거나 수정하지 않는다. 체크 시 열린 PR은 없었다.

기본 검사: 신규 폴링 모의 검사 6개, 진단 요약 검사 3개, 웹 TypeScript, 변경 TS/TSX Prettier, Python 문법, `git diff --check` 통과. 전체 회귀·실제 DB/Redis·외부 API·FCM·Windows CMD 기동·Android 검증은 이번에 수행하지 않았다.

## 준비

명령은 프로젝트 루트의 Windows CMD 기준이다. 기존 `.env`·API 키·DB·모델은 유지한다. 아래 작업은 후속 검증 때 수행한다.

- [ ] `git status --short`로 PC의 미커밋 변경을 확인한다. 변경이 있으면 별도 보존 후 진행하며 강제 덮어쓰기를 하지 않는다.
- [ ] `git fetch origin fix/minjae-followup-integration`으로 작업 브랜치를 가져온다.
- [ ] `git switch --track origin/fix/minjae-followup-integration`으로 검증 브랜치에 진입한다. 이미 로컬 브랜치가 있으면 `git switch fix/minjae-followup-integration`을 사용한다.
- [ ] `npm ci`로 기존 잠금 파일의 의존성을 설치한다.
- [ ] 기존 Python 가상환경에 루트·backend·ai requirements의 의존성이 설치됐는지 확인한다. 이번 PR에는 패키지 추가가 없다.
- [ ] 테스트용 CONTROL_ADMIN 계정을 준비한다.
- [ ] 전달할 기관 소속 RESPONDER 계정을 준비한다.
- [ ] 다른 기관 계정을 권한 차단 확인용으로 준비한다.
- [ ] 기존 `OCTV_DECISION_ENABLED=1`, Redis 주소, Runtime JSON 경로를 확인한다.
- [ ] 기존 외부 API 설정과 매핑을 확인한다. 이미 정상인 키를 재발급하거나 값을 출력하지 않는다.
- [ ] 서버 Firebase 프로젝트 및 서버 자격증명 접근을 준비한다.
- [ ] `OCTV_PUSH_START_AT`을 시간대가 있는 최초 활성화 시각으로 정한다. 관련 프로세스에서 같은 값을 사용하며 재시작할 때마다 변경하지 않는다.
- [ ] 검증 환경에서 `OCTV_PUSH_ENABLED=1`을 적용한다.
- [ ] 검증 환경에서 `OCTV_PUSH_RECOVERY_ENABLED=1`을 적용한다.
- [ ] Android Firebase 클라이언트 파일과 `OCTV_ANDROID_PACKAGE`가 같은 앱을 가리키는지 확인한다. 서버 서비스 계정 파일을 앱에 넣지 않는다.
- [ ] `EXPO_PUBLIC_API_BASE_URL`을 휴대폰에서 접근할 수 있는 백엔드 주소로 설정한다.
- [ ] 카카오내비 검증용 네이티브 앱 키·패키지·키 해시와 설치 앱을 준비한다.

## 서비스 실행

각 장기 실행 프로세스는 별도 CMD 창에서 실행한다. Worker와 Beat는 서로 다른 프로세스이며 Beat는 환경당 한 개만 실행한다.

- [ ] `docker compose up -d db redis mediamtx`로 기존 볼륨을 사용하는 서비스를 시작한다. `down -v`나 초기화 SQL은 실행하지 않는다.
- [ ] `.venv\Scripts\python scripts\check_incident_flow.py`를 실행한다. 설정 존재 여부와 Runtime JSON 검사만 수행하며 외부 연결 성공을 뜻하지 않는다.
- [ ] `.venv\Scripts\python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`으로 검증용 API를 시작한다. 모바일 접근은 허용된 사설망에서만 연다.
- [ ] `scripts\run_analysis_worker.cmd`로 analysis Worker를 시작한다. 기대: `analysis` 큐와 `octv.analyze_incident`, ready.
- [ ] `scripts\run_notification_worker.cmd`로 notifications Worker를 시작한다. 기대: `notifications` 큐와 발송·복구 task, ready.
- [ ] `scripts\run_notification_beat.cmd`로 Beat를 시작한다. 기대: 조건 충족 시 60초 주기 복구 task 예약.
- [ ] `npm run dev:web`으로 웹을 시작한다.
- [ ] 팀원의 기존 `scripts/run_cctv_runtime.py` 실행 절차로 Runtime을 시작한다. 모델·추론·시간 검증 내부는 변경하지 않는다.
- [ ] Firebase 설정을 포함한 Android 개발 빌드 또는 preview APK를 설치한다. Expo Go·모바일 웹은 FCM 실기기 검증 대상이 아니다. 기존 `frontend/mobile/eas.json`의 development/preview profile을 사용한다.
- [ ] 휴대폰의 OCTV 알림 권한을 허용한다.
- [ ] 앱에서 대상 RESPONDER로 로그인한다.

## 같은 Incident ID로 정상 흐름

검증 기록: `Incident ID = ______`, `CCTV ID = ______`, `기관 ID = ______`, `알림 ID = ______`.
가능하면 팀원의 승인된 재난 영상으로 생성한 테스트 사건을 사용한다. 기존 운영 사건이나 이미 평가된 사건의 평가/알림을 지우지 않는다.

- [ ] 웹에서 승인된 CCTV 감시를 ON으로 전환한다. 기대: 매핑 준비와 Runtime 상태를 구분해 확인. 실패 위치: API, analysis Worker, 매핑 캐시 상태.
- [ ] `.venv\Scripts\python scripts\check_context_connections.py --cctv-id <CCTV_ID> --skip-weather --skip-events`를 실행한다. 이미 확인한 기상·돌발 조회를 반복하지 않고 교통 링크 오류를 확인한다. HTTP 200·빈 목록만으로 정상 도로라고 판정하지 않는다.
- [ ] 팀원과 승인한 영상으로 테스트 사건 한 건을 생성한다. 기대: DB Incident ID. 실패 위치: Runtime → 사건 저장 로그. 팀원 내부 수정은 별도 요청한다.
- [ ] 분석 Worker에서 같은 Incident ID의 처리 완료를 확인한다. 기대: Context → Rule → 기관 → 경로 → DB. 실패 위치: `decision_not_queued`, `analysis_publish_failed`, Worker 오류 유형.
- [ ] 웹 사건 화면을 새로고침하지 않고 분석 결과를 확인한다. 기대: 조회 완료 후 약 10초 안에 후속 GET, 같은 선택 사건에 위험도·근거 표시.
- [ ] `.venv\Scripts\python scripts\check_incident_flow.py --incident-id <INCIDENT_ID>`를 실행한다. 기대: contexts/assessments 각 1, 분석 잠금 TTL -2 또는 처리 중 양수. -1은 만료 없음으로 별도 확인한다.
- [ ] Swagger의 기존 관리자 인증으로 `POST /api/incidents/{id}/analysis`를 같은 ID에 재요청한다. 기대: 기존 평가면 `ALREADY_READY_OR_INACTIVE`, 처리 중이면 `ALREADY_QUEUED_OR_RUNNING`. task_id는 분석 결과가 아니다.
- [ ] 같은 진단 명령으로 평가 행 개수가 늘지 않았는지 확인한다.
- [ ] 웹에서 해당 사건을 확인 처리한다. 기대: DETECTED → CONFIRMED.
- [ ] 웹에서 추천 기관을 선택해 전달한다. 기대: 기관 DELIVERED, 사건 SENT, `created_notification_count`, Push 접수 상태를 각각 확인한다.
- [ ] 같은 기관 전달을 한 번 더 요청한다. 기대: 추가 DB 알림 0, 완료 기관을 되돌리지 않음.
- [ ] 같은 진단 명령으로 DB 알림 ID·개수와 Redis 기기별 결과를 확인한다. ACCEPTED는 FCM 접수이며 휴대폰 표시를 뜻하지 않는다. `NO_REDIS_RECORD`는 성공이 아닌 기록 없음이다.
- [ ] 앱 알림 목록에서 해당 DB 알림을 확인한다.
- [ ] 휴대폰 알림 영역에서 Push 표시를 직접 확인한다.
- [ ] Push를 터치한다. 기대: 본인 알림 확인 후 서버가 반환한 사건 ID의 상세 화면.
- [ ] 앱의 경로 화면을 연다. 기대: 같은 사건·본인 기관의 저장 경로, 미확인 통제는 미확인 표시.
- [ ] 카카오내비 실행 버튼을 누른다. 기대: 선택한 유효 경로의 목적지 연결. 실패 위치: 앱 패키지·키 해시·내비 설치·경로 좌표.
- [ ] 다른 기관 계정으로 해당 사건을 조회한다. 기대: 권한 차단 또는 해당 기관 범위에서 제외. 이전 계정의 알림 터치도 접근 권한이 되지 않는다.
- [ ] 대상 RESPONDER 계정에서 현장 대응 완료를 누른다. 기대: 기관 COMPLETED, 마지막 미완료 기관이면 사건 RESOLVED.
- [ ] 종합상황실 화면에서 같은 사건의 상태 자동 갱신을 확인한다.
- [ ] CCTV 마지막 프레임 시각을 웹 KST 표시와 대조한다. `LIVE` 재생 여부와 Runtime 프레임 시각은 별도다.

## 장애와 기기 상태를 묶어서 확인

장애 재현은 격리 검증 환경에서 수행한다. 이미 끝난 알림을 다시 보내기 위해 발송 기록을 삭제하지 않는다. 포그라운드·백그라운드·종료 앱의 새 Push 비교에는 새 DB 알림이 필요하므로 정상 흐름의 Incident ID를 재사용할 수 없는 항목은 보조 테스트 사건 ID를 기록한다.

- [ ] 웹 탭을 숨긴다. 기대: 진행 중 요청 종료 후 새 주기 요청 없음. 확인: 브라우저 Network.
- [ ] 웹 탭으로 돌아온다. 기대: 즉시 조회 재개, 중복 진행 요청 없음.
- [ ] 검증 브라우저를 오프라인으로 전환한다. 기대: 정상/안전 대체 없이 오류 표시.
- [ ] 검증 브라우저 연결을 복구한다. 기대: 다음 조회에서 실제 값 복원.
- [ ] 앱이 전면에 있는 상태에서 새 테스트 알림을 전달한다. 기대: 개인 설정·권한에 따른 표시.
- [ ] 앱을 백그라운드로 둔 상태에서 새 테스트 알림을 전달한다. 기대: Android 표시, 중복 로컬 알림 없음.
- [ ] 앱이 종료된 상태에서 새 알림을 터치한다. 기대: 로그인 복원 후 본인 알림·상세 확인.
- [ ] 앱에서 로그아웃한다. 기대: 기기 등록 해제 후 기존 인증 로그아웃. 실패 시 완료로 표시하지 않음.
- [ ] 같은 설치에서 다른 계정으로 로그인한다. 기대: 소유 관계 갱신, 이전 계정 알림 접근 차단.
- [ ] 개인 Push를 OFF로 전환한다. 기대: DB 알림은 유지되고 새 발송은 USER_PUSH_OFF로 생략.
- [ ] 격리 환경에서 큐 발행 장애를 재현한다. 기대: DB 전달은 유지, `QUEUE_UNCONFIRMED` 구분. 이미 큐에 들어갔을 가능성도 보존.
- [ ] 격리 환경의 큐 연결을 복구한다. 기대: Beat가 30분 이내 미완료 알림을 다시 등록, notifications Worker가 처리. 종료 상태·4회 한도·활성화 기준 이전 알림은 제외.
- [ ] 격리 환경에서 분석의 일시 오류를 재현한다. 기대: 지정 오류만 30초 후 최대 3회 재시도, 최종 종료 시 소유 잠금 해제. 전체 그래프를 다시 실행하며 체크포인트 재개는 아님.
- [ ] 테스트 발송 중 Worker 종료를 재현한다. 기대: 잠금 TTL 만료 후 복구 가능성 확인. FCM 접수 직후 기록 전 종료의 중복 가능성은 별도 기록한다.

## 보호 영역과 후속 요청

- 이번 diff에는 인증·회원가입 내부, 탐지·전처리·사건화·CCTV Runtime 내부, Rule·기관/경로 정책, DB 스키마, 모델·데이터 변경이 없다.
- 현재 독립 진행을 막는 팀원 코드 변경은 확인되지 않았다. Runtime에서 사건이 만들어지지 않으면 CCTV ID·시각·hazard·후보/확정 단계와 `register_detection` 호출 여부를 박수연에게 전달한다. 분석 측 연결 조건은 COMMIT된 양의 Incident ID와 운영 4개 클래스다.
- 팀원에게 전달할 모델 관련 확인: 승인 가중치의 class ID/names, 실제 입력 전처리·confidence·면적·시간 검증 조건. 단일 이미지 평가와 live 사건화의 차이를 확인하되 이 PR에서 내부 정책을 조정하지 않는다.
- 사용자/외부 서비스: Firebase·Android 빌드·기기 권한·API 제공 상태·카카오내비·배포 HTTPS/CORS/MediaMTX·백업 복원은 준비 또는 실환경 확인이 필요하다.
- 정책 결정: 외부 공개 전 회원가입 승인·접근 제한은 확정 후 별도 반영한다.
- 모델: 독립 Holdout, 반복 영상의 사건 독립성, 실제 지연·오탐·미탐 및 최종 가중치 결정은 대기한다.
- 분석은 DB 평가 중복을 막지만 큐 유실 전체를 자동 복구하는 분석용 Beat/outbox는 없다. 현재 명시적 관리자 재요청 또는 이후 탐지 요청을 사용한다. 분석 잠금 기본 TTL 6시간과 broker 재전달의 실제 복구 시간은 후속 실험에서 확인한다.
- Push는 PostgreSQL·Redis·FCM 전체의 정확히 한 번 발송을 보장하지 않는다. Redis 기록 유실, FCM 접수 후 결과 저장 전 종료, 발송 직전 권한 확인 뒤의 변경에는 분산 처리 한계가 있다.
