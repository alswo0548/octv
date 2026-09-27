import { useState } from "react";
import { mock } from "@octv/shared";
import {
  Panel,
  Pair,
  type ShowModal,
  previewMessage,
} from "../components/Primitives";
import { go } from "../routing/useRoute";
export function SettingsPage({
  tab = "analysis",
  show,
}: {
  tab?: string;
  show: ShowModal;
}) {
  const [reset, setReset] = useState(0),
    snapshot = mock.uiSnapshot.settings;
  return (
    <>
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
                  {snapshot.activeCount}
                  <small>대</small>
                </strong>
              </div>
              <button className="primary" onClick={() => go("targets")}>
                대상 선택
              </button>
            </div>
            <dl className="section-gap">
              <Pair label="특보 지역 감시" value="특보 지역 기준 자동 매핑" />
              <Pair label="특보 해제" value="기본 감시로 자동 복귀" />
            </dl>
          </Panel>
          <div className="settings-grid" key={reset}>
            {mock.settings.map((group) => (
              <Panel key={group.title} title={group.title}>
                {group.items.map(([label, value]) => (
                  <div className="field-row" key={label}>
                    <label htmlFor={label}>{label}</label>
                    <input id={label} type="text" defaultValue={value} />
                  </div>
                ))}
              </Panel>
            ))}
            <Panel title="연동 상태 · 현재 실행 확인">
              <dl>
                {snapshot.integrations.map(([k, v]) => (
                  <Pair key={k} label={k} value={v} />
                ))}
              </dl>
              <button className="text-button" onClick={() => go("monitor")}>
                CCTV 모니터링 보기 →
              </button>
              <p className="content-footnote">
                표시값은 목업입니다. 실제 연결·설정 저장은 수행하지 않습니다.
              </p>
            </Panel>
          </div>
          <div className="action-row right">
            <button
              className="secondary"
              onClick={() =>
                show({
                  title: "변경 취소",
                  body: "입력 중인 화면 값을 고정 목업 초기값으로 되돌릴까요?",
                  onConfirm: () => setReset((x) => x + 1),
                })
              }
            >
              변경 취소
            </button>
            <button
              className="primary"
              onClick={() =>
                show({
                  title: "설정 저장 확인",
                  body: previewMessage,
                  confirm: "확인 (미리보기)",
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
            {snapshot.services.map((x) => (
              <Pair
                key={x}
                label={x}
                value={<span className="status detect">정상</span>}
              />
            ))}
          </dl>
          <p className="content-footnote">
            고정 연결 상태 예시 · 실제 외부 API 연결 없음
          </p>
          <button className="text-button" onClick={() => go("monitor")}>
            CCTV 모니터링 보기 →
          </button>
        </Panel>
      )}
    </>
  );
}
