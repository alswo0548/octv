# OCTV 2차 최종 수정·검증 결과 · 2026-09-28

## 기준과 결과물 구분

- 기준 소스: GitHub `alswo0548/octv`의 `main` 커밋 `9fd2e6f4102e43936aed1fceddd17cccea68fe14` (PR #1·#2 병합 후). 시작 전 158개 파일을 실제 소스와 대조했고 제출 전 main이 동일함을 다시 확인했습니다.
- 직전 소스 `OCTV`를 보존하고 별도 `OCTV_round2`에서 작업했습니다. 원본 ZIP을 재전개해 덮어쓰지 않았습니다.
- 기준 자료: `프론트엔드 UI 수정사항 _2차.pptx` 7개 페이지. 설명·스크린샷·표시 위치·상태 참고 표와 붉은 POST_ALERT 수정까지 확인했습니다.
- `OCTV_round2_interim_2026-09-28.zip`은 화면 검증 전 중간본입니다. 최종본은 `OCTV_round2_final_2026-09-28.zip`이며 최종 화면 수정·Penpot 기록·캡처를 포함합니다.
- React WEB / React Native·Expo MOBILE, 로고·색상·글래스 패널·기존 페이지 흐름을 유지했습니다. 실제 인증·API·DB 연결·감시 제어 기능을 추가하지 않았습니다.

## PPT별 반영표

아래 파일 경로에서 WEB은 `frontend/web/src`, MOBILE은 `frontend/mobile/src`를 뜻합니다. 실제 화면 검증은 빌드 결과를 Chrome의 지정 크기 iframe에서 열어 수행했습니다.

| 기준 | 적용 화면·변경 내용 | 관련 파일 | 실제 검증 |
|---|---|---|---|
| PPT 1 | 공통 사이드바 폭과 헤더·본문·카드 폭 연동. 지정 좌하단 문구만 삭제. 원본 비율의 움직이는 전경 영상과 흐린 보조 영상으로 오른쪽 빈 띠 보완 | WEB `layouts/WebLayout.tsx`, `components/Background.tsx`, `styles/refinements.css` | 1280×800·1440×900·1920×1080과 WEB 390×844 확인. 1920에서 사이드바 336px. 영상 시간 증가·paused=false·전경 contain 확인. 앱 가로 넘침 없음 |
| PPT 2 | WEB·MOBILE 이메일 중복 확인 버튼 복원. 클릭 시 조회하지 않는다는 목업 안내만 표시 | WEB `pages/AuthPage.tsx`, 공통 CSS; MOBILE `screens/AuthScreens.tsx`, `App.tsx` | WEB 1440 및 390, MOBILE 320×740에서 버튼·입력창 표시와 안내 팝업 확인. 실제 조회·성공 판정 없음 |
| PPT 3 | 긴급 사건 목록이 패널 가용 높이를 채움. 내부 스크롤·하단 페이지 이동 유지 | WEB `styles/refinements.css` | 1920에서 목록 약 478px, 내부 scrollHeight 약 487px. 페이지 이동은 하단 30px 영역. 다음 페이지 이동 확인 |
| PPT 4 | 지정 두 곳만 단순 화살표 대신 차분한 도로 SVG 적용 | WEB `components/RoadIcon.tsx`, `pages/IncidentsPage.tsx` | 기관 2 선택 시 추천 11분·3.6km 표시. 경로 비교 진입·선택 기관 유지·후보 3개·B 경로 지도 강조/제외 상태 확인 |
| PPT 5 | 모바일 로그인·설정·등록 정보의 역할을 현장 담당자로 통일. 같은 역할의 WEB 회원가입 문구도 정리 | MOBILE `screens/AuthScreens.tsx`; `shared/src/fixtures.json`; WEB `pages/AuthPage.tsx` | MOBILE 430×932 로그인과 설정 표시 확인. 내부 권한 값·인증 구조 변경 없음 |
| PPT 6 | 현재 연결 상태 / 감시 안내 / 감시상태 분리. BASE·OFF·ALERT·POST_ALERT·VERIFY 5상태. 특보 OFF 제한 팝업. 해제 후 ON 유지 및 수동 OFF | WEB `pages/TargetsPage.tsx`, `pages/SettingsPage.tsx`, 공통 CSS | 1280·1440에서 6개 행·5상태 확인. ALERT OFF 시 요청 문구 팝업 및 닫은 뒤 ON 유지. POST_ALERT는 수동 OFF 후 안내 OFF·토글 OFF 일치. 시간/AI 자동 OFF 없음 |
| PPT 7 | 우선순위·상태·유형·기간·검색 라벨과 입력행을 공통 그리드·높이로 정렬. 전체 글자 줄바꿈 방지 | WEB `pages/IncidentsPage.tsx`, 공통 CSS | 1280에서 모든 필터 Y=199, 높이=36px. 전체/P1/P2/P3 한 줄과 P2 선택 표시 유지 확인. 기존 목업 선택 동작 유지 |
| CCTV 출처 | 공통 Camera의 각 CCTV 좌하단에 기존 위치 / 경찰청(UTIC) 제공. 시간 유지, 중복 방지. WEB 상세·확대·모니터링과 MOBILE 사건 정보·실시간 대표 화면에 적용 | WEB·MOBILE `components/Camera.tsx`; `shared/src/attribution.ts`, `shared/src/index.ts` | WEB 상세/확대는 Camera 2개·출처 2개, 모니터링은 1개·1개. MOBILE 상세 두 탭에서 위치·시간·출처 확인. 좁은 화면 줄바꿈·넘침 확인 |

통합관제는 현재 지도와 사건 카드로 구성되어 별도 CCTV 영상이 없습니다. 이후 공통 Camera를 사용하는 CCTV 영역에도 출처가 함께 표시됩니다. 장식용 전체 배경은 기존 ASSET_SOURCES.md에 명시된 Pexels 교통 영상이므로 UTIC 출처를 붙이지 않았습니다. 지도·로고·일반 이미지도 대상에서 제외했습니다. CCTV 표시는 목업 이미지이며 실제 UTIC 연결을 구현하거나 확인한 것은 아닙니다.

## 특보 UI 상태

| 목업 상태 | 안내 | 토글·동작 |
|---|---|---|
| BASE | ON | 수동 OFF 가능 |
| OFF | OFF | 수동 ON 시 BASE |
| ALERT | ON · 특보 감시 중 | OFF 시 감시 중지 불가 팝업, ON 유지 |
| POST_ALERT | ON · 해제 후 확인 대기 | ON 유지, 관리자 수동 OFF 가능 |
| VERIFY | ON · 집중 검증 중 | 목업 ON, 수동 OFF 가능 |

특보 발령에 해당하는 대표 행을 처음부터 ALERT/ON으로 구성했습니다. 실제 특보 이벤트 수신·지역 판정·자동 제어·DB 저장은 구현하지 않았습니다. 기존 연결 정상/끊김은 별도 CCTV fixture를 그대로 사용합니다.

## 빌드와 실행 검증

| 수행 항목 | 결과 |
|---|---|
| `npm run typecheck` | WEB·MOBILE 통과 |
| `npm run check:scope` | 35개 소스 범위 검사 통과 |
| `npm run build:web` | Vite 8.3.1, 39개 모듈 빌드 통과 |
| `npm run build:mobile:web` | Expo WEB export 통과, 종료 코드 0. export 종료 시 강제 종료 안내 메시지는 있었으나 산출물 생성·실제 화면 확인 완료 |
| 변경 소스 Prettier 검사 | 편집한 소스만 검사, 통과 |
| 화면 검증 | Chrome에서 WEB 1280·1440·1920, 모바일 320·390·430 폭과 MOBILE PC 확장 확인. 앱 document 가로 넘침 false. 주요 클릭·영상 재생·출처 확인 |
| MOBILE 배경 | PC 크기에서도 콘텐츠 최대 폭 460px, 배경 전체 뷰포트, contain 유지. 영상 시간 26.72→27.42→28.12, paused=false 관측 |

Node 24.19 / npm 11.9 환경에서 기존 설치 의존성을 재사용했습니다. 새 `npm ci` 설치 검증은 수행하지 않았습니다. 확인에 사용한 iframe·계측 스크립트는 제출 소스에 포함하지 않았습니다. 관측 기록은 `ROUND2_BROWSER_CHECKS.json`, 핵심 캡처는 `screenshots/round2-*.jpg`입니다. 기록은 선택한 관측 시점이며 모든 이벤트의 자동화 테스트 로그는 아닙니다.

## 로컬 확인 방법 (프로젝트 루트 CMD)

Node 24 / npm 11을 준비한 뒤 실행합니다. ZIP은 기존 폴더와 구분되는 새 폴더에 풀어 확인할 수 있습니다. Git 작업을 계속한다면 별도 PR 브랜치 `fix/octv-ui-round2-0928`을 사용합니다. 기존 미커밋 파일을 강제로 덮어쓰지 마세요.

```cmd
npm ci
npm run build:web
npm run build:mobile:web
npm run preview:web
```

WEB: http://localhost:4173

새 CMD에서 같은 프로젝트 폴더로 이동한 다음:

```cmd
npm run preview:mobile:web
```

MOBILE: http://localhost:8081. 종료는 각 실행 창에서 Ctrl+C입니다. 개발 서버는 `npm run dev:web`, `npm run dev:mobile:web`, Expo 개발 시작은 `npm run dev:mobile`입니다. UI에는 DB·API 키가 필요 없습니다. 실제 계정 없이 목업 로그인 버튼으로 화면을 이동합니다.

이번 최종본을 공개 호스팅하지 않았습니다. 기존 README의 이전 배포 링크는 이번 2차 최신 결과가 아닙니다.

## Docker·실행 설정 보존

Docker Compose, DDL, 환경변수 예시, 기존 CMD 스크립트, package/lockfile, 협업 설정은 기준 main과 동일하게 보존했습니다. 감시 상태를 위한 DB 컬럼을 추가하지 않았습니다. 전체 Windows 안내는 `DATABASE.md`를 유지합니다.

```cmd
if not exist .env copy .env.example .env
notepad .env
docker compose config --quiet
docker compose up -d db
docker compose ps
docker compose logs --tail 100 db
docker compose exec db psql -U octv_dev -d octv_dev
```

psql에서 `\dt`로 테이블을 확인하고 `\q`로 나옵니다. 종료는 `docker compose stop db`, 재실행은 `docker compose start db`입니다. 기존 볼륨은 유지하며 빈 볼륨 최초 실행에만 DDL을 적용하는 기존 설정입니다.

## Penpot 수정 사본

기존 수정용 페이지 두 개를 재사용했습니다. 원본 `01 · WEB`, `02 · MOBILE`과 공유 스타일·공통 요소는 수정하지 않았고 중복 페이지를 만들지 않았습니다.

- [01 · WEB · 최종수정본 0928](https://design.penpot.app/#/workspace?team-id=d8ac01df-6646-81d2-8008-ac44f628bb56&file-id=d8ac01df-6646-81d2-8008-ac4abdee3ed7&page-id=51c1e37d-020a-80ac-8008-b4cdadf8b0be&board-id=51c1e37d-020a-80ac-8008-b4d742adac10)

- [02 · MOBILE · 최종수정본 0928](https://design.penpot.app/#/workspace?team-id=d8ac01df-6646-81d2-8008-ac44f628bb56&file-id=d8ac01df-6646-81d2-8008-ac4abdee3ed7&page-id=51c1e37d-020a-80ac-8008-b4d39671b27f&board-id=51c1e37d-020a-80ac-8008-b4d53408b7b1)

- WEB: `19 · W06-1 대상 CCTV 설정`에 감시 안내 5상태·토글·제한 팝업 대표 상태와 Description 반영. `18 · W06 시스템 설정`의 과거 자동 복귀 안내 수정. `14 · W03 사건관리`에 두 도로 아이콘·출처와 필터 정렬 설명, `16 · W04 CCTV 모니터링`에 출처, `12 · W01-2 회원가입`의 가짜 이메일 성공 문구 제거, `13 · W02 통합관제`의 공통 폭·목록·배경 설명 갱신.
- MOBILE: `01_A01_login`, `11_A07_settings`, `04_A01-3_signup_complete` 역할 명칭 정리. `02_A01-1_signup_basic_info`의 실제 중복 조회를 암시하는 성공/오류 문구 제거. `07_A04_incident_detail_info`, `08_A04-1_incident_detail_live_video`의 CCTV 좌하단 출처와 Description 반영.
- 새로고침 후 WEB CCTV 설정과 MOBILE 실시간 영상의 저장된 화면을 캡처했습니다. 로그인·설정·회원가입·사건관리 등 변경 보드 텍스트도 저장 후 다시 대조했습니다.
- Penpot은 편집 가능한 네이티브 텍스트·도형의 대표 상태입니다. W06-1 팝업은 같은 보드 안의 대표 상태로 표현했으며 별도 프로토타입 팝업 전환을 추가하지 않았습니다. 반응형·재생·토글 인터랙션은 실제 React UI에서 검증했습니다.

## 미완료·미검증 구분

- 요청한 소스 UI 수정과 기존 Penpot 사본의 관련 내용 갱신은 완료했습니다.
- Android/iOS 실기기·Safari·다른 브라우저, Windows CMD 자체 실행, 실제 OS 창 최대화는 미검증입니다. 1920×1080은 브라우저 안에서 설정한 뷰포트 검증입니다.
- Docker 컨테이너 최초 기동·DDL 적용·재시작 보존은 이번 환경에서 실행하지 않았습니다. 설정 보존과 실행 검증을 구분합니다.
- Penpot 전체 프로토타입을 처음부터 끝까지 클릭하는 검사는 수행하지 않았습니다.
- 실제 이메일 조회·계정 생성·특보 API·AI 감시 제어·DB 연결·기관 전달은 요청 범위 밖이며 구현하지 않았습니다.
- GitHub PR은 검토·병합 전 상태로 제출합니다. PR 생성 자체가 main이나 사용자 PC 파일을 자동으로 바꾸지는 않습니다.

## 캡처 목록

| 캡처 | 확인 내용 |
|---|---|
| `screenshots/round2-web-overview.jpg` | 공통 폭·영상·통합관제 목록 |
| `screenshots/round2-web-signup.jpg`, `round2-mobile-signup.jpg` | 이메일 중복 확인 버튼 |
| `screenshots/round2-web-filters.jpg` | 필터 기준선·한 줄 우선순위 |
| `screenshots/round2-web-road-icons.jpg` | 지정 두 도로 아이콘·기관 선택 |
| `screenshots/round2-web-targets.jpg`, `round2-web-alert-popup.jpg` | 5상태와 특보 OFF 제한 |
| `screenshots/round2-web-cctv.jpg`, `round2-mobile-cctv.jpg` | 각 CCTV 출처·기존 정보 유지 |
| `screenshots/round2-mobile-login.jpg` | 현장 담당자 명칭 |
| `screenshots/round2-penpot-targets.jpg`, `round2-penpot-mobile.jpg` | 저장된 수정용 스토리보드 |

이전 `VERIFICATION.md`, `CHANGED_FILES.md`, 캡처는 이전 작업의 기록입니다. 이번 2차 상태는 이 문서와 `ROUND2_CHANGED_FILES.md`를 기준으로 합니다.
