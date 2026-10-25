/** Demo MP4 is *synchronized replay*, not a real live camera feed.
 * The same scenario KST start time is used by the 3-up wall and detail view.
 * No YOLO/Incident values are simulated in the browser.
 */
import { useEffect, useRef, useState } from "react";
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
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let disposed = false;
    setUrl(null);
    setError(null);
    if (!camera.is_monitored || !startedAt) return;
    void requestWebApi<PlaybackInfo>(session.version, `/api/demo/v5/playback/${camera.id}`, {
      method: "POST",
    }).then((response) => {
      if (!disposed) setUrl(response.url);
    }).catch((reason) => {
      if (!disposed) setError(operationsError(reason));
    });
    return () => { disposed = true; };
  }, [session.version, camera.id, camera.is_monitored, startedAt, attempt]);

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
      <div className="camera live-camera" style={compact ? { minHeight: 0, aspectRatio: "16 / 9" } : undefined}>
        {url && startedAt ? (
          <video ref={videoRef} src={url} autoPlay muted playsInline loop preload="metadata"
            // Do not expose independent seek UI: timeline is shared across cameras.
            controls={false}
            style={{ display: "block", width: "100%", height: "100%", objectFit: "contain" }}
            aria-label={`${camera.name} 시연 동기화 영상`}
            onError={() => setError("Demo 영상 재생 오류 · API/영상 파일을 확인해주세요.")} />
        ) : (
          <p>{camera.is_monitored
            ? "시연 영상 공통 시작 시각·재생 주소 확인 중"
            : "시연 시작 전 · 영상 대기"}</p>
        )}
        <div className="camera-overlay-label">DEMO · {camera.external_cctv_id}</div>
      </div>
      {error && <p role="alert">{error}</p>}
      {!compact && (
        <>
          <p>시연 시작 시점에 맞춘 동기화 재생입니다. 실제 YOLO·사건 생성은 CCTV Runtime이 별도로 수행합니다.</p>
          <button className="secondary" type="button" disabled={!camera.is_monitored}
            onClick={() => setAttempt((value) => value + 1)}>영상 재연결</button>
        </>
      )}
    </div>
  );
}
