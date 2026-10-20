from __future__ import annotations

from collections.abc import Callable
from threading import Event

import psycopg
from psycopg import sql

from backend.app.config import (
    database_connect_kwargs,
)
from backend.app.cctvs.reconnect_signal import (
    RECONNECT_CHANNEL,
)


DEFAULT_LISTEN_TIMEOUT_SEC = 1.0
DEFAULT_DB_RECONNECT_DELAY_SEC = 2.0


class CctvReconnectListener:
    """
    PostgreSQL LISTEN / NOTIFY를 이용해
    관리자 수동 CCTV 재연결 요청을 수신한다.

    이 Listener는 CCTV Runtime 프로세스 내부에서
    전용 Thread로 실행된다.

    실제 재연결은 직접 수행하지 않고,
    전달받은 reconnect_requester를 호출한다.
    """

    def __init__(
        self,
        *,
        stop_event: Event,
        reconnect_requester: Callable[
            [int],
            None,
        ],
        listen_timeout_sec: float = (
            DEFAULT_LISTEN_TIMEOUT_SEC
        ),
        db_reconnect_delay_sec: float = (
            DEFAULT_DB_RECONNECT_DELAY_SEC
        ),
    ) -> None:

        if listen_timeout_sec <= 0:
            raise ValueError(
                "listen_timeout_sec은 "
                "0보다 커야 합니다."
            )

        if db_reconnect_delay_sec < 0:
            raise ValueError(
                "db_reconnect_delay_sec은 "
                "0 이상이어야 합니다."
            )

        self._stop_event = (
            stop_event
        )

        self._reconnect_requester = (
            reconnect_requester
        )

        self._listen_timeout_sec = float(
            listen_timeout_sec
        )

        self._db_reconnect_delay_sec = float(
            db_reconnect_delay_sec
        )

    def run(
        self,
    ) -> None:
        """
        Runtime 종료 요청 전까지
        PostgreSQL 재연결 명령을 계속 수신한다.

        DB 연결이 끊기면 Runtime 전체를 종료하지 않고
        일정 시간 후 LISTEN 연결만 다시 생성한다.
        """

        print(
            "[RECONNECT LISTENER] "
            "시작"
        )

        while not self._stop_event.is_set():

            try:

                self._listen_once()

            except (
                psycopg.Error,
                OSError,
            ) as exc:

                if self._stop_event.is_set():
                    break

                print(
                    "[RECONNECT LISTENER ERROR] "
                    "PostgreSQL 연결 오류 "
                    f"/ {exc}"
                )

                if self._stop_event.wait(
                    self._db_reconnect_delay_sec
                ):
                    break

            except Exception as exc:

                if self._stop_event.is_set():
                    break

                print(
                    "[RECONNECT LISTENER ERROR] "
                    f"{exc}"
                )

                if self._stop_event.wait(
                    self._db_reconnect_delay_sec
                ):
                    break

        print(
            "[RECONNECT LISTENER] "
            "종료"
        )

    def _listen_once(
        self,
    ) -> None:
        """
        PostgreSQL LISTEN 전용 연결을 생성한다.

        연결이 끊어지면 예외를 run()으로 전달하고,
        run()에서 일정 시간 후 다시 연결한다.
        """

        connect_kwargs = (
            database_connect_kwargs()
        )

        with psycopg.connect(
            **connect_kwargs,
            autocommit=True,
        ) as connection:

            connection.execute(
                sql.SQL(
                    "LISTEN {}"
                ).format(
                    sql.Identifier(
                        RECONNECT_CHANNEL
                    )
                )
            )

            print(
                "[RECONNECT LISTENER] "
                "PostgreSQL LISTEN 준비 완료 "
                f"/ channel={RECONNECT_CHANNEL}"
            )

            while not self._stop_event.is_set():

                notifications = (
                    connection.notifies(
                        timeout=(
                            self._listen_timeout_sec
                        ),
                        stop_after=1,
                    )
                )

                for notification in notifications:

                    if self._stop_event.is_set():
                        return

                    self._handle_notification(
                        notification.payload
                    )

    def _handle_notification(
        self,
        payload: str,
    ) -> None:
        """
        NOTIFY payload를 CCTV ID로 검증한 뒤
        Runtime의 reconnect requester로 전달한다.
        """

        raw = str(
            payload
        ).strip()

        try:

            cctv_id = int(
                raw
            )

        except (
            TypeError,
            ValueError,
        ):

            print(
                "[RECONNECT LISTENER WARNING] "
                "잘못된 payload 무시 "
                f"/ payload={raw!r}"
            )

            return

        if cctv_id <= 0:

            print(
                "[RECONNECT LISTENER WARNING] "
                "잘못된 CCTV ID 무시 "
                f"/ cctv_id={cctv_id}"
            )

            return

        try:

            self._reconnect_requester(
                cctv_id
            )

        except Exception as exc:

            # 특정 CCTV Worker가 없거나
            # 재연결 요청 자체가 실패하더라도
            # Listener Thread는 계속 유지한다.
            print(
                "[RECONNECT REQUEST ERROR] "
                f"CCTV {cctv_id} "
                f"/ {exc}"
            )

            return

        print(
            "[RECONNECT REQUEST] "
            f"CCTV {cctv_id} "
            "수동 재연결 요청 수신"
        )