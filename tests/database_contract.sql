-- 분리한 DDL의 생성 순서·누락을 실제 PostgreSQL에서 검사합니다.
DO $$
DECLARE actual integer;
BEGIN
    SELECT count(*) INTO actual FROM information_schema.tables
      WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
    IF actual <> 14 THEN RAISE EXCEPTION 'Expected 14 tables, got %', actual; END IF;
    SELECT count(*) INTO actual FROM information_schema.columns WHERE table_schema = 'public';
    IF actual <> 134 THEN RAISE EXCEPTION 'Expected 134 columns, got %', actual; END IF;
    SELECT count(*) INTO actual FROM information_schema.table_constraints
      WHERE table_schema = 'public' AND constraint_type = 'FOREIGN KEY';
    IF actual <> 20 THEN RAISE EXCEPTION 'Expected 20 foreign keys, got %', actual; END IF;
    IF enum_range(NULL::monitored_mode_enum)::text <> '{BASE,ALERT,POST_ALERT,VERIFY}' THEN
        RAISE EXCEPTION 'Monitoring modes do not match the confirmed policy';
    END IF;
END $$;
