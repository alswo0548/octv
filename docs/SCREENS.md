# 화면·이동 안내

WEB 파일 기준 폴더: `frontend/web/src/pages/`. `#` 경로는 주소창에 직접 입력할 수 있다.

| ID | 화면명 | 경로 | 파일 | 주요 이동 |
|---|---|---|---|---|
| W01-1 | 로그인 | `#/login` | AuthPage.tsx | 로그인 → W02, 회원가입 → W01-2 |
| W01-2 | 회원가입 | `#/signup` | AuthPage.tsx | 고정 완료 모달 → W01-1 |
| W02 | 통합관제 | `#/overview` | OverviewPage.tsx | 사건 선택 → W03, CCTV → W04, 설정 → W06 |
| W03 | 사건관리 | `#/incidents` | IncidentsPage.tsx | 기관 선택 모달 → W03-1, 영상 → W04 |
| W03-1 | 사건관리 · 경로 평가 | `#/routes/SEL-001` | RoutesPage.tsx | 기관 탭·A/B/C 강조, 전달 확인 모달, W03 복귀 |
| W04 | CCTV 모니터링 | `#/monitor` | MonitorPage.tsx | CCTV 카드 조회, 재연결 안내 모달, 기준 변경 → W06 |
| W05 | CCTV 운영통계 | `#/stats` | StatsPage.tsx | 사건 카드·유형 → W03, 연결 오류 확인 → W04 |
| W06 | 시스템 설정 | `#/settings` | SettingsPage.tsx | 연동 탭: #/settings/integrations, 대상 → W06-1, CCTV → W04 |
| W06-1 | 대상 CCTV 설정 | `#/targets` | TargetsPage.tsx | 활성 토글, 저장·취소 확인 모달, W06 복귀 |

WEB 기관 상태는 `components/AgencyPicker.tsx`의 `viewing`(조회 기관)과 `checked`(전달 대상 표시)로 분리된다. 확인해도 사건의 전달 상태는 바뀌지 않는다.

MOBILE 파일 기준 폴더: `frontend/mobile/src/screens/`. Expo의 메모리 화면 키이며 웹 URL이 아니다. `App.tsx`와 `src/navigation/types.ts`에서 이동한다.

| ID | 화면명 | 화면 키 | 파일 | 주요 이동 |
|---|---|---|---|---|
| A01 | 로그인 | `login` | AuthScreens.tsx | 로그인 → A02, 회원가입 → A01-1 |
| A01-1 | 회원가입 · 기본 정보 | `signup-basic` | AuthScreens.tsx | 다음 → A01-2, 로그인 → A01 |
| A01-2 | 회원가입 · 소속기관 | `signup-agency` | AuthScreens.tsx | 이전 → A01-1, 완료 → A01-3 |
| A01-3 | 회원가입 완료 | `signup-complete` | AuthScreens.tsx | 로그인하기 → A01 |
| A02 | 전달받은 사건 | `home` | IncidentScreens.tsx | 전체 → A03, 사건 → A04, 알림 → A02-1 |
| A02-1 | 알림 | `notifications` | NotificationScreen.tsx | 알림 카드 → A04, 홈 복귀 |
| A03 | 사건 목록 | `incidents` | IncidentScreens.tsx | 사건 선택 → A04 |
| A04 | 사건 상세 · 사건 정보 | `detail` | DetailScreen.tsx | 영상 탭 A04-1, 경로 A05, 요청 A06, 목록 A03 |
| A04-1 | 사건 상세 · 실시간 영상 | `live` | DetailScreen.tsx | 정보 탭 A04, 경로 A05, 요청 A06, 목록 A03 |
| A05 | 추천경로 | `routes` | RoutesScreen.tsx | A/B/C 지도 강조, 외부 앱 안내 모달, A04 복귀 |
| A06 | 추가 대응 요청 | `request` | RequestScreen.tsx | 요청 확인 후 머무름, 작성 취소 확인 → A04, 다른 메뉴 이탈 확인 |
| A07 | 설정 | `settings` | SettingsScreen.tsx | 프로필·알림 토글·정책 안내 모달, 로그아웃 확인 → A01 |

A04와 A04-1은 같은 상세 컴포넌트의 탭이다. 하단 홈·사건·설정 메뉴는 인증 없이 이동한다.
입력·필터·검색·페이지 버튼은 표시 상태만 바꾼다. 현재 목록은 준비된 행으로 유지된다.

## 흐름도 편집
`OCTV_페이지흐름도.pptx`는 9장, 도형·텍스트·커넥터를 개별 편집할 수 있다.
표준 사각형=페이지, 타원=탭, 점선 둥근 사각형=모달. 화살표는 업무 데이터 전달이 아닌 UI 이동이다.
한글 글꼴은 Noto Sans KR이다. 글꼴이 없으면 `fonts/NotoSansKR_400Regular.ttf`를 설치하거나 PowerPoint에서 글꼴을 바꾼다. 라이선스는 `fonts/OFL.md`.
모바일 앱에서의 PowerPoint 편집과 실제 MS PowerPoint 도형 드래그 동작은 미검증이다.
