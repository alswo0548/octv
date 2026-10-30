/** 저장된 분석 스냅샷의 관측값·상태만 기존 외부 상황 카드에 표시합니다. 미확인은 0으로 바꾸지 않습니다. */
import { externalMetric } from "../externalDisplay";
import { useOperations } from "../operationsData";
import { formatSeoulTime, type IncidentDetailDto, type WebIncidentSession } from "../incidentData";

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
type DemoMappingPreview = {
  source: string;
  label?: string;
  external_cctv_id?: string;
  weather_grid?: { nx: number; ny: number };
  rainfall_mm?: number;
  water_level_m?: number;
  water_risk_level?: string;
  blocked_lane_count?: number;
};
type ExternalMapStatus = {
  mapping_state?: Record<string, string>;
  last_received_at: string | null;
  demo_mapping_preview?: DemoMappingPreview | null;
};
export function IncidentContext({ incident, session }: { incident: IncidentDetailDto; session: WebIncidentSession }) {
  const mapped = useOperations<ExternalMapStatus>(session, `/api/dashboard/incidents/${incident.id}/external-status`, 0, 30_000);
  const snapshot = record(incident.risk_breakdown_json?.context_snapshot);
  const measurements = record(snapshot.measurements);
  const preview = mapped.data?.demo_mapping_preview;
  const demo = preview?.source === "DEMO_SIMULATION" ? preview : null;
  const metric = (key: string, unit = "") => {
    const item = record(measurements[key]);
    // Preserve the existing DEMO fallback scope; a real zero always wins.
    const useDemoExample = demo && (
      key === "rainfall_mm" ||
      (key === "water_level_m" && mapped.data?.mapping_state?.water === "DEMO_SIMULATION") ||
      (key === "blocked_lane_count" && mapped.data?.mapping_state?.traffic === "DEMO_SIMULATION")
    );
    const example = useDemoExample ? demo?.[key as "rainfall_mm" | "water_level_m" | "blocked_lane_count"] : undefined;
    return { ...externalMetric(item, unit, example), item };
  };
  const rain = metric("rainfall_mm", "mm");
  const water = metric("water_level_m", "m");
  const lanes = metric("blocked_lane_count");
  const hospital = metric("nearby_hospital_distance_m", "m");
  const hasExample = [rain, water, lanes, hospital].some(value => value.simulated);
  const provenance = (value: ReturnType<typeof metric>) => {
    if (!value.numeric || value.simulated) return null;
    const source = typeof value.item.source === "string" ? value.item.source : "출처 미확인";
    const observed = typeof value.item.observed_at === "string" && Number.isFinite(Date.parse(value.item.observed_at))
      ? formatSeoulTime(value.item.observed_at) : "관측 시각 미확인";
    return <small className="external-provenance">{source} · {observed}</small>;
  };
  return (
    <section className="panel external">
      <div className="section-title">
        <h2>외부 상황</h2>
        <span className="subtle">
          {typeof snapshot.captured_at === "string"
            ? `분석 저장 · ${formatSeoulTime(snapshot.captured_at)}`
            : "저장된 분석 시점 기준"}
        </span>
      </div>
      <div className="weather">
        <div>
          <span className="weather-icon">☂</span>
          <div>
            <label>강수량</label>
            <strong className={rain.numeric ? "external-number" : "external-status"}>
              {rain.text}{rain.unit && <small> {rain.unit}</small>}
            </strong>
            {provenance(rain)}
          </div>
        </div>
        <div>
          <span className="weather-icon">≋</span>
          <div>
            <label>수위</label>
            <strong className={water.numeric ? "external-number" : "external-status"}>
              {water.text}{water.unit && <small> {water.unit}</small>}
            </strong>
            {provenance(water)}
          </div>
        </div>
      </div>
      <div className="external-row">
        <span>차단 차로 수</span>
        <div className="external-row-value"><b>{lanes.text}</b>{provenance(lanes)}</div>
      </div>
      <div className="external-row">
        <span>인근 병원 거리</span>
        <div className="external-row-value"><b>{hospital.text}{hospital.unit && ` ${hospital.unit}`}</b>{provenance(hospital)}</div>
      </div>
      {hasExample && (
        <p className="content-footnote" role="note">
          * 시나리오 설정값 · 실제 관측값과 구분
        </p>
      )}
      {mapped.error && <p role="alert">매핑 조회 실패 · {mapped.error}</p>}
    </section>
  );
}
