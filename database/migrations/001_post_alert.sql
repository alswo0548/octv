-- 기존 OCTV DB 전용: 해제 후 확인 대기 값을 추가합니다. 데이터/테이블 삭제 없음.
-- 반복 실행 가능. 새로운 DB에는 이미 포함되어 있습니다.
-- 기존 CCTV 행의 상태는 임의 변경하지 않습니다.
\set ON_ERROR_STOP on
ALTER TYPE public.monitored_mode_enum ADD VALUE IF NOT EXISTS 'POST_ALERT' BEFORE 'VERIFY';
