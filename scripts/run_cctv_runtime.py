from __future__ import annotations

import signal

from ai.detection.cctv_runtime import (
    CctvDetectionRuntime,
)


def main() -> None:

    runtime = (
        CctvDetectionRuntime()
    )

    # =====================================================
    # Windows Ctrl+C / 배포 SIGTERM 대응
    # =====================================================

    def handle_signal(
        signum,
        frame,
    ) -> None:

        print()

        print(
            f"[PROCESS] "
            f"종료 Signal 수신 "
            f"/ signum={signum}"
        )

        runtime.request_stop()

    signal.signal(
        signal.SIGINT,
        handle_signal,
    )

    if hasattr(
        signal,
        "SIGTERM",
    ):

        signal.signal(
            signal.SIGTERM,
            handle_signal,
        )

    # =====================================================
    # Runtime 실행
    # =====================================================

    runtime.run_forever()


if __name__ == "__main__":

    main()