"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""
# DB에 물어보고 결과를 돌려주는 역할을 하는 코드


# 이메일로 사용자 조회
def find_user_by_email(connection, email: str) -> dict | None:      # connection : PostgreSQL 연결 객체. email → 찾으려는 이메일 -> 사용자 존재시 dict 리턴, 존재하지 않을 시 none 리턴
    with connection.cursor() as cursor: 
        cursor.execute(     # sql 실행
            """
            SELECT
                id,
                email,
                password_hash,
                name,
                role,
                is_active,
                agency_id,
                notification_enabled
            FROM users
            WHERE lower(btrim(email)) = lower(btrim(%s))
            """,
            (email,),
        )

        return cursor.fetchone()        # SQL 조회 결과 중 한 행만 가져오는 함수. 검색 결과 있으면 dict 리턴, 없으면 none 리턴
    # commit은 db/session.py에서 psycopg의 connection context manager는 정상적으로 끝나면 commit하고, 중간에 예외가 발생하면 rollback해.


# 기관 존재 여부 확인
def agency_exists(connection, agency_id: int) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM agencies
            WHERE id = %s
            """,
            (agency_id,),
        )

        return cursor.fetchone() is not None    # 기관 있으면 True, 기관 없으면 False리턴. (기관 없으면 None 리턴 -> None is not None => False)


# 사용자 저장
def insert_user(connection, user_data: dict) -> dict:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO users (
                email,
                password_hash,
                name,
                role,
                agency_id
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING
                id,
                email,
                name,
                role,
                agency_id,
                is_active,
                notification_enabled
            """,        # RETURNING : INSERT한 다음 방금 저장된 행에서 이 컬럼들을 바로 돌려줘. 라는 의미 => 즉 insert와 동시에 dict 받을 수 있음.
            (
                user_data["email"],
                user_data["password_hash"],
                user_data["name"],
                user_data["role"],
                user_data["agency_id"],
            ),
        )

        return cursor.fetchone()


# 기존 jwt에 "sub": str(user_id)만 넣음 -> users.id 이용해 조회할 필요가 있어서 만든 함수
def find_user_by_id(connection, user_id: int) -> dict | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                email,
                password_hash,
                name,
                role,
                is_active,
                agency_id,
                notification_enabled
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        return cursor.fetchone()