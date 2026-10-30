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
