/** UI-only numeric/status formatting; never substitutes missing observations with zero. */
export type ExternalMeasurement = {
  status?: unknown;
  value?: unknown;
  source?: unknown;
  observed_at?: unknown;
};

export function externalMetric(item: ExternalMeasurement | null | undefined, unit = "", example?: number) {
  const raw = item?.value;
  const numeric = typeof raw === "number" ||
    (typeof raw === "string" && /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(raw.trim()));
  const value = numeric ? Number(raw) : NaN;
  if (item?.status === "OK" && Number.isFinite(value) && value >= 0) {
    return { text: String(value), unit, simulated: false, numeric: true };
  }
  if (typeof example === "number" && Number.isFinite(example) && example >= 0) {
    return { text: `${example}*`, unit, simulated: true, numeric: true };
  }
  const statuses: Record<string, string> = {
    STALE: "기간 경과", TIMEOUT: "조회 지연", ERROR: "조회 실패",
    INVALID: "확인 필요", NO_MAPPING: "미수집", NO_DATA: "미수집",
  };
  return { text: statuses[String(item?.status)] ?? "미수집", unit: "", simulated: false, numeric: false };
}

export function externalMetricText(item: ExternalMeasurement | null | undefined, unit = "") {
  const display = externalMetric(item, unit);
  return display.text + (display.unit ? ` ${display.unit}` : "");
}

/** UI-only translation of automatic CCTV mapping cache state. No inference about safety. */
export function mappingStatus(code: string | undefined): string {
  const labels: Record<string, string> = {
    GRID_READY: "CCTV 좌표 격자 연결 준비",
    DEMO_SIMULATION: "DEMO 데이터",
    VERIFIED_EXACT_COLOCATION: "공식 관측소 일치 · 매핑 확인",
    NEARBY_STATION_WITH_THRESHOLDS: "반경 관측소 · 기준값 확인",
    NEARBY_STATION_NO_THRESHOLDS: "인근 관측소 후보 연결 · 기준값 확인 필요",
    NEEDS_ROAD_DIRECTION_VERIFICATION: "도로 촬영 방향 검증 필요",
    RADIUS_MAPPING_NOT_PREPARED: "수위 관측소 매핑 미준비",
    NO_MAPPING: "매핑 대상 미확정",
    CACHE_NOT_READY: "자동 매핑 캐시 없음 · 활성화/Worker 확인",
    CACHE_UNAVAILABLE: "매핑 캐시 조회 실패 · Redis 확인",
    AUTO_MAPPING_DISABLED: "자동 매핑 설정 꺼짐",
  };
  return code ? (labels[code] ?? "매핑 결과 확인 필요") : "매핑 상태 미확인";
}

