import { useState } from "react";
import { mock } from "@octv/shared";
import {
  Panel,
  Select,
  Pagination,
  type ShowModal,
  previewMessage,
} from "../components/Primitives";
import { go } from "../routing/useRoute";
export function TargetsPage({ show }: { show: ShowModal }) {
  const [reset, setReset] = useState(0);
  return (
    <>
      <a className="back-link" href="#/settings">
        ‹ 시스템 설정으로 돌아가기
      </a>
      <p>AI 모니터링에 기본으로 포함할 CCTV를 설정합니다.</p>
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
          <table key={reset}>
            <thead>
              <tr>
                {[
                  "CCTV ID",
                  "CCTV 이름",
                  "설치 지역",
                  "위치 / 도로명",
                  "현재 상태",
                  "기본 활성",
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
                    <td>
                      <input
                        className="switch"
                        type="checkbox"
                        role="switch"
                        aria-label={c.id + " 기본 활성"}
                        defaultChecked={c.active}
                      />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        <Pagination kind="targets" />
        <p className="content-footnote">
          기본 활성 여부는 CCTV 연결 상태와 별개입니다. 변경은 현재 화면에만
          표시됩니다.
        </p>
      </Panel>
      <div className="action-row">
        <button
          className="primary"
          onClick={() =>
            show({
              title: "기본 활성 설정 저장 확인",
              body: previewMessage,
              confirm: "확인 (미리보기)",
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
              body: "기본 활성의 화면 표시를 초기 목업으로 복원할까요?",
              onConfirm: () => setReset((x) => x + 1),
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
