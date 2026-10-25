/** 저장된 분석 스냅샷의 관측값·상태만 기존 외부 상황 카드에 표시합니다. 미확인은 0으로 바꾸지 않습니다. */
import { contextStatus } from "../incidentLabel";
import { formatSeoulTime, type IncidentDetailDto } from "../incidentData";

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
export function IncidentContext({ incident }: { incident: IncidentDetailDto }) {
  const snapshot = record(incident.risk_breakdown_json?.context_snapshot);
  const measurements = record(snapshot.measurements);
  const metric = (key: string) => {
    const item = record(measurements[key]);
    return item.status === "OK" &&
      ["number", "string", "boolean"].includes(typeof item.value)
      ? String(item.value)
      : contextStatus(item.status);
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
        저장된 수집 상태를 표시합니다. 미수집은 안전 또는 정상 판정을 의미하지 않습니다.
      </p>
    </section>
  );
}
