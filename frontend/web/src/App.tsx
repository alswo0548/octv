/**
 * 실제 웹 화면 조립
 *
 * 역할별 접근:
 * - CONTROL_ADMIN: 전체 화면
 * - AGENCY_STAFF / RESPONDER: 통합관제, 사건관리, 경로조회
 * - 관리자 전용 URL 직접 접근 시 overview로 이동
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import { useRoute, go } from "./routing/useRoute";
import { NewIncidentToastV5 } from "./components/NewIncidentToastV5";
import { WebLayout } from "./layouts/WebLayout";
import { Modal, type ModalSpec } from "./components/Primitives";
import { LiveAgencyPicker } from "./components/AgencyPicker";
import { AuthPage } from "./pages/AuthPage";
import { LiveOverviewPage } from "./pages/LiveOverviewPage";
import { LiveIncidentsPage } from "./pages/LiveIncidentsPage";
import { LiveRoutesPage } from "./pages/LiveRoutesPage";
import { MonitorPage } from "./pages/MonitorPage";
import { StatsPage } from "./pages/StatsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TargetsPage } from "./pages/TargetsPage";
import { setDeliveryContext } from "./delivery";
import {
  disconnectWebIncidentSession,
  getWebIncidentApi,
  getWebIncidentSession,
  subscribeWebIncidentSession,
} from "./incidentData";

const titles: Record<string, string> = {
  login: "로그인",
  signup: "회원가입",
  overview: "통합관제",
  incidents: "사건관리",
  routes: "사건관리 · 경로 평가",
  monitor: "CCTV 모니터링",
  stats: "CCTV 운영통계",
  settings: "시스템 설정",
  targets: "대상 CCTV 설정",
};

const ADMIN_ONLY_PAGES = new Set(["monitor", "stats", "settings", "targets"]);

export default function App() {
  const route = useRoute();
  const [raw, id] = route.split("/");
  const page = titles[raw] ? raw : "login";

  const routeIncidentId =
    page === "routes" &&
    /^\d+$/.test(id ?? "") &&
    Number.isSafeInteger(Number(id)) &&
    Number(id) > 0
      ? Number(id)
      : null;

  const session = useSyncExternalStore(
    subscribeWebIncidentSession,
    getWebIncidentSession,
    () => null,
  );

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [picker, setPicker] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [modal, setModal] = useState<ModalSpec | null>(null);

  const refresh = () => setRefreshKey((value) => value + 1);

  const isAdmin = session?.user.role === "CONTROL_ADMIN";

  const canAccessPage =
    page === "login" ||
    page === "signup" ||
    !session ||
    !ADMIN_ONLY_PAGES.has(page) ||
    isAdmin;

  // 비관리자가 관리자 전용 URL을 직접 입력해도
  // 관리자 화면 자체를 렌더링하지 않습니다.
  useEffect(() => {
    if (session && !isAdmin && ADMIN_ONLY_PAGES.has(page)) {
      setPicker(false);
      setSelectedId(null);
      go("overview");
    }
  }, [session, isAdmin, page]);

  // 계정 변경 시 이전 계정의 사건 선택과 전달창 제거
  useEffect(() => {
    setSelectedId(null);
    setPicker(false);
  }, [session?.version]);

  // 기관 전달 context는 CONTROL_ADMIN만 사용
  useEffect(() => {
    const api = session ? getWebIncidentApi(session.version) : null;

    if (
      !session ||
      !isAdmin ||
      !api ||
      (routeIncidentId ?? selectedId) === null ||
      !["incidents", "overview", "routes"].includes(page)
    ) {
      setDeliveryContext(null);
      return;
    }

    setDeliveryContext({
      user: session.user,
      api,
      incidentId: (routeIncidentId ?? selectedId)!,
    });

    return () => setDeliveryContext(null);
  }, [session, isAdmin, selectedId, page, routeIncidentId]);

  useEffect(() => {
    document.title = "OCTV · " + titles[page];
  }, [page]);

  const logout = () => {
    setDeliveryContext(null);

    void disconnectWebIncidentSession()
      .then(() => go("login"))
      .catch(() => {
        go("login");

        setModal({
          title: "로그아웃 처리 확인 필요",
          body: "화면 연결은 해제됐지만, 인증 토큰 삭제 결과를 확인해야 합니다.",
          cancel: "",
        });
      });
  };

  const openIncident = (serverId: number) => {
    setSelectedId(serverId);
    go("incidents");
  };

  const closePicker = () => {
    setPicker(false);
    refresh();
  };

  const loginRequired = (
    <section className="panel live-placeholder" role="status">
      <h2>로그인이 필요합니다.</h2>
      <p>
        로그인하면 계정 권한에 따라 허용된 사건과 기능을 확인할 수 있습니다.
      </p>

      <button className="secondary" onClick={() => go("login")}>
        로그인 화면으로 이동
      </button>
    </section>
  );

  const routePending = (
    <section className="panel live-placeholder" role="status">
      <h2>조회할 사건을 선택해주세요.</h2>

      <p>
        사건 상세에서 경로 비교를 열면 해당 사건의 저장된 경로를 조회합니다.
      </p>

      <button className="secondary" onClick={() => go("incidents")}>
        사건관리로 돌아가기
      </button>
    </section>
  );

  return (
    <>
      <WebLayout
        page={page}
        title={titles[page]}
        show={setModal}
        onLogout={logout}
        user={session?.user ?? null}
        notifications={session && isAdmin ? <NewIncidentToastV5 key={session.version} session={session} openIncident={openIncident} /> : null}
      >
        {!canAccessPage ? null : page === "login" || page === "signup" ? (
          <AuthPage key={page} signup={page === "signup"} show={setModal} />
        ) : page === "overview" ? (
          session ? (
            <LiveOverviewPage
              key={session.version}
              session={session}
              openIncident={openIncident}
            />
          ) : (
            loginRequired
          )
        ) : page === "incidents" ? (
          session ? (
            <LiveIncidentsPage
              key={session.version}
              session={session}
              selectedId={selectedId}
              onSelect={setSelectedId}
              openPicker={() => {
                if (isAdmin) {
                  setPicker(true);
                }
              }}
              show={setModal}
              refreshKey={refreshKey}
              onRefresh={refresh}
            />
          ) : (
            loginRequired
          )
        ) : page === "routes" ? (
          session ? (
            routeIncidentId ? (
              <LiveRoutesPage
                key={`${session.version}:${routeIncidentId}:${refreshKey}`}
                session={session}
                incidentId={routeIncidentId}
                openPicker={() => {
                  if (isAdmin) {
                    setPicker(true);
                  }
                }}
                show={setModal}
              />
            ) : (
              routePending
            )
          ) : (
            loginRequired
          )
        ) : page === "monitor" ? (
          session && isAdmin ? (
            <MonitorPage
              key={`${session.version}:${id}`}
              session={session}
              initial={id}
              show={setModal}
            />
          ) : (
            loginRequired
          )
        ) : page === "stats" ? (
          session && isAdmin ? (
            <StatsPage key={session.version} session={session} />
          ) : (
            loginRequired
          )
        ) : page === "settings" ? (
          session && isAdmin ? (
            <SettingsPage
              key={session.version}
              session={session}
              tab={id}
              show={setModal}
            />
          ) : (
            loginRequired
          )
        ) : session && isAdmin ? (
          <TargetsPage
            key={session.version}
            session={session}
            show={setModal}
          />
        ) : (
          loginRequired
        )}
      </WebLayout>

      {picker && session && isAdmin && <LiveAgencyPicker close={closePicker} />}

      <Modal spec={modal} close={() => setModal(null)} />
    </>
  );
}
