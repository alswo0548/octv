"""CCTV Runtime에 Incident Pipeline과 VERIFY 제어를 연결합니다."""

from __future__ import annotations

from ai.contracts import (
    Detection,
    Frame,
)

from ai.detection.cctv_runtime import (
    CctvDetectionRuntime,
)

from ai.detection.incident_pipeline import (
    IncidentPipeline,
    IncidentPipelineConfig,
)

from ai.detection.verify_restore_store import (
    RedisVerifyRestoreStore,
)

from ai.detection.yolo_worker import (
    YoloPerformance,
)

from backend.app.cctvs import (
    repository as cctv_repository,
)

from backend.app.db.session import (
    get_connection,
)


class IncidentAwareCctvDetectionRuntime(
    CctvDetectionRuntime
):
    """
    실제 운영 CCTV Runtime.

    전체 흐름:

    CCTV Frame
        ↓
    Sampling
        ↓
    Quality Check
        ↓
    YOLO
        ↓
    위험 후보
        ↓
    CCTV monitored_mode = VERIFY
        ↓
    VERIFY 분석 주기 적용
        ↓
    최대 validation window 동안 반복 확인
        ↓
    최소 탐지 횟수 충족
        ↓
    Incident 생성 / 갱신
        ↓
    원래 BASE / ALERT / POST_ALERT 복귀

    DB 구조는 변경하지 않는다.

    VERIFY 이전 감시 모드는:

        Runtime 메모리
        +
        Redis

    에 저장한다.

    Redis 기록은 프로세스가 비정상 종료되어
    메모리가 사라졌을 때의 복구 Journal이다.

    따라서:

    BASE
        → VERIFY
        → crash
        → Runtime restart
        → BASE

    ALERT
        → VERIFY
        → crash
        → Runtime restart
        → ALERT

    POST_ALERT
        → VERIFY
        → crash
        → Runtime restart
        → POST_ALERT

    로 복구할 수 있다.
    """

    def __init__(
        self,
        *args,
        incident_pipeline: (
            IncidentPipeline
            | None
        ) = None,
        **kwargs,
    ) -> None:

        super().__init__(
            *args,
            **kwargs,
        )

        # ----------------------------------------------------
        # Runtime 메모리의 VERIFY 복구 정보
        # ----------------------------------------------------

        self._verify_restore_mode_by_cctv: dict[
            int,
            str,
        ] = {}

        # ----------------------------------------------------
        # 테스트 Pipeline 직접 주입
        #
        # 기존 통합 테스트에서는 Redis를 사용하지 않는다.
        # 실제 운영 Runtime에서만 Redis Store를 초기화한다.
        # ----------------------------------------------------

        if incident_pipeline is not None:

            self._verify_restore_store = None

            self._incident_pipeline = (
                incident_pipeline
            )

            return

        # ----------------------------------------------------
        # Redis VERIFY Recovery Store
        # ----------------------------------------------------

        self._verify_restore_store = (
            RedisVerifyRestoreStore()
        )

        try:

            redis_ok = (
                self
                ._verify_restore_store
                .ping()
            )

        except Exception as exc:

            raise RuntimeError(
                "CCTV Runtime의 VERIFY 복구용 "
                "Redis에 연결할 수 없습니다. "
                f"error={exc}"
            ) from exc

        if not redis_ok:

            raise RuntimeError(
                "CCTV Runtime의 VERIFY 복구용 "
                "Redis PING에 실패했습니다."
            )

        print(
            "[VERIFY RECOVERY] "
            "Redis 연결 완료"
        )

        # ----------------------------------------------------
        # 이전 Runtime crash로 남은 VERIFY 복구
        #
        # Capture / Sampling 시작 전에 실행한다.
        # ----------------------------------------------------

        self._recover_stale_verify_modes()

        # ----------------------------------------------------
        # Incident Pipeline
        # ----------------------------------------------------

        settings = (
            self._load_monitoring_settings()
        )

        incident_config = (
            IncidentPipelineConfig
            .from_settings(
                settings
            )
        )

        self._incident_pipeline = (
            IncidentPipeline(
                config=(
                    incident_config
                )
            )
        )

        print(
            "[INCIDENT RUNTIME] "
            "monitoring_settings 적용 "
            f"/ candidate_confidence="
            f"{incident_config.candidate_confidence_threshold:.2f} "
            f"/ incident_confidence="
            f"{incident_config.incident_confidence_threshold:.2f} "
            f"/ min_hits="
            f"{incident_config.candidate_min_detection_count} "
            f"/ validation_window="
            f"{incident_config.temporal_validation_sec:.1f}s"
        )

    # =====================================================
    # Redis Store Helper
    # =====================================================

    def _get_verify_restore_store(
        self,
    ):

        return getattr(
            self,
            "_verify_restore_store",
            None,
        )

    # =====================================================
    # VERIFY 이전 모드 기억
    # =====================================================

    def _remember_verify_restore_mode(
        self,
        cctv_id: int,
        restore_mode: str,
    ) -> None:
        """
        DB VERIFY Transaction이 commit되기 전에
        Redis에 이전 감시 모드를 기록한다.

        Redis 저장에 실패하면 예외가 발생한다.

        이 메서드는 enter_verify_mode()와
        같은 DB Transaction 안에서 호출되므로
        Redis 저장 실패 시 DB VERIFY 전환 역시
        rollback된다.
        """

        normalized_mode = str(
            restore_mode
        ).upper()

        if (
            normalized_mode
            not in
            cctv_repository
            .VERIFY_RESTORE_MODES
        ):

            raise ValueError(
                "VERIFY 복구 모드가 "
                "올바르지 않습니다. "
                f"mode={normalized_mode}"
            )

        store = (
            self._get_verify_restore_store()
        )

        if store is not None:

            store.save(
                cctv_id=cctv_id,
                restore_mode=(
                    normalized_mode
                ),
            )

        self._verify_restore_mode_by_cctv[
            cctv_id
        ] = normalized_mode

    # =====================================================
    # VERIFY 복구정보 제거
    # =====================================================

    def _forget_verify_restore_mode(
        self,
        cctv_id: int,
    ) -> None:
        """
        DB의 VERIFY 복구가 완료된 뒤
        Redis Journal과 메모리 상태를 제거한다.

        Redis 삭제에 실패하면 메모리 상태를 유지해서
        이후 다시 정리할 수 있게 한다.
        """

        store = (
            self._get_verify_restore_store()
        )

        if store is not None:

            try:

                store.delete(
                    cctv_id
                )

            except Exception as exc:

                print(
                    "[VERIFY STATE ERROR] "
                    "Redis 복구정보 삭제 실패 "
                    f"/ cctv={cctv_id} "
                    f"/ error={exc}"
                )

                return

        self._verify_restore_mode_by_cctv.pop(
            cctv_id,
            None,
        )

    # =====================================================
    # Runtime Startup Crash Recovery
    # =====================================================

    def _recover_stale_verify_modes(
        self,
    ) -> None:
        """
        이전 CCTV Runtime이 비정상 종료되어
        Redis에 VERIFY 복구정보가 남아 있다면
        Runtime 시작 전에 복구한다.

        Redis:
            CCTV 1 → ALERT

        DB:
            CCTV 1 → VERIFY

        라면:

            VERIFY → ALERT

        로 복구한다.

        반대로 DB가 이미 VERIFY가 아니라면
        다른 로직 또는 운영자가 상태를 변경한 것이므로
        DB 상태는 건드리지 않고 Redis Journal만 제거한다.
        """

        store = (
            self._get_verify_restore_store()
        )

        if store is None:
            return

        try:

            restore_modes = (
                store.load_all()
            )

        except Exception as exc:

            raise RuntimeError(
                "Redis VERIFY 복구정보를 "
                "조회할 수 없습니다. "
                f"error={exc}"
            ) from exc

        if not restore_modes:
            return

        print(
            "[VERIFY RECOVERY] "
            "이전 Runtime의 VERIFY 복구정보 발견 "
            f"/ count={len(restore_modes)}"
        )

        for (
            cctv_id,
            restore_mode,
        ) in restore_modes.items():

            normalized_mode = str(
                restore_mode
            ).upper()

            if (
                normalized_mode
                not in
                cctv_repository
                .VERIFY_RESTORE_MODES
            ):

                raise RuntimeError(
                    "Redis VERIFY 복구정보에 "
                    "잘못된 감시 모드가 있습니다. "
                    f"cctv={cctv_id} "
                    f"mode={normalized_mode}"
                )

            try:

                with get_connection() as connection:

                    row = (
                        cctv_repository
                        .restore_from_verify_mode(
                            connection,
                            cctv_id=cctv_id,
                            restore_mode=(
                                normalized_mode
                            ),
                        )
                    )

            except Exception as exc:

                # 복구에 실패했다면 Journal을 지우지 않는다.
                #
                # Runtime을 시작하지 않음으로써
                # stale VERIFY를 정상 상태처럼
                # 계속 운영하는 것을 막는다.
                raise RuntimeError(
                    "stale VERIFY 복구에 "
                    "실패했습니다. "
                    f"cctv={cctv_id} "
                    f"restore={normalized_mode} "
                    f"error={exc}"
                ) from exc

            try:

                store.delete(
                    cctv_id
                )

            except Exception as exc:

                raise RuntimeError(
                    "stale VERIFY는 복구했지만 "
                    "Redis Journal 삭제에 "
                    "실패했습니다. "
                    f"cctv={cctv_id} "
                    f"error={exc}"
                ) from exc

            if row is None:

                print(
                    "[VERIFY RECOVERY] "
                    f"CCTV {cctv_id} "
                    "/ DB가 이미 VERIFY가 아님 "
                    "/ 현재 DB 상태 유지 "
                    "/ Redis Journal 삭제"
                )

                continue

            print(
                "[VERIFY RECOVERY] "
                f"CCTV {cctv_id} "
                f"/ stale VERIFY "
                f"→ {normalized_mode}"
            )

    # =====================================================
    # YOLO Result
    # =====================================================

    def _handle_yolo_result(
        self,
        frame: Frame,
        detections: list[
            Detection
        ],
        performance: YoloPerformance,
    ) -> None:
        """
        YOLO 결과를 Incident Pipeline으로 전달하고
        Temporal 상태에 맞게 VERIFY 모드를 제어한다.

        Detection이 없는 Frame도
        Pipeline에 반드시 전달한다.
        """

        # 기존 Detection 로그 유지.
        super()._handle_yolo_result(
            frame,
            detections,
            performance,
        )

        result = (
            self._incident_pipeline
            .handle_result(
                frame=frame,
                detections=detections,
                performance=performance,
            )
        )

        # 기존 테스트 Fake Pipeline 등과의
        # 호환성을 위해 None이면
        # VERIFY 제어를 수행하지 않는다.
        if result is None:
            return

        # Pipeline 자체 오류가 발생한 경우에는
        # 현재 VERIFY 상태를 임의로 바꾸지 않는다.
        if result.had_error:
            return

        cctv_id = int(
            frame.cctv_id
        )

        # 아직 검증 중인 hazard가 하나라도 있으면
        # VERIFY를 유지한다.
        if result.pending_hazards:

            self._ensure_verify_mode(
                cctv_id=cctv_id,
                pending_hazards=(
                    result.pending_hazards
                ),
            )

            return

        # pending hazard가 없어졌다면
        # VERIFY 세션이 성공 또는 실패로 끝난 것.
        self._restore_verify_mode(
            cctv_id=cctv_id
        )

    # =====================================================
    # VERIFY 진입
    # =====================================================

    def _ensure_verify_mode(
        self,
        cctv_id: int,
        pending_hazards: tuple[
            str,
            ...
        ],
    ) -> None:

        # 이미 이 Runtime이 VERIFY 전환을 수행했고
        # 원래 모드를 기억하고 있으면
        # 중복 DB UPDATE를 하지 않는다.
        if (
            cctv_id
            in self
            ._verify_restore_mode_by_cctv
        ):
            return

        transition = None

        try:

            with get_connection() as connection:

                transition = (
                    cctv_repository
                    .enter_verify_mode(
                        connection,
                        cctv_id,
                    )
                )

                if (
                    transition[
                        "changed"
                    ]
                ):

                    previous_mode = (
                        transition[
                            "previous_mode"
                        ]
                    )

                    if previous_mode is None:

                        raise RuntimeError(
                            "VERIFY 전환 전 모드를 "
                            "확인할 수 없습니다. "
                            f"cctv={cctv_id}"
                        )

                    # -----------------------------------------
                    # 중요:
                    #
                    # DB Transaction commit 전에
                    # Redis Journal을 먼저 저장한다.
                    #
                    # Redis 저장 실패
                    #     → Exception
                    #     → DB VERIFY UPDATE rollback
                    #
                    # Redis 저장 성공 후 process crash
                    #     → 다음 Runtime에서 Redis Journal로
                    #       복구 가능
                    # -----------------------------------------

                    self._remember_verify_restore_mode(
                        cctv_id=cctv_id,
                        restore_mode=str(
                            previous_mode
                        ),
                    )

        except Exception as exc:

            print(
                "[VERIFY MODE ERROR] "
                "VERIFY 전환 실패 "
                f"/ cctv={cctv_id} "
                f"/ error={exc}"
            )

            return

        if transition is None:
            return

        if (
            transition[
                "changed"
            ]
        ):

            previous_mode = (
                transition[
                    "previous_mode"
                ]
            )

            print(
                "[VERIFY MODE] "
                f"CCTV {cctv_id} "
                f"/ {previous_mode} "
                "→ VERIFY "
                f"/ pending="
                f"{','.join(pending_hazards)}"
            )

            return

        current_mode = str(
            transition[
                "monitored_mode"
            ]
        )

        # 이미 VERIFY인데 현재 Runtime 메모리에도,
        # Redis에도 이전 상태가 없다면
        # 임의의 restore mode를 만들지 않는다.
        if current_mode == "VERIFY":

            print(
                "[VERIFY MODE] "
                f"CCTV {cctv_id} "
                "/ 이미 VERIFY "
                "/ restore mode 미확인"
            )

    # =====================================================
    # VERIFY 복귀
    # =====================================================

    def _restore_verify_mode(
        self,
        cctv_id: int,
    ) -> None:

        restore_mode = (
            self
            ._verify_restore_mode_by_cctv
            .get(
                cctv_id
            )
        )

        if restore_mode is None:
            return

        try:

            with get_connection() as connection:

                row = (
                    cctv_repository
                    .restore_from_verify_mode(
                        connection,
                        cctv_id=cctv_id,
                        restore_mode=(
                            restore_mode
                        ),
                    )
                )

        except Exception as exc:

            print(
                "[VERIFY MODE ERROR] "
                "VERIFY 복귀 실패 "
                f"/ cctv={cctv_id} "
                f"/ restore="
                f"{restore_mode} "
                f"/ error={exc}"
            )

            # DB 복귀 실패:
            #
            # Runtime 메모리와 Redis Journal을
            # 그대로 유지한다.
            #
            # 다음 Frame 또는 다음 Runtime 시작에서
            # 다시 복구할 수 있다.
            return

        # DB Transaction이 정상 종료된 후
        # Redis Journal + 메모리 복구정보 제거.
        self._forget_verify_restore_mode(
            cctv_id
        )

        if row is None:

            print(
                "[VERIFY MODE] "
                f"CCTV {cctv_id} "
                "/ VERIFY 복귀 UPDATE 생략 "
                "/ DB 상태가 이미 변경됨"
            )

            return

        print(
            "[VERIFY MODE] "
            f"CCTV {cctv_id} "
            f"/ VERIFY "
            f"→ {restore_mode}"
        )

    # =====================================================
    # Runtime 정상 종료 시 VERIFY 복구
    # =====================================================

    def stop(
        self,
    ) -> None:
        """
        Runtime 정상 종료 시:

        1. Capture / YOLO / Monitor를 모두 종료한다.
        2. 이 Runtime이 VERIFY로 전환했던 CCTV를
           원래 BASE / ALERT / POST_ALERT로 복귀시킨다.
        3. Redis Journal도 제거한다.

        process crash처럼 stop() 자체가 실행되지 않는 경우는
        Redis Journal이 다음 Runtime까지 남으므로
        startup recovery에서 처리한다.
        """

        try:

            super().stop()

        finally:

            self._restore_all_verify_modes()

    def _restore_all_verify_modes(
        self,
    ) -> None:

        cctv_ids = tuple(
            self
            ._verify_restore_mode_by_cctv
            .keys()
        )

        if not cctv_ids:
            return

        print(
            "[VERIFY MODE] "
            "Runtime 종료 전 VERIFY 복구 시작 "
            f"/ count={len(cctv_ids)}"
        )

        for cctv_id in cctv_ids:

            self._restore_verify_mode(
                cctv_id=cctv_id
            )