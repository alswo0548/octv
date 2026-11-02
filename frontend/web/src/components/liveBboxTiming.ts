export type LiveBox = {
  bbox: [number, number, number, number];
  confidence: number;
  hazard_type: string;
};
export type LiveFrame = {
  t: number;
  age_sec: number;
  width: number;
  height: number;
  source_epoch: string;
  boxes: LiveBox[];
};
export function selectLiveFrame(
  frames: LiveFrame[],
  time: number,
  elapsed: number,
): LiveFrame | null {
  if (!Number.isFinite(time) || !Number.isFinite(elapsed) || elapsed < 0)
    return null;
  const valid = frames.filter(
    (f) =>
      Number.isFinite(f.t) &&
      f.t >= 0 &&
      Number.isFinite(f.age_sec) &&
      f.age_sec >= 0 &&
      f.age_sec + elapsed <= 3 &&
      Number.isFinite(f.width) &&
      Number.isFinite(f.height) &&
      f.width > 0 &&
      f.height > 0 &&
      Array.isArray(f.boxes) &&
      f.t <= time &&
      time - f.t <= 0.35,
  );
  return valid.sort((a, b) => b.t - a.t)[0] ?? null;
}
