import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createRoot } from "react-dom/client";
import { LiveBboxOverlay } from "./components/LiveBboxOverlay";
import type { LiveFrame } from "./components/liveBboxTiming";

const API = "http://127.0.0.1:8765";
type Status = {
  active: boolean;
  samples: number;
  positive: number;
  last_pts: number | null;
  playback_variant: string;
  fps: number;
  duration: number;
};

function LocalPreview() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [videoTime, setVideoTime] = useState(0);
  const [dropped, setDropped] = useState("N/A");

  const fetchFrames = useCallback(async (): Promise<{
    enabled: boolean;
    frames: LiveFrame[];
  }> => {
    const response = await fetch(`${API}/api/demo/v5/live-boxes/4`, {
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Local API ${response.status}`);
    return response.json() as Promise<{ enabled: boolean; frames: LiveFrame[] }>;
  }, []);

  const inferVideoFrame = useCallback(async (blob: Blob, mediaTime: number): Promise<{
    enabled: boolean;
    frames: LiveFrame[];
  }> => {
    const response = await fetch(
      `${API}/api/infer-frame?t=${encodeURIComponent(mediaTime.toFixed(3))}`,
      { method: "POST", headers: { "Content-Type": "image/jpeg" },
        body: blob, cache: "no-store" },
    );
    if (!response.ok) throw new Error(`YOLO frame request: ${response.status}`);
    return response.json() as Promise<{ enabled: boolean; frames: LiveFrame[] }>;
  }, []);

  useEffect(() => {
    let alive = true;
    const update = () => {
      const video = videoRef.current;
      if (video) {
        setVideoTime(video.currentTime);
        const quality = video.getVideoPlaybackQuality?.();
        if (quality) {
          setDropped(`${quality.droppedVideoFrames} / ${quality.totalVideoFrames}`);
        }
      }
      void fetch(`${API}/api/status`, { cache: "no-store" })
        .then((response) => {
          if (!response.ok) throw new Error("Preview API unavailable");
          return response.json() as Promise<Status>;
        })
        .then((data) => {
          if (alive) setStatus(data);
        })
        .catch(() => {
          if (alive) setStatus(null);
        });
    };
    update();
    const interval = window.setInterval(update, 1000);
    return () => {
      alive = false;
      window.clearInterval(interval);
    };
  }, []);

  async function start(at: number) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const video = videoRef.current;
      if (!video) throw new Error("비디오를 찾을 수 없습니다.");
      if (!Number.isFinite(video.duration) || video.duration <= 0) {
        await new Promise<void>((resolve, reject) => {
          video.addEventListener("loadedmetadata", () => resolve(), { once: true });
          video.addEventListener("error", () => reject(new Error("MP4 디코딩 실패")), {
            once: true,
          });
          video.load();
        });
      }
      video.pause();
      const target = Math.min(at, video.duration - 0.2);
      if (Math.abs(video.currentTime - target) > 0.01) {
        await new Promise<void>((resolve) => {
          video.addEventListener("seeked", () => resolve(), { once: true });
          video.currentTime = target;
        });
      }
      await video.play();
      const response = await fetch(`${API}/api/start-browser`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ offset: video.currentTime }),
      });
      if (!response.ok) throw new Error(`YOLO API start failed: ${response.status}`);
      setRunning(true);
    } catch (reason) {
      videoRef.current?.pause();
      setRunning(false);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    videoRef.current?.pause();
    setRunning(false);
    try {
      await fetch(`${API}/api/stop`, { method: "POST" });
    } catch {
      setError("API 연결 실패. Python 창에서 Ctrl+C로 종료할 수 있습니다.");
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#071828",
        color: "#e7f4ff",
        fontFamily: "system-ui, sans-serif",
        padding: "28px 16px",
      }}
    >
      <main style={{ maxWidth: 980, margin: "0 auto" }}>
        <div style={{ color: "#65dadd", fontSize: 13 }}>OCTV · 분리 검증 환경</div>
        <h1 style={{ fontSize: 28, margin: "7px 0" }}>N001 실시간 YOLO 바운딩박스</h1>
        <p style={{ color: "#a6bccb", marginTop: 5, lineHeight: 1.6 }}>
          실제 N001 영상과 실제 N052 YOLO 모델을 사용합니다. 운영 DB·Redis·알림·서버에는
          연결하지 않습니다. 브라우저는 영상을 30FPS로 그대로 재생하면서, 화면의 실제 프레임을
          약 0.7초마다 Python YOLO에 보내 추론합니다. 가짜 박스나 사전 JSON은 사용하지 않습니다.
        </p>
        <div
          style={{
            position: "relative",
            width: "100%",
            aspectRatio: "16/9",
            background: "#000",
            overflow: "hidden",
            border: "1px solid #29546a",
            borderRadius: 14,
          }}
        >
          <video
            ref={videoRef}
            src={`${API}/video`}
            crossOrigin="anonymous"
            muted
            playsInline
            loop
            preload="metadata"
            controls={false}
            style={{ width: "100%", height: "100%", objectFit: "contain" }}
          />
          {running && (
            <LiveBboxOverlay
              cameraId={4}
              sessionVersion={0}
              videoRef={videoRef}
              fetchFrames={fetchFrames}
              inferVideoFrame={inferVideoFrame}
            />
          )}
          <div
            style={{
              position: "absolute",
              left: 14,
              top: 12,
              borderRadius: 6,
              padding: "5px 9px",
              background: "rgba(0,0,0,.7)",
              fontSize: 12,
            }}
          >
            {running ? "실제 추론 연결 · 테스트" : "재생 대기"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16 }}>
          <button disabled={busy || !status} onClick={() => void start(52)}
            style={buttonStyle}>52초 침수 구간부터 보기</button>
          <button disabled={busy || !status} onClick={() => void start(0)}
            style={buttonStyle}>영상 처음부터 보기</button>
          <button disabled={!running} onClick={() => void stop()}
            style={{ ...buttonStyle, background: "#26455b" }}>테스트 중지</button>
        </div>
        {error && <p role="alert" style={{ color: "#ffadad" }}>{error}</p>}
        {!status && <p style={{ color: "#ffcf94" }}>
          Python 테스트 API가 연결되지 않았습니다. 별도 실행 창을 확인하세요.
        </p>}
        <section style={{
          marginTop: 18, padding: 16, background: "#102b3f",
          border: "1px solid #284d63", borderRadius: 12, lineHeight: 1.8,
        }}>
          <div>영상 시각: <b>{videoTime.toFixed(2)}초</b> ·
            Python YOLO 갱신: <b>{status?.samples ?? 0}회</b> ·
            실제 탐지 결과: <b>{status?.positive ?? 0}회</b></div>
          <div>최근 YOLO PTS: {status?.last_pts?.toFixed(2) ?? "-"}초 ·
            브라우저 프레임 드롭: {dropped}</div>
          <div>재생 파일: {status?.playback_variant ?? "-"} ·
            분석 원본: N001_demo.mp4</div>
        </section>
        <p style={{ color: "#adc7d4", fontSize: 13, lineHeight: 1.7 }}>
          <span style={{ color: "#42e8ed" }}>■ 청록색 실선</span>은 실제 YOLO가
          해당 화면 프레임을 분석한 결과입니다. 청록색 점선은 최대 1.1초 안의
          최근 YOLO 박스 위치이며, 새 탐지·객체 추적이 아닙니다. 다음 분석에서 탐지가
          없거나 결과가 오래되면 즉시 사라집니다. 감지·추론 이외의 사건 처리는 하지 않습니다.
          검증 후 테스트 창을 닫고 실행 창 두 개에서 Ctrl+C를 누르면 종료됩니다.
        </p>
      </main>
    </div>
  );
}

const buttonStyle: CSSProperties = {
  padding: "11px 16px",
  background: "#087f87",
  color: "white",
  borderRadius: 8,
  border: "none",
  fontWeight: 700,
  cursor: "pointer",
};

createRoot(document.getElementById("root")!).render(<LocalPreview />);
