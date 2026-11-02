/** Real sampled YOLO anchors + bounded browser-only visual tracking.
 * MP4 playback is independent. Lost/late anchors never become invented detections.
 */
import { useEffect, useRef, type RefObject } from "react";
import { requestWebApi } from "../incidentData";
import type { LiveFrame } from "./liveBboxTiming";
import {
  grayscale,
  reconcileVisualTrack,
  SNAPSHOT_HISTORY_SEC,
  SNAPSHOT_INTERVAL_MS,
  type GraySnapshot,
  type VisualTrack,
} from "./liveBboxTracking";

export function LiveBboxOverlay({
  videoRef,
  cameraId,
  sessionVersion,
  fetchFrames,
  inferVideoFrame,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  cameraId: number;
  sessionVersion: number;
  fetchFrames?: () => Promise<{ enabled: boolean; frames: LiveFrame[] }>;
  inferVideoFrame?: (blob: Blob, mediaTime: number) => Promise<{
    enabled: boolean;
    frames: LiveFrame[];
  }>;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let disposed = false;
    let timer = 0;
    let animation = 0;
    let videoFrameId = 0;
    let frames: LiveFrame[] = [];
    let receivedAt = 0;
    let frameRevision = 0;
    let metadataRevision = 0;
    let computedFrameRevision = -1;
    let computedMetadataRevision = -1;
    let visual: VisualTrack | null = null;
    let visualAnchor: LiveFrame | null = null;
    let lastDraw = 0;
    let lastCaptured = 0;
    let lastMediaTime = -1;
    let browserLoop = 0;
    let lastInfer = 0;
    let inferPending = false;
    const inferCanvas = document.createElement("canvas");
    inferCanvas.width = 640;
    inferCanvas.height = 360;
    const inferContext = inferCanvas.getContext("2d");
    const snapshots: GraySnapshot[] = [];
    const scaled = document.createElement("canvas");
    scaled.width = 256;
    scaled.height = 144;
    const captureContext = scaled.getContext("2d", { willReadFrequently: true });

    const clear = () => {
      frames = [];
      receivedAt = 0;
      metadataRevision++;
      snapshots.length = 0;
      frameRevision++;
      visual = null;
      visualAnchor = null;
    };

    // The video stays at its native FPS. Only a small 256x144 grayscale copy
    // is sampled for visualization, at <= 8Hz, with bounded memory and CPU.
    const capture = (now: number, mediaTime: number) => {
      if (inferVideoFrame) return; // Local test uses the actual displayed video frame as YOLO input.
      if (disposed || document.hidden || video.paused || video.seeking ||
          video.readyState < 2 || !captureContext ||
          !Number.isFinite(mediaTime)) return;
      if (lastMediaTime >= 0 && mediaTime < lastMediaTime - 0.15) {
        browserLoop++;
        clear(); // Never track across a seek or MP4 loop.
      }
      lastMediaTime = mediaTime;
      if (now - lastCaptured < SNAPSHOT_INTERVAL_MS) return;
      if (snapshots.length && mediaTime <= snapshots[snapshots.length - 1].time) return;
      lastCaptured = now;
      try {
        captureContext.drawImage(video, 0, 0, scaled.width, scaled.height);
        const pixels = grayscale(
          captureContext.getImageData(0, 0, scaled.width, scaled.height).data,
        );
        snapshots.push({
          time: mediaTime,
          loop: browserLoop,
          width: scaled.width,
          height: scaled.height,
          pixels,
        });
        while (snapshots.length &&
               mediaTime - snapshots[0].time > SNAPSHOT_HISTORY_SEC) {
          snapshots.shift();
        }
        frameRevision++;
      } catch {
        // Canvas/security/performance failure hides optional boxes only.
        snapshots.length = 0;
        visual = null;
      }
    };

    const onVideoFrame = (now: number, metadata: VideoFrameCallbackMetadata) => {
      capture(now, metadata.mediaTime);
      if (!disposed) videoFrameId = video.requestVideoFrameCallback(onVideoFrame);
    };
    const hasVideoFrameCallback = typeof video.requestVideoFrameCallback === "function";
    if (hasVideoFrameCallback) {
      videoFrameId = video.requestVideoFrameCallback(onVideoFrame);
    }

    const sendDisplayedFrame = (now: number) => {
      if (!inferVideoFrame || !inferContext || disposed || inferPending ||
          video.paused || video.seeking || document.hidden || video.readyState < 3 ||
          !video.videoWidth || !video.videoHeight ||
          now - lastInfer < 650) return;
      const mediaTime = video.currentTime;
      if (!Number.isFinite(mediaTime)) return;
      const sent = performance.now();
      lastInfer = now;
      inferPending = true;
      inferCanvas.height = Math.max(1, Math.round(640 * video.videoHeight / video.videoWidth));
      try {
        inferContext.drawImage(video, 0, 0, inferCanvas.width, inferCanvas.height);
        inferCanvas.toBlob((blob) => {
          if (!blob || disposed) {
            inferPending = false;
            return;
          }
          void inferVideoFrame(blob, mediaTime).then((data) => {
            if (disposed) return;
            frames = data.enabled && Array.isArray(data.frames) ? data.frames : [];
            receivedAt = sent;
            metadataRevision++;
          }).catch(() => {
            if (!disposed) clear();
          }).finally(() => {
            inferPending = false;
          });
        }, "image/jpeg", 0.78);
      } catch {
        inferPending = false;
        clear();
      }
    };

    const poll = async () => {
      // Include network latency in age; never assume a received result is new.
      const sent = performance.now();
      try {
        if (!document.hidden) {
          const data = fetchFrames
            ? await fetchFrames()
            : await requestWebApi<{
                enabled: boolean;
                frames: LiveFrame[];
              }>(sessionVersion, `/api/demo/v5/live-boxes/${cameraId}`);
          if (disposed) return;
          frames = data.enabled && Array.isArray(data.frames) ? data.frames : [];
          receivedAt = sent;
          metadataRevision++;
        } else clear();
      } catch {
        clear();
      }
      if (!disposed) timer = window.setTimeout(() => void poll(), 500);
    };

    const reset = () => {
      clear();
      lastMediaTime = -1;
      lastCaptured = 0;
      browserLoop++;
    };
    video.addEventListener("seeking", reset);
    video.addEventListener("waiting", reset);
    video.addEventListener("emptied", reset);

    const draw = (now: number) => {
      const canvas = canvasRef.current;
      if (canvas && now - lastDraw >= 50) {
        lastDraw = now;
        if (!hasVideoFrameCallback) capture(now, video.currentTime);
        sendDisplayedFrame(now);
        const w = video.clientWidth;
        const h = video.clientHeight;
        if (canvas.width !== w) canvas.width = w;
        if (canvas.height !== h) canvas.height = h;
        canvas.style.left = `${video.offsetLeft}px`;
        canvas.style.top = `${video.offsetTop}px`;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.clearRect(0, 0, w, h);
          const canShow = !video.paused && !video.seeking &&
            !document.hidden && video.readyState >= 3 &&
            receivedAt > 0 && (inferVideoFrame ? true : snapshots.length > 0);
          if (canShow && !inferVideoFrame &&
              (frameRevision !== computedFrameRevision ||
               metadataRevision !== computedMetadataRevision)) {
            computedFrameRevision = frameRevision;
            computedMetadataRevision = metadataRevision;
            visual = null;
            visualAnchor = null;
            const elapsed = (now - receivedAt) / 1000;
            // A newer YOLO "no object" supersedes an older positive result.
            const newest = [...frames]
              .filter((frame) => frame.t <= video.currentTime)
              .sort((a, b) => b.t - a.t)[0];
            if (newest) {
              visual = reconcileVisualTrack(
                newest, snapshots, video.currentTime, elapsed,
              );
              visualAnchor = visual ? newest : null;
            }
          }
          const current = canShow && visual && visualAnchor &&
            now - receivedAt <= 3600 &&
            Math.abs(snapshots[snapshots.length - 1].time - video.currentTime) <= 0.18
              ? visual : null;
          // Local browser-driven preview: only render detections from an actual
          // frame captured from this <video>. A dashed outline is the LAST
          // sampled result (<1.1s old), not a new inference or fake tracking.
          const recent = canShow && inferVideoFrame && now - receivedAt <= 1400
            ? frames.find((f) => Number.isFinite(f.t) &&
                f.t <= video.currentTime &&
                video.currentTime - f.t <= 1.1 &&
                f.boxes?.length > 0)
            : undefined;
          const source = recent ?? (current ? visualAnchor : null);
          const boxes = recent?.boxes ?? current?.boxes;
          if (source && boxes?.length) {
            const ratio = Math.min(w / source.width, h / source.height);
            const dx = (w - source.width * ratio) / 2;
            const dy = (h - source.height * ratio) / 2;
            const sampledAge = recent ? video.currentTime - recent.t : 0;
            const cached = !!recent && sampledAge > 0.12;
            const tracked = !recent && current?.kind === "visual-track";
            ctx.lineWidth = 2;
            ctx.font = "bold 13px sans-serif";
            ctx.strokeStyle = tracked ? "#ffd07b" : "#42e8ed";
            ctx.fillStyle = ctx.strokeStyle;
            ctx.setLineDash(cached ? [7, 4] : []);
            for (const box of boxes) {
              const b = box.bbox;
              if (!b.every(Number.isFinite) || b[0] < 0 || b[1] < 0 ||
                  b[2] > source.width || b[3] > source.height ||
                  b[2] <= b[0] || b[3] <= b[1]) continue;
              const x = dx + b[0] * ratio;
              const y = dy + b[1] * ratio;
              ctx.strokeRect(x, y, (b[2] - b[0]) * ratio, (b[3] - b[1]) * ratio);
              ctx.fillText(
                tracked ? `${box.hazard_type} · 화면 추적` :
                  cached ? `${box.hazard_type} · 최근 YOLO ${sampledAge.toFixed(1)}초` :
                  `${box.hazard_type} ${(box.confidence * 100).toFixed(1)}% · YOLO`,
                x, Math.max(14, y - 5),
              );
            }
            ctx.setLineDash([]);
          }
        }
      }
      if (!disposed) animation = requestAnimationFrame(draw);
    };
    if (!inferVideoFrame) void poll();
    animation = requestAnimationFrame(draw);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      cancelAnimationFrame(animation);
      if (hasVideoFrameCallback) video.cancelVideoFrameCallback(videoFrameId);
      video.removeEventListener("seeking", reset);
      video.removeEventListener("waiting", reset);
      video.removeEventListener("emptied", reset);
    };
  }, [videoRef, cameraId, sessionVersion, fetchFrames, inferVideoFrame]);
  return (
    <canvas
      ref={canvasRef}
      aria-label="실제 YOLO 탐지와 구분되는 영상 기반 추적 시각화"
      style={{ position: "absolute", pointerEvents: "none", zIndex: 1 }}
    />
  );
}
