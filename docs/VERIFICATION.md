> 이전 인수인계 검증 기록입니다. 2차 최신 결과는 [ROUND2_VERIFICATION.md](ROUND2_VERIFICATION.md)를 확인하세요.

# 최종 수정·재검증 결과 · 2026-09-28

이전 저장본을 보존하고 이어받았습니다. 아래 PPT 14쪽의 반영 소스·캡처 표시 영역을 대조했으며 주요 UI 흐름을 새 빌드로 다시 실행했습니다. 이전 작업의 상세 기록은 VERIFICATION_PREVIOUS.md, 이번 실행 결과와 제한은 HANDOVER_RECHECK.md를 기준으로 합니다.

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

## 추가 요청 검증표
| 항목 | 이번 확인 결과 |
|---|---|
| 실제 저장본 | ZIP 153개 파일·압축 오류 없음·소스와 바이트 일치 |
| 소스 포맷·타입·범위 | 통과. 기존 의존성을 재사용했으며 이번에 npm ci를 새로 실행한 것은 아님 |
| WEB·Expo 웹 빌드 | 모두 exit 0 |
| 영상 | WEB 3종, MOBILE 390/430px 및 PC 3종의 비율·재생·콘텐츠 폭 확인 |
| 목록/지도 | 5/5/2건 동일 사건 ID·이전 마커 제거 확인 |
| 기관 조회·전달 | 1개 추천 요약·3개 경로·복수 체크·0개 비활성·조회 유지 확인 |
| 지원요청 | 본문=첫 목록 항목·14:38→14:21 최신순·닫기 확인 |
| 모바일 제외 경로 | B 조회 가능·네비 비활성, C 선택 후 재활성 |
| Docker | 공식 17.11 태그·데이터 경로 확인, YAML·변수·DDL 동일성 정적 점검. 실행 미검증 |
| Penpot | 기존 2개 수정 사본과 주요 보드·Description 재확인, 재캡처. 새 사본/원본 변경 없음 |
| 원격 GitHub | 사용자 승인 후 재개. main이 기준 커밋과 같음을 재확인. 별도 브랜치/PR로 제출하며 main 병합은 별도 |
| 배포 링크 | 이전 버전 유지. 최신화 연결 오류. 로컬 최신 빌드 확인 방법 제공 |
| 반환 ZIP | .git·개인 .env·node_modules·dist·캐시·로그·DB 데이터 제외 검사 |

마커 마우스 호버·OS 움직임 줄이기/자동재생 차단 분기는 소스 검토이며 이번에 강제 재현하지 않았습니다. Penpot 전체 보기 모드 연결 재클릭, Docker 컨테이너, Android/iOS 실기기, Windows 자체 실행은 미검증입니다.
