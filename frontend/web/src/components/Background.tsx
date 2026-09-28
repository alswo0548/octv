import { useEffect, useRef, useState } from "react";

/** Decorative video only. Incident CCTV content is a separate component. */
export function Background() {
  const video = useRef<HTMLVideoElement>(null);
  const fillVideo = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (reduced) {
      video.current?.pause();
      fillVideo.current?.pause();
      setPlaying(false);
    } else {
      video.current?.play().catch(() => setPlaying(false));
      fillVideo.current?.play().catch(() => {});
    }
  }, [reduced]);
  return (
    <>
      <div className="ambient" aria-hidden="true">
        <div className="ambient-still" />
        <video
          ref={fillVideo}
          className={
            "ambient-video ambient-fill" +
            (playing && !reduced ? " is-playing" : "")
          }
          src="/assets/night-traffic.mp4"
          autoPlay
          muted
          loop
          playsInline
          preload="auto"
          tabIndex={-1}
        />
        <video
          ref={video}
          className={
            "ambient-video" + (playing && !reduced ? " is-playing" : "")
          }
          src="/assets/night-traffic.mp4"
          poster="/assets/road.jpg"
          autoPlay
          muted
          loop
          playsInline
          preload="auto"
          tabIndex={-1}
          onPlaying={() => setPlaying(true)}
          onError={() => setPlaying(false)}
          onPause={() => setPlaying(false)}
        />
      </div>
      <div className="shade" aria-hidden="true" />
    </>
  );
}
