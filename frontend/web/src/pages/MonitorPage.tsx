import { useState } from "react";

/** CCTV 목록·상태와 인증된 스트림 준비 API를 기존 모니터링 레이아웃에 연결합니다. */

import {
  formatSeoulTime,
  requestWebApi,
  type WebIncidentSession,
} from "../incidentData";

import {
  useOperations,
  monitoringLabels,
  operationsError,
  statusLabel,
  type Cctv,
} from "../operationsData";

import { Panel, Pair, type ShowModal } from "../components/Primitives";
import { LiveCamera } from "../components/LiveCamera";
import { DemoV5Video } from "../components/DemoV5Video";

import { go } from "../routing/useRoute";
import { isTestCamera } from "../cameraVisibility";

type DemoStartResponse = {
  scenario: string;
  ready: boolean;
  started: boolean;
  case_count: number;
  resolved_cctv_count: number;
  fake_alert_count: number;
  cctvs: {
    id: number;
    provider: string;
    external_cctv_id: string;
    name: string;
    region_code: string | null;
  }[];
};

type DemoMappingResponse = {
  items: {
    external_cctv_id: string;
    weather_grid_ready: boolean;
    water_status: string;
    traffic_status: string;
  }[];
};

type DemoStopResponse = {
  scenario: string;
  stopped: boolean;
  case_count: number;
  stopped_cctv_count: number;
  ended_alert_count: number;
};

/**
 * CCTV 수집 Runtime의 연결 상태를 표시합니다.
 *
 * 브라우저의 실시간 영상 재생 상태와
 * AI/CCTV Runtime의 프레임 수집 상태를
 * 혼동하지 않도록 "수집"이라는 표현을 사용합니다.
 */
function captureConnectionLabel(value: string | null) {
  if (value === "CONNECTED") {
    return "수집 연결됨";
  }

  if (value === "DISCONNECTED") {
    return "수집 연결 끊김";
  }

  if (value === "RECONNECTING") {
    return "수집 재연결 중";
  }

  return statusLabel(value);
}

export function MonitorPage({
  initial,
  session,
}: {
  initial?: string;
  show: ShowModal;
  session: WebIncidentSession;
}) {
  const [id, setId] = useState(initial ?? "");
  const [revision, setRevision] = useState(0);
  const [query, setQuery] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);

  const monitoring = useOperations<{base_analysis_interval_sec:number;alert_analysis_interval_sec:number;verify_analysis_interval_sec:number}>(session, "/api/settings/monitoring", revision, 30_000);
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoActive, setDemoActive] = useState(false);
  const [demoMessage, setDemoMessage] = useState<string | null>(null);

  const { data, loading, error } = useOperations<Cctv[]>(
    session,
    "/api/cctvs",
    revision,
    10_000,
  );

  // Existing Demo start/stop buttons remain the single control surface.
  // V5 observes the same server-side scenario without creating additional buttons.
  const demoStatus = useOperations<{
    active: boolean;
    active_alert_count: number;
  }>(session, "/api/demo/status", revision, 5_000);
  const demoSync = useOperations<{
    active: boolean;
    started_at: string | null;
  }>(session, "/api/demo/v5/sync", revision, 5_000);
  const activeDemoAlert = (demoStatus.data?.active_alert_count ?? 0) > 0;
  const isDemoActive = demoStatus.data?.active ?? demoActive;
  const startedAt = demoSync.data?.active ? demoSync.data.started_at : null;
  const visibleData = (data ?? []).filter(
    (camera) => {
      if (isTestCamera(camera)) return false;
      const provider = camera.provider.trim().toUpperCase();
      // During a rehearsal show only the monitored UTIC cameras. Operators
      // retain the existing Settings screen for safely choosing the two feeds.
      if (provider === "UTIC" && isDemoActive && !camera.is_monitored) return false;
      return provider !== "DEMO" || (activeDemoAlert && camera.is_monitored);
    },
  ).sort((a, b) => {
    // Demo cameras first during the scenario; preserve original UTIC order.
    const isActiveDemo = (camera: Cctv) =>
      camera.provider.trim().toUpperCase() === "DEMO" && camera.is_monitored;
    return Number(isActiveDemo(b)) - Number(isActiveDemo(a));
  });

  const rows = visibleData.filter(
    (camera) =>
      (!errorsOnly || camera.connection_status !== "CONNECTED") &&
      `${camera.external_cctv_id} ${camera.name} ${camera.address ?? ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );

  const c =
    rows.find(
      (camera) => String(camera.id) === id || camera.external_cctv_id === id,
    ) ?? rows[0];

  const cards: [string, number | string][] = [
    ["전체 CCTV", data ? visibleData.length : "–"],
    [
      "감시 중",
      data ? visibleData.filter((camera) => camera.is_monitored).length : "–",
    ],
    [
      "수집 연결됨",
      data
        ? visibleData.filter(
            (camera) => camera.connection_status === "CONNECTED",
          ).length
        : "–",
    ],
    [
      "수집 연결 확인 필요",
      data
        ? visibleData.filter(
            (camera) => camera.connection_status !== "CONNECTED",
          ).length
        : "–",
    ],
  ];

  async function startDemo() {
    if (demoBusy) {
      return;
    }

    setDemoBusy(true);
    setDemoMessage(null);

    let demoMappingSummary = "";
    try {
      // Prefer real provider mappings; the backend returns explicitly labelled
      // DEMO-only examples when official station/traffic mapping is unavailable.
      // This is a backend operation, not a UI/test fixture or a Risk score override.
      // External data may still be unavailable when official matching is unverified.
      try {
        const mapping = await requestWebApi<DemoMappingResponse>(
          session.version,
          "/api/demo/v5/prepare-mapping",
          { method: "POST" },
        );
        const simulated = mapping.items.filter(item =>
          item.water_status === "DEMO_SIMULATION" ||
          item.traffic_status === "DEMO_SIMULATION",
        ).length;
        if (simulated) {
          demoMappingSummary = ` · DEMO 자동 매핑 ${simulated}대 준비`;
        }
      } catch {
        // Do not prevent the original Demo start when a provider is unavailable.
        // Missing measurements remain unverified in existing Context/Rule.
        console.warn("[OCTV Demo] 외부 데이터 매핑 사전 준비 실패");
      }

      const result = await requestWebApi<DemoStartResponse>(
        session.version,
        "/api/demo/start",
        {
          method: "POST",
          body: JSON.stringify({
            scenario: "main_demo",
          }),
        },
      );

      setDemoActive(true);

      const firstDemo = result.cctvs[0];

      if (firstDemo) {
        setId(String(firstDemo.id));
      }

      setRevision((value) => value + 1);
      setDemoMessage(`기상특보가 발효되어 Demo CCTV 감시가 시작됐습니다.${demoMappingSummary}`);
    } catch (error) {
      setDemoMessage(operationsError(error));
    } finally {
      setDemoBusy(false);
    }
  }

  async function stopDemo() {
    if (demoBusy) {
      return;
    }

    setDemoBusy(true);
    setDemoMessage(null);

    try {
      await requestWebApi<DemoStopResponse>(session.version, "/api/demo/stop", {
        method: "POST",
        body: JSON.stringify({
          scenario: "main_demo",
        }),
      });

      setDemoActive(false);
      setId("");
      setRevision((value) => value + 1);
      setDemoMessage("Demo 기상특보가 종료되고 Demo CCTV가 비활성화됐습니다.");
    } catch (error) {
      setDemoMessage(operationsError(error));
    } finally {
      setDemoBusy(false);
    }
  }

  return (
    <>
      <div className="stat-grid">
        {cards.map(([title, count]) => (
          <div className="panel stat-card" key={title}>
            <span>{title}</span>

            <strong>
              {count}
              <small>대</small>
            </strong>
          </div>
        ))}
      </div>

      <div className="monitor-filter">
        <label>
          수집 연결 상태
          <select
            value={String(errorsOnly)}
            onChange={(event) => setErrorsOnly(event.target.value === "true")}
          >
            <option value="false">전체 CCTV</option>

            <option value="true">수집 연결 확인 필요</option>
          </select>
        </label>

        <label>
          검색
          <input
            placeholder="CCTV ID / 위치 검색"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>

      {loading && <p role="status">CCTV 상태 조회 중</p>}

      {error && <p role="alert">{error}</p>}

      <div className="action-row">
        {!isDemoActive ? (
          <button
            className="primary"
            disabled={demoBusy}
            onClick={() => void startDemo()}
          >
            {demoBusy ? "재난 시연 시작 중…" : "재난 발생 · 시연 시작"}
          </button>
        ) : (
          <button
            className="secondary"
            disabled={demoBusy}
            onClick={() => void stopDemo()}
          >
            {demoBusy ? "시연 종료 중…" : "재난 시연 종료"}
          </button>
        )}

        <button
          className="secondary"
          onClick={() => setRevision((value) => value + 1)}
        >
          현재 상태 새로고침
        </button>
      </div>

      {demoMessage && <p role="status">{demoMessage}</p>}

      {activeDemoAlert && visibleData.some(
        (camera) => camera.provider.trim().toUpperCase() === "DEMO" &&
          camera.is_monitored && camera.analysis_status !== "RUNNING",
      ) && (
        <p role="alert">
          시연 영상 표시와 YOLO 분석은 별개입니다. 일부 Demo CCTV의
          분석 상태가 RUNNING이 아닙니다. v5 Runtime 로그를 확인해주세요.
        </p>
      )}

      <div className="monitor-layout">
        <Panel title="CCTV 목록" className="monitor-list-panel">
          <div className="camera-list">
            {rows.map((camera) => (
              <button
                key={camera.external_cctv_id}
                className={camera.id === c?.id ? "active" : ""}
                onClick={() => setId(String(camera.id))}
              >
                <strong>{camera.external_cctv_id}</strong>

                <p>
                  {camera.name}
                  {" · "}
                  {camera.address}
                </p>

                <span
                  className={
                    "status " +
                    (camera.connection_status === "CONNECTED"
                      ? "detect"
                      : "check")
                  }
                >
                  {captureConnectionLabel(camera.connection_status)}
                </span>

                <p className="camera-mode">
                  {monitoringLabels[camera.monitored_mode ?? "OFF"]}
                </p>
              </button>
            ))}
          </div>
        </Panel>

        <Panel
          title="선택 CCTV 영상 및 분석 상태"
          className="monitor-detail-panel"
        >
          {!c && (
            <div className="camera live-camera-empty">
              {loading
                ? "목록 조회 중"
                : error
                  ? "CCTV 목록을 조회하지 못했습니다."
                  : "표시할 CCTV가 없습니다."}
            </div>
          )}

          {c && (c.provider.trim().toUpperCase() === "DEMO" && startedAt ? (
            <DemoV5Video
              key={`${session.version}:${c.id}:${c.is_monitored}`}
              session={session}
              camera={c}
              startedAt={startedAt}
            />
          ) : (
            <LiveCamera
              key={`${session.version}:${c.id}:${c.is_monitored}`}
              session={session}
              camera={c}
            />
          ))}

          {c && (
            <div className="status-grid">
              <dl>
                <Pair
                  label="수집 연결 / 분석"
                  value={`${captureConnectionLabel(
                    c.connection_status,
                  )} / ${statusLabel(c.analysis_status)}`}
                />

                <Pair
                  label="마지막 수집 프레임"
                  value={
                    c.last_frame_at
                      ? formatSeoulTime(c.last_frame_at)
                      : "수신 기록 없음"
                  }
                />

                <Pair
                  label="수집 영상 품질"
                  value={statusLabel(c.video_quality_status)}
                />
              </dl>

              <dl>
                <Pair
                  label="감시 모드"
                  value={monitoringLabels[c.monitored_mode ?? "OFF"]}
                />

                <Pair
                  label="현재 분석 주기"
                  value={monitoring.data ? `${c.monitored_mode === "VERIFY" ? monitoring.data.verify_analysis_interval_sec : c.monitored_mode === "ALERT" ? monitoring.data.alert_analysis_interval_sec : monitoring.data.base_analysis_interval_sec}초 (설정 기준)` : "설정 조회 대기"}
                />

              </dl>
            </div>
          )}

          <div className="action-row">
            <button className="primary" onClick={() => go("settings")}>
              감시 기준 변경
            </button>
          </div>
        </Panel>
      </div>

    </>
  );
}
