# 최종 레이아웃 보완 · 2026-09-28

- 기준: PR #4 병합 후 main `e8a5151225d776d1adc45595beb02d630b976366`. 로컬 기존 커밋 `5a42821` 및 작업 브랜치 보존. 미커밋 변경 없음 확인 후 `fix/viewport-fill-cctv-height-0928` 분기.
- 완료: WEB/MOBILE 장식용 배경 영상의 contain을 cover로 변경. 창 비율에 따라 원본 비율을 유지하며 중앙 기준 가장자리만 크롭해 전체 영역을 채움. WEB의 별도 흐린 채움 영상 제거. 배경 영상 파일·오버레이·명암 설정은 유지.
- 완료: W04 왼쪽 CCTV 목록 카드를 오른쪽 상세 카드 하단까지 stretch. 목록의 별도 최대 높이 제한을 해제하고 목록 내용만 스크롤. 오른쪽 상세는 내용 높이대로 펼치며 내부 스크롤 없음. 760px 이하 한 열 배치에서는 기존 목록 높이 유지.
- 변경 파일: `frontend/web/src/components/Background.tsx`, `frontend/web/src/styles/refinements.css`, `frontend/mobile/src/components/Background.tsx`, 이 문서.
- 검증 완료: `npm run typecheck`, `npm run format:check`, `npm run check:scope`, `npm run build:web`, `npm run build:mobile:web`, `git diff --check` 통과. WEB 39개, MOBILE WEB 333개 모듈 빌드 완료. 기존 npm http-proxy·색상 환경변수 경고 외 빌드 오류 없음.
- 보존 검증: 현재 main의 179개 파일 Git blob SHA를 로컬 수정 전 커밋과 비교해 전부 동일함을 확인. 변경 대상 3개 소스와 신규 현황 문서만 별도 PR에 포함.
- 미검증: 로컬 미리보기 접근 제한으로 실제 브라우저 화면·창 크기 변경·영상 재생 재검증 미완료. 첨부 image(6), image(7)의 표시 위치와 소스를 대조해 수정.
- 다음 확인: 일반 창·최대화·세로 창에서 배경 상하/좌우 띠 없음, CCTV 양쪽 카드 하단 일치, 목록의 마지막 CCTV까지 스크롤 가능, 오른쪽 상태·버튼은 페이지 스크롤로 노출.
- 이 문서는 이전 ROUND2_FOLLOWUP_STATUS.md의 contain 유지·목록 최대 높이 설명을 이번 요청 기준으로 갱신함. 실제 CCTV 영상 컴포넌트와 Penpot 파일은 이번 수정 대상 아님.
