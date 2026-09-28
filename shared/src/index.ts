import fixtures from "./fixtures.json";
/** UI snapshots only. Values are prepared, never calculated or persisted at runtime. */
export const mock = fixtures;
export type Incident = (typeof fixtures.incidents)[number];
export type Camera = (typeof fixtures.cctvs)[number];
export type Agency = (typeof fixtures.agencies)[keyof typeof fixtures.agencies];
export type RouteOption =
  (typeof fixtures.routes)[keyof typeof fixtures.routes][number];
export type Recommendation =
  (typeof fixtures.recommendations)[keyof typeof fixtures.recommendations][number];
export const incidentById = (id: string): Incident =>
  mock.incidents.find((x) => x.id === id) ?? mock.incidents[0];
export const agencyById = (id: string): Agency =>
  (mock.agencies as Record<string, Agency>)[id];
export const recommendationsFor = (id: string): Recommendation[] =>
  (mock.recommendations as Record<string, Recommendation[]>)[id];
export const routesFor = (
  incidentId: string,
  agencyId: string,
): RouteOption[] =>
  (mock.routes as Record<string, RouteOption[]>)[`${incidentId}|${agencyId}`];
export const webScreens = [
  ["W01-1", "로그인", "login", "AuthPage.tsx"],
  ["W01-2", "회원가입", "signup", "AuthPage.tsx"],
  ["W02", "통합관제", "overview", "OverviewPage.tsx"],
  ["W03", "사건관리", "incidents", "IncidentsPage.tsx"],
  ["W03-1", "사건관리 · 경로 평가", "routes/SEL-001", "RoutesPage.tsx"],
  ["W04", "CCTV 모니터링", "monitor", "MonitorPage.tsx"],
  ["W05", "CCTV 운영통계", "stats", "StatsPage.tsx"],
  ["W06", "시스템 설정", "settings", "SettingsPage.tsx"],
  ["W06-1", "대상 CCTV 설정", "targets", "TargetsPage.tsx"],
] as const;
export const mobileScreens = [
  ["A01", "로그인", "login", "AuthScreens.tsx"],
  ["A01-1", "회원가입 · 기본 정보", "signup-basic", "AuthScreens.tsx"],
  ["A01-2", "회원가입 · 소속기관", "signup-agency", "AuthScreens.tsx"],
  ["A01-3", "회원가입 완료", "signup-complete", "AuthScreens.tsx"],
  ["A02", "전달받은 사건", "home", "IncidentScreens.tsx"],
  ["A02-1", "알림", "notifications", "NotificationScreen.tsx"],
  ["A03", "사건 목록", "incidents", "IncidentScreens.tsx"],
  ["A04", "사건 상세 · 사건 정보", "detail", "DetailScreen.tsx"],
  ["A04-1", "사건 상세 · 실시간 영상", "live", "DetailScreen.tsx"],
  ["A05", "추천경로", "routes", "RoutesScreen.tsx"],
  ["A06", "추가 지원요청", "request", "RequestScreen.tsx"],
  ["A07", "설정", "settings", "SettingsScreen.tsx"],
] as const;

export const recommendedRouteFor = (incidentId: string, agencyId: string) =>
  routesFor(incidentId, agencyId).find(
    (route) => route.recommended && !route.blocked,
  );
export type SupportRequest =
  (typeof fixtures.supportRequests)[keyof typeof fixtures.supportRequests][number];
// Fixtures are supplied newest first, independently for each incident.
export const supportRequestsFor = (incidentId: string): SupportRequest[] =>
  (mock.supportRequests as Record<string, SupportRequest[]>)[incidentId] ?? [];
