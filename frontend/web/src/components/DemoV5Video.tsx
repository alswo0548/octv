/** Demo MP4 is *synchronized replay*, not a real live camera feed.
 * The same scenario KST start time is used by the 3-up wall and detail view.
 * No YOLO/Incident values are simulated in the browser.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { RealtimeJsonOverlay } from "./RealtimeJsonOverlay";
import type { LiveFrame } from "./liveBboxTiming";
import { N001BboxOverlay, type N001OverlayData } from "./N001BboxOverlay";
import { requestWebApi, type WebIncidentSession } from "../incidentData";
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
  const [liveMode, setLiveMode] = useState(false);
  const [overlay, setOverlay] = useState<N001OverlayData | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [syncWarning, setSyncWarning] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Only DEMO-N001 uses the optional real-time YOLO JSON display endpoint.
  // All other camera playback and detection paths are untouched.
  const fetchN001Frames = useCallback(
    (_videoTime: number) => requestWebApi<{ enabled: boolean; frames: LiveFrame[] }>(
      session.version, `/api/demo/v5/n001-live-boxes/${camera.id}`,
    ),
    [session.version, camera.id],
  );

  const restoreN001Overlay = useCallback(() => {
    setLiveMode(false);
    void requestWebApi<N001OverlayData>(
      session.version, `/api/demo/v5/n001-overlay/${camera.id}`,
    ).then((data) => {
      if (data.ready) setOverlay(data);
    }).catch(() => {
      // Never interfere with native MP4 playback if the optional JSON fails.
    });
  }, [session.version, camera.id]);

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

  // The API opt-in flag selects live metadata; existing offline assets remain intact.
  useEffect(() => {
    let disposed = false;
    setOverlay(null);
    setLiveMode(false);
    if (!camera.is_monitored || !startedAt || !n001) return;
    void (async () => {
      let enabled = false;
      try {
        const mode = await requestWebApi<{ enabled: boolean }>(session.version,
          `/api/demo/v5/n001-live-boxes/${camera.id}`);
        enabled = mode.enabled;
      } catch { /* Older API: preserve the existing explicitly labelled replay. */ }
      if (disposed) return;
      setLiveMode(enabled);
      if (!enabled && n001) {
        try {
          const data = await requestWebApi<N001OverlayData>(session.version,
            `/api/demo/v5/n001-overlay/${camera.id}`);
          if (!disposed && data.ready) setOverlay(data);
        } catch { /* Metadata failure never prevents MP4 playback. */ }
      }
    })();
    return () => { disposed = true; };
  }, [n001, camera.id, camera.is_monitored, startedAt, session.version, attempt]);

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
        {liveMode && n001 && url && startedAt && (
          <RealtimeJsonOverlay key={`${camera.id}:${startedAt}:${attempt}`}
            videoRef={videoRef} fetchFrames={fetchN001Frames}
            onUnavailable={restoreN001Overlay} />
        )}
        {!liveMode && n001 && url && startedAt && overlay?.ready && (
          <N001BboxOverlay videoRef={videoRef} data={overlay} />
        )}
        <div className="camera-overlay-label">
          DEMO · {camera.external_cctv_id}
          {liveMode && n001 ? " · 실제 YOLO JSON" : n001 && overlay?.ready ? " · 사전 YOLO 박스" : " · 원본 영상"}
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
      {syncWarning && <p role="status">{syncWarning}</p>}
      {!compact && (
        <>
          {liveMode ? (
            <p>실제 YOLO가 분석 중 생성한 JSON을 표시합니다. 영상은 기존 속도로 재생되고, 표시용 분석은 사건 생성과 분리되어 있습니다.</p>
          ) : n001 ? (
            <p>MP4 시점에 맞춘 사전 YOLO 결과입니다.</p>
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


