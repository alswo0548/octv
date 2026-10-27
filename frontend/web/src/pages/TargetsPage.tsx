import { useState } from "react";

/**
 * 기존 CCTV 목록·감시 API 연결.
 * 저장 결과 재조회 후 표시하며 특보 Runtime 정책은 바꾸지 않습니다.
 */

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
import { isTestCamera } from "../cameraVisibility";

/**
 * connection_status는 브라우저의 WebRTC 영상 재생 상태가 아니라
 * CCTV Runtime의 프레임 수집 연결 상태입니다.
 *
 * W04와 동일한 용어를 사용해
 * 웹 영상 연결 상태와 혼동하지 않도록 합니다.
 */
function captureConnectionLabel(value: string | null) {
  if (value === "CONNECTED") {
    return "수집 연결됨";
  }

  if (value === "DISCONNECTED") {
    return "수집 연결 끊김";
  }

  if (value === "RECONNECTING") {
    return "수집 재연결 중";
  }

  return statusLabel(value);
}

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
    10_000,
  );

  const [busy, setBusy] = useState<number | null>(null);

  const [message, setMessage] = useState<string | null>(null);

  const [region, setRegion] = useState("");

  const [query, setQuery] = useState("");

  const rows = (data ?? []).filter(
    (camera) => !isTestCamera(camera) &&
      (!region || camera.region_code === region) &&
      `${camera.external_cctv_id} ${camera.name} ${camera.address ?? ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );

  async function toggleMonitoring(camera: Cctv) {
    if (busy !== null) {
      return;
    }

    setBusy(camera.id);

    setMessage(null);

    try {
      await requestWebApi(
        session.version,
        `/api/cctvs/${camera.id}/monitoring`,
        {
          method: "PATCH",

          body: JSON.stringify({
            enabled: !camera.is_monitored,
          }),
        },
      );

      setMessage(
        camera.is_monitored
          ? "감시를 중지했습니다. " +
              "해당 CCTV의 웹 스트림 준비도 함께 종료됩니다."
          : "감시를 시작했습니다. " +
              "실시간 영상 확인을 위해 스트림을 미리 준비합니다.",
      );
    } catch (reason) {
      setMessage(operationsError(reason));
    } finally {
      setBusy(null);

      setRevision((value) => value + 1);
    }
  }

  return (
    <>
      <a className="back-link" href="#/settings">
        ‹ 시스템 설정으로 돌아가기
      </a>

      <p>대상 CCTV의 수집 연결 상태와 AI 감시 상태를 확인합니다. DEMO CCTV는 모니터링 화면의 시연 시작·종료로 일괄 제어합니다.</p>

      <Panel title="CCTV 목록">
        <div className="monitor-filter">
          <label>
            지역
            <select
              value={region}
              onChange={(event) => setRegion(event.target.value)}
            >
              <option value="">전체 지역</option>

              {Array.from(
                new Map(
                  (data ?? [])
                    .filter((camera) => camera.region_code)
                    .map((camera) => [
                      camera.region_code!,
                      `${camera.sido_name ?? ""} ${
                        camera.sigungu_name ?? camera.region_code
                      }`,
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
              placeholder="CCTV ID / 이름 검색"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
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
                  "수집 연결 상태",
                  "감시 안내",
                  "감시상태",
                ].map((title) => (
                  <th key={title}>{title}</th>
                ))}
              </tr>
            </thead>

            <tbody>
              {rows.map((camera) => (
                <tr key={camera.id}>
                  <td>{camera.external_cctv_id}</td>

                  <td>{camera.name}</td>

                  <td>
                    {camera.sigungu_name ?? camera.region_code ?? "미확인"}
                  </td>

                  <td>
                    <span
                      className={
                        "status " +
                        (camera.connection_status === "CONNECTED"
                          ? "detect"
                          : "check")
                      }
                    >
                      {captureConnectionLabel(camera.connection_status)}
                    </span>
                  </td>

                  <td
                    className="monitoring-notice"
                    data-mode={camera.monitored_mode ?? "OFF"}
                  >
                    {monitoringLabels[camera.monitored_mode ?? "OFF"]}
                  </td>

                  <td>
                    <input
                      className="switch"
                      type="checkbox"
                      role="switch"
                      aria-label={camera.id + " 감시상태"}
                      checked={camera.is_monitored}
                      disabled={busy !== null || loading || camera.provider === "DEMO"}
                      onChange={() =>
                        show({
                          title: camera.is_monitored
                            ? "감시 중지"
                            : "감시 시작",

                          body: `${camera.name} 감시를 ${
                            camera.is_monitored ? "중지" : "시작"
                          }할까요?${
                            camera.monitored_mode === "ALERT"
                              ? " 특보 자동 감시 정책으로 " +
                                "다시 켜질 수 있습니다."
                              : ""
                          }`,

                          onConfirm: () => {
                            void toggleMonitoring(camera);
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
          수집 연결 상태는 CCTV Runtime의 프레임 수집 상태입니다. CCTV 모니터링
          화면의 실시간 영상 재생 상태와는 별도로 표시됩니다. 감시 ON 시 실시간
          영상 스트림을 미리 준비하고, OFF 시 해당 스트림을 종료합니다.
        </p>

        <p className="content-footnote">
          감시 ON/OFF와 실제 수집·분석 상태는 별개입니다. 특보 해제 후에도
          감시는 ON을 유지하며 관리자 확인 후 수동으로 종료할 수 있습니다.
        </p>
      </Panel>

      <div className="action-row">
        <button
          className="primary"
          disabled={busy !== null}
          onClick={() => setRevision((value) => value + 1)}
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
