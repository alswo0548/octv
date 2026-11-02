/** Actual sampled YOLO metadata. Missing/late results hide boxes, never seek video. */
import { useEffect, useRef, type RefObject } from "react";
import { requestWebApi } from "../incidentData";
import { selectLiveFrame, type LiveFrame } from "./liveBboxTiming";

export function LiveBboxOverlay({ videoRef, cameraId, sessionVersion }: {
  videoRef: RefObject<HTMLVideoElement | null>; cameraId: number; sessionVersion: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let disposed = false;
    let timer = 0;
    let animation = 0;
    let frames: LiveFrame[] = [];
    let received = 0;
    let lastDraw = 0;
    const clear = () => { frames = []; };
    const poll = async () => {
      const sent = performance.now();
      try {
        if (!document.hidden) {
          const data = await requestWebApi<{ enabled: boolean; frames: LiveFrame[] }>(
            sessionVersion, `/api/demo/v5/live-boxes/${cameraId}`);
          if (disposed) return;
          // Include full request latency conservatively; do not trust client wall clock.
          frames = data.enabled && Array.isArray(data.frames) ? data.frames : [];
          received = sent;
        } else clear();
      } catch { clear(); }
      if (!disposed) timer = window.setTimeout(() => { void poll(); }, 500);
    };
    const video = videoRef.current;
    video?.addEventListener("seeking", clear);
    video?.addEventListener("waiting", clear);
    video?.addEventListener("emptied", clear);
    let previousTime = -1;
    const draw = (now: number) => {
      const canvas = canvasRef.current;
      if (canvas && video && now - lastDraw >= 50) {
        lastDraw = now;
        if (video.currentTime < previousTime) clear(); // loop/seek boundary
        previousTime = video.currentTime;
        const w = video.clientWidth, h = video.clientHeight;
        if (canvas.width !== w) canvas.width = w;
        if (canvas.height !== h) canvas.height = h;
        canvas.style.left = `${video.offsetLeft}px`;
        canvas.style.top = `${video.offsetTop}px`;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.clearRect(0, 0, w, h);
          const frame = !video.paused && !video.seeking && !document.hidden && video.readyState >= 3
            ? selectLiveFrame(frames, video.currentTime, (now - received) / 1000) : null;
          if (frame) {
            const ratio = Math.min(w / frame.width, h / frame.height);
            const dx = (w - frame.width * ratio) / 2, dy = (h - frame.height * ratio) / 2;
            ctx.strokeStyle = "#42e8ed";
            ctx.fillStyle = "#42e8ed";
            ctx.lineWidth = 2;
            ctx.font = "bold 14px sans-serif";
            for (const box of frame.boxes.slice(0, 100)) {
              const b = box.bbox;
              if (!Array.isArray(b) || b.length !== 4 || !b.every(Number.isFinite) ||
                  b[0] < 0 || b[1] < 0 || b[2] > frame.width || b[3] > frame.height ||
                  b[2] <= b[0] || b[3] <= b[1] || !Number.isFinite(box.confidence)) continue;
              const x = dx + b[0] * ratio, y = dy + b[1] * ratio;
              ctx.strokeRect(x, y, (b[2] - b[0]) * ratio, (b[3] - b[1]) * ratio);
              ctx.fillText(`${box.hazard_type} ${(box.confidence * 100).toFixed(1)}%`, x, Math.max(14, y - 5));
            }
          }
        }
      }
      animation = requestAnimationFrame(draw);
    };
    void poll();
    animation = requestAnimationFrame(draw);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      cancelAnimationFrame(animation);
      video?.removeEventListener("seeking", clear);
      video?.removeEventListener("waiting", clear);
      video?.removeEventListener("emptied", clear);
    };
  }, [videoRef, cameraId, sessionVersion]);
  return <canvas ref={canvasRef} aria-label="실제 YOLO 분석 프레임과 시각이 일치할 때만 표시"
    style={{ position: "absolute", pointerEvents: "none", zIndex: 1 }} />;
}
