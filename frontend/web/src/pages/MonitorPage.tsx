import { useState } from "react";

/** CCTV 목록·상태와 인증된 스트림 준비 API를 기존 모니터링 레이아웃에 연결합니다. */

import { formatSeoulTime, type WebIncidentSession } from "../incidentData";

import {
  useOperations,
  monitoringLabels,
  statusLabel,
  type Cctv,
} from "../operationsData";

import { Panel, Pair, type ShowModal } from "../components/Primitives";
import { LiveCamera } from "../components/LiveCamera";
import { DemoV5Controls } from "../components/DemoV5Controls";
import { DemoV5Video } from "../components/DemoV5Video";
import { NewIncidentToastV5 } from "../components/NewIncidentToastV5";
import { go } from "../routing/useRoute";

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

  const { data, loading, error } = useOperations<Cctv[]>(
    session,
    "/api/cctvs",
    revision,
    10_000,
  );

  // 시연 시작은 가상 특보와 DEMO CCTV 활성화를 같은 DB 트랜잭션에서 처리한다.
  // 일반 UTIC는 언제나 보이지만, DEMO 목록은 특보 ACTIVE + 감시 ON일 때만 표시한다.
  const demoStatus = useOperations<{ active_alert_count: number }>(
    session,
    "/api/demo/status",
    revision,
    5_000,
  );
  // Runtime/video playback is synchronized with the *same* scenario's issued_at.
  const demoSync = useOperations<{ active: boolean; started_at: string | null }>(
    session,
    "/api/demo/v5/sync",
    revision,
    5_000,
  );
  const activeDemoAlert = (demoStatus.data?.active_alert_count ?? 0) > 0;
  const startedAt = demoSync.data?.active ? demoSync.data.started_at : null;
  const visibleCctvs = (data ?? []).filter(
    (camera) =>
      camera.provider.toUpperCase() !== "DEMO" ||
      (activeDemoAlert && camera.is_monitored),
  ).sort((a, b) => {
    // Active alerts first; ordinary UTIC selection/order stays untouched.
    const aAlert = a.provider.toUpperCase() === "DEMO" && a.is_monitored;
    const bAlert = b.provider.toUpperCase() === "DEMO" && b.is_monitored;
    return Number(bAlert) - Number(aAlert);
  });

  const rows = visibleCctvs.filter(
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
    ["전체 CCTV", data ? visibleCctvs.length : "–"],
    ["감시 중", data ? visibleCctvs.filter((camera) => camera.is_monitored).length : "–"],
    [
      "수집 연결됨",
      data ? visibleCctvs.filter((camera) => camera.connection_status === "CONNECTED")
        .length : "–",
    ],
    [
      "수집 연결 확인 필요",
      data ? visibleCctvs.filter((camera) => camera.connection_status !== "CONNECTED")
        .length : "–",
    ],
  ];

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

      <button
        className="secondary"
        onClick={() => setRevision((value) => value + 1)}
      >
        현재 상태 새로고침
      </button>

      {activeDemoAlert && visibleCctvs.some((camera) =>
        camera.provider.toUpperCase() === "DEMO" && camera.is_monitored &&
        camera.analysis_status !== "RUNNING"
      ) && (
        <p role="alert" style={{ marginBottom: 12 }}>
          주의: 시연 영상 표시와 YOLO 분석은 별개입니다. 현재 Demo CCTV 중
          YOLO가 RUNNING이 아닌 기기가 있습니다. v5 CCTV Runtime 창에서
          [RUNTIME SYNC] started 및 [YOLO WORKER] cctv=4/5/6 로그를 확인해주세요.
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

          {c && (
            c.provider.toUpperCase() === "DEMO" ? (
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
            )
          )}

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
                  value="Runtime 기준 · 현재 주기 미제공"
                />

                <Pair label="위험 후보" value="현재 후보 수 미제공" />
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

      <NewIncidentToastV5 session={session} />

      {/* 기존 CCTV 모니터링을 방해하지 않도록 시연 제어는 맨 아래에 둔다. */}
      <DemoV5Controls
        session={session}
        onChanged={() => setRevision((value) => value + 1)}
      />
    </>
  );
}
