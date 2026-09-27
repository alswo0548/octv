import { mock } from "@octv/shared";
import { useEffect, useRef, useState, type ReactNode } from "react";
export const Brand = () => (
  <a
    className="brand octv-brand"
    href="#/overview"
    aria-label="OCTV · Open Circuit Television"
  >
    <img
      className="octv-symbol"
      src="/assets/octv-symbol.png"
      width="38"
      height="38"
      alt=""
    />
    <span className="octv-wordmark">
      OCTV<small>OPEN CIRCUIT TELEVISION</small>
    </span>
  </a>
);
export const Panel = ({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) => (
  <section className={"panel page-section " + className}>
    {title && (
      <div className="section-title">
        <h2>{title}</h2>
      </div>
    )}
    {children}
  </section>
);
export const Badge = ({ priority }: { priority: string }) => (
  <span className={"badge " + priority}>{priority}</span>
);
export const Pair = ({ label, value }: { label: string; value: ReactNode }) => (
  <div>
    <dt>{label}</dt>
    <dd>{value}</dd>
  </div>
);
export function Select({
  label,
  options,
}: {
  label: string;
  options: string[];
}) {
  return (
    <label>
      {label}
      <select defaultValue={options[0]}>
        {options.map((v) => (
          <option key={v}>{v}</option>
        ))}
      </select>
    </label>
  );
}
export function Segments({
  options,
  initial,
}: {
  options: string[];
  initial?: string;
}) {
  const [active, set] = useState(initial || options[0]);
  return (
    <div className="segments">
      {options.map((v) => (
        <button
          type="button"
          key={v}
          className={v === active ? "selected" : ""}
          aria-pressed={v === active}
          onClick={() => set(v)}
        >
          {v}
        </button>
      ))}
    </div>
  );
}
export function Pagination({
  kind = "incidents",
}: {
  kind?: "incidents" | "targets";
}) {
  const [page, set] = useState("1");
  return (
    <div className="table-footer">
      <span>{mock.uiSnapshot.pagination[kind]}</span>
      <div className="pagination">
        {mock.uiSnapshot.pagination.pages.map((v) => (
          <button
            key={v}
            className={page === v ? "current" : ""}
            onClick={() => set(v)}
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}
export type ModalSpec = {
  title: string;
  body: ReactNode;
  confirm?: string;
  onConfirm?: () => void;
  cancel?: string;
};
export function Modal({
  spec,
  close,
}: {
  spec: ModalSpec | null;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (spec) ref.current?.showModal();
    else ref.current?.close();
  }, [spec]);
  if (!spec) return null;
  return (
    <dialog ref={ref} onCancel={close} aria-label={spec.title}>
      <div className="modal-head">
        <h2>{spec.title}</h2>
        <button className="close" onClick={close} aria-label="닫기">
          ×
        </button>
      </div>
      <div className="confirm-message">{spec.body}</div>
      <div className="confirm-actions">
        {spec.cancel !== "" && (
          <button className="secondary" onClick={close}>
            {spec.cancel || "취소"}
          </button>
        )}
        <button
          className="primary"
          onClick={() => {
            close();
            spec.onConfirm?.();
          }}
        >
          {spec.confirm || "확인"}
        </button>
      </div>
    </dialog>
  );
}
export type ShowModal = (spec: ModalSpec) => void;
export const previewMessage =
  "UI 확인 화면입니다. 입력값 검사·저장·전송은 수행하지 않습니다.";
export function ActionPreview({
  label,
  show,
}: {
  label: string;
  show: ShowModal;
}) {
  return (
    <button
      className="secondary"
      onClick={() => show({ title: label, body: previewMessage, cancel: "" })}
    >
      {label}
    </button>
  );
}
