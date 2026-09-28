# 2차 추가 보완 현황 · 2026-09-28

- 기준: 복구 브랜치 `recovery/round2-835b7b0`의 `95c6bc3`. 원격 UI 기준 `835b7b0`, PR #3. 미커밋 변경 없음 확인 후 `fix/background-monitor-0928` 분기. 기존 커밋과 baseline ZIP 보존.
- 원격 대조: PR #3은 main에 병합됨. 현재 main `c9ef63551a29947fe9006501465c84ce2b34a105`의 변경 대상 2개 소스가 복구 기준과 동일함을 Git blob SHA로 확인. 추가 수정은 이 main을 기반으로 별도 브랜치·PR에 반영.
- 완료: WEB 배경 두 영상의 절대 위치 중첩 복구. 기존 원본 영상·contain 비율·블러 채움 유지. 어두운 막 완화, WEB/MOBILE 대체 배경 흐림 완화. MOBILE 영상 불투명도 보완.
- 완료: W04 고정 행 높이와 상세 카드 내부 스크롤 제거. 영상·상태·버튼을 페이지 흐름으로 펼침. 왼쪽 CCTV 목록 스크롤 유지.
- 근거: 2차 PPT 3의 내부 스크롤 조정 대상은 통합관제 긴급 사건 목록. W04 상세 카드 내부 스크롤은 사용자 지시가 아니며 이번 추가 요청으로 해제.
- 변경 파일: `frontend/web/src/styles/refinements.css`, `frontend/mobile/src/components/Background.tsx`, 이 문서.
- 검증 완료: `npm run typecheck`, `npm run format:check`, `npm run check:scope`, `npm run build:web`, `npm run build:mobile:web`, `git diff --check` 통과. WEB 39개 모듈, MOBILE WEB 324개 모듈 번들 및 기존 3개 자산 export 완료.
- 실행 로그: npm의 기존 http-proxy 설정 경고, Expo의 색상 환경변수 경고와 export 완료 후 강제 종료 메시지가 있었으며 명령 종료 코드는 0. 네이티브 앱 실행·빌드는 수행하지 않음.
- 미완료/미검증: 새 브라우저 화면에서 배경 재생·가시성, W04 긴 페이지·작은 창·최대화 확인. 이전 작업에서 로컬 미리보기 접근 정책이 차단되어 있었음.
- 다음: 사용자 실행 환경에서 WEB 로그인 배경(일반 창·최대화), MOBILE 배경, W04 상세 카드 하단 상태·버튼까지 페이지 스크롤로 표시되는지 확인. 실제 화면 검증 전까지 PR은 초안으로 유지.
- 확인 방법: `npm run dev:web` → 로그인·CCTV 모니터링, `npm run dev:mobile:web` → 로그인·홈. W04 오른쪽 카드 자체에는 스크롤바가 없어야 하며 왼쪽 목록만 내부 스크롤이 가능해야 함. 영상 로딩 실패·동작 줄이기에서는 선명도를 유지한 대체 배경이 표시되어야 함.
