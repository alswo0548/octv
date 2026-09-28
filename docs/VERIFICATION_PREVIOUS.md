# 이전 작업의 검증 기록 — 인수인계 전 저장본

첨부 PPT 14쪽의 문구·캡처·화살표를 렌더 이미지와 함께 대조했습니다. 기준은 첨부 OCTV.zip입니다. 이전 패키지의 검사 결과를 이번 실행 결과로 재사용하지 않았습니다.

## PPT별 반영
| 쪽 | 결과 / 주요 소스 | Penpot 사본 |
|---|---|---|
| 1 | 완료 — WEB refinements.css·WebLayout·AuthPage, MOBILE UI·AuthScreens; 아래 화살표 우측 정렬, 시연 요소·사이드바 숫자 제거 | WEB/MOBILE 공통 요소 |
| 2 | 완료 — RoutesScreen·UI.Button, 카드 높이 88px(390px 폭), 제외 카드 조회 가능·네비 disabled | A05, A05-S2 |
| 3 | 완료 — SettingsScreen 개인정보 항목 제거 | A07 |
| 4 | 완료 — AuthScreens 일반 안내 문장 + 로그인 텍스트 링크 | A01-1 |
| 5 | 완료 — RoadMap·refinements.css, 기존 우선순위 색·핀·물결·호버/포커스 강조 | W02 대표 상태·Description |
| 6 | 완료 — OverviewPage·fixtures, 5/5/2건 목록·동일 ID 마커 동기화 | W02 |
| 7 | 완료 — IncidentsPage·Pagination, 두 안내 문구 제거·총건수/페이지 유지 | W03 |
| 8 | 완료 — Camera·IncidentsPage, 캡션 제거·영상 아래 우측 CCTV 버튼 | W03 |
| 9 | 완료 — shared 및 WEB/MOBILE 관련 화면에 추가 지원요청 통일 | 관련 보드·Description |
| 10 | 완료 — 사건별 최신순 fixtures·IncidentsPage, 최신 본문과 목록 첫 요청 동일 | W03, W03-P1 |
| 11 | 완료 — 기관 탭·recommendedRouteFor, 기관별 추천 1개·좌상단 경로 비교 | W03 |
| 12 | 완료 — AgencyPicker·RoutesPage, 3경로 유지·복수 체크·미선택 disabled·조회 분리 | W03-1, P1/P2 |
| 13 | 완료 — MonitorPage·refinements.css, 유연한 높이·내부 스크롤·패널 하단 일치 | W04 |
| 14 | 완료 — StatsPage·fixtures.dailyConfirmed, 날짜/건수 점·선 차트 | W05 |

WEB 소스는 `frontend/web/src`, MOBILE은 `frontend/mobile/src`, 데이터는 `shared/src` 아래입니다. 화면별 정확한 경로는 SCREENS.md, 전체 파일 목록은 CHANGED_FILES.md를 봅니다.

## 실제 실행 검사
| 검사 | 결과 |
|---|---|
| npm ci | 통과. 기존 의존성 유지, 포맷터 Prettier 3.6.2만 추가 |
| npm run format:check | 통과. 편집 소스·설정만 대상, 생성물 제외 |
| npm run typecheck | WEB·MOBILE 통과 |
| npm run check:scope | 33개 소스 통과. 네트워크·영속 저장·인증 등 수동 검토 병행 |
| npm run build:web | Vite 빌드 통과 |
| npm run build:mobile:web | Expo 웹 내보내기 통과. 종료 단계의 Expo 강제 종료 안내는 있었으나 exit 0과 번들 생성 확인 |
| git diff --check | 통과 |
| UI 독립 실행 | API·DB·계정 키 없이 WEB/Expo 웹 빌드 화면 실행 |
| GitHub CI | 포맷 검사 추가, 기존 타입·범위·양쪽 빌드 유지. 원격 CI 실행은 미검증 |

검증 환경은 Linux·Chrome·Node 24.19.0/npm 11.9.0입니다. Windows CMD, Android/iOS 실기기·시뮬레이터 검증과 구분합니다.

## 브라우저 확인
- WEB 1920×1080, 1440×900, 1280×800. 영상 `currentTime` 19.96→20.99→22.00초 증가, paused=false, contain, opacity 0.82. 문서 가로 넘침 없음.
- MOBILE 웹 390×844, 430×932와 위 PC 3종. 영상 박스가 각 뷰포트 전체 크기로 변하고 콘텐츠만 최대 460px 유지. currentTime 20.11→23.29초 증가, muted·loop·playsinline 확인.
- 새로고침 후 재생과 화면 이동 중 재생 유지 확인. 모바일 재로드 직후 0.07초→14.39초, paused=false.
- 통합관제 1/2/3페이지의 카드 ID와 마커 ID를 각각 비교: 5/5/2개 모두 일치. 키보드 포커스 강조 시 나머지 4개 물결 paused 확인. 마우스 호버는 같은 상태 경로를 사용하는 소스 검토로 확인.
- 사건관리 기관 조회를 강남구청 도로관리과로 바꾸면 11분/3.6km로 갱신, 경로평가로 이동해 조회 기관 유지. 전달 대상 0개 disabled, 2개 체크 후 enabled. 전달 UI 확인 후에도 조회 기관 유지.
- 지원요청 본문과 팝업 첫 항목 동일. 14:38→14:21 최신순 2개 목록·닫기 확인.
- 모바일 B 제외 경로도 선택됨. 네비 버튼 aria-disabled=true, tabindex=-1, 회색. C 선택 시 재활성, 선택 경로 확인 팝업만 표시.
- 설정 개인정보 항목 제거, 가입 문장은 일반 텍스트이고 로그인만 버튼 역할의 텍스트 링크임을 DOM으로 확인.
- 모니터링 패널 높이는 각 PC 크기에서 752/572/472px, 좌우 하단 일치. 내부 목록 overflow:auto, 662/482/382px로 변화.
- 통계 차트의 7개 날짜·점·선·건 단위 확인. 기존 다른 통계 스냅샷 수치는 보존했으며 각 화면 수치는 실시간 합산이 아니다.

원시 확인값: screenshots/browser-checks.json. 캡처: screenshots/ 아래. 크기별 검사는 실제 크기의 iframe 뷰포트를 브라우저 창에 축소해 보여주는 검사 화면에서 수행했습니다. 실제 기기 검증은 아닙니다.

모바일도 statusChange와 playingChange를 함께 구독하여 로드만 되고 재생되지 않는 동안 기존 이미지가 남도록 처리했습니다. 최종 재빌드에서 playing 이벤트 후 opacity 0.82·paused=false를 다시 확인했습니다.

재생 실패·자동재생 차단·OS 움직임 줄이기 분기는 코드로 검토했습니다. 해당 OS/실기기 조건을 강제로 재현한 검사는 미검증입니다. 네이티브 빌드는 이번 회차에 다시 실행하지 않았습니다.

## Docker·DDL·보존
| 항목 | 결과 |
|---|---|
| compose.yaml | 정적 YAML 파싱 및 PostgreSQL 1서비스·localhost 포트·named volume·healthcheck·read-only DDL 마운트 확인 |
| 이미지/경로 | 공식 PostgreSQL 17.11-bookworm, 17계열 데이터 경로를 공식 문서에서 확인 |
| 환경변수 | 루트 DB/USER/PORT와 향후 로컬 FastAPI URL 예시 일치. 개인 .env 미수정 |
| database/schema.sql | 원본 ZIP과 바이트 동일. SHA256 `2803c4c692e012f10ab4ce2192b213e7571426ac7261b3d73da1c4b56817e43b` |
| 컨테이너·DDL 실행·재시작 유지 | 미검증 — Docker 실행 도구 없음. healthcheck/테이블 생성 성공으로 보고하지 않음 |
| 원본 자료 | 원본 ZIP, SQL, 참고 PPT/PDF/이미지, 로고·영상 자산 보존 |
| 반환 ZIP | .git·개인 .env·의존성·빌드·캐시·로그·DB데이터/덤프 제외, .env.example·DDL·소스·영상 포함 |

## Penpot·GitHub·공개 범위
- Penpot 사본 실제 편집 완료. 페이지·팝업·레이어·연결·캡처는 PENPOT.md. 정적 대표 상태와 실제 UI 상호작용의 검증 범위를 구분했습니다.
- GitHub 문서·검사 설정 완료. origin `https://github.com/alswo0548/octv.git`, 기준 main은 첨부 .git에서 확인했습니다.
- 원격 반영은 미실행: 인증 오류로 최신 팀원 변경/쓰기 권한을 확인하지 못했습니다. GitHub branch/commit/PR 생성·push·병합 없음. 적용 절차는 GITHUB.md.
- 별도의 본인 전용 WEB/MOBILE 확인 사이트를 배포했습니다. README의 링크 참고. 기존 샘플 사이트는 변경하지 않았습니다.
- 실제 인증·계정 생성·검증·DB 연결·AI/경로 계산·기관 전달·외부 네비·알림·업무 저장은 의도적으로 미구현입니다.
