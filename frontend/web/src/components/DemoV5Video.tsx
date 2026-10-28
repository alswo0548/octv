/** Demo MP4 is *synchronized replay*, not a real live camera feed.
 * The same scenario KST start time is used by the 3-up wall and detail view.
 * No YOLO/Incident values are simulated in the browser.
 */
import { useEffect, useRef, useState } from "react";
import { N001BboxOverlay, type N001OverlayData } from "./N001BboxOverlay";
import type { Preview } from "./InferencePreview";
import { hazardLabel } from "@octv/shared";
import { formatSeoulTime, requestWebApi, loadDemoVideoUrl, type WebIncidentSession } from "../incidentData";
import { operationsError, type Cctv } from "../operationsData";

export function DemoV5Video({ session, camera, startedAt, compact = false }: {
  session: WebIncidentSession;
  camera: Cctv;
  startedAt: string | null;
  compact?: boolean;
}) {
  const [attempt, setAttempt] = useState(0);
  const n001 = camera.provider.trim().toUpperCase() === "DEMO" && camera.external_cctv_id === "DEMO-N001";
  const [overlay, setOverlay] = useState<N001OverlayData | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // This mode shows the exact frame analyzed by the running YOLO worker.
  // It never places current detections over a different MP4 playback frame.
  // Start every DEMO in synchronized video mode; YOLO preview remains opt-in.
  const [showLiveInference, setShowLiveInference] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Reset the default only when the scenario or selected camera changes.
  // Manual video/inference switching remains available during one session.
  useEffect(() => {
    setShowLiveInference(false);
  }, [camera.id, camera.is_monitored, startedAt]);

  useEffect(() => {
    let disposed = false;
    let objectUrl: string | null = null;
    const controller = new AbortController();
    setUrl(null);
    setError(null);
    if (!camera.is_monitored || !startedAt) return;
    // Use the existing authorized, browser-compatible MP4 variant (H.264)
    // instead of streaming the large original source with a short-lived ticket.
    // No DEMO video, YOLO input, incident or backend API behavior is changed.
    void loadDemoVideoUrl(session.version, camera.id, controller.signal, true)
      .then((videoUrl) => {
        if (disposed) {
          URL.revokeObjectURL(videoUrl);
          return;
        }
        objectUrl = videoUrl;
        setUrl(videoUrl);
      })
      .catch((reason) => {
        if (!disposed) setError(operationsError(reason));
      });
    return () => {
      disposed = true;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [session.version, camera.id, camera.is_monitored, startedAt, attempt]);

  // Only N001 uses offline inference metadata aligned to ORIGINAL MP4 time.
  // Failure or missing data falls back to the unmodified video player.
  useEffect(() => {
    let disposed = false;
    setOverlay(null);
    if (!n001 || !camera.is_monitored || !startedAt) return;
    void requestWebApi<N001OverlayData>(session.version, `/api/demo/v5/n001-overlay/${camera.id}`)
      .then(data => { if (!disposed && data.ready) setOverlay(data); })
      .catch(() => { /* N001 overlay is optional; never prevent video playback */ });
    return () => { disposed = true; };
  }, [n001, camera.id, camera.is_monitored, startedAt, session.version, attempt]);

  // Poll only for the selected DEMO camera while the real-inference view is
  // visible. Existing JWT/session cancellation and read-only API are reused.
  useEffect(() => {
    setPreview(null);
    setPreviewError(false);
    if (compact || !showLiveInference || !camera.is_monitored || !startedAt) return;

    let disposed = false;
    let inFlight = false;
    let currentController: AbortController | null = null;
    const update = async () => {
      if (disposed || document.hidden || inFlight) return;
      inFlight = true;
      const controller = new AbortController();
      currentController = controller;
      try {
        const data = await requestWebApi<Preview>(
          session.version,
          `/api/demo/v5/preview/${camera.id}`,
          { signal: controller.signal },
        );
        if (!disposed) {
          setPreview(data);
          setPreviewError(false);
        }
      } catch {
        if (!disposed && !controller.signal.aborted) {
          setPreview(null);
          setPreviewError(true);
        }
      } finally {
        inFlight = false;
      }
    };
    void update();
    const timer = window.setInterval(() => { void update(); }, 1500);
    const onVisible = () => { if (!document.hidden) void update(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      disposed = true;
      currentController?.abort();
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [compact, showLiveInference, session.version, camera.id, camera.is_monitored, startedAt]);

  const liveFrame = showLiveInference && preview?.state === "READY" ? preview.frame : null;

  // A newly opened camera jumps to the *current* scenario position instead
  // of starting the prerecorded file at 00:00.
  useEffect(() => {
    const video = videoRef.current;
    if (!url || !startedAt || !video) return;
    const startMs = Date.parse(startedAt);
    if (!Number.isFinite(startMs)) return;

    function synchronize() {
      if (!video) return;
      const duration = video.duration;
      if (!Number.isFinite(duration) || duration <= 0) return;
      const elapsed = Math.max(0, (Date.now() - startMs) / 1000);
      const target = elapsed % duration;
      // Wrapped time is circular; avoid unneeded seeks near the loop boundary.
      const delta = Math.abs(video.currentTime - target);
      if (Math.min(delta, duration - delta) > 1.2) {
        video.currentTime = target;
      }
      if (video.paused && !document.hidden) {
        void video.play().catch(() => { /* muted autoplay may be restricted */ });
      }
    }
    const onVisible = () => { if (!document.hidden) synchronize(); };
    video.addEventListener("loadedmetadata", synchronize);
    video.addEventListener("canplay", synchronize);
    document.addEventListener("visibilitychange", onVisible);
    const interval = window.setInterval(synchronize, 2500);
    synchronize();
    return () => {
      video.removeEventListener("loadedmetadata", synchronize);
      video.removeEventListener("canplay", synchronize);
      document.removeEventListener("visibilitychange", onVisible);
      window.clearInterval(interval);
    };
  }, [url, startedAt]);

  return (
    <div>
      {!compact && (
        <div className="action-row" role="group" aria-label="시연 CCTV 화면 모드">
          <button type="button" className={!showLiveInference ? "primary" : "secondary"}
            aria-pressed={!showLiveInference} onClick={() => setShowLiveInference(false)}>
            동기화 영상
          </button>
          <button type="button" className={showLiveInference ? "primary" : "secondary"}
            aria-pressed={showLiveInference} disabled={!camera.is_monitored || !startedAt}
            onClick={() => setShowLiveInference(true)}>
            실제 YOLO 추론 화면
          </button>
        </div>
      )}
      <div className="camera live-camera" style={compact ? { minHeight: 0, aspectRatio: "16 / 9" } : undefined}>
        {url && startedAt ? (
          <video ref={videoRef} src={url} autoPlay muted playsInline loop preload="metadata"
            // Do not expose independent seek UI: timeline is shared across cameras.
            controls={false}
            style={{ display: showLiveInference ? "none" : "block", width: "100%", height: "100%", objectFit: "contain" }}
            aria-label={`${camera.name} 시연 동기화 영상`}
            onError={() => setError("Demo 영상 재생 오류 · API/영상 파일을 확인해주세요.")} />
        ) : (
          <p>{camera.is_monitored
            ? "시연 영상 공통 시작 시각·재생 주소 확인 중"
            : "시연 시작 전 · 영상 대기"}</p>
        )}
        {!showLiveInference && n001 && url && startedAt && overlay?.ready && (
          <N001BboxOverlay videoRef={videoRef} data={overlay} />
        )}
        {showLiveInference && (liveFrame ? (
          <svg viewBox={`0 0 ${liveFrame.width} ${liveFrame.height}`}
            preserveAspectRatio="xMidYMid meet" role="img"
            aria-label={`${camera.external_cctv_id} 실제 YOLO 분석 프레임과 탐지 결과`}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
            <image href={`data:image/jpeg;base64,${liveFrame.image}`}
              width={liveFrame.width} height={liveFrame.height} />
            {liveFrame.detections.map((d, i) => (
              <g key={i}>
                <rect x={d.bbox[0]} y={d.bbox[1]}
                  width={Math.max(0, d.bbox[2] - d.bbox[0])}
                  height={Math.max(0, d.bbox[3] - d.bbox[1])}
                  fill="none" stroke="#42e8ed" strokeWidth={3} />
                <text x={d.bbox[0] + 4} y={Math.max(22, d.bbox[1] - 8)}
                  fill="#dffeff" stroke="#071a29" strokeWidth={4}
                  paintOrder="stroke" fontSize={Math.max(16, liveFrame.width / 60)}
                  fontWeight="700">
                  {hazardLabel(d.hazard_type)} {(d.confidence * 100).toFixed(1)}%
                </text>
              </g>
            ))}
          </svg>
        ) : (
          <p role="status" style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", padding: 16 }}>
            {previewError ? "실제 YOLO 프레임 조회 실패 · API 상태를 확인해주세요."
              : preview?.state === "OFF" ? "CCTV 감시 OFF"
              : "최근 YOLO 분석 프레임 대기 중"}
          </p>
        ))}
        <div className="camera-overlay-label">
          DEMO · {camera.external_cctv_id}
          {showLiveInference ? " · 실제 YOLO 추론" : n001 && overlay?.ready ? " · 사전 YOLO 시각화" : " · 원본 영상"}
        </div>
      </div>
      {!showLiveInference && error && <p role="alert">{error}</p>}
      {!compact && (
        <>
          {showLiveInference ? (
            <p>
              {liveFrame ? `${formatSeoulTime(liveFrame.captured_at)} · 실제 분석 프레임 · 탐지 ${liveFrame.detections.length}개`
                : "현재 분석 프레임을 기다리고 있습니다."}
              {" · "}추론 프레임 갱신 표시이며 원본 영상과 동기화된 연속 영상이 아닙니다.
            </p>
          ) : (
            <p>시연 시작 시점에 맞춘 동기화 재생입니다. N001 박스는 사전 분석 시각화이며, 실제 YOLO·사건 생성은 별도로 수행합니다.</p>
          )}
          <button className="secondary" type="button" disabled={!camera.is_monitored}
            onClick={() => setAttempt((value) => value + 1)}>영상 재연결</button>
        </>
      )}
    </div>
  );
}
