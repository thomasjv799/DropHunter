-- Apply after the base schema. Supports existing Supabase (public) and home
-- server (drophunter) tables without moving or copying any existing data.
BEGIN;

DO $$
DECLARE
    app_schema text;
BEGIN
    FOREACH app_schema IN ARRAY ARRAY['public', 'drophunter'] LOOP
        IF to_regclass(format('%I.allowed_users', app_schema)) IS NOT NULL THEN
            EXECUTE format(
                'ALTER TABLE %I.allowed_users ADD COLUMN IF NOT EXISTS email text', app_schema
            );
            EXECUTE format('ALTER TABLE %I.allowed_users ENABLE ROW LEVEL SECURITY', app_schema);
        END IF;
    END LOOP;
END $$;

CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS ops.job_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('ok', 'error')),
    error_text text,
    counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_job_runs_started_at ON ops.job_runs (started_at);
ALTER TABLE ops.job_runs ENABLE ROW LEVEL SECURITY;

-- No API grants or public policies: only the trusted server database role
-- accesses these records. A separate reporting role needs explicit SELECT grants.
COMMIT;
