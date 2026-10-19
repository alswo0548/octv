/** 서비스 클래스의 표시명. 모델 ID나 저장된 과거 유형을 변환하지 않습니다. */
export const hazardLabels: Record<string, string> = {
  flood: "도로 침수",
  fallen_tree: "쓰러진 나무",
  severe_road_damage: "심각한 도로 파손",
  road_obstacle: "도로 장애물",
};
export function hazardLabel(value: string): string {
  return hazardLabels[value] ?? `${value} · 과거/미확인 유형`;
}
