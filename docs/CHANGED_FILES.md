# 변경 파일 목록

기준: 첨부 OCTV.zip의 원본 체크아웃. 삭제한 파일은 없습니다. UI 요소 삭제는 아래 소스 파일 내부 변경입니다. 이번 회차에서 원격 main이 원본 ZIP의 기준 커밋과 같음을 확인했습니다. 이후 변경이 있다면 GITHUB.md 절차로 파일별 병합합니다.

포맷 전용 파일은 UI 수정 전 별도로 보관한 Prettier 결과와 바이트 비교해 분류했습니다. CSS의 선택자·속성 순서와 import 순서를 바꾸지 않았습니다. 정상 형식의 TSX는 요청한 UI 변경에 필요한 부분만 수정했습니다. shared JSON은 표시용 필드 추가와 Prettier 배열 정리가 함께 있습니다.

| 구분 | 파일 | 변경 성격 |
|---|---|---|
| 수정 | `.env.example` | DB 개발환경·제외 설정 |
| 수정 | `.github/workflows/ui.yml` | 포맷 도구·검사 설정 |
| 수정 | `.gitignore` | DB 개발환경·제외 설정 |
| 추가 | `.prettierignore` | 포맷 도구·검사 설정 |
| 추가 | `.prettierrc.json` | 포맷 도구·검사 설정 |
| 수정 | `PROJECT_CONTEXT.md` | 문서 |
| 수정 | `README.md` | 문서 |
| 수정 | `backend/.env.example` | DB 개발환경·제외 설정 |
| 추가 | `compose.yaml` | DB 개발환경·제외 설정 |
| 추가 | `docs/CHANGED_FILES.md` | 문서 |
| 수정 | `docs/DATABASE.md` | 문서 |
| 수정 | `docs/GITHUB.md` | 문서 |
| 추가 | `docs/PENPOT.md` | 문서 |
| 수정 | `docs/SCREENS.md` | 문서 |
| 수정 | `docs/STRUCTURE.md` | 문서 |
| 수정 | `docs/TODO.md` | 문서 |
| 수정 | `docs/UI_RUN.md` | 문서 |
| 수정 | `docs/VERIFICATION.md` | 문서 |
| 추가 | `docs/screenshots/browser-checks.json` | 검증 증빙 |
| 추가 | `docs/screenshots/mobile-blocked-390.jpg` | 검증 증빙 |
| 추가 | `docs/screenshots/mobile-pc-1920.jpg` | 검증 증빙 |
| 추가 | `docs/screenshots/penpot-agency.jpg` | 검증 증빙 |
| 추가 | `docs/screenshots/penpot-mobile.jpg` | 검증 증빙 |
| 추가 | `docs/screenshots/penpot-support.jpg` | 검증 증빙 |
| 추가 | `docs/screenshots/penpot-web.jpg` | 검증 증빙 |
| 추가 | `docs/screenshots/web-agency-1440.jpg` | 검증 증빙 |
| 추가 | `docs/screenshots/web-stats-1280.jpg` | 검증 증빙 |
| 추가 | `docs/screenshots/web-stats-1440.jpg` | 검증 증빙 |
| 추가 | `docs/screenshots/web-support-1440.jpg` | 검증 증빙 |
| 수정 | `frontend/mobile/App.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/components/Background.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/components/Camera.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/components/RoadMap.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/components/UI.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/screens/AuthScreens.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/screens/DetailScreen.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/screens/IncidentScreens.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/screens/NotificationScreen.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/screens/RequestScreen.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/screens/RoutesScreen.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/src/screens/SettingsScreen.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/mobile/tsconfig.json` | 포맷 전용 |
| 수정 | `frontend/web/index.html` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/App.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/components/AgencyPicker.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 추가 | `frontend/web/src/components/Background.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/components/Camera.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/components/Primitives.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/components/RoadMap.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/layouts/WebLayout.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/main.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/pages/AuthPage.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/pages/IncidentsPage.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/pages/MonitorPage.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/pages/OverviewPage.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/pages/RoutesPage.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/pages/SettingsPage.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/pages/StatsPage.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/pages/TargetsPage.tsx` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/styles/agency-flow.css` | 포맷 전용 |
| 수정 | `frontend/web/src/styles/development.css` | 포맷 전용 |
| 추가 | `frontend/web/src/styles/refinements.css` | UI·배경 수정 (일부 포맷 포함) |
| 수정 | `frontend/web/src/styles/style.css` | 포맷 전용 |
| 수정 | `frontend/web/src/styles/ui.css` | 포맷 전용 |
| 수정 | `frontend/web/tsconfig.json` | 포맷 전용 |
| 수정 | `frontend/web/vite.config.ts` | 포맷 전용 |
| 수정 | `package-lock.json` | 포맷 도구·검사 설정 |
| 수정 | `package.json` | 포맷 도구·검사 설정 |
| 수정 | `shared/src/fixtures.json` | 표시용 데이터·조회 도우미·용어 (포맷 포함) |
| 수정 | `shared/src/index.ts` | 표시용 데이터·조회 도우미·용어 (포맷 포함) |

미변경: `database/schema.sql`, 기존 로고·영상·도로 이미지, `.editorconfig`, `.gitattributes`, PR 템플릿, 기존 참고 PPT/PDF/ERD. 개인 `.env`와 원본 ZIP은 수정하지 않았습니다.

## 인수인계 회차의 추가 변경
- 시스템 설정의 잔여 시연 문구 1곳 정리
- package.json: `preview:web` 명령 추가
- README, PROJECT_CONTEXT, GITHUB, TODO, UI_RUN: 원격 접근·배포 상태·실행 방법 최신화
- HANDOVER_RECHECK.md 및 VERIFICATION.md: 이번 재검증과 이전 기록 구분
- VERIFICATION_PREVIOUS.md: 이전 저장본 검증 기록 보존
- screenshots/recheck-browser.json, recheck-penpot-web.jpg, recheck-penpot-mobile.jpg 추가
