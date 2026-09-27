import { useState } from "react";
import { View, Text } from "react-native";
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
} from "../components/UI";
import { s, color } from "../styles/theme";
import type { Navigate, Screen } from "../navigation/types";
export function AuthScreens({ screen, go }: { screen: Screen; go: Navigate }) {
  const [example, set] = useState(false);
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
        <Text style={s.title}>회원가입 완료 화면 예시</Text>
        <T muted>{mock.profile.name}님의 고정 등록 정보입니다.</T>
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
        <View style={s.info}>
          <T>실제 계정은 생성되지 않았습니다.</T>
        </View>
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
          <T muted>기관 유형 · 소방 · 고정 예시</T>
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
        {signup ? "출동을 더 빠르고 안전하게," : "출동대원 로그인"}
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
      <Field label="이메일" placeholder="name@example.com" />
      {signup && (
        <Link onPress={() => set(true)}>중복 확인 · 상태 예시 보기</Link>
      )}
      <Field
        label="비밀번호"
        placeholder={signup ? "8~10자, 영문·숫자·특수문자 포함" : "비밀번호"}
        secureTextEntry
      />
      {signup && <Field label="비밀번호 확인" secureTextEntry />}
      <Link onPress={() => set(!example)}>
        안내 문구 예시 {example ? "숨기기" : "보기"}
      </Link>
      {example && (
        <Text
          style={[
            s.muted,
            { color: signup ? "#8cdec9" : "#f49caa", marginBottom: 12 },
          ]}
        >
          {signup
            ? "사용 가능한 이메일입니다. / 비밀번호가 일치합니다. (고정 예시)"
            : "아이디 또는 비밀번호가 올바르지 않습니다. (고정 예시)"}
        </Text>
      )}
      <Button onPress={() => go(signup ? "signup-agency" : "home")}>
        {signup ? "다음: 소속기관 선택" : "로그인"}
      </Button>
      <Button secondary onPress={() => go(signup ? "login" : "signup-basic")}>
        {signup ? "이미 계정이 있으신가요? 로그인" : "회원가입"}
      </Button>
      <Text style={[s.muted, { fontSize: 12, marginTop: 24 }]}>
        UI 미리보기 · 입력 검사와 인증 없이 이동합니다. 실제 계정정보는 필요하지
        않습니다.
      </Text>
    </View>
  );
}
