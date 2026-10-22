import type { CurrentUserDto } from "@octv/shared";
import type { ReactNode } from "react";
import { Background } from "../components/Background";
import { Brand, type ShowModal } from "../components/Primitives";
import { go } from "../routing/useRoute";

const menu = [
  ["overview", "통합관제", "▦"],
  ["incidents", "사건관리", "▤"],
  ["monitor", "CCTV 모니터링", "▣"],
  ["stats", "CCTV 운영통계", "▥"],
  ["settings", "시스템 설정", "⚙"],
] as const;

const ADMIN_MENU = new Set(["monitor", "stats", "settings"]);

const ROLE_LABELS: Record<string, string> = {
  CONTROL_ADMIN: "상황실 관리자",
  AGENCY_STAFF: "기관 담당자",
  RESPONDER: "현장 담당자",
};

export function WebLayout({
  page,
  title,
  children,
  show,
  onLogout,
  user,
}: {
  page: string;
  title: string;
  children: ReactNode;
  show: ShowModal;
  onLogout?: () => void;
  user?: CurrentUserDto | null;
}) {
  const isAdmin = user?.role === "CONTROL_ADMIN";

  const visibleMenu = menu.filter(([id]) => !ADMIN_MENU.has(id) || isAdmin);

  const roleLabel = user ? (ROLE_LABELS[user.role] ?? user.role) : "";
  const profileName = user?.name ?? "";
  const avatar = profileName.trim().charAt(0) || "O";

  return (
    <>
      <Background />

      <aside>
        <Brand />

        <div className="navlabel">WORKSPACE</div>

        <nav>
          {visibleMenu.map(([id, name, icon]) => (
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
            <i /> 서버 상태 미확인
          </div>

          {user && (
            <>
              <small>
                {user.agency_name ??
                  (user.role === "CONTROL_ADMIN"
                    ? "OCTV 상황실"
                    : "소속기관 미확인")}
              </small>

              <div className="profile">
                <span>{avatar}</span>

                <div>
                  {profileName}
                  <small>{roleLabel}</small>
                </div>
              </div>
            </>
          )}

          {user && (
            <button
              className="side-logout"
              onClick={() =>
                show({
                  title: "로그아웃",
                  body: "로그인 화면으로 이동할까요?",
                  confirm: "로그아웃",
                  onConfirm: onLogout ?? (() => go("login")),
                })
              }
            >
              로그아웃
            </button>
          )}
        </div>
      </aside>

      <main>
        <header>
          <div>
            <div className="eyebrow">
              OCTV <span>/</span> {page.toUpperCase()}
            </div>

            <h1>{title}</h1>
          </div>

          <div className="header-right">
            <time>사건 시각 KST 기준</time>

            <span className="signal">
              <i /> 미확인
            </span>

            {user && <span className="avatar">{avatar}</span>}
          </div>
        </header>

        {children}
      </main>
    </>
  );
}
