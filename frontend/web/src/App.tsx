/**
 * 후속-03 · 실제 사건 화면 조립
 * - 수연 담당 로그인에서 주입한 세션만 실제 사건 API에 사용합니다.
 * - 실제 사건 ID를 선택하면 기존 delivery.ts에 전달합니다.
 * - 인증이 아직 연결되지 않았다면 샘플 사건을 실제 사건처럼 보여주지 않습니다.
 * - 기존 다른 페이지(CCTV·설정·통계)의 구현은 수정하지 않습니다.
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import { useRoute, go } from "./routing/useRoute";
import { WebLayout } from "./layouts/WebLayout";
import { Modal, type ModalSpec } from "./components/Primitives";
import { LiveAgencyPicker } from "./components/AgencyPicker";
import { AuthPage } from "./pages/AuthPage";
import { LiveOverviewPage } from "./pages/LiveOverviewPage";
import { LiveIncidentsPage } from "./pages/LiveIncidentsPage";
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

export default function App() {
  const route = useRoute();
  const [raw, id] = route.split("/");
  const page = titles[raw] ? raw : "login";
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

  // 계정 변경 시 다른 계정의 이전 사건 선택과 전달 창을 남겨두지 않습니다.
  useEffect(() => {
    setSelectedId(null);
    setPicker(false);
  }, [session?.version]);

  // 세션/사건 선택이 실제로 바뀔 때만 기존 기관 전달 모듈에 연결합니다.
  useEffect(() => {
    const api = session ? getWebIncidentApi(session.version) : null;
    if (
      !session ||
      !api ||
      selectedId === null ||
      (page !== "incidents" && page !== "overview")
    ) {
      setDeliveryContext(null);
      return;
    }
    setDeliveryContext({ user: session.user, api, incidentId: selectedId });
    return () => setDeliveryContext(null);
  }, [session, selectedId, page]);

  useEffect(() => {
    document.title = "OCTV · " + titles[page];
  }, [page]);

  // 인증 화면의 JWT 삭제 책임은 기존 로그인 담당 logout 함수에 있습니다.
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
    refresh(); // 전달 후 사건 상태는 서버를 재조회합니다.
  };

  const loginRequired = (
    <section className="panel live-placeholder" role="status">
      <h2>실제 사건 조회를 위한 로그인 연결 대기</h2>
      <p>
        샘플 사건을 보여주지 않습니다. 인증 담당 코드에서 검증한 관리자 세션을
        incidentData.ts에 전달하면 실제 DB 사건 목록이 표시됩니다.
      </p>
      <button className="secondary" onClick={() => go("login")}>
        로그인 화면으로 이동
      </button>
    </section>
  );
  const routePending = (
    <section className="panel live-placeholder" role="status">
      <h2>실제 경로 화면 연결 대기</h2>
      <p>
        후속-02의 경로 조회 API는 준비돼 있습니다. 지도·경로 비교 화면은
        후속-05에서 연결하며, 샘플 A/B/C 경로를 실제 경로로 표시하지 않습니다.
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
      >
        {page === "login" || page === "signup" ? (
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
              openPicker={() => setPicker(true)}
              show={setModal}
              refreshKey={refreshKey}
              onRefresh={refresh}
            />
          ) : (
            loginRequired
          )
        ) : page === "routes" ? (
          routePending
        ) : page === "monitor" ? (
          <MonitorPage key={id} initial={id} show={setModal} />
        ) : page === "stats" ? (
          <StatsPage />
        ) : page === "settings" ? (
          <SettingsPage tab={id} show={setModal} />
        ) : (
          <TargetsPage show={setModal} />
        )}
      </WebLayout>
      {picker && session && <LiveAgencyPicker close={closePicker} />}
      <Modal spec={modal} close={() => setModal(null)} />
    </>
  );
}
