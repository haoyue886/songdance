-- Run in the selected Supabase project as its existing migration role (postgres).
-- This alternative does not grant access to the provider-owned auth schema.
-- Only the same nine fields are exposed in a private, non-API schema.
-- Keep the dedicated LOGIN role and its existing password; grant it membership
-- in songdance_auth_reader separately. Set SONGDANCE_AUTH_SESSION_SCHEMA=songdance_auth.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'songdance_auth_reader') THEN
    CREATE ROLE songdance_auth_reader NOLOGIN;
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS songdance_auth;
REVOKE ALL ON SCHEMA songdance_auth FROM PUBLIC;

-- Default view semantics check the migration owner's permissions on auth.
-- The views are not SECURITY INVOKER: the reader never needs auth schema USAGE.
CREATE OR REPLACE VIEW songdance_auth.sessions WITH (security_barrier = true) AS
  SELECT id, user_id, created_at, refreshed_at, not_after FROM auth.sessions;
CREATE OR REPLACE VIEW songdance_auth.users WITH (security_barrier = true) AS
  SELECT id, email_confirmed_at, banned_until, deleted_at FROM auth.users;
REVOKE ALL ON songdance_auth.sessions, songdance_auth.users FROM PUBLIC;
GRANT USAGE ON SCHEMA songdance_auth TO songdance_auth_reader;
GRANT SELECT ON songdance_auth.sessions, songdance_auth.users TO songdance_auth_reader;
