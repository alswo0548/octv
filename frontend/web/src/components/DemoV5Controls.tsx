/** Optional v5 Demo controls; calls existing CONTROL_ADMIN endpoints only. */
import { useState } from "react";
import { requestWebApi, type WebIncidentSession } from "../incidentData";
import { operationsError, useOperations } from "../operationsData";
import { Panel } from "./Primitives";

type DemoStatus = {
  enabled: boolean;
  active: boolean;
  scenario: string | null;
  case_count: number;
  active_cctv_count: number;
  active_alert_count: number;
};

type DemoResult = { started?: boolean; stopped?: boolean; scenario: string };

export function DemoV5Controls({
  session,
  onChanged,
}: {
  session: WebIncidentSession;
  onChanged: () => void;
}) {
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const status = useOperations<DemoStatus>(session, "/api/demo/status", revision, 5_000);

  async function change(action: "start" | "stop") {
    const verb = action === "start" ? "시작" : "종료";
    if (!window.confirm(`시연을 ${verb}할까요? Demo CCTV 3대와 가상 기상특보 상태가 변경됩니다.`)) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await requestWebApi<DemoResult>(session.version, `/api/demo/${action}`, {
        method: "POST",
        body: JSON.stringify({ scenario: "main_demo" }),
      });
      setMessage(
        action === "start"
          ? `시연 시작 요청 성공 (${result.scenario}). YOLO·사건 생성은 Runtime에서 별도 확인 필요.`
          : `시연 종료 요청 성공 (${result.scenario}).`,
      );
      setRevision((value) => value + 1);
      onChanged();
    } catch (err) {
      setMessage(operationsError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="시연 제어 · Demo CCTV 3대">
      {status.error ? (
        <p role="alert">Demo API 사용 불가: 백엔드의 OCTV_DEMO_ENABLED 설정과 관리자 로그인을 확인해주세요.</p>
      ) : (
        <p role="status">
          상태: {status.loading && !status.data ? "확인 중" : status.data?.active ? "진행 중" : "대기 중"}
          {status.data ? ` · Demo 활성 ${status.data.active_cctv_count}/${status.data.case_count}대` : ""}
        </p>
      )}
      <div className="action-row">
        <button className="primary" type="button"
          disabled={busy || !status.data || status.data.active}
          onClick={() => void change("start")}>시연 시작</button>
        <button className="secondary" type="button"
          disabled={busy || !status.data || !status.data.active}
          onClick={() => void change("stop")}>시연 종료</button>
      </div>
      {message && <p role="status">{message}</p>}
      <p>기존 실제 UTIC CCTV는 유지됩니다. 이 버튼은 재난 사건을 인위적으로 생성하지 않습니다.</p>
    </Panel>
  );
}
