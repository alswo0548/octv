/**
 * 후속-03 · 상황실 통합관제의 실제 사건 목록
 * 기존 mock 통계·도로 좌표 SVG를 실제 수치·지도인 것처럼 보여주지 않습니다.
 * 기존 Dashboard API의 카드·사건·외부 상태를 기존 통합관제 배치에 연결합니다.
 */
import { useState } from "react";
import { hazardLabel } from "@octv/shared";
import { Panel, Pair, Badge } from "../components/Primitives";
import { formatSeoulTime, type WebIncidentSession } from "../incidentData";
import { LiveMap } from "../components/LiveMap";
import { useOperations } from "../operationsData";
import { go } from "../routing/useRoute";
import "../styles/live-incidents.css";
type Dashboard = {
  summary: {
    monitored_cctv_count: number;
    today_incident_count: number;
    connection_error_count: number;
    active_weather_alert_count: number;
  };
  incidents: {
    items: {
      id: number;
      incident_no: string;
      hazard_type: string;
      priority: string;
      status: string;
      cctv_name: string;
      latitude: number;
      longitude: number;
      detected_at: string;
    }[];
    total: number;
    total_pages: number;
  };
};
type External = {
  weather_alerts: { title: string }[];
  rainfall_mm: { status: string; value: number | null };
  water_level_m: { status: string; value: number | null };
  road_control_count: { status: string; value: number | null };
  focused_monitoring_cctv_count: number;
  last_received_at: string | null;
};

export function LiveOverviewPage({
  session,
  openIncident,
}: {
  session: WebIncidentSession;
  openIncident: (id: number) => void;
}) {
  const [revision, setRevision] = useState(0);
  const [page, setPage] = useState(1);
  const { data, loading, error } = useOperations<Dashboard>(
    session,
    `/api/dashboard?page=${page}&page_size=5`,
    revision,
  );
  const urgent = data?.incidents;
  const first = urgent?.items[0];
  const external = useOperations<External>(
    session,
    first ? `/api/dashboard/incidents/${first.id}/external-status` : null,
    revision,
  );
  const cards: [string, number | string, string][] = [
    ["감시 중 CCTV", data?.summary.monitored_cctv_count ?? "–", "대"],
    ["오늘 사건", data?.summary.today_incident_count ?? "–", "건"],
    ["연결 오류 CCTV", data?.summary.connection_error_count ?? "–", "대"],
    ["활성 특보", data?.summary.active_weather_alert_count ?? "–", "건"],
  ];
  const metric = (
    value: { status: string; value: number | null } | undefined,
  ) =>
    value?.status === "OK" && value.value != null
      ? String(value.value)
      : "미확인";

  return (
    <>
      <div className="stat-grid">
        {cards.map(([title, value, unit], index) => (
          <button
            className="panel stat-card"
            key={title}
            onClick={() => go(index === 1 ? "incidents" : "monitor")}
          >
            <span>{title}</span>
            <strong>
              {value}
              <small>{unit}</small>
            </strong>
          </button>
        ))}
      </div>
      <div className="live-overview-actions">
        <button
          className="secondary"
          onClick={() => setRevision((value) => value + 1)}
        >
          서버 사건 새로고침
        </button>
        {loading && <span role="status">실제 사건 조회 중</span>}
        {error && <span role="alert">{error}</span>}
      </div>
      <div className="two-col overview-layout">
        <Panel title="사건 지도 · 우선순위별 현황">
          <LiveMap
            markers={(urgent?.items ?? []).map((item) => ({
              id: item.id,
              label: item.incident_no,
              longitude: item.longitude,
              latitude: item.latitude,
              priority: item.priority,
            }))}
            onSelect={openIncident}
          />
          <p className="type-caption">
            마커를 선택하면 해당 사건의 상세정보로 이동합니다.
          </p>
        </Panel>
        <Panel title="긴급 사건 / P1 우선" className="overview-list-panel">
          {urgent?.items.length === 0 && (
            <p>현재 조회되는 긴급 사건이 없습니다.</p>
          )}
          <div className="overview-incident-list">
            {urgent?.items.map((item) => (
              <button
                key={item.id}
                className="incident-card"
                onClick={() => openIncident(item.id)}
              >
                <div className="incident-card-top">
                  <Badge priority={item.priority} />
                  <span className="subtle">{item.status}</span>
                </div>
                <h3>
                  {hazardLabel(item.hazard_type)} · {item.incident_no}
                </h3>
                <p>
                  {item.cctv_name} · {formatSeoulTime(item.detected_at)}
                </p>
              </button>
            ))}
          </div>
          <nav
            className="pagination overview-pagination"
            aria-label="통합관제 사건 페이지"
          >
            <button
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => p - 1)}
            >
              이전
            </button>
            <span>
              {page} / {urgent?.total_pages || 1}
            </span>
            <button
              disabled={loading || page >= (urgent?.total_pages ?? 0)}
              onClick={() => setPage((p) => p + 1)}
            >
              다음
            </button>
          </nav>
        </Panel>
      </div>
      <Panel title="외부 상황">
        {external.error && <p role="alert">{external.error}</p>}
        <div className="weather-alert info-strip">
          <span>☂</span>
          <div>
            <strong>
              {external.data?.weather_alerts
                .map((alert) => alert.title)
                .join(" · ") ||
                (external.data
                  ? "해당 지역 활성 특보 없음"
                  : "선택 사건의 특보 조회 대기")}
            </strong>
            <p>{first?.cctv_name ?? "선택 사건 없음"}</p>
          </div>
        </div>
        <dl>
          <Pair
            label="강수량 / 수위"
            value={`${metric(external.data?.rainfall_mm)} mm / ${metric(external.data?.water_level_m)} m`}
          />
          <Pair
            label="도로 통제"
            value={metric(external.data?.road_control_count)}
          />
          <Pair
            label="집중 감시 CCTV"
            value={external.data?.focused_monitoring_cctv_count ?? "미확인"}
          />
          <Pair
            label="최근 수집"
            value={
              external.data?.last_received_at
                ? formatSeoulTime(external.data.last_received_at)
                : "미확인"
            }
          />
        </dl>
        <div className="quick-links">
          <button className="secondary" onClick={() => go("monitor")}>
            CCTV 상태 확인
          </button>
          <button className="primary" onClick={() => go("settings")}>
            감시 설정
          </button>
        </div>
      </Panel>
    </>
  );
}
