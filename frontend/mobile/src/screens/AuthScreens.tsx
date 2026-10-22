import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  View,
  Text,
  TextInput,
  Pressable,
} from "react-native";
import type {
  EmailCheckDto,
  SignupAgencyDto,
  SignupAgencyType,
  SignupRole,
  SignupSidoDto,
  SignupSigunguDto,
  UserDto,
} from "@octv/shared";
import { ApiError, createApi } from "../api";
import {
  Brand,
  Button,
  Link,
  Panel,
  Pair,
  Field,
  Choice,
  T,
  type ShowDialog,
} from "../components/UI";
import { s, color } from "../styles/theme";
import type { Navigate, Screen } from "../navigation/types";

const ROLE_LABELS: Record<SignupRole, string> = {
  AGENCY_STAFF: "기관 담당자",
  RESPONDER: "현장 담당자",
};

const AGENCY_TYPE_LABELS: Record<SignupAgencyType, string> = {
  FIRE: "소방",
  POLICE: "경찰",
  ROAD_MANAGEMENT: "도로관리",
  LOCAL_GOVERNMENT: "지자체",
};

function anonymousApi() {
  const baseUrl = (process.env.EXPO_PUBLIC_API_BASE_URL ?? "")
    .trim()
    .replace(/\/$/, "");

  if (!/^https?:\/\//.test(baseUrl)) {
    throw new Error(
      "EXPO_PUBLIC_API_BASE_URL에 접속할 Backend 주소를 설정해주세요.",
    );
  }

  return createApi(baseUrl, () => null);
}

function passwordError(password: string): string | null {
  if (password.length < 8 || password.length > 10) {
    return "비밀번호는 8~10자여야 합니다.";
  }

  if (!/[A-Za-z]/.test(password)) {
    return "비밀번호에는 영문자가 포함되어야 합니다.";
  }

  if (!/\d/.test(password)) {
    return "비밀번호에는 숫자가 포함되어야 합니다.";
  }

  if (/\s/.test(password)) {
    return "비밀번호에는 공백을 사용할 수 없습니다.";
  }

  if (!/[^A-Za-z0-9]/.test(password)) {
    return "비밀번호에는 특수문자가 포함되어야 합니다.";
  }

  return null;
}

export function AuthScreens({
  screen,
  go,
  show,
  onLogin,
}: {
  screen: Screen;
  go: Navigate;
  show: ShowDialog;
  onLogin?: (email: string, password: string) => Promise<void>;
}) {
  // 로그인
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);

  // 회원가입 기본정보
  const [name, setName] = useState("");
  const [signupEmail, setSignupEmail] = useState("");
  const [signupPassword, setSignupPassword] = useState("");
  const [signupPasswordConfirm, setSignupPasswordConfirm] = useState("");
  const [role, setRole] = useState<SignupRole>("AGENCY_STAFF");
  const [checkedEmail, setCheckedEmail] = useState<string | null>(null);
  const [checkingEmail, setCheckingEmail] = useState(false);

  // 회원가입 기관정보
  const [sidos, setSidos] = useState<SignupSidoDto[]>([]);
  const [sido, setSido] = useState("");
  const [sigungus, setSigungus] = useState<SignupSigunguDto[]>([]);
  const [regionCode, setRegionCode] = useState("");
  const [agencyType, setAgencyType] = useState<SignupAgencyType>("FIRE");
  const [agencies, setAgencies] = useState<SignupAgencyDto[]>([]);
  const [agencyId, setAgencyId] = useState("");

  const [signupError, setSignupError] = useState<string | null>(null);
  const [loadingRegion, setLoadingRegion] = useState(false);
  const [loadingAgencies, setLoadingAgencies] = useState(false);
  const [signingUp, setSigningUp] = useState(false);

  const [completed, setCompleted] = useState<{
    user: UserDto;
    agencyName: string;
  } | null>(null);

  // 시·도
  useEffect(() => {
    if (!screen.startsWith("signup") || sidos.length > 0) return;

    let active = true;

    void (async () => {
      try {
        const response = await anonymousApi()<SignupSidoDto[]>(
          "/api/auth/signup/sidos",
        );

        if (!active) return;

        setSidos(response);

        if (response[0]) {
          setSido(response[0].sido_name);
        }
      } catch {
        if (active) {
          setSignupError("지역 정보를 불러오지 못했습니다.");
        }
      }
    })();

    return () => {
      active = false;
    };
  }, [screen, sidos.length]);

  // 시·군·구
  useEffect(() => {
    if (!sido) {
      setSigungus([]);
      setRegionCode("");
      return;
    }

    let active = true;
    setLoadingRegion(true);

    void (async () => {
      try {
        const response = await anonymousApi()<SignupSigunguDto[]>(
          `/api/auth/signup/sigungus?sido_name=${encodeURIComponent(sido)}`,
        );

        if (!active) return;

        setSigungus(response);
        setRegionCode(response[0]?.region_code ?? "");
        setAgencyId("");
      } catch {
        if (active) {
          setSigungus([]);
          setRegionCode("");
          setSignupError("시·군·구 정보를 불러오지 못했습니다.");
        }
      } finally {
        if (active) setLoadingRegion(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [sido]);

  // 기관
  useEffect(() => {
    if (!regionCode) {
      setAgencies([]);
      setAgencyId("");
      return;
    }

    let active = true;
    setLoadingAgencies(true);

    void (async () => {
      try {
        const response = await anonymousApi()<SignupAgencyDto[]>(
          `/api/auth/signup/agencies?region_code=${encodeURIComponent(
            regionCode,
          )}&agency_type=${encodeURIComponent(agencyType)}`,
        );

        if (!active) return;

        setAgencies(response);
        setAgencyId(response[0] ? String(response[0].id) : "");
      } catch {
        if (active) {
          setAgencies([]);
          setAgencyId("");
          setSignupError("소속기관 정보를 불러오지 못했습니다.");
        }
      } finally {
        if (active) setLoadingAgencies(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [regionCode, agencyType]);

  async function submitLogin() {
    if (loggingIn) return;

    if (!onLogin) {
      show({
        title: "로그인 연결 대기",
        body: "로그인 기능을 연결한 후 다시 시도해주세요.",
        cancel: false,
      });
      return;
    }

    setLoggingIn(true);

    try {
      await onLogin(loginEmail, loginPassword);
      setLoginPassword("");
      go("home");
    } catch (error) {
      show({
        title: "로그인 확인",
        body:
          error instanceof Error
            ? error.message
            : "로그인에 실패했습니다. 다시 시도해주세요.",
        cancel: false,
      });
    } finally {
      setLoggingIn(false);
    }
  }

  async function checkEmail() {
    const email = signupEmail.trim().toLowerCase();

    if (!email) {
      show({
        title: "이메일 확인",
        body: "이메일을 입력해주세요.",
        cancel: false,
      });
      return;
    }

    setCheckingEmail(true);
    setCheckedEmail(null);

    try {
      const result = await anonymousApi()<EmailCheckDto>(
        "/api/auth/email-check",
        {
          method: "POST",
          body: JSON.stringify({ email }),
        },
      );

      if (result.available) {
        setCheckedEmail(email);

        show({
          title: "이메일 중복 확인",
          body: "사용 가능한 이메일입니다.",
          cancel: false,
        });
      } else {
        show({
          title: "이메일 중복 확인",
          body: "이미 사용 중인 이메일입니다.",
          cancel: false,
        });
      }
    } catch {
      show({
        title: "이메일 확인",
        body: "이메일 형식 또는 서버 연결을 확인해주세요.",
        cancel: false,
      });
    } finally {
      setCheckingEmail(false);
    }
  }

  function nextSignupStep() {
    const email = signupEmail.trim().toLowerCase();

    if (!name.trim()) {
      setSignupError("이름을 입력해주세요.");
      return;
    }

    if (!email) {
      setSignupError("이메일을 입력해주세요.");
      return;
    }

    if (checkedEmail !== email) {
      setSignupError("이메일 중복 확인을 완료해주세요.");
      return;
    }

    const passwordProblem = passwordError(signupPassword);

    if (passwordProblem) {
      setSignupError(passwordProblem);
      return;
    }

    if (signupPassword !== signupPasswordConfirm) {
      setSignupError("비밀번호가 서로 일치하지 않습니다.");
      return;
    }

    setSignupError(null);
    go("signup-agency");
  }

  async function submitSignup() {
    if (signingUp) return;

    if (!agencyId || Number(agencyId) <= 0) {
      setSignupError("소속기관을 선택해주세요.");
      return;
    }

    setSigningUp(true);
    setSignupError(null);

    try {
      const user = await anonymousApi()<UserDto>("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          email: signupEmail.trim().toLowerCase(),
          password: signupPassword,
          name: name.trim(),
          role,
          agency_id: Number(agencyId),
        }),
      });

      const selectedAgency = agencies.find(
        (agency) => agency.id === Number(agencyId),
      );

      setCompleted({
        user,
        agencyName: selectedAgency?.name ?? "소속기관",
      });

      setLoginEmail(user.email);
      setLoginPassword("");
      setSignupPassword("");
      setSignupPasswordConfirm("");

      go("signup-complete");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setSignupError("이미 사용 중인 이메일입니다.");
      } else if (error instanceof ApiError && error.status === 400) {
        setSignupError("소속기관 정보를 다시 확인해주세요.");
      } else if (error instanceof ApiError && error.status === 422) {
        setSignupError("회원가입 입력값을 다시 확인해주세요.");
      } else {
        setSignupError("회원가입을 완료하지 못했습니다.");
      }
    } finally {
      setSigningUp(false);
    }
  }

  if (screen === "signup-complete") {
    return (
      <>
        <Text
          style={{
            color: color.cyan,
            fontSize: 50,
            textAlign: "center",
            margin: 24,
          }}
        >
          ✓
        </Text>

        <Text style={s.title}>회원가입 완료</Text>

        {completed ? (
          <>
            <T muted>{completed.user.name}님의 등록 정보입니다.</T>

            <View style={{ height: 20 }} />

            <Panel title="등록 정보">
              <Pair label="이름" value={completed.user.name} />
              <Pair
                label="역할"
                value={
                  ROLE_LABELS[completed.user.role as SignupRole] ??
                  completed.user.role
                }
              />
              <Pair label="소속기관" value={completed.agencyName} />
              <Pair
                label="계정 상태"
                value={completed.user.is_active ? "활성" : "비활성"}
              />
            </Panel>
          </>
        ) : (
          <T>회원가입 정보를 확인할 수 없습니다.</T>
        )}

        <Button onPress={() => go("login")}>로그인하기</Button>
      </>
    );
  }

  if (screen === "signup-agency") {
    const selectedAgency = agencies.find(
      (agency) => agency.id === Number(agencyId),
    );

    return (
      <>
        <T muted>2 / 2</T>
        <Text style={[s.title, { marginTop: 20 }]}>소속기관 선택</Text>
        <T muted>지역과 기관 유형을 선택해 소속기관을 지정합니다.</T>

        <View style={{ height: 20 }} />

        <Choice
          label="시·도"
          options={sidos.map((item) => item.sido_name)}
          value={sido}
          onChange={(value) => {
            setSido(value);
            setAgencyId("");
          }}
        />

        <Choice
          label="시·군·구"
          options={sigungus.map((item) => ({
            label: item.sigungu_name,
            value: item.region_code,
          }))}
          value={regionCode}
          onChange={(value) => {
            setRegionCode(value);
            setAgencyId("");
          }}
          disabled={loadingRegion}
        />

        <Choice
          label="기관 유형"
          options={(
            Object.entries(AGENCY_TYPE_LABELS) as [SignupAgencyType, string][]
          ).map(([value, label]) => ({
            value,
            label,
          }))}
          value={agencyType}
          onChange={(value) => {
            setAgencyType(value as SignupAgencyType);
            setAgencyId("");
          }}
        />

        <Choice
          label="소속기관"
          options={agencies.map((agency) => ({
            label: agency.name,
            value: String(agency.id),
          }))}
          value={agencyId}
          onChange={setAgencyId}
          disabled={loadingAgencies}
        />

        {(loadingRegion || loadingAgencies) && (
          <ActivityIndicator color={color.cyan} />
        )}

        {selectedAgency && (
          <Panel title={selectedAgency.name}>
            <T muted>{selectedAgency.address ?? "주소 정보 없음"}</T>
            <T muted>
              기관 유형 · {AGENCY_TYPE_LABELS[selectedAgency.agency_type]}
            </T>
          </Panel>
        )}

        {signupError && (
          <View style={s.info}>
            <T>{signupError}</T>
          </View>
        )}

        <Button
          disabled={signingUp || !agencyId}
          onPress={() => void submitSignup()}
        >
          {signingUp ? "회원가입 처리 중…" : "회원가입 완료"}
        </Button>

        <Button secondary onPress={() => go("signup-basic")}>
          이전
        </Button>
      </>
    );
  }

  const signup = screen === "signup-basic";

  return (
    <View style={{ paddingTop: signup ? 0 : 32 }}>
      {!signup && (
        <>
          <Brand />
          <View style={{ height: 28 }} />
        </>
      )}

      <Text style={s.title}>
        {signup ? "출동을 더 빠르고 안전하게," : "현장 담당자 로그인"}
      </Text>

      <T muted>
        {signup
          ? "지금 계정을 만들어 시작하세요."
          : "소속기관에 전달된 사건과 예상 접근경로를 확인합니다."}
      </T>

      <View style={{ height: 26 }} />

      {signup ? (
        <>
          <T muted>1 / 2</T>

          <Field
            label="이름"
            placeholder="이름"
            value={name}
            onChangeText={setName}
          />

          <T>이메일</T>

          <View
            style={{
              flexDirection: "row",
              alignItems: "stretch",
              gap: 8,
              marginTop: 7,
              marginBottom: 16,
            }}
          >
            <TextInput
              accessibilityLabel="이메일"
              placeholder="name@example.com"
              placeholderTextColor={color.muted}
              autoCapitalize="none"
              keyboardType="email-address"
              value={signupEmail}
              onChangeText={(value) => {
                setSignupEmail(value);
                setCheckedEmail(null);
              }}
              style={[
                s.input,
                {
                  flex: 1,
                  minWidth: 0,
                  marginTop: 0,
                  marginBottom: 0,
                },
              ]}
            />

            <Pressable
              accessibilityRole="button"
              disabled={checkingEmail}
              onPress={() => void checkEmail()}
              style={[
                s.button,
                s.secondary,
                { marginTop: 0, paddingHorizontal: 10 },
              ]}
            >
              <Text style={[s.buttonText, { fontSize: 12 }]}>
                {checkingEmail ? "확인 중…" : "이메일 중복 확인"}
              </Text>
            </Pressable>
          </View>

          <Field
            label="비밀번호"
            placeholder="8~10자, 영문·숫자·특수문자 포함"
            secureTextEntry
            value={signupPassword}
            onChangeText={setSignupPassword}
          />

          <Field
            label="비밀번호 확인"
            secureTextEntry
            value={signupPasswordConfirm}
            onChangeText={setSignupPasswordConfirm}
          />

          <Choice
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
            onChange={(value) => setRole(value as SignupRole)}
          />

          {signupError && (
            <View style={s.info}>
              <T>{signupError}</T>
            </View>
          )}

          <Button onPress={nextSignupStep}>다음: 소속기관 선택</Button>

          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              marginTop: 12,
            }}
          >
            <T muted>이미 계정이 있으신가요?</T>
            <Link onPress={() => go("login")}>로그인</Link>
          </View>
        </>
      ) : (
        <>
          <Field
            label="이메일"
            placeholder="name@example.com"
            value={loginEmail}
            onChangeText={setLoginEmail}
            keyboardType="email-address"
          />

          <Field
            label="비밀번호"
            placeholder="비밀번호"
            secureTextEntry
            value={loginPassword}
            onChangeText={setLoginPassword}
          />

          <Button disabled={loggingIn} onPress={() => void submitLogin()}>
            {loggingIn ? "로그인 중…" : "로그인"}
          </Button>

          <Button secondary onPress={() => go("signup-basic")}>
            회원가입
          </Button>
        </>
      )}
    </View>
  );
}
