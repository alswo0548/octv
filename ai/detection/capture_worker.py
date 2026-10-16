"""CCTV 영상 연결 유지·재연결을 담당하는 Capture Worker."""

import time

from threading import Event
from typing import Callable

from ..contracts import Frame
from .video import VideoSource


class CaptureWorker:
    """
    하나의 CCTV 영상 source를 지속적으로 수신한다.

    담당 역할:
    - 영상 source 연결
    - 프레임 연속 수신
    - 수신 중단 감지
    - 자동 재연결
    - 최대 자동 재연결 횟수 제한
    - 외부 재연결 요청 처리
    - 연결 시 Stream URL 갱신
    - 외부 stop 요청 처리
    - 연결 상태 변경 알림

    stream_url_resolver가 있으면
    최초 연결 및 모든 재연결 시도마다
    최신 Stream URL을 다시 조회한다.
    """

    def __init__(
        self,
        cctv_id: int,
        stream_url: str | None = None,
        stream_url_resolver: Callable[[], str] | None = None,
        reconnect_delay_sec: float = 2.0,
        max_reconnect_attempts: int | None = None,
        realtime_pacing: bool = False,
    ):
        if reconnect_delay_sec < 0:
            raise ValueError(
                "reconnect_delay_sec은 "
                "0 이상이어야 합니다."
            )

        if (
            max_reconnect_attempts is not None
            and max_reconnect_attempts <= 0
        ):
            raise ValueError(
                "max_reconnect_attempts는 "
                "1 이상이어야 합니다."
            )

        if (
            not stream_url
            and stream_url_resolver is None
        ):
            raise ValueError(
                "stream_url 또는 "
                "stream_url_resolver 중 "
                "하나는 필요합니다."
            )

        self.cctv_id = cctv_id

        self.stream_url = stream_url

        self.stream_url_resolver = (
            stream_url_resolver
        )

        self.reconnect_delay_sec = (
            reconnect_delay_sec
        )

        self.max_reconnect_attempts = (
            max_reconnect_attempts
        )

        self.realtime_pacing = (
            realtime_pacing
        )

        # 고정 URL 방식이면 기존처럼
        # 처음부터 VideoSource를 만들어둔다.
        if stream_url is not None:

            self.source: VideoSource | None = (
                VideoSource(
                    cctv_id=cctv_id,
                    stream_url=stream_url,
                )
            )

        else:

            self.source = None

        # Worker 전체 종료 요청
        self._stop_event = Event()

        # 현재 연결을 다시 열도록 요청
        self._reconnect_event = Event()

    # =====================================================
    # 외부 제어
    # =====================================================

    def stop(self) -> None:
        """
        Capture Worker 전체 종료를 요청한다.
        """

        self._stop_event.set()

    def request_reconnect(self) -> None:
        """
        현재 CCTV 연결을 다시 열도록 요청한다.

        여기서 VideoSource.close()를 직접 호출하지 않는다.

        실제 close/open은 CaptureWorker 자신의
        Thread에서 수행한다.
        """

        if self._stop_event.is_set():
            return

        self._reconnect_event.set()

    # =====================================================
    # 연결에 사용할 Source 준비
    # =====================================================

    def _prepare_source_for_connection(
        self,
    ) -> None:
        """
        이번 연결 시도에서 사용할 VideoSource를 준비한다.

        stream_url_resolver가 있으면
        연결 시도마다 최신 URL을 다시 조회한다.

        resolver가 없으면 기존 고정 URL 방식을 사용한다.
        """

        # -------------------------------------------------
        # 고정 URL 방식
        # -------------------------------------------------

        if self.stream_url_resolver is None:

            if self.source is None:

                if not self.stream_url:
                    raise ConnectionError(
                        "사용할 Stream URL이 없습니다."
                    )

                self.source = VideoSource(
                    cctv_id=self.cctv_id,
                    stream_url=self.stream_url,
                )

            return

        # -------------------------------------------------
        # 동적 URL 방식
        # -------------------------------------------------

        try:

            resolved_url = (
                self.stream_url_resolver()
            )

        except Exception as exc:

            raise ConnectionError(
                "Stream URL 조회에 실패했습니다: "
                f"{exc}"
            ) from exc

        if not resolved_url:
            raise ConnectionError(
                "Stream URL Resolver가 "
                "빈 URL을 반환했습니다."
            )

        # 기존 source가 있다면 정리
        if self.source is not None:
            self.source.close()

        self.stream_url = resolved_url

        self.source = VideoSource(
            cctv_id=self.cctv_id,
            stream_url=resolved_url,
        )

        print(
            f"[CCTV {self.cctv_id}] "
            "Stream URL 새로 조회 완료"
        )

    # =====================================================
    # Capture Loop
    # =====================================================

    def run(
        self,
        on_frame: Callable[[Frame], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        max_connection_cycles: int | None = None,
    ) -> None:
        """
        CCTV 수신 루프를 실행한다.

        max_connection_cycles:
        - 테스트용 전체 연결 시도 횟수 제한

        max_reconnect_attempts:
        - 한 번의 장애에 대한
          자동 재연결 최대 횟수
        """

        connection_cycle = 0

        reconnect_attempt = 0

        is_reconnecting = False

        skip_reconnect_wait_once = False

        try:

            while not self._stop_event.is_set():

                # -----------------------------------------
                # 테스트용 전체 연결 횟수 제한
                # -----------------------------------------

                if (
                    max_connection_cycles is not None
                    and connection_cycle
                    >= max_connection_cycles
                ):
                    break

                # =========================================
                # 재연결 상태 처리
                # =========================================

                if is_reconnecting:

                    # -------------------------------------
                    # 최대 자동 재연결 횟수 도달
                    # -------------------------------------

                    if (
                        self.max_reconnect_attempts
                        is not None
                        and reconnect_attempt
                        >= self.max_reconnect_attempts
                    ):

                        print(
                            f"[CCTV {self.cctv_id}] "
                            f"자동 재연결 "
                            f"{self.max_reconnect_attempts}회 "
                            f"실패"
                        )

                        self._notify_status(
                            on_status=on_status,
                            status="DISCONNECTED",
                        )

                        print(
                            f"[CCTV {self.cctv_id}] "
                            "외부 재연결 요청 대기"
                        )

                        reconnect_requested = (
                            self._wait_for_reconnect_request()
                        )

                        if not reconnect_requested:
                            break

                        print(
                            f"[CCTV {self.cctv_id}] "
                            "외부 재연결 요청 수신 "
                            "→ 재시도 횟수 초기화"
                        )

                        reconnect_attempt = 0

                        skip_reconnect_wait_once = True

                        self._notify_status(
                            on_status=on_status,
                            status="RECONNECTING",
                        )

                    # -------------------------------------
                    # 재연결 전 대기
                    # -------------------------------------

                    if skip_reconnect_wait_once:

                        skip_reconnect_wait_once = False

                    else:

                        if self._wait_before_reconnect():
                            break

                    reconnect_attempt += 1

                    print(
                        f"[CCTV {self.cctv_id}] "
                        f"재연결 시도 "
                        f"#{reconnect_attempt}"
                    )

                # =========================================
                # 실제 연결 시도
                # =========================================

                connection_cycle += 1

                self._reconnect_event.clear()

                print(
                    f"[CCTV {self.cctv_id}] "
                    f"연결 시도 #{connection_cycle}"
                )

                # =========================================
                # 1. 최신 Stream URL 준비 + 연결
                # =========================================

                try:

                    self._prepare_source_for_connection()

                    if self.source is None:
                        raise ConnectionError(
                            "VideoSource가 "
                            "생성되지 않았습니다."
                        )

                    self.source.open()

                except ConnectionError as exc:

                    print(
                        f"[CCTV {self.cctv_id}] "
                        f"연결 실패: {exc}"
                    )

                    self._notify_status(
                        on_status=on_status,
                        status="RECONNECTING",
                    )

                    if not is_reconnecting:

                        is_reconnecting = True

                        reconnect_attempt = 0

                    continue

                # =========================================
                # 2. 연결 성공
                # =========================================

                print(
                    f"[CCTV {self.cctv_id}] "
                    "연결 성공"
                )

                self._notify_status(
                    on_status=on_status,
                    status="CONNECTED",
                )

                reconnect_attempt = 0

                is_reconnecting = False

                # =========================================
                # 3. 로컬 영상 FPS pacing
                # =========================================

                fps = self.source.get_fps()

                frame_interval = (
                    1.0 / fps
                    if (
                        self.realtime_pacing
                        and fps > 0
                    )
                    else None
                )

                next_frame_at = (
                    time.perf_counter()
                )

                reconnect_required = False

                # =========================================
                # 4. Frame 수신 Loop
                # =========================================

                while not self._stop_event.is_set():

                    # -------------------------------------
                    # read() 전 외부 재연결 요청
                    # -------------------------------------

                    if self._reconnect_event.is_set():

                        self._reconnect_event.clear()

                        print(
                            f"[CCTV {self.cctv_id}] "
                            "외부 재연결 요청 감지"
                        )

                        self._notify_status(
                            on_status=on_status,
                            status="RECONNECTING",
                        )

                        reconnect_required = True

                        break

                    # -------------------------------------
                    # Frame 읽기
                    # -------------------------------------

                    frame = self.source.read()

                    # -------------------------------------
                    # Frame 수신 실패
                    # -------------------------------------

                    if frame is None:

                        print(
                            f"[CCTV {self.cctv_id}] "
                            "프레임 수신 중단 감지"
                        )

                        self._notify_status(
                            on_status=on_status,
                            status="RECONNECTING",
                        )

                        reconnect_required = True

                        break

                    # -------------------------------------
                    # Frame 외부 전달
                    # -------------------------------------

                    if on_frame is not None:
                        on_frame(frame)

                    # -------------------------------------
                    # read 도중 재연결 요청 확인
                    # -------------------------------------

                    if self._reconnect_event.is_set():

                        self._reconnect_event.clear()

                        print(
                            f"[CCTV {self.cctv_id}] "
                            "외부 재연결 요청 감지"
                        )

                        self._notify_status(
                            on_status=on_status,
                            status="RECONNECTING",
                        )

                        reconnect_required = True

                        break

                    # -------------------------------------
                    # 로컬 MP4 pacing
                    # -------------------------------------

                    if frame_interval is not None:

                        next_frame_at += (
                            frame_interval
                        )

                        sleep_time = (
                            next_frame_at
                            - time.perf_counter()
                        )

                        if sleep_time > 0:

                            self._stop_event.wait(
                                sleep_time
                            )

                # =========================================
                # 5. 현재 연결 종료
                # =========================================

                self.source.close()

                if self._stop_event.is_set():
                    break

                if (
                    max_connection_cycles is not None
                    and connection_cycle
                    >= max_connection_cycles
                ):
                    break

                # =========================================
                # 6. 장애 → 재연결 모드
                # =========================================

                if reconnect_required:

                    is_reconnecting = True

                    reconnect_attempt = 0

                    continue

                break

        finally:

            if self.source is not None:
                self.source.close()

            self._notify_status(
                on_status=on_status,
                status="DISCONNECTED",
            )

            print(
                f"[CCTV {self.cctv_id}] "
                "Capture Worker 종료"
            )

    # =====================================================
    # Status Callback
    # =====================================================

    def _notify_status(
        self,
        on_status: Callable[[str], None] | None,
        status: str,
    ) -> None:
        """
        외부에 CCTV 연결 상태 변경을 알린다.

        CaptureWorker는 DB에 직접 의존하지 않는다.
        """

        if on_status is None:
            return

        try:

            on_status(status)

        except Exception as exc:

            print(
                f"[CCTV {self.cctv_id}] "
                f"상태 callback 실패 "
                f"({status}): {exc}"
            )

    # =====================================================
    # Reconnect Wait
    # =====================================================

    def _wait_before_reconnect(
        self,
    ) -> bool:
        """
        자동 재연결 전 대기한다.

        True:
            Worker 종료

        False:
            재연결 계속 진행
        """

        print(
            f"[CCTV {self.cctv_id}] "
            f"{self.reconnect_delay_sec}초 후 재연결"
        )

        return self._stop_event.wait(
            self.reconnect_delay_sec
        )

    # =====================================================
    # 최대 재연결 실패 후 외부 요청 대기
    # =====================================================

    def _wait_for_reconnect_request(
        self,
    ) -> bool:
        """
        최대 자동 재연결 횟수를 모두 사용한 뒤
        외부 request_reconnect() 요청을 기다린다.
        """

        while not self._stop_event.is_set():

            requested = (
                self._reconnect_event.wait(
                    timeout=0.5
                )
            )

            if not requested:
                continue

            if self._stop_event.is_set():
                return False

            self._reconnect_event.clear()

            return True

        return False