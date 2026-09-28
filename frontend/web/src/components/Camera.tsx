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
      <img src="/assets/road.jpg" alt="도로 CCTV 화면" />
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
          <p>영상 연결을 확인해주세요</p>
        </div>
      )}
      <div className="camera-bottom">
        <div>
          <span>{d.location}</span>
          <small>{d.time}:36</small>
        </div>
        {onExpand ? (
          <button onClick={onExpand} aria-label="CCTV 확대">
            ⛶ CCTV 확대
          </button>
        ) : null}
      </div>
    </div>
  );
}
