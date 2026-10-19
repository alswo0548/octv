import { useState } from "react";
import { View, Text, TextInput, Pressable } from "react-native";
import { mock } from "@octv/shared";
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
  // 기존 로그인 입력창·회원가입 화면을 유지하고 로그인할 때만 Backend를 호출합니다.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
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
      await onLogin(email, password);
      setPassword("");
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
  if (screen === "signup-complete")
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
        <T muted>{mock.profile.name}님의 등록 정보입니다.</T>
        <View style={{ height: 20 }} />
        <Panel title="등록 정보">
          <Pair label="이름" value={mock.profile.name} />
          <Pair label="역할" value={mock.profile.role} />
          <Pair label="소속기관" value={mock.profile.agency} />
          <Pair
            label="계정 상태"
            value={mock.uiSnapshot.mobile.accountStatus}
          />
        </Panel>
        <Button onPress={() => go("login")}>로그인하기</Button>
      </>
    );
  if (screen === "signup-agency")
    return (
      <>
        <T muted>2 / 2</T>
        <Text style={[s.title, { marginTop: 20 }]}>소속기관 선택</Text>
        <T muted>지역과 기관 유형을 선택해 소속기관을 지정합니다.</T>
        <View style={{ height: 20 }} />
        <Choice label="시·도" options={["서울특별시", "경기도"]} />
        <Choice label="시·군·구" options={["강남구", "서대문구", "구리시"]} />
        <Choice
          label="기관 유형"
          options={["소방", "경찰", "도로관리", "지자체"]}
        />
        <Choice
          label="소속기관"
          options={["강남소방서", "강남구청 도로관리과", "역삼소방서"]}
        />
        <Panel title={mock.profile.agency}>
          <T muted>{mock.uiSnapshot.mobile.agencyAddress}</T>
          <T muted>기관 유형 · 소방</T>
        </Panel>
        <Button onPress={() => go("signup-complete")}>회원가입 완료</Button>
        <Button secondary onPress={() => go("signup-basic")}>
          이전
        </Button>
      </>
    );
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
      {signup && (
        <>
          <T muted>1 / 2</T>
          <Field label="이름" placeholder="이름" />
        </>
      )}
      {signup ? (
        <>
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
              style={[
                s.input,
                { flex: 1, minWidth: 0, marginTop: 0, marginBottom: 0 },
              ]}
            />
            <Pressable
              accessibilityRole="button"
              onPress={() =>
                show({
                  title: "이메일 중복 확인",
                  body: "이 화면에서는 이메일 중복 여부를 조회하지 않습니다.",
                  confirm: "확인",
                  cancel: false,
                })
              }
              style={[
                s.button,
                s.secondary,
                { marginTop: 0, paddingHorizontal: 10 },
              ]}
            >
              <Text style={[s.buttonText, { fontSize: 12 }]}>
                이메일 중복 확인
              </Text>
            </Pressable>
          </View>
        </>
      ) : (
        <Field
          label="이메일"
          placeholder="name@example.com"
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
        />
      )}
      <Field
        label="비밀번호"
        placeholder={signup ? "8~10자, 영문·숫자·특수문자 포함" : "비밀번호"}
        secureTextEntry
        {...(!signup ? { value: password, onChangeText: setPassword } : {})}
      />
      {signup && <Field label="비밀번호 확인" secureTextEntry />}
      <Button
        disabled={!signup && loggingIn}
        onPress={() => {
          if (signup) go("signup-agency");
          else void submitLogin();
        }}
      >
        {signup ? "다음: 소속기관 선택" : loggingIn ? "로그인 중…" : "로그인"}
      </Button>
      {signup ? (
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
      ) : (
        <Button secondary onPress={() => go("signup-basic")}>
          회원가입
        </Button>
      )}
    </View>
  );
}
