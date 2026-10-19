/**
 * 후속-03 · 상황실 통합관제의 실제 사건 목록
 * 기존 mock 통계·도로 좌표 SVG를 실제 수치·지도인 것처럼 보여주지 않습니다.
 * 지도/외부 상황 표시의 실제 연결은 후속-05/08/09에서 진행합니다.
 */
import { useEffect, useState } from "react";
import type { IncidentDto, PageDto } from "@octv/shared";
import { Panel } from "../components/Primitives";
import {
  formatSeoulTime,
  incidentErrorMessage,
  listServerIncidents,
  type WebIncidentSession,
} from "../incidentData";
import "../styles/live-incidents.css";

export function LiveOverviewPage({
  session, openIncident,
}: {
  session: WebIncidentSession;
  openIncident: (id: number) => void;
}) {
  const [all, setAll] = useState<PageDto<IncidentDto> | null>(null);
  const [urgent, setUrgent] = useState<PageDto<IncidentDto> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setAll(null);
    setUrgent(null);
    void Promise.all([
      listServerIncidents(session.version, { page: 1, page_size: 5 }, controller.signal),
      listServerIncidents(session.version, { page: 1, page_size: 5, priority: "P1" }, controller.signal),
    ])
      .then(([allIncidents, urgentIncidents]) => {
        if (!controller.signal.aborted) {
          setAll(allIncidents);
          setUrgent(urgentIncidents);
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(incidentErrorMessage(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [session.version, revision]);

  return (
    <>
      <div className="stat-grid">
        <div className="panel stat-card"><span>실제 사건 수 (오탐 제외)</span>
          <strong>{all?.total ?? "–"}<small>건</small></strong></div>
        <div className="panel stat-card"><span>P1 우선순위 사건</span>
          <strong>{urgent?.total ?? "–"}<small>건</small></strong></div>
        <div className="panel stat-card"><span>데이터 출처</span>
          <strong className="live-source-label">PostgreSQL</strong></div>
      </div>
      <div className="live-overview-actions">
        <button className="secondary" onClick={() => setRevision((value) => value + 1)}>서버 사건 새로고침</button>
        {loading && <span role="status">실제 사건 조회 중</span>}
        {error && <span role="alert">{error}</span>}
      </div>
      <div className="two-col overview-layout">
        <Panel title="최근 사건 · 실제 위치 좌표" className="overview-list-panel">
          {all?.items.length === 0 && <p>조회되는 사건이 없습니다.</p>}
          <div className="overview-incident-list">
            {all?.items.map((item) => (
              <button key={item.id} className="incident-card" onClick={() => openIncident(item.id)}>
                <div className="incident-card-top"><strong>{item.priority ?? "미분석"}</strong>
                  <span className="subtle">{formatSeoulTime(item.detected_at)}</span></div>
                <h3>{item.hazard_type} · {item.incident_no}</h3>
                <p>{item.cctv_name} · {item.latitude}, {item.longitude}</p>
              </button>
            ))}
          </div>
          <p className="subtle">실제 지도의 좌표 마커는 후속-05/08에서 연결합니다.</p>
        </Panel>
        <Panel title="P1 긴급 사건 · 실제 조회" className="overview-list-panel">
          {urgent?.items.length === 0 && <p>현재 조회되는 P1 사건이 없습니다.</p>}
          <div className="overview-incident-list">
            {urgent?.items.map((item) => (
              <button key={item.id} className="incident-card" onClick={() => openIncident(item.id)}>
                <div className="incident-card-top"><strong>{item.priority ?? "미분석"}</strong>
                  <span className="subtle">{item.status}</span></div>
                <h3>{item.hazard_type} · {item.incident_no}</h3>
                <p>{item.cctv_name} · {formatSeoulTime(item.detected_at)}</p>
              </button>
            ))}
          </div>
        </Panel>
      </div>
      <Panel title="외부 상황·운영통계 연동 상태">
        <p className="subtle">현재 화면의 사건 수와 우선순위만 실제 사건 API를 기준으로 표시합니다. 외부 상황 요약과 운영통계는 이후 PR에서 실제 데이터 연결 후 표시합니다.</p>
      </Panel>
    </>
  );
}
