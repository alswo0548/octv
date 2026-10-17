/**
 * 기존 WEB 화면·모달 연결을 유지합니다.
 * PR 4: 로그인 화면 진입 시 이전 실제 사건의 전달 연결만 해제합니다.
 * 로그인·회원가입 구현과 실제 사건 선택 연결은 해당 담당 기능에서 제공합니다.
 */
import { useEffect, useState } from "react";
import { incidentById, recommendationsFor } from "@octv/shared";
import { useRoute } from "./routing/useRoute";
import { WebLayout } from "./layouts/WebLayout";
import { Modal, type ModalSpec } from "./components/Primitives";
import { AgencyPicker, type AgencyUI } from "./components/AgencyPicker";
import { AuthPage } from "./pages/AuthPage";
import { OverviewPage } from "./pages/OverviewPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { RoutesPage } from "./pages/RoutesPage";
import { MonitorPage } from "./pages/MonitorPage";
import { StatsPage } from "./pages/StatsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TargetsPage } from "./pages/TargetsPage";
import { setDeliveryContext } from "./delivery";
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
  const route = useRoute(),
    [raw, id] = route.split("/"),
    page = titles[raw] ? raw : "login";
  const [selected, setSelected] = useState("SEL-001"),
    [states, setStates] = useState<Record<string, AgencyUI>>({}),
    [picker, setPicker] = useState(false),
    [modal, setModal] = useState<ModalSpec | null>(null);
  const incident = incidentById(page === "routes" && id ? id : selected),
    state = states[incident.id] || {
      viewing: recommendationsFor(incident.id)[0].agencyId,
      checked: [],
    };
  const set = (value: AgencyUI) =>
    setStates((s) => ({ ...s, [incident.id]: value }));
  useEffect(() => {
    // 로그인 화면으로 이동하면 이전 실제 사건의 전달 연결을 해제합니다. 인증 구현은 기존 담당 영역입니다.
    if (page === "login" || page === "signup") setDeliveryContext(null);
    if (page === "routes" && id) setSelected(incidentById(id).id);
    document.title = "OCTV · " + titles[page];
  }, [page, id]);
  const common = {
    incident,
    state,
    open: () => setPicker(true),
    show: setModal,
  };
  return (
    <>
      <WebLayout page={page} title={titles[page]} show={setModal}>
        {page === "login" || page === "signup" ? (
          <AuthPage key={page} signup={page === "signup"} show={setModal} />
        ) : page === "overview" ? (
          <OverviewPage select={setSelected} />
        ) : page === "incidents" ? (
          <IncidentsPage {...common} select={setSelected} set={set} />
        ) : page === "routes" ? (
          <RoutesPage key={incident.id} {...common} set={set} />
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
      {picker && (
        <AgencyPicker
          incident={incident}
          state={state}
          set={set}
          close={() => setPicker(false)}
        />
      )}
      <Modal spec={modal} close={() => setModal(null)} />
    </>
  );
}
