import { Brand, Select, type ShowModal } from "../components/Primitives";
import { go } from "../routing/useRoute";
export function AuthPage({
  signup = false,
  show,
}: {
  signup?: boolean;
  show: ShowModal;
}) {
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
          onSubmit={(e) => e.preventDefault()}
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
              type="text"
              placeholder="name@example.com"
              autoComplete="off"
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
          <button
            type="button"
            className="primary"
            onClick={() =>
              signup
                ? show({
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
      </section>
    </div>
  );
}
