import type { CurrentUserDto } from "@octv/shared";
import { useEffect, useState, type ReactNode } from "react";
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
  notifications,
}: {
  page: string;
  title: string;
  children: ReactNode;
  show: ShowModal;
  onLogout?: () => void;
  user?: CurrentUserDto | null;
  notifications?: ReactNode;
}) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const isAdmin = user?.role === "CONTROL_ADMIN";

  const visibleMenu = menu.filter(([id]) => !ADMIN_MENU.has(id) || isAdmin);

  const roleLabel = user ? (ROLE_LABELS[user.role] ?? user.role) : "";
  const profileName = user?.name ?? "";
  // 기관 계정 표시명에 대괄호 등 기호가 있어도 아바타에는 글자만 표시합니다.
  const avatar = profileName.match(/[가-힣A-Za-z0-9]/u)?.[0]?.toUpperCase() ?? "O";

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
            <i /> 서버 연결은 데이터 조회 시 확인
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
        <header className="octv-global-header">
          <div>
            <div className="eyebrow">
              OCTV <span>/</span> {page.toUpperCase()}
            </div>

            <h1>{title}</h1>
          </div>

          <div className="header-right">
            <time dateTime={now.toISOString()}>현재 KST {new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(now)}</time>

            {user && <span className="avatar">{avatar}</span>}
            {notifications}
          </div>
        </header>

        {children}
      </main>
    </>
  );
}
