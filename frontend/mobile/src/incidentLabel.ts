/** WEB incidentLabel.ts와 같은 표시 규칙만 적용합니다. DB 원본번호/API ID는 변경하지 않습니다. */
import type { IncidentDto } from "@octv/shared";

type IncidentIdentity = Pick<IncidentDto, "id" | "priority" | "hazard_type">;
const typeCodes: Record<string, string> = {
  flood: "flood",
  fallen_tree: "tree",
  severe_road_damage: "damage",
  road_obstacle: "obstacle",
};

export function incidentDisplayNo(incident: IncidentIdentity): string {
  const type = typeCodes[incident.hazard_type] || incident.hazard_type;
  return `OCTV_${incident.priority || "대기"}_${String(incident.id).padStart(2, "0")}_${type}`;
}

const incidentStatus: Record<IncidentDto["status"], string> = {
  DETECTED: "탐지됨",
  CONFIRMED: "사건 확인",
  SENT: "기관 전달",
  RESOLVED: "종료",
  FALSE_POSITIVE: "오탐",
};
export function incidentStatusLabel(value: IncidentDto["status"]): string {
  return incidentStatus[value] ?? value;
}
export function agencyDeliveryStatusLabel(value: string | null): string {
  return ({ RECOMMENDED: "추천", DELIVERED: "전달 완료", COMPLETED: "대응 완료" } as Record<string,string>)[value ?? ""] ?? "확인 필요";
}
