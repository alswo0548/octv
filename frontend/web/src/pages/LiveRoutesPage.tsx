import { incidentLabel } from "../incidentLabel";
import { statusLabel } from "../operationsData";
/** 기존 경로 비교 레이아웃에 실제 추천 기관·저장 경로를 연결합니다. 경로 재계산·전달 상태 변경은 하지 않습니다. */

import { useState } from "react";
import { hazardLabel } from "@octv/shared";
import type { IncidentDetailDto, WebIncidentSession } from "../incidentData";
import { useOperations } from "../operationsData";
import { LiveMap, geometryLines } from "../components/LiveMap";
import { Badge, type ShowModal } from "../components/Primitives";
import type { RouteResponse } from "../../../mobile/src/liveRoutes";

type DemoRouteResponse = Omit<RouteResponse, "items"> & {
  items: (RouteResponse["items"][number] & {
    demo_traffic?: {
      type: "SIMULATED_FULL_CLOSURE" | "SIMULATED_DELAY";
      label: string;
      reason: string;
      simulated: boolean;
      point?: number[] | null;
      delay_sec?: number;
    } | null;
    demo_rank_status?: "SIMULATED_EXCLUDED" | "SIMULATED_DELAY" | "ALTERNATIVE" | null;
    demo_total_score?: number | null;
    demo_duration_sec?: number | null;
  })[];
};

type Agency = {
  agency_id: number;
  agency_name: string;
  recommendation_rank: number;
  recommendation_status: string;
};

export function LiveRoutesPage({
  session,
  incidentId,
  openPicker,
}: {
  session: WebIncidentSession;
  incidentId: number;
  openPicker: () => void;
  show: ShowModal;
}) {
  const [agencyId, setAgencyId] = useState<number | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);

  const [revision, setRevision] = useState(0);

  const isAdmin = session.user.role === "CONTROL_ADMIN";

  const incident = useOperations<IncidentDetailDto>(
    session,
    `/api/incidents/${incidentId}`,
    revision,
    10_000,
  );

  const agencies = useOperations<{
    items: Agency[];
  }>(
    session,
    `/api/agencies/incidents/${incidentId}/recommendations`,
    revision,
    10_000,
  );

  const agency =
    agencies.data?.items.find((item) => item.agency_id === agencyId) ??
    agencies.data?.items[0];

  const routes = useOperations<DemoRouteResponse>(
    session,
    agency
      ? `/api/routes/incidents/${incidentId}/agencies/${agency.agency_id}`
      : null,
    revision,
    10_000,
  );

  const active =
    routes.data?.items.find((route) => route.id === selectedId) ??
    routes.data?.items.find((route) => route.navigation_available && route.demo_rank_status !== "SIMULATED_EXCLUDED") ??
    routes.data?.items[0];

  const lines = (routes.data?.items ?? []).flatMap((route) =>
    geometryLines(route.id, route.route_path_json),
  );
  // Stored path endpoints only: choose the endpoint farther from the incident
  // for the agency marker. Never invent an unprovided coordinate.
  const activeLine = lines.find(line => line.id === active?.id);
  const endpoints = activeLine?.coords.length ? [activeLine.coords[0], activeLine.coords[activeLine.coords.length-1]] : [];
  const agencyEndpoint = incident.data && endpoints.length === 2
    ? [...endpoints].sort((a, b) =>
        Math.hypot(b[0] - incident.data!.longitude, b[1] - incident.data!.latitude) -
        Math.hypot(a[0] - incident.data!.longitude, a[1] - incident.data!.latitude))[0]
    : null;

  const error = incident.error ?? agencies.error ?? routes.error;

  return (
    <>
      <a className="back-link" href="#/incidents">
        ‹ 사건관리
      </a>

      <div className="page-heading">
        <div>
          <h2>
            {incident.data
              ? `${incidentLabel(incident.data)} · ${hazardLabel(
                  incident.data.hazard_type,
                )}`
              : "사건 경로 조회"}{" "}
            {incident.data?.priority && (
              <Badge priority={incident.data.priority} />
            )}
          </h2>

          <p>{incident.data?.cctv_name}</p>
        </div>
      </div>

      {error && <p role="alert">{error}</p>}

      {(incident.loading || agencies.loading || routes.loading) && (
        <p role="status">저장된 경로 조회 중</p>
      )}

      <section className="panel page-section octv-route-heading">
      <div className="section-title">
        <h2>{isAdmin ? "기관별 추천경로" : "우리 기관 경로"}</h2>

        <div className="action-row">
          <button
            className="secondary"
            onClick={() => setRevision((value) => value + 1)}
          >
            다시 조회
          </button>

          {isAdmin && (
            <button
              className="primary"
              disabled={
                !incident.data
              }
              onClick={openPicker}
            >
              기관 선택·전달
            </button>
          )}
        </div>
      </div>
      <div
        className="agency-tabs"
        role="tablist"
        aria-label="현재 경로 조회 기관"
      >
        {agencies.data?.items.map((item) => (
          <button
            key={item.agency_id}
            role="tab"
            aria-selected={agency?.agency_id === item.agency_id}
            onClick={() => {
              setAgencyId(item.agency_id);
              setSelectedId(null);
            }}
          >
            {item.agency_name}

            <small>
              {isAdmin
                ? `추천 ${item.recommendation_rank}순위 · ${statusLabel(item.recommendation_status)}`
                : statusLabel(item.recommendation_status)}
            </small>
          </button>
        ))}
      </div>

      {agencies.data?.items.length === 0 && (
        <p>추천된 기관이 없습니다. 분석 상태를 확인해주세요.</p>
      )}

      <p className="agency-origin">
        현재 조회: <strong>{agency?.agency_name ?? "미선택"}</strong> →{" "}
        {incident.data?.cctv_name ?? "사건 위치"}
      </p>
      </section>

      <LiveMap
        controls={false}
        emphasizeRoutes
        lines={lines}
        selectedId={active?.id}
        markers={
          incident.data
            ? [
                {
                  id: incidentId,
                  label: incidentLabel(incident.data),
                  longitude: incident.data.longitude,
                  latitude: incident.data.latitude,
                  kind: "incident" as const,
                },
                ...(agencyEndpoint && agency ? [{
                  id: 1000000 + agency.agency_id,
                  label: `${agency.agency_name} · 저장 경로 시작점`,
                  longitude: agencyEndpoint[0],
                  latitude: agencyEndpoint[1],
                  kind: "agency" as const,
                }] : []),
              ]
            : []
        }
        onSelect={setSelectedId}
        onMarkerSelect={() => {}}
      />

      {routes.data?.items.some((route) => route.demo_traffic) && (
        <p role="status" className="content-footnote">
          시연용 가상 교통상황 적용 중 · 통제 및 정체는 실제 교통 API 정보가 아닙니다.
          원본 시간·거리 점수는 유지하며 시연 종료 시 자동 해제됩니다.
        </p>
      )}

      <section className="panel page-section section-gap">
        <div className="table-scroll">
          <table className="route-table">
            <caption>후보 경로 · {agency?.agency_name ?? "미선택"}</caption>

            <thead>
              <tr>
                {[
                  "후보",
                  "거리 / 시간",
                  "총점",
                  "판정",
                ].map((text) => (
                  <th key={text}>{text}</th>
                ))}
              </tr>
            </thead>

            <tbody>
              {routes.data?.items.map((route) => (
                <tr
                  key={route.id}
                  tabIndex={0}
                  role="button"
                  aria-label={`경로 ${route.route_name} 확인`}
                  className={
                    (active?.id === route.id ? "chosen " : "") +
                    (!route.navigation_available ? "blocked" : "")
                  }
                  onClick={() => setSelectedId(route.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      setSelectedId(route.id);
                    }
                  }}
                >
                  <td>{(routes.data?.items ?? []).findIndex(item => item.id === route.id) + 1}</td>

                  <td>
                    {(route.distance_m / 1000).toFixed(1)} km /{" "}
                    {Math.ceil(route.duration_sec / 60)}분
                    {route.demo_duration_sec != null && route.demo_traffic?.type === "SIMULATED_DELAY" && <small> · 시연 {Math.ceil(route.demo_duration_sec / 60)}분</small>}
                  </td>

                  <td>{route.total_score ?? "미평가"}
                    {route.demo_traffic?.type === "SIMULATED_DELAY" && route.demo_total_score != null && (
                      <small> · 시연 {route.demo_total_score}점</small>
                    )}
                  </td>


                  <td>{route.demo_rank_status === "SIMULATED_EXCLUDED"
                      ? "시연상 제외"
                      : route.demo_rank_status === "SIMULATED_DELAY"
                        ? "시연상 후순위"
                        : (({ VERIFIED: "검증 완료", NEEDS_REVIEW: "추가 확인 필요", DISQUALIFIED: "제외" } as Record<string, string>)[route.verification_status ?? ""] ?? "평가 대기")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {routes.data?.items.length === 0 && (
          <p>저장된 경로가 없습니다. ({statusLabel(routes.data.result_status)})</p>
        )}

        {active && (
          <p className="route-feedback">
            조회 중: {active.route_name} ·{" "}
            {active.requires_review
              ? "통제 미확인 — 현장 확인 필요"
              : active.navigation_available
                ? "저장된 평가 기준"
                : "제외된 경로"}
          </p>
        )}

        <p className="content-footnote">
          현장 내비 실행은 기존 Android 카카오내비 기능에서 제공합니다. 외부
          내비 경로는 다시 계산될 수 있습니다.
        </p>
      </section>
    </>
  );
}
