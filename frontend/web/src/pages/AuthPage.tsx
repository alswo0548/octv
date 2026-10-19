/**
 * 기존 로그인 API → JWT 본인 확인 → 웹 사건 세션 연결.
 * JWT는 이 로그인에만 묶인 메모리에 보관하고 로그아웃 시 폐기합니다.
 * 로그인 중 화면 이동·로그아웃이 발생하면 늦은 응답을 사용하지 않습니다.
 */
import type { LoginDto } from "@octv/shared";
import { useEffect, useRef, useState } from "react";
import { ApiError, createApi, getCurrentUser } from "../api";
import { Brand, Select, type ShowModal } from "../components/Primitives";
import {
  disconnectWebIncidentSession,
  setWebIncidentSession,
  subscribeWebIncidentSession,
} from "../incidentData";
import { go } from "../routing/useRoute";
export function AuthPage({
  signup = false,
  show,
}: {
  signup?: boolean;
  show: ShowModal;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingLogin = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      pendingLogin.current?.abort();
      pendingLogin.current = null;
    };
  }, []);

  async function login() {
    // state가 화면에 반영되기 전의 연속 제출도 같은 ref로 차단합니다.
    if (signup || pendingLogin.current) return;
    if (!email.trim() || !password) {
      setError("이메일과 비밀번호를 입력해주세요.");
      return;
    }
    const controller = new AbortController();
    pendingLogin.current = controller;
    setLoggingIn(true);
    setError(null);
    let token: string | null = null;
    let connected = false;
    let unsubscribe = () => {};
    const isCurrent = () =>
      pendingLogin.current === controller && !controller.signal.aborted;
    const cancel = () => {
      token = null;
      unsubscribe();
    };
    controller.signal.addEventListener("abort", cancel, { once: true });

    try {
      // 앞선 계정의 세션을 정리한 뒤, 이후의 로그아웃·계정 변경을 감지합니다.
      const previousLogout = disconnectWebIncidentSession();
      unsubscribe = subscribeWebIncidentSession(() => {
        controller.abort();
        if (pendingLogin.current === controller) {
          pendingLogin.current = null;
          setLoggingIn(false);
          setPassword("");
        }
      });
      await previousLogout;
      if (!isCurrent()) return;

      // 설정이 비어 있으면 기존 Vite /api 프록시를 사용합니다.
      const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
      const anonymousApi = createApi(baseUrl, () => null);
      const response = await anonymousApi<LoginDto>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password }),
        signal: controller.signal,
      });
      if (!isCurrent()) return;
      if (
        !response ||
        typeof response.access_token !== "string" ||
        !response.access_token.trim() ||
        response.token_type?.toLowerCase() !== "bearer" ||
        !Number.isSafeInteger(response.user?.id) ||
        response.user.id <= 0
      ) {
        setError("로그인 응답을 확인할 수 없습니다. 다시 시도해주세요.");
        return;
      }

      token = response.access_token;
      const api = createApi(baseUrl, () => token);
      const user = await getCurrentUser((path, options) => {
        if (!isCurrent()) return Promise.reject(new Error("취소된 로그인"));
        return api(path, { ...options, signal: controller.signal });
      });
      if (!isCurrent()) return;
      if (user.id !== response.user.id) {
        setError(
          "로그인 사용자 정보를 확인할 수 없습니다. 다시 로그인해주세요.",
        );
        return;
      }
      if (user.role !== "CONTROL_ADMIN" || user.is_active !== true) {
        setError("활성 상황실 관리자 계정으로 로그인해주세요.");
        return;
      }

      // 인계가 끝난 JWT는 화면 이동 시 지우지 않고, 세션의 logout에서 지웁니다.
      unsubscribe();
      setWebIncidentSession({
        user,
        api,
        getToken: () => token,
        baseUrl,
        logout: () => {
          token = null;
        },
      });
      connected = true;
      pendingLogin.current = null;
      setPassword("");
      setLoggingIn(false);
      go("overview");
    } catch (cause) {
      if (!isCurrent()) return;
      // 서버 응답 본문이나 인증값을 오류 메시지에 그대로 출력하지 않습니다.
      setError(
        cause instanceof ApiError && cause.status === 401
          ? "로그인 정보를 확인할 수 없습니다. 이메일과 비밀번호를 확인해주세요."
          : cause instanceof ApiError && cause.status === 403
            ? "사용할 수 없는 계정입니다. 계정 상태를 확인해주세요."
            : cause instanceof ApiError && cause.status === 422
              ? "이메일 형식과 입력값을 확인해주세요."
              : "로그인을 완료하지 못했습니다. 서버 연결을 확인한 뒤 다시 시도해주세요.",
      );
    } finally {
      unsubscribe();
      controller.signal.removeEventListener("abort", cancel);
      if (!connected) token = null;
      if (pendingLogin.current === controller) {
        pendingLogin.current = null;
        setLoggingIn(false);
      }
    }
  }

  return (
    <div className={"auth-wrap " + (signup ? "signup" : "")}>
      <section className="panel auth-panel">
        <div className="auth-brand">
          <Brand />
        </div>
        <h2>{signup ? "회원가입" : "상황실 로그인"}</h2>
        <p className="intro">
          {signup
            ? "소속기관과 계정 정보를 입력해주세요."
            : "재난 대응 정보를 한눈에 확인하세요."}
        </p>
        <form
          className="form-stack"
          noValidate
          aria-busy={loggingIn}
          onSubmit={(e) => {
            e.preventDefault();
            if (!signup) void login();
          }}
        >
          {signup && (
            <label>
              이름
              <input placeholder="이름" autoComplete="off" />
            </label>
          )}
          <label htmlFor="auth-email">이메일</label>
          <div className="input-action">
            <input
              id="auth-email"
              aria-label="이메일"
              type="email"
              placeholder="name@example.com"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loggingIn}
            />
            {signup && (
              <button
                type="button"
                className="secondary email-check"
                onClick={() =>
                  show({
                    title: "이메일 중복 확인",
                    body: "이 화면에서는 이메일 중복 여부를 조회하지 않습니다.",
                    confirm: "확인",
                    cancel: "",
                  })
                }
              >
                이메일 중복 확인
              </button>
            )}
          </div>
          <label>
            비밀번호
            <input
              type="password"
              autoComplete={signup ? "new-password" : "current-password"}
              placeholder="비밀번호"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loggingIn}
            />
          </label>
          {signup && (
            <>
              <label>
                비밀번호 확인
                <input type="password" autoComplete="new-password" />
              </label>
              <Select
                label="계정 유형"
                options={["기관 담당자", "현장 담당자", "상황실 관리자"]}
              />
              <div className="form-grid">
                <Select label="시·도" options={["서울특별시", "경기도"]} />
                <Select
                  label="시·군·구"
                  options={["강남구", "서대문구", "구리시"]}
                />
                <Select
                  label="기관 유형"
                  options={["소방", "경찰", "도로관리", "지자체"]}
                />
                <Select
                  label="소속기관"
                  options={["강남소방서", "강남구청 도로관리과", "역삼소방서"]}
                />
              </div>
            </>
          )}
          {!signup && error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button
            type={signup ? "button" : "submit"}
            className="primary"
            disabled={loggingIn}
            onClick={
              signup
                ? () =>
                    show({
                      title: "회원가입 완료",
                      body: (
                        <>
                          <p>홍길동 · 현장 담당자 · 강남소방서</p>
                          <p>등록 정보를 확인해주세요.</p>
                        </>
                      ),
                      confirm: "로그인으로 이동",
                      onConfirm: () => go("login"),
                    })
                : undefined
            }
          >
            {signup ? "회원가입" : loggingIn ? "로그인 확인 중…" : "로그인"}
          </button>
        </form>
        <div className="auth-links">
          {signup ? "이미 계정이 있으신가요?" : "계정이 없으신가요?"}{" "}
          <a href={signup ? "#/login" : "#/signup"}>
            {signup ? "로그인" : "회원가입"}
          </a>
        </div>
      </section>
    </div>
  );
}
