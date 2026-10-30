/** 웹과 동일하게 서버가 저장한 사건 대표 이미지 탐지 사각형만 사용합니다. */
export type IncidentDetectionBox = { x1: number; y1: number; x2: number; y2: number };

export function readIncidentDetectionBox(value: unknown): IncidentDetectionBox | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const source = value as Record<string, unknown>;
  const x1 = Number(source.x1);
  const y1 = Number(source.y1);
  const x2 = Number(source.x2);
  const y2 = Number(source.y2);
  if (![x1, y1, x2, y2].every(Number.isFinite) || x2 <= x1 || y2 <= y1) return null;
  return { x1, y1, x2, y2 };
}
