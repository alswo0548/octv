import { useState } from "react";
import { mock, incidentById } from "@octv/shared";
import {
  Panel,
  Pair,
  Select,
  ActionPreview,
  type ShowModal,
} from "../components/Primitives";
import { Camera } from "../components/Camera";
import { go } from "../routing/useRoute";
export function MonitorPage({
  initial = "CCTV-012",
  show,
}: {
  initial?: string;
  show: ShowModal;
}) {
  const [id, setId] = useState(initial),
    c = mock.cctvs.find((x) => x.id === id) || mock.cctvs[0],
    source =
      mock.incidents.find((x) => x.camera === id) || incidentById("SEL-001"),
    d = { ...source, camera: c.id, location: c.region + " " + c.road };
  return (
    <>
      <div className="stat-grid">
        {mock.uiSnapshot.monitorCards.map(([t, n]) => (
          <div className="panel stat-card" key={t}>
            <span>{t}</span>
            <strong>
              {n}
              <small>대</small>
            </strong>
          </div>
        ))}
      </div>
      <div className="monitor-filter">
        <Select label="연결 상태" options={["전체 CCTV", "연결 오류 CCTV"]} />
        <label>
          검색
          <input placeholder="CCTV ID / 위치 검색" />
        </label>
      </div>
      <div className="monitor-layout">
        <Panel title="CCTV 목록" className="monitor-list-panel">
          <div className="camera-list">
            {mock.cctvs.map((c) => (
              <button
                key={c.id}
                className={c.id === id ? "active" : ""}
                onClick={() => setId(c.id)}
              >
                <strong>{c.id}</strong>
                <p>
                  {c.region} {c.road}
                </p>
                <span
                  className={"status " + (c.connected ? "detect" : "check")}
                >
                  {c.connected ? "연결 정상" : "연결 끊김"}
                </span>
                <p className="camera-mode">{c.mode}</p>
              </button>
            ))}
          </div>
        </Panel>
        <Panel
          title="선택 CCTV 영상 및 분석 상태"
          className="monitor-detail-panel"
        >
          <Camera incident={d} connected={c.connected} />
          <div className="status-grid">
            <dl>
              <Pair
                label="연결 / 분석"
                value={c.connected ? "정상 / 분석 중" : "연결 끊김 / 분석 중지"}
              />
              <Pair
                label="마지막 프레임"
                value={mock.uiSnapshot.cameraStatus.lastFrame}
              />
              <Pair
                label="영상 품질"
                value={c.connected ? "양호" : "확인 불가"}
              />
            </dl>
            <dl>
              <Pair label="감시 모드" value={c.mode} />
              <Pair
                label="현재 분석 주기"
                value={mock.uiSnapshot.cameraStatus.interval}
              />
              <Pair
                label="위험 후보"
                value={mock.uiSnapshot.cameraStatus.candidate}
              />
            </dl>
          </div>
          <div className="action-row">
            <ActionPreview label="재연결 시도" show={show} />
            <button className="primary" onClick={() => go("settings")}>
              감시 기준 변경
            </button>
          </div>
        </Panel>
      </div>
    </>
  );
}
