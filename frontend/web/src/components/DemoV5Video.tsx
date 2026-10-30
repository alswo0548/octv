/** Demo MP4 is *synchronized replay*, not a real live camera feed.
 * The same scenario KST start time is used by the 3-up wall and detail view.
 * No YOLO/Incident values are simulated in the browser.
 */
import { useEffect, useRef, useState } from "react";
import { N001BboxOverlay, type N001OverlayData } from "./N001BboxOverlay";
import type { Preview } from "./InferencePreview";
import { hazardLabel } from "@octv/shared";
import { formatSeoulTime, requestWebApi, type WebIncidentSession } from "../incidentData";
import { operationsError, type Cctv } from "../operationsData";

type PlaybackInfo = { url: string; expires_in: number };

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
  const [isPlaying, setIsPlaying] = useState(false);
  const [syncWarning, setSyncWarning] = useState<string | null>(null);
  // Exact YOLO inference frames are shown in a small, clearly labeled inset.
  // They must never be overlaid on a different, independently playing MP4 frame.
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let disposed = false;
    setUrl(null);
    setError(null);
    setIsPlaying(false);
    setSyncWarning(null);
    if (!camera.is_monitored || !startedAt) return;
    // A JWT-authenticated ticket grants native HTTP Range streaming of the
    // mobile-compatible MP4. Avoid waiting for a full fetch()/blob() download
    // before displaying the video, especially over distant connections.
    void requestWebApi<PlaybackInfo>(
      session.version,
      `/api/demo/v5/playback/${camera.id}?mobile_compatible=true`,
      { method: "POST" },
    )
      .then(({ url: playbackUrl }) => {
        if (!playbackUrl.startsWith(`/api/demo/v5/watch/${camera.id}?token=`)) {
          throw new Error("시연 영상 주소 형식을 확인할 수 없습니다.");
        }
        if (!disposed) setUrl(playbackUrl);
      })
      .catch((reason) => {
        if (!disposed) setError(operationsError(reason));
      });
    return () => { disposed = true; };
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

  // Only the full-size N001 player polls its existing, read-only preview API.
  // This adds no detector inference and never affects incident creation.
  useEffect(() => {
    setPreview(null);
    setPreviewError(false);
    if (compact || !n001 || !camera.is_monitored || !startedAt) return;

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
  }, [compact, n001, session.version, camera.id, camera.is_monitored, startedAt]);

  const recentFrame = preview?.state === "READY" ? preview.frame : null;
  // Do not retain a stale detection or imply a continuous live video feed.
  const liveFrame = recentFrame && Number.isFinite(Date.parse(recentFrame.captured_at))
    && Math.abs(Date.now() - Date.parse(recentFrame.captured_at)) <= 15_000
    ? recentFrame : null;

  // Synchronize once after the browser can actually play decoded frames.
  // Repeated seeking every 2.5s while buffering generated overlapping Range
  // requests and prevented slow-network playback from ever becoming ready.
  useEffect(() => {
    const video = videoRef.current;
    if (!url || !startedAt || !video) return;
    const startMs = Date.parse(startedAt);
    if (!Number.isFinite(startMs)) return;

    let synced = false;
    let initialSeekAt = 0;
    let fallback = false;

    function playWhenReady() {
      if (video && !document.hidden && video.paused) {
        void video.play().catch(() => {
          // Browser autoplay restrictions are surfaced via the video error UI.
        });
      }
    }

    function synchronizeOnce() {
      if (!video || document.hidden || synced || fallback ||
          video.seeking || video.paused || video.readyState < 3) return;
      const duration = video.duration;
      if (!Number.isFinite(duration) || duration <= 0) return;
      // Allow the beginning to render before issuing one bounded timeline seek.
      synced = true;
      const elapsed = Math.max(0, (Date.now() - startMs) / 1000);
      const target = elapsed % duration;
      const delta = Math.abs(video.currentTime - target);
      if (Math.min(delta, duration - delta) > 3) {
        initialSeekAt = Date.now();
        video.currentTime = target;
      }
    }

    function onPlaying() {
      setIsPlaying(true);
      // The first frame was decoded; at most one initial seek is permitted.
      synchronizeOnce();
    }
    function onWaiting() {
      setIsPlaying(false);
    }
    function onCanPlay() {
      playWhenReady();
    }
    function onVisible() {
      if (!document.hidden) playWhenReady();
    }
    const checkBuffer = window.setInterval(() => {
      if (!video || document.hidden) return;
      // If the one initial seek stalls, show the recording from frame zero
      // rather than displaying an empty screen for the entire rehearsal.
      if (!fallback && initialSeekAt && Date.now() - initialSeekAt > 10000 &&
          (video.seeking || video.readyState < 2)) {
        fallback = true;
        setSyncWarning("재생 위치 동기화가 지연되어 영상 처음부터 재생합니다.");
        video.currentTime = 0;
        playWhenReady();
      } else if (!synced && !video.paused) {
        synchronizeOnce();
      }
    }, 2000);

    video.addEventListener("playing", onPlaying);
    video.addEventListener("waiting", onWaiting);
    video.addEventListener("canplay", onCanPlay);
    document.addEventListener("visibilitychange", onVisible);
    playWhenReady();
    return () => {
      video.removeEventListener("playing", onPlaying);
      video.removeEventListener("waiting", onWaiting);
      video.removeEventListener("canplay", onCanPlay);
      document.removeEventListener("visibilitychange", onVisible);
      window.clearInterval(checkBuffer);
    };
  }, [url, startedAt]);

  return (
    <div>
      <div className="camera live-camera" style={compact ? { minHeight: 0, aspectRatio: "16 / 9" } : undefined}>
        {url && startedAt ? (
          <video ref={videoRef} src={url} autoPlay muted playsInline loop preload="auto"
            // Do not expose independent seek UI: timeline is shared across cameras.
            controls={false}
            style={{ width: "100%", height: "100%", objectFit: "contain" }}
            aria-label={`${camera.name} 시연 동기화 영상`}
            onPlaying={() => setIsPlaying(true)}
            onWaiting={() => setIsPlaying(false)}
            onError={(event) => {
              setIsPlaying(false);
              setError(`Demo 영상 재생 오류 (미디어 코드 ${event.currentTarget.error?.code ?? "미확인"}) · 재연결을 눌러주세요.`);
            }} />
        ) : (
          <p>{camera.is_monitored
            ? "시연 영상 공통 시작 시각·재생 주소 확인 중"
            : "시연 시작 전 · 영상 대기"}</p>
        )}
        {url && !isPlaying && !error && (
          <p role="status" style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", padding: 16, pointerEvents: "none" }}>
            동기화 영상 재생 준비 중…
          </p>
        )}
        {n001 && url && startedAt && overlay?.ready && (
          <N001BboxOverlay videoRef={videoRef} data={overlay} />
        )}
        {!compact && n001 && camera.is_monitored && startedAt && (
          <aside aria-label="N001 최근 실제 YOLO 분석 프레임" style={{
            position: "absolute", right: 12, bottom: 12, zIndex: 2,
            width: "34%", minWidth: 165, maxWidth: 280,
            padding: 8, borderRadius: 8, pointerEvents: "none",
            border: "1px solid rgba(66,232,237,0.45)",
            background: "rgba(7,26,41,0.92)", color: "#dffeff",
            boxSizing: "border-box",
          }}>
            <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 5 }}>
              실제 YOLO · 최근 분석 프레임
            </div>
            {liveFrame ? (
              <>
                <svg viewBox={`0 0 ${liveFrame.width} ${liveFrame.height}`}
                  preserveAspectRatio="xMidYMid meet" role="img"
                  aria-label="실제 분석된 이미지와 그 이미지에서 검출된 객체"
                  style={{ display: "block", width: "100%", height: "auto" }}>
                  <image href={`data:image/jpeg;base64,${liveFrame.image}`}
                    width={liveFrame.width} height={liveFrame.height} />
                  {liveFrame.detections.filter(d => d.bbox.length === 4).map((d, i) => (
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
                <div style={{ fontSize: 10, marginTop: 4 }}>
                  {formatSeoulTime(liveFrame.captured_at)} · 탐지 {liveFrame.detections.length}개
                </div>
              </>
            ) : (
              <div role="status" style={{ fontSize: 11, padding: "12px 0" }}>
                {previewError ? "실제 YOLO 프레임 조회 실패"
                  : preview?.state === "OFF" ? "CCTV 감시 OFF"
                  : "최근 분석 프레임 대기 중"}
              </div>
            )}
          </aside>
        )}
        <div className="camera-overlay-label">
          DEMO · {camera.external_cctv_id}
          {n001 && overlay?.ready ? " · 사전 YOLO 박스" : " · 원본 영상"}
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
      {syncWarning && <p role="status">{syncWarning}</p>}
      {!compact && (
        <>
          {n001 ? (
            <p>메인 영상의 박스는 MP4 시점에 맞춘 사전 YOLO 결과입니다. 오른쪽 작은 화면은 실제 YOLO의 최근 분석 프레임으로, 메인 영상과 동일한 프레임은 아닙니다.</p>
          ) : (
            <p>시연 시작 시점에 맞춘 동기화 재생입니다. 실제 YOLO 분석과 사건 생성은 별도로 수행합니다.</p>
          )}
          <button className="secondary" type="button" disabled={!camera.is_monitored}
            onClick={() => setAttempt((value) => value + 1)}>영상 재연결</button>
        </>
      )}
    </div>
  );
}
