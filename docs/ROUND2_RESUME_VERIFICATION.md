# OCTV 2차 수정 재개 결과 · 2026-09-28

## 복구 결과

중단 후에도 GitHub PR #3에 2차 수정 소스와 검증 기록이 저장되어 있었습니다. 이번에는 이 저장본을 복구하고, 전체 파일을 대조한 뒤 빌드를 다시 수행했습니다. 정상 반영된 UI는 다시 작성하지 않았습니다.

- 기준: `fix/octv-ui-round2-0928` / `835b7b0511d87de64fb51f7711fceb168d288910`.
- 원격 176개 파일을 Git blob SHA로 대조해 모두 일치함을 확인했습니다.
- 중간 ZIP보다 최신인 `SettingsPage.tsx`, `refinements.css`와 추가 문서·캡처를 복구했습니다. 중간 ZIP 대비 추가/변경은 총 22개 파일입니다.
- 이전 로컬 폴더의 main·미커밋 변경사항, 원본 ZIP과 중간 ZIP은 보존했습니다. 복구 시작 상태도 별도 ZIP과 로컬 Git 기준 커밋으로 보존했습니다.
- Docker Compose·DDL·환경변수 예시·의존성·로고·영상·기관/경로 목업 코드는 기준 PR과 동일합니다.

## PPT별 반영표

**소스 반영은 모두 확인했습니다. 아래 이전 화면 검증은 PR에 저장된 당시 기록과 캡처를 뜻하며, 이번 세션에서 클릭 검사를 재수행했다는 의미가 아닙니다.** WEB 경로는 `frontend/web/src`, MOBILE 경로는 `frontend/mobile/src` 기준입니다.

| 기준 | 적용 화면 | 변경 내용 | 관련 파일 | 검증 여부 |
|---|---|---|---|---|
| PPT 1 | WEB 공통 | 사이드바·본문 폭 연동, 배경 영상 비율 유지와 보조 영상 채움, 좌하단 지정 문구 삭제 | WEB `layouts/WebLayout.tsx`, `components/Background.tsx`, `styles/refinements.css` | 이번 소스·빌드 확인. 이전 1280/1440/1920 화면·영상 재생 기록 있음 |
| PPT 2 | WEB·MOBILE 회원가입 | 이메일 중복 확인 버튼 복원, 실제 조회하지 않는다는 안내만 표시 | WEB `pages/AuthPage.tsx`; MOBILE `screens/AuthScreens.tsx`, `../App.tsx` | 이번 소스·빌드 확인. 이전 버튼·팝업 캡처 있음. 모바일 Penpot 안내도 재확인 |
| PPT 3 | WEB 통합관제 | 긴급 사건 목록의 높이 확장, 내부 스크롤·하단 페이지 이동 유지 | WEB `styles/refinements.css` | 이번 소스 확인. 이전 1920 화면의 목록 478px·페이지 이동 위치 기록과 캡처 대조 |
| PPT 4 | WEB 사건관리 | 요청한 두 화살표를 도로 SVG로 교체 | WEB `components/RoadIcon.tsx`, `pages/IncidentsPage.tsx` | 이번 소스 확인. 이전 기관 변경·경로 비교·선택 유지 기록 있음 |
| PPT 5 | MOBILE 로그인·설정 | 현장 담당자로 표시 명칭 통일 | MOBILE `screens/AuthScreens.tsx`, `screens/SettingsScreen.tsx`; `shared/src/fixtures.json` | 이번 소스 확인, Penpot 로그인·설정의 저장 문구 직접 재확인 |
| PPT 6 | WEB 대상 CCTV 설정 | 현재 상태/감시 안내/감시상태 분리, 5상태, ALERT OFF 제한 팝업, POST_ALERT 수동 OFF | WEB `pages/TargetsPage.tsx`, `pages/SettingsPage.tsx`, `styles/refinements.css` | 이번 소스 확인, Penpot 5상태·팝업·Description 직접 재확인. 이전 실제 토글 검사 기록 있음 |
| PPT 7 | WEB 사건관리 필터 | 우선순위 포함 공통 입력 높이·라벨 간격·반응형 정렬 | WEB `pages/IncidentsPage.tsx`, `styles/refinements.css` | 이번 소스 확인. 이전 1280 화면에서 모든 입력 Y=199·높이 36px 기록과 캡처 대조 |
| CCTV 출처 | WEB 상세·확대·모니터링, MOBILE 사건 정보·실시간 영상 | 기존 위치 / 경찰청(UTIC) 제공, 시간 유지, 중복 방지 | WEB·MOBILE `components/Camera.tsx`; `shared/src/attribution.ts`, `shared/src/index.ts` | 이번 전체 이미지·영상 사용처 검색. 이전 Camera/출처 개수 대조 기록 있음. 모바일 Penpot 직접 재확인 |

통합관제에는 현재 지도와 목록만 있고 CCTV 영상 카드는 없습니다. 개별 CCTV 렌더링은 위 Camera 두 컴포넌트로 모입니다. 로고·지도·Pexels 장식 배경은 CCTV가 아니므로 UTIC 문구를 붙이지 않았습니다. 해당 출처 문구는 요청된 UI 표기이며 실제 UTIC 영상 연결은 구현하지 않았습니다.

## 특보 정책 확인

| 모드 | 표시 | 목업 동작 |
|---|---|---|
| BASE | ON | 수동 OFF 가능 |
| OFF | OFF | 수동 ON 가능 |
| ALERT | ON · 특보 감시 중 | OFF 시 감시 중지 불가 팝업, 상태 변경 없이 ON 유지 |
| POST_ALERT | ON · 해제 후 확인 대기 | 자동 OFF 없음, 관리자 수동 OFF 가능 |
| VERIFY | ON · 집중 검증 중 | ON 대표 상태 |

특보 발령/해제는 각 상태의 대표 행으로 표현되어 있습니다. 실제 특보 이벤트 수신·CCTV 제어·시간 경과·AI 판단·DB 저장은 없습니다. ALERT 토글은 클릭 가능한 상태이며, 변경 함수는 안내 팝업을 열고 ON을 유지합니다.

## 이번에 실제 수행한 검사

| 검사 | 결과 |
|---|---|
| PPT 7장 | 전체 렌더 이미지, 표시 위치·참고 표·붉은 POST_ALERT 확인. 설명 텍스트는 원본 XML과 병행 대조 |
| 원격 복구 | 176개 파일의 Git blob SHA 일치 |
| `npm run typecheck` | WEB·MOBILE 통과 |
| `npm run check:scope` | 35개 소스 통과. API·인증·업무 저장 추가 없음 수동 검토 병행 |
| `npm run format:check` | 전체 대상 소스 통과 |
| `npm run build:web` | Vite 8.3.1, 39개 모듈, 종료 코드 0 |
| `npm run build:mobile:web` | Expo WEB export, 333개 모듈, 종료 코드 0. export 뒤 강제 종료 안내는 있었으나 파일 생성 완료 |
| `git diff --check` | 통과 |
| Penpot | WEB W06-1 화면·팝업·Description, MOBILE 실시간 영상·출처·로그인·설정·회원가입 안내 직접 재확인. 사본만 조회했고 수정 없음 |

기존 설치 의존성을 복사해 사용했습니다. 새 `npm ci` 설치 검사는 하지 않았습니다. 이전 작업의 검사 결과는 `ROUND2_VERIFICATION.md`, `ROUND2_BROWSER_CHECKS.json`에 보존되어 있습니다.

## 이번에 완료하지 못한 검증

- **현재 세션의 웹·모바일 실행 화면 재검증:** 서버 프로세스는 시작했지만 브라우저의 로컬 서버 접근이 보안 정책으로 차단되었습니다. 별도 로컬 HTTP 확인도 연결에 실패했습니다. 이번 세션의 영상 재생·클릭·뷰포트 검사를 통과로 기록하지 않습니다.
- 이전 동일 소스에서는 WEB 1280/1440/1920, MOBILE 320/390/430 뷰포트와 주요 목업 클릭을 확인한 기록이 있습니다. 저장된 캡처·측정값을 이번에 읽고 대조했으나 새 실행의 증거로 재사용하지 않습니다.
- OS 창의 실제 최대화, Windows CMD 자체, Android/iOS 실기기, Docker 기동·DDL 적용·데이터 유지, Penpot 전체 프로토타입 순회는 미검증입니다.
- 외부 사이트 재배포는 하지 않았습니다. README의 이전 배포 링크는 이번 최신 패키지와 다를 수 있습니다.

## 캡처와 변경 파일

이번 재개에서 생성한 캡처(최종 ZIP 전용):
- `docs/screenshots/resume-penpot-targets.jpg` — 최종 ZIP에 포함
- `docs/screenshots/resume-penpot-mobile.jpg` — 최종 ZIP에 포함

이전 동일 소스의 실제 UI 캡처:
- [통합관제](screenshots/round2-web-overview.jpg), [필터](screenshots/round2-web-filters.jpg), [도로 아이콘](screenshots/round2-web-road-icons.jpg)
- [WEB 회원가입](screenshots/round2-web-signup.jpg), [MOBILE 회원가입](screenshots/round2-mobile-signup.jpg), [MOBILE 로그인](screenshots/round2-mobile-login.jpg)
- [감시 상태](screenshots/round2-web-targets.jpg), [OFF 제한 팝업](screenshots/round2-web-alert-popup.jpg)
- [WEB CCTV](screenshots/round2-web-cctv.jpg), [MOBILE CCTV](screenshots/round2-mobile-cctv.jpg)

2차 UI의 전체 변경 파일은 [ROUND2_CHANGED_FILES.md](ROUND2_CHANGED_FILES.md)에 있습니다. 이번 재개에서는 UI 소스를 변경하지 않았으며 다음만 갱신/추가했습니다.

- `README.md`, `docs/GITHUB.md`, `docs/PENPOT.md`: 최신 PR과 재개 검증 구분 안내.
- `docs/ROUND2_RESUME_STATUS.md`, `docs/ROUND2_RESUME_VERIFICATION.md`: 복구 현황·이번 검증 결과.
- `docs/screenshots/resume-penpot-targets.jpg`, `docs/screenshots/resume-penpot-mobile.jpg`: 이번 확인 캡처.

신규 Penpot 캡처 2장의 GitHub 업로드는 자동 승인 검토가 해당 저장소로의 이미지 전송 승인이 명확하지 않다는 이유로 거절했습니다. 이미지는 ZIP에만 포함하고 GitHub에는 재개 문서만 반영합니다. 기존 PR의 이전 캡처는 보존합니다.

## 작업 위치와 실행

- [GitHub PR #3](https://github.com/alswo0548/octv/pull/3), 브랜치 `fix/octv-ui-round2-0928`. main은 변경하지 않고 PR 검토·병합을 남깁니다.
- [Penpot WEB 사본](https://design.penpot.app/#/workspace?team-id=d8ac01df-6646-81d2-8008-ac44f628bb56&file-id=d8ac01df-6646-81d2-8008-ac4abdee3ed7&page-id=51c1e37d-020a-80ac-8008-b4cdadf8b0be&board-id=51c1e37d-020a-80ac-8008-b4d742adac10)
- [Penpot MOBILE 사본](https://design.penpot.app/#/workspace?team-id=d8ac01df-6646-81d2-8008-ac44f628bb56&file-id=d8ac01df-6646-81d2-8008-ac4abdee3ed7&page-id=51c1e37d-020a-80ac-8008-b4d39671b27f&board-id=51c1e37d-020a-80ac-8008-b4d53408b7b1)

ZIP을 새 폴더에 풀고 프로젝트 루트에서 `npm ci` 후 `npm run dev:web`을 실행합니다. 새 터미널에서 `npm run dev:mobile:web`을 실행합니다. 기본 주소는 WEB `http://localhost:4173`, MOBILE `http://localhost:8081`입니다. DB나 API 키는 필요 없습니다. 기존 작업 폴더를 통째로 덮어쓰지 않습니다.

최종 ZIP에는 소스·자산·설정·환경변수 예시·DDL·문서·캡처를 포함하고 `.git`, `node_modules`, 개인 `.env`, 빌드·캐시·로그·DB 데이터는 제외합니다.
