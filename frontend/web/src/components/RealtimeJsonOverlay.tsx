/** Lightweight overlay for real-time YOLO JSON. No video frame readback,
 * no browser-side detector, no tracking, and no playback-rate/seeking changes.
 * Every box was inferred from an actual MP4 frame by the independent YOLO worker.
 */
import { useEffect, useRef, useState, type RefObject } from "react";
import type { LiveFrame } from "./liveBboxTiming";

type Picked = { frame: LiveFrame; timeDifference: number };

function pick(frames: LiveFrame[], videoTime: number): Picked | null {
  if (!Number.isFinite(videoTime)) return null;
  const eligible = frames.filter((frame) =>
    Number.isFinite(frame.t) &&
    Number.isFinite(frame.age_sec) && frame.age_sec >= 0 &&
    Number.isFinite(frame.width) && frame.width > 0 &&
    Number.isFinite(frame.height) && frame.height > 0 &&
    Array.isArray(frame.boxes) &&
    videoTime - frame.t >= -0.10 &&
    videoTime - frame.t <= 1.35 &&
    frame.age_sec <= 2.5,
  ).sort((a, b) => b.t - a.t);
  const recent = eligible[0];
  if (!recent || recent.boxes.length === 0) return null;
  return { frame: recent, timeDifference: Math.max(0, videoTime - recent.t) };
}

export function RealtimeJsonOverlay({
  videoRef, apiBase,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  apiBase: string;
}) {
  const [selected, setSelected] = useState<Picked | null>(null);
  const framesRef = useRef<LiveFrame[]>([]);
  const receivedRef = useRef(0);
  useEffect(() => {
    let disposed = false;
    let polling = 0;
    const video = videoRef.current;
    if (!video) return;
    const clear = () => {
      framesRef.current = [];
      receivedRef.current = 0;
      setSelected(null);
    };
    async function poll() {
      if (disposed) return;
      if (document.hidden || video!.paused || video!.seeking || video!.readyState < 2) {
        clear();
      } else {
        try {
          const stamp = video!.currentTime;
          const response = await fetch(
            `${apiBase}/api/demo/v5/live-boxes/4?video_time=${encodeURIComponent(stamp.toFixed(3))}`,
            { cache: "no-store" },
          );
          if (!response.ok) throw new Error("YOLO JSON network error");
          const data = await response.json() as { enabled: boolean; frames: LiveFrame[] };
          if (!disposed) {
            framesRef.current = data.enabled && Array.isArray(data.frames) ? data.frames : [];
            receivedRef.current = performance.now();
          }
        } catch {
          if (!disposed) clear();
        }
      }
      if (!disposed) polling = window.setTimeout(() => void poll(), 500);
    }
    let lastVideoTime = video.currentTime;
    const display = window.setInterval(() => {
      if (disposed || document.hidden || video.paused || video.seeking ||
          video.readyState < 2 || !receivedRef.current ||
          performance.now() - receivedRef.current > 1900) {
        setSelected(null);
        return;
      }
      const time = video.currentTime;
      if (time < lastVideoTime - 0.2) {
        clear(); // MP4 loop / seek: no stale boxes from the previous loop.
      }
      lastVideoTime = time;
      setSelected(pick(framesRef.current, time));
    }, 100);
    const onReset = () => {
      lastVideoTime = -1;
      clear();
    };
    video.addEventListener("seeking", onReset);
    video.addEventListener("waiting", onReset);
    video.addEventListener("emptied", onReset);
    void poll();
    return () => {
      disposed = true;
      clearTimeout(polling);
      clearInterval(display);
      video.removeEventListener("seeking", onReset);
      video.removeEventListener("waiting", onReset);
      video.removeEventListener("emptied", onReset);
    };
  }, [apiBase, videoRef]);

  const frame = selected?.frame;
  return (
    <svg
      aria-label="실시간 YOLO JSON 기반 바운딩박스. 기존 영상 속도는 변경하지 않음"
      viewBox={frame ? `0 0 ${frame.width} ${frame.height}` : "0 0 16 9"}
      preserveAspectRatio="xMidYMid meet"
      style={{
        position: "absolute", inset: 0, width: "100%", height: "100%",
        pointerEvents: "none", zIndex: 1, overflow: "visible",
      }}
    >
      {frame?.boxes.slice(0, 25).map((box, i) => {
        const [x1, y1, x2, y2] = box.bbox;
        if (![x1, y1, x2, y2].every(Number.isFinite) ||
            x1 < 0 || y1 < 0 || x2 > frame.width ||
            y2 > frame.height || x2 <= x1 || y2 <= y1) return null;
        const label = `${box.hazard_type} ${(box.confidence * 100).toFixed(1)}%`;
        return (
          <g key={i}>
            <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1}
              fill="none" stroke="#031623" strokeWidth="5" />
            <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1}
              fill="none" stroke="#42e8ed" strokeWidth="2.5" />
            <rect x={x1} y={Math.max(0, y1 - 24)}
              width={Math.min(frame.width - x1, Math.max(115, label.length * 9))}
              height="24" rx="3" fill="#071a29" fillOpacity=".9" />
            <text x={x1 + 5} y={Math.max(17, y1 - 7)}
              fill="#dffeff" fontSize="14" fontWeight="700">{label}</text>
          </g>
        );
      })}
    </svg>
  );
}
