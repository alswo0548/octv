/** Browser-only visual tracking between real, sampled YOLO anchors.
 * Never feeds incidents or decisions. No video seeking or playback-rate changes.
 * Only replay frames from the SAME browser playback loop; hide unverified tracks.
 */
import type { LiveBox, LiveFrame } from "./liveBboxTiming";

export type GraySnapshot = {
  time: number;
  loop: number;
  width: number;
  height: number;
  pixels: Uint8Array;
};

export type VisualTrack = {
  boxes: LiveBox[];
  kind: "yolo" | "visual-track";
  anchorTime: number;
};

export const SNAPSHOT_INTERVAL_MS = 125;
export const SNAPSHOT_HISTORY_SEC = 4.5;
export const MAX_TRACK_SEC = 3.35;
const ANCHOR_TOLERANCE_SEC = 0.095;

export function grayscale(data: Uint8ClampedArray): Uint8Array {
  const result = new Uint8Array(data.length / 4);
  for (let i = 0, j = 0; i < data.length; i += 4, j++) {
    result[j] = (data[i] * 77 + data[i + 1] * 150 + data[i + 2] * 29) >> 8;
  }
  return result;
}

/** Follow one visible, textured region using bounded block matching (not AI detection). */
export function moveBox(
  from: GraySnapshot,
  to: GraySnapshot,
  box: readonly [number, number, number, number],
): [number, number, number, number] | null {
  if (from.width !== to.width || from.height !== to.height || from.loop !== to.loop)
    return null;
  const w = box[2] - box[0];
  const h = box[3] - box[1];
  if (w < 7 || h < 7 || !box.every(Number.isFinite)) return null;

  // The inner grid avoids unstable polygon boundaries and large pixel copies.
  const points: number[] = [];
  for (let yy = 0; yy < 9; yy++) {
    for (let xx = 0; xx < 9; xx++) {
      const x = Math.round(box[0] + w * (0.2 + (xx / 8) * 0.6));
      const y = Math.round(box[1] + h * (0.2 + (yy / 8) * 0.6));
      if (x < 6 || x >= from.width - 6 || y < 6 || y >= from.height - 6)
        return null;
      points.push(y * from.width + x);
    }
  }
  let sum = 0;
  let square = 0;
  for (const p of points) {
    const v = from.pixels[p];
    sum += v;
    square += v * v;
  }
  const variance = square / points.length - (sum / points.length) ** 2;
  // Flat water or darkness cannot be tracked reliably: hide rather than guess.
  if (variance < 35) return null;

  let best = Infinity;
  let bestDx = 0;
  let bestDy = 0;
  for (let dy = -5; dy <= 5; dy++) {
    for (let dx = -5; dx <= 5; dx++) {
      let diff = 0;
      for (const p of points) {
        diff += Math.abs(from.pixels[p] - to.pixels[p + dy * from.width + dx]);
      }
      const cost = diff / points.length + 0.18 * (Math.abs(dx) + Math.abs(dy));
      if (cost < best) {
        best = cost;
        bestDx = dx;
        bestDy = dy;
      }
    }
  }
  // Occlusion, major scene change or wrong temporal association.
  if (best > 24) return null;
  if (
    box[0] + bestDx < 0 || box[1] + bestDy < 0 ||
    box[2] + bestDx > from.width || box[3] + bestDy > from.height
  ) return null;
  return [box[0] + bestDx, box[1] + bestDy, box[2] + bestDx, box[3] + bestDy];
}

/** Reconcile delayed YOLO metadata with past browser frames, then track forward.
 * A mismatch, gap, expired anchor or low-texture scene displays NO box.
 */
export function reconcileVisualTrack(
  anchor: LiveFrame,
  snapshots: readonly GraySnapshot[],
  videoTime: number,
  elapsedSinceFetchSec: number,
): VisualTrack | null {
  if (
    !Number.isFinite(videoTime) || !Number.isFinite(elapsedSinceFetchSec) ||
    elapsedSinceFetchSec < 0 || !Number.isFinite(anchor.t) ||
    !Number.isFinite(anchor.age_sec) || anchor.age_sec < 0 ||
    anchor.age_sec + elapsedSinceFetchSec > 3.6 ||
    !Number.isFinite(anchor.width) || anchor.width <= 0 ||
    !Number.isFinite(anchor.height) || anchor.height <= 0 ||
    !Array.isArray(anchor.boxes) || anchor.boxes.length === 0 ||
    videoTime < anchor.t || videoTime - anchor.t > MAX_TRACK_SEC ||
    snapshots.length === 0
  ) return null;

  const latest = snapshots[snapshots.length - 1];
  if (Math.abs(latest.time - videoTime) > 0.18) return null;
  let start = -1;
  let error = ANCHOR_TOLERANCE_SEC;
  for (let i = 0; i < snapshots.length; i++) {
    const item = snapshots[i];
    const diff = Math.abs(item.time - anchor.t);
    if (item.loop === latest.loop && diff <= error) {
      start = i;
      error = diff;
    }
  }
  if (start < 0) return null;
  const seed = snapshots[start];
  const scaleX = seed.width / anchor.width;
  const scaleY = seed.height / anchor.height;
  let positions = anchor.boxes.slice(0, 30).map((b) => ({
    ...b,
    bbox: [b.bbox[0] * scaleX, b.bbox[1] * scaleY,
      b.bbox[2] * scaleX, b.bbox[3] * scaleY] as [number, number, number, number],
  })).filter((b) => b.bbox.every(Number.isFinite));
  if (!positions.length) return null;

  for (let i = start + 1; i < snapshots.length; i++) {
    const before = snapshots[i - 1];
    const after = snapshots[i];
    if (
      after.loop !== before.loop || after.time < before.time ||
      after.time - before.time > 0.3 || after.time - anchor.t > MAX_TRACK_SEC
    ) return null;
    positions = positions.flatMap((b) => {
      const next = moveBox(before, after, b.bbox);
      return next ? [{ ...b, bbox: next }] : [];
    });
    if (!positions.length) return null;
  }
  return {
    boxes: positions.map((b) => ({
      ...b,
      bbox: [b.bbox[0] / scaleX, b.bbox[1] / scaleY,
        b.bbox[2] / scaleX, b.bbox[3] / scaleY] as [number, number, number, number],
    })),
    kind: videoTime - anchor.t <= 0.12 ? "yolo" : "visual-track",
    anchorTime: anchor.t,
  };
}
