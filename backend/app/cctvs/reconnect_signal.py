from __future__ import annotations


RECONNECT_CHANNEL = (
    "octv_cctv_reconnect"
)


def publish_reconnect_request(
    connection,
    cctv_id: int,
) -> None:
    """
    PostgreSQL NOTIFY를 이용해
    CCTV Runtime에 수동 재연결 요청을 전달한다.

    실제 CCTV 재연결은 수행하지 않는다.

    이 함수는 현재 DB transaction 안에서
    NOTIFY를 등록하며, PostgreSQL 특성상
    transaction commit 이후 Listener에 전달된다.
    """

    if cctv_id <= 0:
        raise ValueError(
            "cctv_id는 1 이상이어야 합니다."
        )

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT pg_notify(
                %s,
                %s
            );
            """,
            (
                RECONNECT_CHANNEL,
                str(cctv_id),
            ),
        )