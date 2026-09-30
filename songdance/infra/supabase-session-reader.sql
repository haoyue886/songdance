-- Apply manually in the chosen Supabase project with an administrative migration role.
-- No password is created or stored here. Grant this NOLOGIN role to a dedicated LOGIN
-- role managed in the provider dashboard; use its TLS DSN in FastAPI only.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'songdance_auth_reader') THEN
    CREATE ROLE songdance_auth_reader NOLOGIN;
  END IF;
END $$;
GRANT USAGE ON SCHEMA auth TO songdance_auth_reader;
GRANT SELECT (id, user_id, created_at, refreshed_at, not_after)
  ON auth.sessions TO songdance_auth_reader;
GRANT SELECT (id, email_confirmed_at, banned_until, deleted_at)
  ON auth.users TO songdance_auth_reader;
-- Do not grant the LOGIN role membership in postgres/supabase_admin/service_role.
