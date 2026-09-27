import type { Incident } from "@octv/shared";
export function Camera({
  incident: d,
  connected = true,
  live = true,
  onExpand,
}: {
  incident: Incident;
  connected?: boolean;
  live?: boolean;
  onExpand?: () => void;
}) {
  return (
    <div
      className={
        "camera shared-camera " + (live ? "live-camera" : "capture-camera")
      }
    >
      <img src="/assets/road.jpg" alt="도로 CCTV 도식용 샘플 이미지" />
      <div className="camera-tint" />
      <div className="camera-top">
        <span>
          <i className="live-dot" />
          {live ? "LIVE" : "CAPTURE"} <b>{d.camera}</b>
        </span>
        <span>
          AI ANALYSIS <i className="ai-dot" />
        </span>
      </div>
      {connected ? (
        <>
          <div className="scanline" />
          <div className="bounding visible">
            <i />
            <i />
            <i />
            <i />
            <div className="box-label">
              <span>{d.label}</span>
              <b>{d.confidence}%</b>
            </div>
          </div>
        </>
      ) : (
        <div className="camera-offline">
          <span>연결 끊김</span>
          <p>연결 상태 예시</p>
        </div>
      )}
      <div className="camera-bottom">
        <div>
          <span>{d.location}</span>
          <small>SIMULATED FEED · {d.time}:36</small>
        </div>
        {onExpand ? (
          <button onClick={onExpand} aria-label="CCTV 확대">
            ⛶ CCTV 확대
          </button>
        ) : (
          <span className="tag">시연 영상</span>
        )}
      </div>
    </div>
  );
}
