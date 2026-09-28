import { mock } from "@octv/shared";
import { type ReactNode } from "react";
import { Background } from "../components/Background";
import { Brand, type ShowModal } from "../components/Primitives";
import { go } from "../routing/useRoute";
const menu = [
  ["overview", "통합관제", "▦"],
  ["incidents", "사건관리", "▤"],
  ["monitor", "CCTV 모니터링", "▣"],
  ["stats", "CCTV 운영통계", "▥"],
  ["settings", "시스템 설정", "⚙"],
];
export function WebLayout({
  page,
  title,
  children,
  show,
}: {
  page: string;
  title: string;
  children: ReactNode;
  show: ShowModal;
}) {
  return (
    <>
      <Background />
      <aside>
        <Brand />
        <div className="navlabel">WORKSPACE</div>
        <nav>
          {menu.map(([id, name, icon]) => (
            <button
              key={id}
              className={
                page === id ||
                (page === "routes" && id === "incidents") ||
                (page === "targets" && id === "settings")
                  ? "active"
                  : ""
              }
              onClick={() => go(id)}
            >
              <span>{icon}</span>
              {name}
            </button>
          ))}
        </nav>
        <div className="side-foot">
          <div className="signal">
            <i /> 시스템 정상
          </div>
          <small>119 종합상황실</small>
          <div className="profile">
            <span>관</span>
            <div>
              관리자<small>상황실 운영자</small>
            </div>
          </div>
          <button
            className="side-logout"
            onClick={() =>
              show({
                title: "로그아웃",
                body: "로그인 화면으로 이동할까요?",
                confirm: "로그아웃",
                onConfirm: () => go("login"),
              })
            }
          >
            로그아웃
          </button>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <div className="eyebrow">
              CONTROL CENTER <span>/</span> {page.toUpperCase()}
            </div>
            <h1>{title}</h1>
          </div>
          <div className="header-right">
            <time>
              {mock.uiSnapshot.header.date} <b>{mock.uiSnapshot.header.time}</b>
            </time>
            <span className="signal">
              <i /> 정상
            </span>
            <span className="avatar">관</span>
          </div>
        </header>
        {children}
      </main>
    </>
  );
}
