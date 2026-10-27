/** Exact-video-timeline visualization for approved DEMO-N001 only.
 * Rectangles were inferred once from N001_demo.mp4; the browser aligns them to
 * this <video>'s currentTime. They never drive incidents/risks/notifications.
 */
import { useEffect, useState, type RefObject } from "react";

export type N001Box = { bbox: [number, number, number, number]; confidence: number };
export type N001OverlayFrame = { t: number; boxes: N001Box[] };
export type N001OverlayData = {
  ready: boolean;
  width?: number;
  height?: number;
  duration_sec?: number;
  frames?: N001OverlayFrame[];
};

type DrawBox = { bbox: number[]; confidence: number; opacity: number };

function overlap(a: number[], b: number[]) {
  const area = (r: number[]) => Math.max(0, r[2] - r[0]) * Math.max(0, r[3] - r[1]);
  const intersection = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) *
    Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  return intersection / Math.max(1, area(a) + area(b) - intersection);
}

function boxesAt(frames: N001OverlayFrame[], time: number): DrawBox[] {
  if (!frames.length || time < 0 || !Number.isFinite(time)) return [];
  // Binary search: frame <= current video playback position.
  let lo = 0;
  let hi = frames.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (frames[mid].t <= time) lo = mid + 1;
    else hi = mid;
  }
  const index = lo - 1;
  if (index < 0 || time - frames[index].t > 0.8) return [];
  const current = frames[index];
  const next = frames[index + 1];
  const span = next?.t - current.t;
  const ratio = next && span > 0 && span < 1 ? Math.max(0, Math.min(1, (time - current.t) / span)) : 0;
  return current.boxes.map(box => {
    const matching = next?.boxes
      .map(candidate => ({ candidate, score: overlap(box.bbox, candidate.bbox) }))
      .sort((a, b) => b.score - a.score)[0];
    if (matching && matching.score >= 0.15) {
      return {
        bbox: box.bbox.map((v, i) => v + (matching.candidate.bbox[i] - v) * ratio),
        confidence: box.confidence + (matching.candidate.confidence - box.confidence) * ratio,
        opacity: 1,
      };
    }
    // Stop showing an unmatched/expired prediction; never invent a new box.
    return { bbox: [...box.bbox], confidence: box.confidence, opacity: next ? 1 - ratio : 1 };
  });
}

export function N001BboxOverlay({ videoRef, data }: {
  videoRef: RefObject<HTMLVideoElement | null>;
  data: N001OverlayData;
}) {
  const [boxes, setBoxes] = useState<DrawBox[]>([]);
  useEffect(() => {
    const video = videoRef.current;
    const frames = data.frames;
    if (!video || !frames?.length) return;
    let animation = 0;
    let last = 0;
    const draw = (now: number) => {
      if (now - last >= 48) {
        last = now;
        const visible = !video.paused && !video.seeking && !document.hidden && video.readyState >= 2;
        setBoxes(visible ? boxesAt(frames, video.currentTime) : []);
      }
      animation = window.requestAnimationFrame(draw);
    };
    animation = window.requestAnimationFrame(draw);
    return () => { window.cancelAnimationFrame(animation); };
  }, [videoRef, data]);

  const width = data.width ?? 0;
  const height = data.height ?? 0;
  if (!width || !height || !data.frames?.length) return null;

  return (
    <svg aria-label="N001 원본 MP4와 동기화된 사전 YOLO 침수 탐지 표시"
      viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 1 }}>
      {boxes.filter(({ bbox, opacity }) => opacity > 0.05 && bbox[2] > bbox[0] && bbox[3] > bbox[1]).map(({ bbox, confidence, opacity }, i) => (
        <g key={i} opacity={opacity}>
          <rect x={bbox[0]} y={bbox[1]} width={bbox[2] - bbox[0]} height={bbox[3] - bbox[1]}
            fill="none" stroke="#041521" strokeWidth="5" />
          <rect x={bbox[0]} y={bbox[1]} width={bbox[2] - bbox[0]} height={bbox[3] - bbox[1]}
            fill="none" stroke="#42e8ed" strokeWidth="2.8" />
          <rect x={bbox[0]} y={Math.max(0, bbox[1] - 27)} width="123" height="26"
            rx="3" fill="#071a29" fillOpacity="0.87" />
          <text x={bbox[0] + 5} y={Math.max(19, bbox[1] - 8)}
            fill="#dffeff" fontSize="16" fontWeight="700">{`침수 ${(confidence * 100).toFixed(1)}%`}</text>
        </g>
      ))}
    </svg>
  );
}
