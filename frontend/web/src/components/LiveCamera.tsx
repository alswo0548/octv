/** 인증된 준비 API→WHEP 협상→영상 재생. 화면 이탈 시 연결을 닫고 실제 재생 중에만 LIVE를 표시합니다. */
import { useEffect, useRef, useState } from "react";
import { requestWebApi, type WebIncidentSession } from "../incidentData";
import { operationsError, type Cctv } from "../operationsData";

type StreamInfo = { cctv_id: number; playback_url: string; whep_url: string };
export function LiveCamera({
  session,
  camera,
}: {
  session: WebIncidentSession;
  camera: Cctv;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [phase, setPhase] = useState("대기");
  const [playing, setPlaying] = useState(false);
  const [playback, setPlayback] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let peer: RTCPeerConnection | null = null;
    let resource: string | null = null;
    let prepared = false;
    let stopped = false;
    setPlaying(false);
    setPlayback(null);
    const stop = () => {
      stopped = true;
      peer?.close();
      if (resource) {
        void fetch(resource, { method: "DELETE", keepalive: true }).catch(
          () => {},
        );
        resource = null;
      }
    };
    if (!camera.is_monitored) {
      setPhase("감시 OFF · 영상을 준비하지 않습니다.");
      return;
    }
    setPhase("스트림 준비 중");
    const timer = window.setTimeout(() => {
      setPhase(
        prepared
          ? "스트림 준비됨 · 영상 수신 시간 초과. 네트워크·코덱을 확인해주세요."
          : "스트림 준비 시간 초과",
      );
      setPlaying(false);
      controller.abort();
      stop();
    }, 20000);
    void (async () => {
      const info = await requestWebApi<StreamInfo>(
        session.version,
        `/api/cctvs/${camera.id}/stream`,
        { method: "POST", signal: controller.signal },
      );
      const endpoint = new URL(info.whep_url, window.location.href);
      const page = new URL(info.playback_url, window.location.href);
      if (
        info.cctv_id !== camera.id ||
        !["http:", "https:"].includes(endpoint.protocol) ||
        !["http:", "https:"].includes(page.protocol)
      )
        throw new Error("invalid stream response");
      if (stopped || controller.signal.aborted) return;
      prepared = true;
      setPlayback(page.href);
      setPhase("스트림 준비됨 · 영상 연결 중");
      peer = new RTCPeerConnection();
      const current = peer;
      current.addTransceiver("video", { direction: "recvonly" });
      current.addTransceiver("audio", { direction: "recvonly" });
      current.ontrack = (event) => {
        if (!stopped && video.current)
          video.current.srcObject =
            event.streams[0] ?? new MediaStream([event.track]);
      };
      current.onconnectionstatechange = () => {
        if (
          !stopped &&
          ["failed", "disconnected", "closed"].includes(current.connectionState)
        ) {
          setPlaying(false);
          setPhase("스트림 준비됨 · 영상 연결 끊김. 다시 연결해주세요.");
        }
      };
      await current.setLocalDescription(await current.createOffer());
      if (current.iceGatheringState !== "complete")
        await new Promise<void>((resolve, reject) => {
          const onAbort = () => {
            cleanup();
            reject(new Error("aborted"));
          };
          const onIce = () => {
            if (current.iceGatheringState === "complete") {
              cleanup();
              resolve();
            }
          };
          const cleanup = () => {
            current.removeEventListener("icegatheringstatechange", onIce);
            controller.signal.removeEventListener("abort", onAbort);
          };
          current.addEventListener("icegatheringstatechange", onIce);
          controller.signal.addEventListener("abort", onAbort, { once: true });
          if (controller.signal.aborted) onAbort();
          else onIce();
        });
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/sdp" },
        body: current.localDescription?.sdp,
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("WHEP rejected");
      const location = response.headers.get("Location");
      if (location) {
        const url = new URL(location, endpoint);
        if (url.origin === endpoint.origin) resource = url.href;
      }
      await current.setRemoteDescription({
        type: "answer",
        sdp: await response.text(),
      });
      if (stopped) {
        stop();
        return;
      }
    })().catch((error) => {
      if (!controller.signal.aborted) {
        setPhase(
          prepared
            ? "스트림 준비됨 · 브라우저 표시 실패. MediaMTX 주소·CORS·코덱을 확인해주세요."
            : operationsError(error),
        );
        setPlaying(false);
      }
      stop();
      window.clearTimeout(timer);
    });
    const element = video.current;
    const onPlaying = () => {
      if (!stopped) {
        window.clearTimeout(timer);
        setPlaying(true);
        setPhase("영상 재생 중");
      }
    };
    const onWaiting = () => {
      if (!stopped) {
        setPlaying(false);
        setPhase("스트림 준비됨 · 영상 버퍼링 중");
      }
    };
    element?.addEventListener("playing", onPlaying);
    element?.addEventListener("waiting", onWaiting);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
      stop();
      element?.removeEventListener("playing", onPlaying);
      element?.removeEventListener("waiting", onWaiting);
      if (element) element.srcObject = null;
    };
  }, [session.version, camera.id, camera.is_monitored, attempt]);
  return (
    <>
      <div className="camera live-camera">
        <video
          ref={video}
          autoPlay
          muted
          playsInline
          controls
          aria-label={`${camera.name} 실시간 영상`}
          onPause={() => {
            setPlaying(false);
            setPhase("영상 일시 정지");
          }}
          onEnded={() => {
            setPlaying(false);
            setPhase("영상 재생 종료");
          }}
          onError={() => {
            setPlaying(false);
            setPhase("영상 표시 실패 · 코덱과 연결을 확인해주세요.");
          }}
        />
        <div className="camera-overlay-label">
          {playing ? "● LIVE" : "영상 대기"} · {camera.external_cctv_id}
        </div>
      </div>
      <p role="status">{phase}</p>
      <div className="action-row">
        <button
          className="secondary"
          disabled={!camera.is_monitored}
          onClick={() => setAttempt((n) => n + 1)}
        >
          영상 다시 연결
        </button>
        {playback && (
          <a
            className="secondary"
            href={playback}
            target="_blank"
            rel="noreferrer"
          >
            영상 서버에서 확인
          </a>
        )}
      </div>
    </>
  );
}
