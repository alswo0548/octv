import { useState } from "react";
/** 기존 CCTV 목록·감시 API 연결. 저장 결과 재조회 후 표시하며 특보 Runtime 정책은 바꾸지 않습니다. */
import { requestWebApi, type WebIncidentSession } from "../incidentData";
import {
  useOperations,
  operationsError,
  monitoringLabels,
  statusLabel,
  type Cctv,
} from "../operationsData";
import { Panel, type ShowModal } from "../components/Primitives";
import { go } from "../routing/useRoute";

export function TargetsPage({
  show,
  session,
}: {
  show: ShowModal;
  session: WebIncidentSession;
}) {
  const [revision, setRevision] = useState(0);
  const { data, loading, error } = useOperations<Cctv[]>(
    session,
    "/api/cctvs",
    revision,
  );
  const [busy, setBusy] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [region, setRegion] = useState("");
  const [query, setQuery] = useState("");
  const rows = (data ?? []).filter(
    (c) =>
      (!region || c.region_code === region) &&
      `${c.external_cctv_id} ${c.name} ${c.address ?? ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  async function toggleMonitoring(camera: Cctv) {
    if (busy !== null) return;
    setBusy(camera.id);
    setMessage(null);
    try {
      await requestWebApi(
        session.version,
        `/api/cctvs/${camera.id}/monitoring`,
        {
          method: "PATCH",
          body: JSON.stringify({ enabled: !camera.is_monitored }),
        },
      );
      setMessage(
        "감시 설정을 저장했습니다. 실제 연결·분석 상태는 Runtime 동작 후 갱신됩니다.",
      );
    } catch (reason) {
      setMessage(operationsError(reason));
    } finally {
      setBusy(null);
      setRevision((v) => v + 1);
    }
  }
  return (
    <>
      <a className="back-link" href="#/settings">
        ‹ 시스템 설정으로 돌아가기
      </a>
      <p>대상 CCTV의 연결 상태와 AI 감시상태를 확인합니다.</p>
      <Panel title="CCTV 목록">
        <div className="monitor-filter">
          <label>
            지역
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              <option value="">전체 지역</option>
              {Array.from(
                new Map(
                  (data ?? [])
                    .filter((c) => c.region_code)
                    .map((c) => [
                      c.region_code!,
                      `${c.sido_name ?? ""} ${c.sigungu_name ?? c.region_code}`,
                    ]),
                ).entries(),
              ).map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            검색
            <input
              placeholder="CCTV ID / 이름 / 도로명 검색"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
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
              {rows.map((c) => (
                <tr key={c.id}>
                  <td>{c.external_cctv_id}</td>
                  <td>{c.name}</td>
                  <td>{c.sigungu_name ?? c.region_code ?? "미확인"}</td>
                  <td>{c.address ?? "미확인"}</td>
                  <td>
                    <span
                      className={
                        "status " +
                        (c.connection_status === "CONNECTED"
                          ? "detect"
                          : "check")
                      }
                    >
                      {statusLabel(c.connection_status)}
                    </span>
                  </td>
                  <td
                    className="monitoring-notice"
                    data-mode={c.monitored_mode ?? "OFF"}
                  >
                    {monitoringLabels[c.monitored_mode ?? "OFF"]}
                  </td>
                  <td>
                    <input
                      className="switch"
                      type="checkbox"
                      role="switch"
                      aria-label={c.id + " 감시상태"}
                      checked={c.is_monitored}
                      disabled={busy !== null || loading}
                      onChange={() =>
                        show({
                          title: c.is_monitored ? "감시 중지" : "감시 시작",
                          body: `${c.name} 감시를 ${c.is_monitored ? "중지" : "시작"}할까요?${c.monitored_mode === "ALERT" ? " 특보 자동 감시 정책으로 다시 켜질 수 있습니다." : ""}`,
                          onConfirm: () => {
                            void toggleMonitoring(c);
                          },
                        })
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {loading && <p role="status">CCTV 목록 조회 중</p>}
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        {!loading && !error && rows.length === 0 && (
          <p>조건에 맞는 CCTV가 없습니다.</p>
        )}
        <p className="content-footnote">
          감시 ON/OFF는 연결·분석 상태와 별개입니다. 특보 해제 후에도 ON을
          유지합니다. 수동 변경은 확인 즉시 저장하며, 특보 중 수동 OFF도
          허용하는 현재 서버 동작을 따릅니다. 자동 특보 정책이 다시 ON으로 바꿀
          수 있습니다.
        </p>
      </Panel>
      <div className="action-row">
        <button
          className="primary"
          disabled={busy !== null}
          onClick={() => setRevision((v) => v + 1)}
        >
          현재 상태 새로고침
        </button>
        <button className="secondary" onClick={() => go("settings")}>
          시스템 설정으로 돌아가기
        </button>
      </div>
    </>
  );
}
