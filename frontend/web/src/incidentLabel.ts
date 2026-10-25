/** 표시 전용. DB ID/UUID 및 API 요청에는 사용하지 않습니다. */
export function incidentLabel(item: { id: number; priority?: string | null; hazard_type: string }) {
  const types: Record<string, string> = { flood: "flood", fallen_tree: "tree", severe_road_damage: "damage", road_obstacle: "obstacle" };
  return `OCTV_${item.priority || "대기"}_${String(item.id).padStart(2, "0")}_${types[item.hazard_type] || item.hazard_type}`;
}
export function contextStatus(status: unknown): string {
  const labels: Record<string, string> = { OK: "수집 완료", NO_DATA: "데이터 미수집", INVALID: "응답값 검증 실패", STALE: "관측값 유효시간 경과", ERROR: "API 연동 실패", FAILED: "API 연동 실패", TIMEOUT: "API 응답 지연", UNAVAILABLE: "조회 불가", MISSING: "데이터 미수집", UNKNOWN: "데이터 미수집", NOT_CONFIGURED: "연동 설정 필요", NOT_APPLICABLE: "해당 위치 연결 대상 없음", PENDING: "분석 대기" };
  return labels[String(status)] ?? "데이터 미수집 · 상세 확인 필요";
}
