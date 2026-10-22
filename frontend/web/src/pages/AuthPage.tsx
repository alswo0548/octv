/**
 * WEB 인증 화면
 *
 * 로그인:
 * - 기존 /api/auth/login 사용
 * - JWT 본인 확인 후 웹 사건 세션 연결
 * - CONTROL_ADMIN / AGENCY_STAFF / RESPONDER 로그인 허용
 *
 * 회원가입:
 * - 이메일 중복 확인
 * - 시·도 → 시·군·구 → 기관유형 → 소속기관 조회
 * - AGENCY_STAFF / RESPONDER 가입
 * - CONTROL_ADMIN은 공개 회원가입에서 생성하지 않음
 */
import type {
  EmailCheckDto,
  LoginDto,
  SignupAgencyDto,
  SignupAgencyType,
  SignupRole,
  SignupSidoDto,
  SignupSigunguDto,
  UserDto,
} from "@octv/shared";

import { useEffect, useRef, useState } from "react";

import { ApiError, createApi, getCurrentUser } from "../api";
import { Brand, Select, type ShowModal } from "../components/Primitives";

import {
  disconnectWebIncidentSession,
  setWebIncidentSession,
  subscribeWebIncidentSession,
} from "../incidentData";

import { go } from "../routing/useRoute";

const ROLE_LABELS: Record<SignupRole, string> = {
  AGENCY_STAFF: "기관 담당자",
  RESPONDER: "현장 담당자",
};

const AGENCY_TYPE_OPTIONS: {
  label: string;
  value: SignupAgencyType;
}[] = [
  {
    label: "소방",
    value: "FIRE",
  },
  {
    label: "경찰",
    value: "POLICE",
  },
  {
    label: "도로관리",
    value: "ROAD_MANAGEMENT",
  },
  {
    label: "지자체",
    value: "LOCAL_GOVERNMENT",
  },
];

function validateSignupPassword(value: string): string | null {
  if (value.length < 8 || value.length > 10) {
    return "비밀번호는 8~10자여야 합니다.";
  }

  if (!/[A-Za-z]/.test(value)) {
    return "비밀번호에는 영문자가 포함되어야 합니다.";
  }

  if (!/\d/.test(value)) {
    return "비밀번호에는 숫자가 포함되어야 합니다.";
  }

  if (/\s/.test(value)) {
    return "비밀번호에는 공백을 사용할 수 없습니다.";
  }

  if (!/[^A-Za-z0-9]/.test(value)) {
    return "비밀번호에는 특수문자가 포함되어야 합니다.";
  }

  return null;
}

export function AuthPage({
  signup = false,
  show,
}: {
  signup?: boolean;
  show: ShowModal;
}) {
  // =========================================================
  // 공통 입력값
  // =========================================================

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState<string | null>(null);

  // =========================================================
  // 로그인
  // =========================================================

  const [loggingIn, setLoggingIn] = useState(false);

  const pendingLogin = useRef<AbortController | null>(null);

  // =========================================================
  // 회원가입 기본정보
  // =========================================================

  const [name, setName] = useState("");

  const [passwordConfirm, setPasswordConfirm] = useState("");

  const [role, setRole] = useState<SignupRole>("AGENCY_STAFF");

  const [checkedEmail, setCheckedEmail] = useState<string | null>(null);

  const [checkingEmail, setCheckingEmail] = useState(false);

  const [signingUp, setSigningUp] = useState(false);

  // =========================================================
  // 회원가입 지역 / 기관
  // =========================================================

  const [sidos, setSidos] = useState<SignupSidoDto[]>([]);

  const [sido, setSido] = useState("");

  const [sigungus, setSigungus] = useState<SignupSigunguDto[]>([]);

  const [regionCode, setRegionCode] = useState("");

  const [agencyType, setAgencyType] = useState<SignupAgencyType>("FIRE");

  const [agencies, setAgencies] = useState<SignupAgencyDto[]>([]);

  const [agencyId, setAgencyId] = useState("");

  // =========================================================
  // API
  // =========================================================

  const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").trim();

  const anonymousApi = createApi(baseUrl, () => null);

  const busy = loggingIn || signingUp;

  // =========================================================
  // 로그인 중 화면을 나가면 진행 중 요청 취소
  // =========================================================

  useEffect(() => {
    return () => {
      pendingLogin.current?.abort();
      pendingLogin.current = null;
    };
  }, []);

  // =========================================================
  // 회원가입: 시·도 조회
  // =========================================================

  useEffect(() => {
    if (!signup || sidos.length > 0) {
      return;
    }

    let active = true;

    void anonymousApi<SignupSidoDto[]>("/api/auth/signup/sidos")
      .then((result) => {
        if (!active) {
          return;
        }

        setSidos(result);

        const first = result[0]?.sido_name ?? "";

        setSido(first);
      })
      .catch(() => {
        if (!active) {
          return;
        }

        setError("지역 정보를 불러오지 못했습니다.");
      });

    return () => {
      active = false;
    };
  }, [signup, sidos.length]);

  // =========================================================
  // 회원가입: 시·군·구 조회
  // =========================================================

  useEffect(() => {
    if (!signup || !sido) {
      return;
    }

    let active = true;

    // 상위 선택이 바뀌면 하위 선택 초기화
    setSigungus([]);
    setRegionCode("");
    setAgencies([]);
    setAgencyId("");

    void anonymousApi<SignupSigunguDto[]>(
      "/api/auth/signup/sigungus" + `?sido_name=${encodeURIComponent(sido)}`,
    )
      .then((result) => {
        if (!active) {
          return;
        }

        setSigungus(result);

        setRegionCode(result[0]?.region_code ?? "");
      })
      .catch(() => {
        if (!active) {
          return;
        }

        setError("시·군·구 정보를 불러오지 못했습니다.");
      });

    return () => {
      active = false;
    };
  }, [signup, sido]);

  // =========================================================
  // 회원가입: 기관 조회
  // =========================================================

  useEffect(() => {
    if (!signup || !regionCode) {
      return;
    }

    let active = true;

    setAgencies([]);
    setAgencyId("");

    void anonymousApi<SignupAgencyDto[]>(
      "/api/auth/signup/agencies" +
        `?region_code=${encodeURIComponent(regionCode)}` +
        `&agency_type=${encodeURIComponent(agencyType)}`,
    )
      .then((result) => {
        if (!active) {
          return;
        }

        setAgencies(result);

        setAgencyId(result[0] ? String(result[0].id) : "");
      })
      .catch(() => {
        if (!active) {
          return;
        }

        setError("소속기관 정보를 불러오지 못했습니다.");
      });

    return () => {
      active = false;
    };
  }, [signup, regionCode, agencyType]);

  // =========================================================
  // 로그인
  // =========================================================

  async function login() {
    // state가 반영되기 전
    // 연속 제출도 ref로 막습니다.
    if (signup || pendingLogin.current) {
      return;
    }

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

    controller.signal.addEventListener("abort", cancel, {
      once: true,
    });

    try {
      // 이전 로그인 세션 제거
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

      if (!isCurrent()) {
        return;
      }

      const loginApi = createApi(baseUrl, () => null);

      const response = await loginApi<LoginDto>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          password,
        }),
        signal: controller.signal,
      });

      if (!isCurrent()) {
        return;
      }

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
        if (!isCurrent()) {
          return Promise.reject(new Error("취소된 로그인"));
        }

        return api(path, {
          ...options,
          signal: controller.signal,
        });
      });

      if (!isCurrent()) {
        return;
      }

      if (user.id !== response.user.id) {
        setError(
          "로그인 사용자 정보를 확인할 수 없습니다. 다시 로그인해주세요.",
        );

        return;
      }

      // WEB 접속 가능 역할
      if (
        user.is_active !== true ||
        !["CONTROL_ADMIN", "AGENCY_STAFF", "RESPONDER"].includes(user.role)
      ) {
        setError("사용할 수 없는 계정입니다.");

        return;
      }

      // 기관 사용자에게는 소속기관 필요
      if (user.role !== "CONTROL_ADMIN" && !user.agency_id) {
        setError("소속기관 정보가 없는 계정입니다.");

        return;
      }

      // JWT는 이후 웹 세션에서 사용
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
      if (!isCurrent()) {
        return;
      }

      setError(
        cause instanceof ApiError && cause.status === 401
          ? "로그인 정보를 확인할 수 없습니다. " +
              "이메일과 비밀번호를 확인해주세요."
          : cause instanceof ApiError && cause.status === 403
            ? "사용할 수 없는 계정입니다. " + "계정 상태를 확인해주세요."
            : cause instanceof ApiError && cause.status === 422
              ? "이메일 형식과 입력값을 확인해주세요."
              : "로그인을 완료하지 못했습니다. " +
                "서버 연결을 확인한 뒤 다시 시도해주세요.",
      );
    } finally {
      unsubscribe();

      controller.signal.removeEventListener("abort", cancel);

      if (!connected) {
        token = null;
      }

      if (pendingLogin.current === controller) {
        pendingLogin.current = null;

        setLoggingIn(false);
      }
    }
  }

  // =========================================================
  // 이메일 중복 확인
  // =========================================================

  async function checkSignupEmail() {
    if (checkingEmail) {
      return;
    }

    const normalized = email.trim().toLowerCase();

    if (!normalized) {
      setError("이메일을 입력해주세요.");

      return;
    }

    setCheckingEmail(true);
    setCheckedEmail(null);
    setError(null);

    try {
      const result = await anonymousApi<EmailCheckDto>(
        "/api/auth/email-check",
        {
          method: "POST",
          body: JSON.stringify({
            email: normalized,
          }),
        },
      );

      if (!result.available) {
        setError("이미 사용 중인 이메일입니다.");

        return;
      }

      setCheckedEmail(normalized);

      show({
        title: "이메일 중복 확인",
        body: "사용 가능한 이메일입니다.",
        confirm: "확인",
        cancel: "",
      });
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 422) {
        setError("올바른 이메일 형식을 입력해주세요.");
      } else {
        setError("이메일 중복 여부를 확인하지 못했습니다.");
      }
    } finally {
      setCheckingEmail(false);
    }
  }

  // =========================================================
  // 회원가입
  // =========================================================

  async function signupUser() {
    if (signingUp) {
      return;
    }

    const normalized = email.trim().toLowerCase();

    const normalizedName = name.trim();

    if (!normalizedName) {
      setError("이름을 입력해주세요.");

      return;
    }

    if (!normalized) {
      setError("이메일을 입력해주세요.");

      return;
    }

    if (checkedEmail !== normalized) {
      setError("이메일 중복 확인을 완료해주세요.");

      return;
    }

    const passwordProblem = validateSignupPassword(password);

    if (passwordProblem) {
      setError(passwordProblem);

      return;
    }

    if (password !== passwordConfirm) {
      setError("비밀번호가 서로 일치하지 않습니다.");

      return;
    }

    if (
      !agencyId ||
      !Number.isSafeInteger(Number(agencyId)) ||
      Number(agencyId) <= 0
    ) {
      setError("소속기관을 선택해주세요.");

      return;
    }

    setSigningUp(true);
    setError(null);

    try {
      const user = await anonymousApi<UserDto>("/api/auth/signup", {
        method: "POST",

        body: JSON.stringify({
          name: normalizedName,

          email: normalized,

          password,

          role,

          agency_id: Number(agencyId),
        }),
      });

      const agency = agencies.find((item) => item.id === Number(agencyId));

      show({
        title: "회원가입 완료",

        body: (
          <>
            <p>
              {user.name}
              {" · "}
              {ROLE_LABELS[role]}
            </p>

            <p>{agency?.name ?? "소속기관"}</p>

            <p>등록한 계정으로 로그인해주세요.</p>
          </>
        ),

        confirm: "로그인으로 이동",

        onConfirm: () => go("login"),
      });

      setPassword("");
      setPasswordConfirm("");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        setCheckedEmail(null);

        setError("이미 사용 중인 이메일입니다.");
      } else if (cause instanceof ApiError && cause.status === 400) {
        setError("소속기관 정보를 다시 확인해주세요.");
      } else if (cause instanceof ApiError && cause.status === 422) {
        setError("회원가입 입력값을 다시 확인해주세요.");
      } else {
        setError("회원가입을 완료하지 못했습니다. 서버 연결을 확인해주세요.");
      }
    } finally {
      setSigningUp(false);
    }
  }

  // =========================================================
  // 화면
  // =========================================================

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
          aria-busy={busy || checkingEmail}
          onSubmit={(event) => {
            event.preventDefault();

            if (signup) {
              void signupUser();
            } else {
              void login();
            }
          }}
        >
          {/* -----------------------------------------------
              회원가입 이름
          ------------------------------------------------ */}

          {signup && (
            <label>
              이름
              <input
                placeholder="이름"
                autoComplete="name"
                value={name}
                onChange={(event) => {
                  setName(event.target.value);

                  setError(null);
                }}
                disabled={busy}
              />
            </label>
          )}

          {/* -----------------------------------------------
              이메일
          ------------------------------------------------ */}

          <label htmlFor="auth-email">이메일</label>

          <div className="input-action">
            <input
              id="auth-email"
              aria-label="이메일"
              type="email"
              placeholder="name@example.com"
              autoComplete="username"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);

                setError(null);

                if (signup) {
                  setCheckedEmail(null);
                }
              }}
              disabled={busy}
            />

            {signup && (
              <button
                type="button"
                className="secondary email-check"
                disabled={busy || checkingEmail}
                onClick={() => void checkSignupEmail()}
              >
                {checkingEmail ? "확인 중…" : "이메일 중복 확인"}
              </button>
            )}
          </div>

          {/* -----------------------------------------------
              비밀번호
          ------------------------------------------------ */}

          <label>
            비밀번호
            <input
              type="password"
              autoComplete={signup ? "new-password" : "current-password"}
              placeholder={
                signup ? "8~10자, 영문·숫자·특수문자 포함" : "비밀번호"
              }
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);

                setError(null);
              }}
              disabled={busy}
            />
          </label>

          {/* -----------------------------------------------
              회원가입 전용
          ------------------------------------------------ */}

          {signup && (
            <>
              <label>
                비밀번호 확인
                <input
                  type="password"
                  autoComplete="new-password"
                  placeholder="비밀번호 확인"
                  value={passwordConfirm}
                  onChange={(event) => {
                    setPasswordConfirm(event.target.value);

                    setError(null);
                  }}
                  disabled={busy}
                />
              </label>

              {/* 계정 유형 */}

              <Select
                label="계정 유형"
                options={[
                  {
                    label: "기관 담당자",
                    value: "AGENCY_STAFF",
                  },
                  {
                    label: "현장 담당자",
                    value: "RESPONDER",
                  },
                ]}
                value={role}
                onChange={(value) => {
                  setRole(value as SignupRole);

                  setError(null);
                }}
                disabled={busy}
              />

              {/* 지역 / 기관 */}

              <div className="form-grid">
                <Select
                  label="시·도"
                  options={sidos.map((item) => item.sido_name)}
                  value={sido}
                  onChange={(value) => {
                    setSido(value);

                    setAgencyId("");

                    setError(null);
                  }}
                  disabled={busy || sidos.length === 0}
                />

                <Select
                  label="시·군·구"
                  options={sigungus.map((item) => ({
                    label: item.sigungu_name,

                    value: item.region_code,
                  }))}
                  value={regionCode}
                  onChange={(value) => {
                    setRegionCode(value);

                    setAgencyId("");

                    setError(null);
                  }}
                  disabled={busy || sigungus.length === 0}
                />

                <Select
                  label="기관 유형"
                  options={AGENCY_TYPE_OPTIONS}
                  value={agencyType}
                  onChange={(value) => {
                    setAgencyType(value as SignupAgencyType);

                    setAgencyId("");

                    setError(null);
                  }}
                  disabled={busy}
                />

                <Select
                  label="소속기관"
                  options={agencies.map((agency) => ({
                    label: agency.name,

                    value: String(agency.id),
                  }))}
                  value={agencyId}
                  onChange={(value) => {
                    setAgencyId(value);

                    setError(null);
                  }}
                  disabled={busy || agencies.length === 0}
                />
              </div>
            </>
          )}

          {/* -----------------------------------------------
              오류
          ------------------------------------------------ */}

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          {/* -----------------------------------------------
              제출
          ------------------------------------------------ */}

          <button
            type="submit"
            className="primary"
            disabled={busy || checkingEmail}
          >
            {signup
              ? signingUp
                ? "회원가입 처리 중…"
                : "회원가입"
              : loggingIn
                ? "로그인 확인 중…"
                : "로그인"}
          </button>
        </form>

        {/* -----------------------------------------------
            로그인 / 회원가입 이동
        ------------------------------------------------ */}

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
