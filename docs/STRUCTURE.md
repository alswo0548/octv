# 프로젝트 구조

| 경로 | 역할 |
|---|---|
| frontend/web | React·Vite WEB UI |
| frontend/mobile | React Native·Expo MOBILE UI |
| shared/src/fixtures.json | 사건·기관·경로·지원요청·일별 통계 목업 |
| shared/src/index.ts | 화면 목록·목업 조회 도우미 |
| frontend/web/src/components/Background.tsx | 재생 상태·움직임 줄이기 처리 |
| frontend/web/src/styles/refinements.css | 이번 UI 수정 스타일 |
| frontend/mobile/src/components/Background.tsx | 콘텐츠 바깥 영상 배경 |
| backend/app/main.py | FastAPI 객체만 생성, DB 연결 없음 |
| ai/* | 팀 구현 위치 안내 |
| database/schema.sql | 기존 ERD 기반 DDL, 변경 없음 |
| database/erd-transcription.json | 기존 전사 기록 |
| compose.yaml | PostgreSQL 한 서비스·볼륨·최초 SQL 마운트 |
| .env.example / backend/.env.example | 개인 환경변수 준비용, 비밀값 없음 |
| .prettierrc.json / .prettierignore | 소스 형식 정리 기준 |
| .github/workflows/ui.yml | 포맷·타입·범위·빌드 검사, DB 불필요 |
| docs/PENPOT.md / docs/screenshots | 최신 Penpot 사본 링크·브라우저/스토리보드 검증 캡처 |
| docs/CHANGED_FILES.md / docs/VERIFICATION.md | 적용할 파일 목록·이번 검증 범위 |
| docs/references | 기존 스토리보드·ERD·AI 자료 보존 |
| docs/OCTV_페이지흐름도.pptx | 기존 원본 참고 파일, 이번 최신 UI 반영본 아님 |

node_modules·dist·.expo·로그·개인 .env·DB 볼륨·백업 덤프는 ZIP·Git 대상에서 제외합니다. 기존 배경 영상 추적 예외는 유지합니다.
