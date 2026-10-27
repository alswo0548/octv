/** 관리자 설정 조회→입력 검증→기존 행 저장. Runtime 적용 시점과 미연결 필드를 구분합니다. */
import { useEffect, useState } from "react";
import {
  formatSeoulTime,
  requestWebApi,
  type WebIncidentSession,
} from "../incidentData";
import {
  useOperations,
  operationsError,
  type MonitoringSettings,
  type SettingsValues,
  type Cctv,
} from "../operationsData";
import { Panel, Pair, type ShowModal } from "../components/Primitives";
import { go } from "../routing/useRoute";
type IntegrationEvidence = {
  weather: { status: string; detail: string };
  water: { status: string; detail: string };
  traffic: { status: string; detail: string };
  kakao: { status: string; detail: string };
  fcm: { status: string; detail: string };
  disclaimer: string;
};

export function SettingsPage({
  tab = "analysis",
  show,
  session,
}: {
  tab?: string;
  show: ShowModal;
  session: WebIncidentSession;
}) {
  const [revision, setRevision] = useState(0);
  const settings = useOperations<MonitoringSettings>(
    session,
    "/api/settings/monitoring",
    revision,
  );
  const cameras = useOperations<Cctv[]>(session, "/api/cctvs", revision);
  const evidence = useOperations<IntegrationEvidence>(
    session, tab === "integrations" ? "/api/dashboard/integration-evidence" : null,
    revision, 30_000,
  );
  const [draft, setDraft] = useState<SettingsValues | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    if (!settings.data) {
      setDraft(null);
      return;
    }
    const {
      id: _id,
      updated_by: _by,
      updated_at: _at,
      application: _app,
      ...values
    } = settings.data;
    setDraft(values);
  }, [settings.data]);
  const groups: { title: string; items: [keyof SettingsValues, string][] }[] = [
    {
      title: "분석 주기",
      items: [
        ["base_analysis_interval_sec", "기본 분석 주기 (초)"],
        ["alert_analysis_interval_sec", "특보 분석 주기 (초)"],
        ["verify_analysis_interval_sec", "집중 분석 주기 (초)"],
      ],
    },
    {
      title: "사건 후보 · 연결 대기",
      items: [
        ["candidate_confidence_threshold", "후보 신뢰도 (0~1)"],
        ["candidate_min_detection_count", "후보 최소 탐지 횟수"],
        ["temporal_validation_sec", "시간 검증 기준 (초)"],
        ["incident_confidence_threshold", "사건 확정 신뢰도 (0~1)"],
      ],
    },
    {
      title: "영상 품질 · 재연결",
      items: [
        ["quality_threshold", "영상 품질 기준 (0~1)"],
        ["reconnect_interval_sec", "재연결 주기 (초)"],
        ["max_reconnect_attempts", "최대 재연결 횟수"],
      ],
    },
  ];
  const save = async () => {
    if (!draft || saving) return;
    const valid = Object.entries(draft).every(([key, value]) => {
      const n = Number(value);
      const threshold = key.includes("threshold");
      return (
        value !== "" &&
        Number.isFinite(n) &&
        (threshold
          ? n >= 0 &&
            n <= 1 &&
            Math.abs(n * 10000 - Math.round(n * 10000)) < 1e-7
          : Number.isInteger(n) && n > 0 && n <= 2147483647)
      );
    });
    if (!valid) {
      setMessage(
        "주기·횟수는 양의 정수, 임계값은 0~1 (소수 4자리 이내)로 입력해주세요.",
      );
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      await requestWebApi(session.version, "/api/settings/monitoring", {
        method: "PUT",
        body: JSON.stringify(draft),
      });
      setMessage("DB에 저장했습니다. 항목별 Runtime 반영 시점을 확인해주세요.");
    } catch (error) {
      setMessage(operationsError(error));
    } finally {
      setSaving(false);
      setRevision((v) => v + 1);
    }
  };
  return (
    <>
      {(settings.loading || saving) && (
        <p role="status">{saving ? "설정 저장 중" : "설정 조회 중"}</p>
      )}
      {settings.error && (
        <p role="alert">
          {settings.error}{" "}
          <button onClick={() => setRevision((v) => v + 1)}>다시 조회</button>
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab !== "integrations"}
          className={tab !== "integrations" ? "active" : ""}
          onClick={() => go("settings")}
        >
          감시·분석 설정
        </button>
        <button
          role="tab"
          aria-selected={tab === "integrations"}
          className={tab === "integrations" ? "active" : ""}
          onClick={() => go("settings/integrations")}
        >
          연동 상태
        </button>
      </div>
      {tab !== "integrations" ? (
        <>
          <Panel title="감시 대상">
            <div className="settings-summary">
              <div>
                <span className="subtle">기본 감시 CCTV</span>
                <br />
                <strong>
                  {cameras.data?.filter((c) => c.is_monitored).length ?? "–"}
                  <small>대</small>
                </strong>
              </div>
              <button className="primary" onClick={() => go("targets")}>
                대상 CCTV ON/OFF 설정
              </button>
            </div>
            <dl className="section-gap">
              <Pair label="특보 지역 감시" value="특보 지역 기준 자동 매핑" />
              <Pair
                label="특보 발령 중"
                value="감시 ON · 수동 OFF는 현재 서버 정책을 따름"
              />
              <Pair
                label="특보 해제"
                value="감시 ON 유지 · 관리자 확인 후 수동 OFF"
              />
            </dl>
          </Panel>
          <div className="settings-grid">
            {groups.map((group) => (
              <Panel key={group.title} title={group.title}>
                {group.items.map(([key, label]) => (
                  <div key={key} className="setting-item">
                    <div className="field-row">
                      <label htmlFor={key}>{label}</label>
                      <input
                        id={key}
                        type="number"
                        min={key.includes("threshold") ? 0 : 1}
                        max={key.includes("threshold") ? 1 : 2147483647}
                        step={key.includes("threshold") ? 0.0001 : 1}
                        value={draft?.[key] ?? ""}
                        disabled={
                          !draft ||
                          saving ||
                          settings.data?.application[key].mode ===
                            "NOT_CONNECTED"
                        }
                        onChange={(e) =>
                          setDraft((current) =>
                            current
                              ? {
                                  ...current,
                                  [key]:
                                    e.target.value === ""
                                      ? ""
                                      : Number(e.target.value),
                                }
                              : null,
                          )
                        }
                      />
                    </div>
                  </div>
                ))}
              </Panel>
            ))}
            <Panel title="연동 상태 · 현재 실행 확인">
              <dl>
                <Pair
                  label="수정 사용자"
                  value={
                    settings.data?.updated_by == null
                      ? "기록 없음"
                      : `사용자 #${settings.data.updated_by}`
                  }
                />
                <Pair
                  label="최근 수정 (KST)"
                  value={
                    settings.data
                      ? formatSeoulTime(settings.data.updated_at)
                      : "미조회"
                  }
                />

              </dl>
              <button className="text-button" onClick={() => go("monitor")}>
                CCTV 모니터링 보기 →
              </button>
            </Panel>
          </div>
          <div className="action-row right">
            <button
              className="secondary"
              onClick={() =>
                show({
                  title: "변경 취소",
                  body: "입력을 취소하고 DB 저장값을 다시 조회할까요?",
                  onConfirm: () => {
                    setMessage(null);
                    setRevision((v) => v + 1);
                  },
                })
              }
            >
              변경 취소
            </button>
            <button
              className="primary"
              disabled={!draft || saving}
              onClick={() =>
                show({
                  title: "설정 저장 확인",
                  body: "연결된 감시 설정을 저장할까요? 재연결 설정은 기존 Runtime 재시작이 필요합니다.",
                  confirm: "저장",
                  onConfirm: () => {
                    void save();
                  },
                })
              }
            >
              변경사항 저장
            </button>
          </div>
        </>
      ) : (
        <Panel title="외부 서비스 연동 상태">
          <dl>
            {([
              ["기상청", "weather"], ["수위", "water"], ["교통", "traffic"],
              ["카카오 경로", "kakao"], ["FCM", "fcm"],
            ] as const).map(([name, key]) => {
              const entry = evidence.data?.[key];
              return <Pair key={key} label={name} value={
                <span className={entry?.status === "RECORDED" ? "status detect" : "status check"}>
                  {entry?.status === "RECORDED" ? "저장 기록 확인" : "실제 응답 미검증"}
                  <small className="octv-evidence-detail">
                    {entry?.detail ?? (evidence.loading ? "기록 확인 중" : "증거 조회 필요")}
                  </small>
                </span>
              } />;
            })}
            <Pair label="CCTV Runtime" value={cameras.data
              ? <span className={cameras.data.some(c => c.is_monitored && c.connection_status === "CONNECTED") ? "status detect" : "status check"}>
                  감시 중 수집 연결 {cameras.data.filter(c => c.is_monitored && c.connection_status === "CONNECTED").length}대
                </span>
              : <span className="status check">연결 조회 필요</span>} />
          </dl>
          {evidence.error && <p role="alert">연동 기록 조회 오류 · {evidence.error}</p>}
          <p className="content-footnote">{evidence.data?.disclaimer ?? "DB 기록과 실제 API 응답은 구분합니다."} CCTV 수집 연결과 영상 재생도 별도 상태입니다.</p>
          <button className="secondary" type="button" onClick={() => setRevision(v => v + 1)}>연동 기록 새로고침</button>
          <button className="text-button" onClick={() => go("monitor")}>
            CCTV 모니터링 보기 →
          </button>
        </Panel>
      )}
    </>
  );
}
