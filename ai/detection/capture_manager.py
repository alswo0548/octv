from __future__ import annotations

from dataclasses import dataclass
from threading import Lock, Thread
from typing import Callable, Mapping, Protocol, Sequence

from ai.contracts import Frame


class CaptureWorkerProtocol(Protocol):
    """
    CaptureWorkerManager가 필요로 하는
    CaptureWorker 최소 인터페이스.

    실제 CaptureWorker뿐 아니라
    테스트용 Fake Worker도 사용할 수 있다.
    """

    def run(
        self,
        on_frame: Callable[[Frame], None],
        on_status: Callable[[str], None],
    ) -> None:
        ...

    def stop(self) -> None:
        ...


WorkerFactory = Callable[
    [Mapping[str, object]],
    CaptureWorkerProtocol,
]

FrameCallback = Callable[
    [Frame],
    None,
]

StatusCallback = Callable[
    [int, str],
    None,
]


@dataclass
class ManagedCaptureWorker:
    """
    CCTV 한 대에 대응하는
    Worker + Thread 묶음.
    """

    cctv_id: int

    worker: CaptureWorkerProtocol

    thread: Thread


class CaptureWorkerManager:
    """
    여러 CCTV의 CaptureWorker를 관리한다.

    역할
    ----
    1. CCTV별 CaptureWorker 생성
    2. CCTV별 Thread 시작
    3. 새 CCTV가 생기면 Worker 시작
    4. 감시 대상에서 빠지면 Worker 종료
    5. 전체 Worker 일괄 종료

    이 Manager는
    CCTV Stream 자체의 reconnect는 담당하지 않는다.

    각 CCTV 내부 reconnect는
    기존 CaptureWorker가 담당한다.

    Manager는 오직
    '어떤 CCTV Worker가 살아 있어야 하는가'
    를 관리한다.
    """

    def __init__(
        self,
        worker_factory: WorkerFactory,
        on_frame: FrameCallback,
        on_status: StatusCallback,
    ) -> None:

        self._worker_factory = (
            worker_factory
        )

        self._on_frame = (
            on_frame
        )

        self._on_status = (
            on_status
        )

        self._lock = Lock()

        self._workers: dict[
            int,
            ManagedCaptureWorker,
        ] = {}

    # =====================================================
    # 내부 Helper
    # =====================================================

    @staticmethod
    def _get_cctv_id(
        cctv: Mapping[str, object],
    ) -> int:

        raw_cctv_id = (
            cctv.get(
                "id"
            )
        )

        if raw_cctv_id is None:

            raise ValueError(
                "CCTV 데이터에 "
                "'id'가 없습니다."
            )

        return int(
            raw_cctv_id
        )

    def _run_worker(
        self,
        cctv_id: int,
        worker: CaptureWorkerProtocol,
    ) -> None:
        """
        실제 Worker Thread 진입점.

        기존 CaptureWorker의
        on_status(status) Callback을

        외부에서는

        on_status(cctv_id, status)

        형태로 받을 수 있도록
        CCTV ID를 붙여준다.
        """

        def handle_status(
            status: str,
        ) -> None:

            self._on_status(
                cctv_id,
                status,
            )

        try:

            worker.run(
                on_frame=(
                    self._on_frame
                ),
                on_status=(
                    handle_status
                ),
            )

        except Exception as exc:

            print(
                f"[CAPTURE MANAGER ERROR] "
                f"CCTV {cctv_id} "
                f"Worker 비정상 종료 "
                f"/ error={exc}"
            )

            try:

                self._on_status(
                    cctv_id,
                    "DISCONNECTED",
                )

            except Exception as callback_exc:

                print(
                    "[CAPTURE MANAGER ERROR] "
                    f"CCTV {cctv_id} "
                    "DISCONNECTED Callback 실패 "
                    f"/ error={callback_exc}"
                )

    # =====================================================
    # 단일 CCTV 시작
    # =====================================================

    def start_cctv(
        self,
        cctv: Mapping[str, object],
    ) -> bool:
        """
        CCTV Worker를 시작한다.

        이미 정상 실행 중이면
        아무것도 하지 않고 False.

        새로 시작하면 True.
        """

        cctv_id = (
            self._get_cctv_id(
                cctv
            )
        )

        with self._lock:

            existing = (
                self._workers.get(
                    cctv_id
                )
            )

            if (
                existing is not None
                and existing.thread.is_alive()
            ):

                return False

            if existing is not None:

                self._workers.pop(
                    cctv_id,
                    None,
                )

            worker = (
                self._worker_factory(
                    cctv
                )
            )

            thread = Thread(
                target=self._run_worker,
                args=(
                    cctv_id,
                    worker,
                ),
                name=(
                    f"capture-worker-"
                    f"{cctv_id}"
                ),
            )

            managed = (
                ManagedCaptureWorker(
                    cctv_id=cctv_id,
                    worker=worker,
                    thread=thread,
                )
            )

            self._workers[
                cctv_id
            ] = managed

            thread.start()

        print(
            f"[CAPTURE MANAGER] "
            f"CCTV {cctv_id} "
            "Worker 시작"
        )

        return True

    # =====================================================
    # 단일 CCTV 종료
    # =====================================================

    def stop_cctv(
        self,
        cctv_id: int,
        join_timeout_sec: float = 10.0,
    ) -> bool:
        """
        CCTV Worker 하나를 종료한다.

        실행 중인 Worker가 없으면 False.
        정상 종료 요청을 했다면 True.
        """

        with self._lock:

            managed = (
                self._workers.pop(
                    cctv_id,
                    None,
                )
            )

        if managed is None:

            return False

        print(
            f"[CAPTURE MANAGER] "
            f"CCTV {cctv_id} "
            "Worker 종료 요청"
        )

        managed.worker.stop()

        managed.thread.join(
            timeout=(
                join_timeout_sec
            )
        )

        if (
            managed.thread.is_alive()
        ):

            raise RuntimeError(
                f"CCTV {cctv_id} "
                "CaptureWorker Thread가 "
                f"{join_timeout_sec:.1f}초 안에 "
                "종료되지 않았습니다."
            )

        print(
            f"[CAPTURE MANAGER] "
            f"CCTV {cctv_id} "
            "Worker 종료 완료"
        )

        return True

    # =====================================================
    # DB 상태 ↔ 실행 Worker 동기화
    # =====================================================

    def sync(
        self,
        cctvs: Sequence[
            Mapping[str, object]
        ],
    ) -> dict[str, list[int]]:
        """
        전달된 CCTV 목록과
        현재 실행 중 Worker를 맞춘다.

        전달 목록에 새 CCTV가 있으면 시작.

        기존에는 실행 중인데
        전달 목록에서 사라졌으면 종료.

        반환 예:
        {
            "started": [2, 3],
            "stopped": [1],
            "running": [2, 3],
        }
        """

        desired_by_id: dict[
            int,
            Mapping[str, object],
        ] = {}

        for cctv in cctvs:

            cctv_id = (
                self._get_cctv_id(
                    cctv
                )
            )

            desired_by_id[
                cctv_id
            ] = cctv

        desired_ids = set(
            desired_by_id.keys()
        )

        with self._lock:

            current_ids = set(
                self._workers.keys()
            )

            dead_ids = {
                cctv_id
                for (
                    cctv_id,
                    managed,
                ) in self._workers.items()
                if not (
                    managed.thread.is_alive()
                )
            }

        # 이미 죽어 있는 Worker는
        # 재시작 대상으로 취급한다.
        for cctv_id in dead_ids:

            with self._lock:

                self._workers.pop(
                    cctv_id,
                    None,
                )

        current_ids -= (
            dead_ids
        )

        to_stop = sorted(
            current_ids
            - desired_ids
        )

        to_start = sorted(
            (
                desired_ids
                - current_ids
            )
            | (
                dead_ids
                & desired_ids
            )
        )

        stopped: list[int] = []

        started: list[int] = []

        # 먼저 더 이상 필요 없는
        # Worker를 종료한다.
        for cctv_id in to_stop:

            if self.stop_cctv(
                cctv_id
            ):

                stopped.append(
                    cctv_id
                )

        # 새로 필요한 Worker 시작.
        for cctv_id in to_start:

            cctv = (
                desired_by_id[
                    cctv_id
                ]
            )

            if self.start_cctv(
                cctv
            ):

                started.append(
                    cctv_id
                )

        running = (
            self.running_cctv_ids()
        )

        return {
            "started":
                started,

            "stopped":
                stopped,

            "running":
                running,
        }

    # =====================================================
    # 전체 종료
    # =====================================================

    def stop_all(
        self,
        join_timeout_sec: float = 10.0,
    ) -> None:
        """
        현재 실행 중인
        모든 CCTV Worker를 종료한다.
        """

        with self._lock:

            cctv_ids = sorted(
                self._workers.keys()
            )

        for cctv_id in cctv_ids:

            self.stop_cctv(
                cctv_id=cctv_id,
                join_timeout_sec=(
                    join_timeout_sec
                ),
            )

    # =====================================================
    # 조회
    # =====================================================

    def running_cctv_ids(
        self,
    ) -> list[int]:
        """
        현재 살아 있는
        CCTV Worker ID 목록.
        """

        with self._lock:

            running = [
                cctv_id
                for (
                    cctv_id,
                    managed,
                ) in self._workers.items()
                if (
                    managed.thread.is_alive()
                )
            ]

        return sorted(
            running
        )

    def is_running(
        self,
        cctv_id: int,
    ) -> bool:
        """
        특정 CCTV Worker가
        현재 실행 중인지 확인한다.
        """

        with self._lock:

            managed = (
                self._workers.get(
                    cctv_id
                )
            )

            if managed is None:

                return False

            return (
                managed.thread.is_alive()
            )

    def worker_count(
        self,
    ) -> int:
        """
        현재 살아 있는
        CaptureWorker 수.
        """

        return len(
            self.running_cctv_ids()
        )