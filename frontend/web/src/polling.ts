/** 조회 전용 폴링. 이전 요청이 끝난 뒤 예약하고 숨겨진 탭에서는 쉬어갑니다. */
type Visibility = Pick<
  Document,
  "hidden" | "addEventListener" | "removeEventListener"
>;

export function pollWhileVisible<T>(
  read: (signal: AbortSignal) => Promise<T>,
  options: {
    onValue: (value: T) => void;
    onError: (error: unknown) => void;
    onSettled?: () => void;
    intervalMs?: number;
    visibility?: Visibility;
  },
): () => void {
  const visibility = options.visibility ?? document;
  const interval = options.intervalMs ?? 10_000;
  let stopped = false;
  let inFlight = false;
  let refreshOnReturn = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;

  const clearTimer = () => {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
  };

  const run = async () => {
    if (stopped || inFlight || (interval > 0 && visibility.hidden)) return;
    inFlight = true;
    controller = new AbortController();
    try {
      const value = await read(controller.signal);
      if (!stopped) options.onValue(value);
    } catch (error) {
      if (!stopped) {
        options.onError(error);
        // 권한 오류를 반복 호출하지 않습니다. 새 세션/수동 조회가 새 폴링을 만듭니다.
        if (
          error &&
          typeof error === "object" &&
          "status" in error &&
          (error.status === 401 || error.status === 403)
        )
          stopped = true;
      }
    } finally {
      inFlight = false;
      if (!controller.signal.aborted) options.onSettled?.();
      if (!stopped && !visibility.hidden && interval > 0) {
        timer = setTimeout(run, refreshOnReturn ? 0 : interval);
      }
      refreshOnReturn = false;
    }
  };

  const onVisibility = () => {
    clearTimer();
    if (!visibility.hidden) {
      if (inFlight) refreshOnReturn = true;
      else void run();
    }
  };

  if (interval > 0)
    visibility.addEventListener("visibilitychange", onVisibility);
  // interval=0인 단발 조회는 기존처럼 숨겨진 탭에서도 실행합니다.
  void run();
  return () => {
    stopped = true;
    clearTimer();
    controller?.abort();
    visibility.removeEventListener("visibilitychange", onVisibility);
  };
}
