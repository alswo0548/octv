import { useState } from "react";
import { mock } from "@octv/shared";
import {
  Panel,
  Select,
  Pagination,
  type ShowModal,
  actionMessage,
} from "../components/Primitives";
import { go } from "../routing/useRoute";

type MonitoringMode = "BASE" | "OFF" | "ALERT" | "POST_ALERT" | "VERIFY";
const monitoringLabels: Record<MonitoringMode, string> = {
  BASE: "ON",
  OFF: "OFF",
  ALERT: "ON · 특보 감시 중",
  POST_ALERT: "ON · 해제 후 확인 대기",
  VERIFY: "ON · 집중 검증 중",
};
// UI examples only. Connection status remains in the separate CCTV fixture.
const initialMonitoring: Record<string, MonitoringMode> = {
  "CCTV-001": "BASE",
  "CCTV-002": "OFF",
  "CCTV-003": "ALERT",
  "CCTV-004": "POST_ALERT",
  "CCTV-005": "OFF",
  "CCTV-006": "VERIFY",
};
export function TargetsPage({ show }: { show: ShowModal }) {
  const [monitoring, setMonitoring] = useState(initialMonitoring);
  function toggleMonitoring(id: string) {
    if (monitoring[id] === "ALERT") {
      show({
        title: "감시 중지 불가",
        body: (
          <>
            <p>특보 발령 중인 CCTV는 감시를 중지할 수 없습니다.</p>
            <p>
              특보 해제 후 관리자가 상황을 확인한 뒤 비활성화할 수 있습니다.
            </p>
          </>
        ),
        confirm: "확인",
        cancel: "",
      });
      return;
    }
    setMonitoring((current) => ({
      ...current,
      [id]: current[id] === "OFF" ? "BASE" : "OFF",
    }));
  }
  return (
    <>
      <a className="back-link" href="#/settings">
        ‹ 시스템 설정으로 돌아가기
      </a>
      <p>대상 CCTV의 연결 상태와 AI 감시상태를 확인합니다.</p>
      <Panel title="CCTV 목록">
        <div className="monitor-filter">
          <Select
            label="지역"
            options={["전체 지역", "구리시", "강남구", "서대문구"]}
          />
          <label>
            검색
            <input placeholder="CCTV ID / 이름 / 도로명 검색" />
          </label>
        </div>
        <div className="table-scroll">
          <table className="targets-table">
            <thead>
              <tr>
                {[
                  "CCTV ID",
                  "CCTV 이름",
                  "설치 지역",
                  "위치 / 도로명",
                  "현재 상태",
                  "감시 안내",
                  "감시상태",
                ].map((x) => (
                  <th key={x}>{x}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {mock.targetIds
                .map((id) => mock.cctvs.find((c) => c.id === id)!)
                .map((c) => (
                  <tr key={c.id}>
                    <td>{c.id}</td>
                    <td>{c.name}</td>
                    <td>{c.region}</td>
                    <td>{c.road}</td>
                    <td>
                      <span
                        className={
                          "status " + (c.connected ? "detect" : "check")
                        }
                      >
                        {c.connected ? "연결 정상" : "연결 끊김"}
                      </span>
                    </td>
                    <td
                      className="monitoring-notice"
                      data-mode={monitoring[c.id]}
                    >
                      {monitoringLabels[monitoring[c.id]]}
                    </td>
                    <td>
                      <input
                        className="switch"
                        type="checkbox"
                        role="switch"
                        aria-label={c.id + " 감시상태"}
                        checked={monitoring[c.id] !== "OFF"}
                        onChange={() => toggleMonitoring(c.id)}
                      />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        <Pagination kind="targets" />
        <p className="content-footnote">
          감시상태는 CCTV 연결 상태와 별개입니다. 특보 대상 CCTV는 ON으로
          표시되며 특보 중에는 OFF로 변경할 수 없습니다. 해제 후에도 ON을
          유지하며, 관리자가 상황을 확인한 뒤 수동으로 OFF할 수 있습니다. 변경은
          현재 화면에만 표시됩니다.
        </p>
      </Panel>
      <div className="action-row">
        <button
          className="primary"
          onClick={() =>
            show({
              title: "감시상태 설정 저장 확인",
              body: actionMessage,
              confirm: "확인",
            })
          }
        >
          변경사항 저장
        </button>
        <button
          className="secondary"
          onClick={() =>
            show({
              title: "변경 취소",
              body: "감시상태의 화면 표시를 초기 표시값으로 복원할까요?",
              onConfirm: () => setMonitoring(initialMonitoring),
            })
          }
        >
          변경 취소
        </button>
        <button className="secondary" onClick={() => go("settings")}>
          시스템 설정으로 돌아가기
        </button>
      </div>
    </>
  );
}
