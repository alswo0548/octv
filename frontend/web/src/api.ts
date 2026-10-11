// 로그인 화면에서 전달한 토큰으로 API를 호출하고, 기존 응답으로 본인 정보를 구성합니다.
import type { AgencyDto, CurrentUserDto, UserDto } from "@octv/shared";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// baseUrl은 서버 주소, path는 /api로 시작하는 경로입니다.
// WEB은 VITE_API_BASE_URL, MOBILE은 EXPO_PUBLIC_API_BASE_URL 값을 전달합니다.
export function createApi(baseUrl: string, getToken: () => string | null) {
  const base = baseUrl.replace(/\/$/, "");

  return async function api<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const headers = new Headers(options.headers);

    // JSON 문자열은 호출하는 쪽에서 JSON.stringify로 만듭니다.
    // FormData·URLSearchParams의 Content-Type은 fetch가 지정합니다.
    if (typeof options.body === "string" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    // 요청마다 다시 읽어 로그인·로그아웃 후 토큰 변경을 반영합니다.
    const token = getToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(base + path, { ...options, headers });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      const detail =
        typeof body === "object" && body !== null && "detail" in body
          ? body.detail
          : undefined;

      // 화면에서 status로 401 등을 처리하고, 422의 검증 내용은 detail로 확인합니다.
      throw new ApiError(
        response.status,
        typeof detail === "string" ? detail : "요청을 처리하지 못했습니다.",
        detail,
      );
    }

    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  };
}

// auth 응답을 바꾸지 않고 기존 기관 목록에서 소속기관명을 찾습니다.
export async function getCurrentUser(
  api: ReturnType<typeof createApi>,
): Promise<CurrentUserDto> {
  const user = await api<UserDto>("/api/auth/me");
  if (user.agency_id === null) {
    return { ...user, agency_name: null };
  }

  const agencies = await api<AgencyDto[]>("/api/agencies");
  const agency = agencies.find((item) => item.id === user.agency_id);
  return { ...user, agency_name: agency?.name ?? null };
}
