/** 저장된 분석 스냅샷의 관측값·상태만 기존 외부 상황 카드에 표시합니다. 미확인은 0으로 바꾸지 않습니다. */
import { contextStatus } from "../incidentLabel";
import { mappingStatus } from "../externalDisplay";
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
  const metric = (key: string) => {
    const item = record(measurements[key]);
    if (item.status === "OK" &&
        ["number", "string", "boolean"].includes(typeof item.value)) {
      return String(item.value);
    }
    // Clearly labelled fallback for DEMO only; the real DB Context is intact.
    if (demo && (key === "rainfall_mm" || key === "water_level_m" ||
                 key === "blocked_lane_count")) {
      const example = demo[key];
      if (typeof example === "number" && Number.isFinite(example)) {
        return `${example} (시연용)`;
      }
    }
    return contextStatus(item.status);
  };
  return (
    <section className="panel external">
      <div className="section-title">
        <h2>외부 상황</h2>
        <span className="subtle">
          {typeof snapshot.captured_at === "string"
            ? formatSeoulTime(snapshot.captured_at)
            : "저장된 분석 시점 기준"}
        </span>
      </div>
      <div className="weather">
        <div>
          <span className="weather-icon">☂</span>
          <div>
            <label>강수량</label>
            <strong>
              {metric("rainfall_mm")}
              <small> mm</small>
            </strong>
          </div>
        </div>
        <div>
          <span className="weather-icon">≋</span>
          <div>
            <label>수위</label>
            <strong>
              {metric("water_level_m")}
              <small> m</small>
            </strong>
          </div>
        </div>
      </div>
      <div className="external-row">
        <span>차단 차로 수</span>
        <b>{metric("blocked_lane_count")}</b>
      </div>
      <div className="external-row">
        <span>인근 병원 거리</span>
        <b>{metric("nearby_hospital_distance_m")} m</b>
      </div>
      <p className="content-footnote">
        저장된 분석 시점의 수집 상태입니다. 미수집은 안전 또는 정상 판정이 아닙니다.
      </p>
      {demo && (
        <p className="content-footnote" role="note">
          🎬 시연용 자동 매핑 · 기상 격자 ({demo.weather_grid?.nx ?? "–"}, {demo.weather_grid?.ny ?? "–"})
          {" · "}가상 수위 위험등급: {demo.water_risk_level ?? "미설정"}
          {" · "}‘시연용’ 표시값은 실제 관측·도로 통제 정보가 아닙니다.
          실제 외부 데이터와 사건 분석 기록은 변경하지 않습니다.
        </p>
      )}
      {mapped.error ? <p role="alert">사건별 매핑 조회 실패 · {mapped.error}</p> : (
        <p className="content-footnote">
          자동 매핑 확인 · 기상: {mappingStatus(mapped.data?.mapping_state?.weather)} / 수위: {mappingStatus(mapped.data?.mapping_state?.water)} / 교통: {mappingStatus(mapped.data?.mapping_state?.traffic)}
          <br/>외부 API 실제 수집은 사건 분석 Worker와 별도로 검증해야 합니다.
        </p>
      )}
    </section>
  );
}
