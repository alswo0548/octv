import { useState } from "react";
import { Brand, Select, type ShowModal } from "../components/Primitives";
import { go } from "../routing/useRoute";
export function AuthPage({
  signup = false,
  show,
}: {
  signup?: boolean;
  show: ShowModal;
}) {
  const [example, setExample] = useState("기본");
  return (
    <div className={"auth-wrap " + (signup ? "signup" : "")}>
      <section className="panel auth-panel">
        <div className="auth-brand">
          <Brand />
        </div>
        <h2>{signup ? "회원가입" : "상황실 로그인"}</h2>
        <p className="intro">
          {signup
            ? "입력과 선택 화면을 확인하세요."
            : "재난 대응 정보를 한눈에 확인하세요."}
        </p>
        <form
          className="form-stack"
          noValidate
          onSubmit={(e) => e.preventDefault()}
        >
          {signup && (
            <label>
              이름
              <input placeholder="이름" autoComplete="off" />
            </label>
          )}
          <label>이메일</label>
          <div className="input-action">
            <input
              aria-label="이메일"
              type="text"
              placeholder="name@example.com"
              autoComplete="off"
            />
            {signup && (
              <button
                type="button"
                className="secondary"
                onClick={() => setExample("사용 가능 예시")}
              >
                중복 확인
              </button>
            )}
          </div>
          <label>
            비밀번호
            <input
              type="password"
              autoComplete="new-password"
              placeholder="비밀번호"
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
                options={["기관 담당자", "출동대원", "상황실 관리자"]}
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
          <div className="preview-status">
            <label>
              안내 문구 미리보기
              <select
                value={example}
                onChange={(e) => setExample(e.target.value)}
              >
                {["기본", "오류 예시", "사용 가능 예시"].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            {example === "오류 예시" && (
              <p className="form-error">
                아이디 또는 비밀번호가 올바르지 않습니다. (고정 예시)
              </p>
            )}
            {example === "사용 가능 예시" && (
              <p className="field-feedback">
                사용 가능한 이메일입니다. (입력과 무관한 고정 예시)
              </p>
            )}
          </div>
          <button
            type="button"
            className="primary"
            onClick={() =>
              signup
                ? show({
                    title: "회원가입 완료 화면 예시",
                    body: (
                      <>
                        <p>홍길동 · 현장대응 담당자 · 강남소방서</p>
                        <p>
                          고정 등록 정보 예시입니다. 실제 계정은 생성되지
                          않습니다.
                        </p>
                      </>
                    ),
                    confirm: "로그인으로 이동",
                    onConfirm: () => go("login"),
                  })
                : go("overview")
            }
          >
            {signup ? "회원가입" : "로그인"}
          </button>
        </form>
        <div className="auth-links">
          {signup ? "이미 계정이 있으신가요?" : "계정이 없으신가요?"}{" "}
          <a href={signup ? "#/login" : "#/signup"}>
            {signup ? "로그인" : "회원가입"}
          </a>
        </div>
        <p className="demo-note">
          UI 미리보기 · 어떤 입력값으로도 이동할 수 있습니다.
          <br />
          인증·입력 검사·계정 생성은 미구현입니다.
        </p>
      </section>
    </div>
  );
}
