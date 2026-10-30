/**
 * 인증된 준비 API
 * → WHEP 협상
 * → 영상 재생
 *
 * 스트림 "준비" 시간과 실제 "영상 수신" 시간을
 * 별도의 timeout으로 관리합니다.
 *
 * 화면 이탈 시 연결을 닫고
 * 실제 재생 중에만 LIVE를 표시합니다.
 */

import { useEffect, useRef, useState } from "react";

import {
  loadDemoVideoUrl,
  requestWebApi,
  getAdminStreamHeaders,
  type WebIncidentSession,
} from "../incidentData";

import { operationsError, type Cctv } from "../operationsData";

import { CCTV_SOURCE } from "@octv/shared";

type StreamInfo = {
  cctv_id: number;
  playback_url: string;
  whep_url: string;
};

const PREPARE_TIMEOUT_MS = 30_000;
const PLAYBACK_TIMEOUT_MS = 25_000;
// 일시적인 WebRTC 끊김은 잠시 기다리고, 지속되는 장애만 재연결합니다.
const DISCONNECT_GRACE_MS = 4_000;
const STALL_TIMEOUT_MS = 12_000;
const STABLE_PLAYBACK_MS = 15_000;
const RECONNECT_DELAYS_MS = [2_000, 5_000, 10_000];

export function LiveCamera({
  session,
  camera,
}: {
  session: WebIncidentSession;
  camera: Cctv;
}) {
  const video = useRef<HTMLVideoElement>(null);

  const [attempt, setAttempt] = useState(0);
  // 이 컴포넌트의 연속 장애만 카운트하며, 안정적으로 재생되면 초기화합니다.
  const reconnectCount = useRef(0);

  const [phase, setPhase] = useState("대기");

  const [playing, setPlaying] = useState(false);

  const sourceLabel = camera.provider.toUpperCase().includes("UTIC")
    ? CCTV_SOURCE
    : `${camera.provider} 제공`;

  useEffect(() => {
    const controller = new AbortController();

    let peer: RTCPeerConnection | null = null;

    let resource: string | null = null;
    let streamHeaders: { Authorization: string } | null = null;

    let demoObjectUrl: string | null = null;

    let stopped = false;

    let prepared = false;

    let prepareTimer: number | null = null;

    let playbackTimer: number | null = null;
    let disconnectTimer: number | null = null;
    let stallTimer: number | null = null;
    let stableTimer: number | null = null;
    let retryTimer: number | null = null;
    let hasPlayed = false;

    // =====================================================
    // Timer 정리
    // =====================================================

    const clearPrepareTimer = () => {
      if (prepareTimer !== null) {
        window.clearTimeout(prepareTimer);

        prepareTimer = null;
      }
    };

    const clearPlaybackTimer = () => {
      if (playbackTimer !== null) {
        window.clearTimeout(playbackTimer);

        playbackTimer = null;
      }
    };

    const clearTimers = () => {
      clearPrepareTimer();
      clearPlaybackTimer();
      if (disconnectTimer !== null) window.clearTimeout(disconnectTimer);
      if (stallTimer !== null) window.clearTimeout(stallTimer);
      if (stableTimer !== null) window.clearTimeout(stableTimer);
      disconnectTimer = null;
      stallTimer = null;
      stableTimer = null;
    };

    // =====================================================
    // WebRTC / WHEP 연결 종료
    // =====================================================

    const stop = () => {
      stopped = true;

      clearTimers();

      peer?.close();

      peer = null;

      if (resource && streamHeaders) {
        void fetch(resource, {
          method: "DELETE",
          headers: streamHeaders,
          keepalive: true,
        }).catch(() => {});
        resource = null;
      }
      streamHeaders = null;

      if (demoObjectUrl) {
        URL.revokeObjectURL(demoObjectUrl);

        demoObjectUrl = null;
      }
    };

    // =====================================================
    // 초기 상태
    // =====================================================

    setPlaying(false);
    if (!camera.is_monitored) {
      setPhase("감시 OFF · 영상을 준비하지 않습니다.");

      return;
    }

    const isDemo = camera.provider.trim().toUpperCase() === "DEMO";

    // DEMO MP4에는 영향 없이, 실시간 스트림에만 제한적 재연결을 적용합니다.
    const failOrReconnect = (message: string) => {
      if (stopped) return;

      if (!isDemo && reconnectCount.current < RECONNECT_DELAYS_MS.length) {
        const retry = reconnectCount.current++;
        const delay = RECONNECT_DELAYS_MS[retry];
        setPlaying(false);
        setPhase(`영상 연결 끊김 · ${Math.round(delay / 1000)}초 후 자동 재연결 (${retry + 1}/${RECONNECT_DELAYS_MS.length})`);
        controller.abort();
        stop();
        retryTimer = window.setTimeout(() => {
          retryTimer = null;
          setAttempt((value) => value + 1);
        }, delay);
        return;
      }

      setPlaying(false);
      setPhase(isDemo ? message : "자동 재연결 실패 · 영상 다시 연결 버튼을 눌러주세요.");
      controller.abort();
      stop();
    };

    // =====================================================
    // 1. FastAPI → UTIC → MediaMTX 준비
    // =====================================================

    setPhase("스트림 정보 준비 중");

    prepareTimer = window.setTimeout(() => {
      if (stopped) {
        return;
      }

      failOrReconnect("스트림 준비 시간 초과 · UTIC 또는 영상 서버 연결을 확인해주세요.");
    }, PREPARE_TIMEOUT_MS);

    // =====================================================
    // 비동기 연결
    // =====================================================

    void (async () => {
      if (isDemo) {
        setPhase("Demo 영상 준비 중");

        const url = await loadDemoVideoUrl(
          session.version,
          camera.id,
          controller.signal,
        );

        if (stopped || controller.signal.aborted) {
          URL.revokeObjectURL(url);
          return;
        }

        clearPrepareTimer();

        prepared = true;
        demoObjectUrl = url;

        const element = video.current;

        if (!element) {
          throw new Error("영상 요소를 찾을 수 없습니다.");
        }

        element.srcObject = null;
        element.src = url;
        element.loop = true;

        setPhase("Demo 영상 준비됨 · 영상 연결 중");

        playbackTimer = window.setTimeout(() => {
          if (stopped || playing) {
            return;
          }

          setPlaying(false);
          setPhase("Demo 영상 수신 시간 초과. 다시 연결해주세요.");

          controller.abort();
          stop();
        }, PLAYBACK_TIMEOUT_MS);

        await element.play();

        return;
      }

      const info = await requestWebApi<StreamInfo>(
        session.version,
        `/api/cctvs/${camera.id}/stream`,
        {
          method: "POST",
          signal: controller.signal,
        },
      );

      if (stopped || controller.signal.aborted) {
        return;
      }

      clearPrepareTimer();

      prepared = true;

      const endpoint = new URL(info.whep_url, window.location.href);

      const page = new URL(info.playback_url, window.location.href);

      if (
        info.cctv_id !== camera.id ||
        !["http:", "https:"].includes(endpoint.protocol) ||
        !["http:", "https:"].includes(page.protocol)
      ) {
        throw new Error("invalid stream response");
      }

      setPhase("스트림 준비됨 · 영상 연결 중");

      // ===================================================
      // 준비가 끝난 시점부터 영상 수신 timeout 시작
      // ===================================================

      playbackTimer = window.setTimeout(() => {
        if (stopped || playing) {
          return;
        }

        failOrReconnect("스트림 준비됨 · 영상 수신 시간 초과. 다시 연결을 시도해주세요.");
      }, PLAYBACK_TIMEOUT_MS);

      // ===================================================
      // WebRTC
      // ===================================================

      peer = new RTCPeerConnection();

      const current = peer;

      current.addTransceiver("video", {
        direction: "recvonly",
      });

      current.addTransceiver("audio", {
        direction: "recvonly",
      });

      current.ontrack = (event) => {
        if (stopped || !video.current) {
          return;
        }

        video.current.srcObject =
          event.streams[0] ?? new MediaStream([event.track]);
      };

      current.onconnectionstatechange = () => {
        if (stopped) return;
        const state = current.connectionState;

        // 순간적인 disconnected 상태에서는 즉시 재협상하지 않습니다.
        if (state === "disconnected") {
          if (disconnectTimer === null) {
            disconnectTimer = window.setTimeout(() => {
              disconnectTimer = null;
              if (!stopped && current.connectionState === "disconnected") {
                failOrReconnect("스트림 준비됨 · 영상 연결 끊김. 다시 연결해주세요.");
              }
            }, DISCONNECT_GRACE_MS);
          }
          return;
        }

        if (disconnectTimer !== null) window.clearTimeout(disconnectTimer);
        disconnectTimer = null;
        if (state === "failed" || state === "closed") {
          failOrReconnect("스트림 준비됨 · 영상 연결 끊김. 다시 연결해주세요.");
        }
      };

      // ===================================================
      // SDP Offer 생성
      // ===================================================

      await current.setLocalDescription(await current.createOffer());

      // ===================================================
      // ICE Gathering 완료 대기
      // ===================================================

      if (current.iceGatheringState !== "complete") {
        await new Promise<void>((resolve, reject) => {
          const cleanup = () => {
            current.removeEventListener("icegatheringstatechange", onIce);

            controller.signal.removeEventListener("abort", onAbort);
          };

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

          current.addEventListener("icegatheringstatechange", onIce);

          controller.signal.addEventListener("abort", onAbort, {
            once: true,
          });

          if (controller.signal.aborted) {
            onAbort();
          } else {
            onIce();
          }
        });
      }

      if (stopped || controller.signal.aborted) {
        return;
      }

      // ===================================================
      // MediaMTX WHEP
      // ===================================================

      // MediaMTX HTTP는 외부 비공개이며 Caddy가 관리자 JWT를 매번 검증합니다.
      // ICE/DTLS 실제 미디어는 WHEP 인증 협상 뒤에만 연결할 수 있습니다.
      streamHeaders = getAdminStreamHeaders(session.version);
      const response = await fetch(endpoint, {
        method: "POST",

        headers: {
          "Content-Type": "application/sdp",
          ...streamHeaders,
        },

        body: current.localDescription?.sdp,

        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`WHEP rejected: ${response.status}`);
      }

      const location = response.headers.get("Location");

      if (location) {
        const url = new URL(location, endpoint);

        if (url.origin === endpoint.origin) {
          resource = url.href;
        }
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
      if (stopped || controller.signal.aborted) return;
      failOrReconnect(
        prepared
          ? "스트림 준비됨 · 브라우저 영상 연결에 실패했습니다. 다시 연결을 시도해주세요."
          : operationsError(error),
      );
    });

    // =====================================================
    // HTML Video Events
    // =====================================================

    const element = video.current;

    const onPlaying = () => {
      if (stopped) {
        return;
      }

      clearTimers();
      hasPlayed = true;
      setPlaying(true);
      setPhase("영상 재생 중");
      if (!isDemo) {
        // 잠시 보이다 끊기는 경우는 성공으로 세지 않습니다.
        stableTimer = window.setTimeout(() => {
          if (!stopped) reconnectCount.current = 0;
        }, STABLE_PLAYBACK_MS);
      }
    };

    const onWaiting = () => {
      if (stopped) {
        return;
      }

      setPlaying(false);
      setPhase("스트림 준비됨 · 영상 버퍼링 중");
      if (stableTimer !== null) window.clearTimeout(stableTimer);
      stableTimer = null;
      // 재생 중 멈춘 경우에만 감시합니다. 최초 수신은 기존 timeout을 사용합니다.
      if (!isDemo && hasPlayed && !element?.paused && stallTimer === null) {
        stallTimer = window.setTimeout(() => {
          stallTimer = null;
          if (!stopped && !element?.paused) {
            failOrReconnect("스트림 준비됨 · 영상 버퍼링이 계속됩니다.");
          }
        }, STALL_TIMEOUT_MS);
      }
    };

    element?.addEventListener("playing", onPlaying);

    element?.addEventListener("waiting", onWaiting);

    // =====================================================
    // Cleanup
    // =====================================================

    return () => {
      controller.abort();
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      retryTimer = null;
      stop();

      element?.removeEventListener("playing", onPlaying);

      element?.removeEventListener("waiting", onWaiting);

      if (element) {
        element.srcObject = null;
        element.removeAttribute("src");
        element.load();
      }
    };
  }, [
    session.version,
    camera.id,
    camera.provider,
    camera.is_monitored,
    attempt,
  ]);

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
          {playing ? "● LIVE" : "영상 대기"}
          {" · "}
          {camera.external_cctv_id}
        </div>
        <div className="camera-source-label">{sourceLabel}</div>
      </div>

      <p role="status">{phase}</p>

      <div className="action-row">
        <button
          className="secondary"
          disabled={!camera.is_monitored}
          onClick={() => {
            reconnectCount.current = 0;
            setAttempt((value) => value + 1);
          }}
        >
          영상 다시 연결
        </button>


      </div>
    </>
  );
}
