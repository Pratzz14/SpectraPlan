CREATE TABLE IF NOT EXISTS spectraplan.assessment_jobs (
 run_id text PRIMARY KEY REFERENCES spectraplan.explainability_runs(run_id),
 owner_user_id text NOT NULL, idempotency_key text NOT NULL,
 request jsonb NOT NULL, status text NOT NULL DEFAULT 'queued',
 created_at timestamptz NOT NULL DEFAULT now(), claim_token text,
 lease_until timestamptz, corpus_version text, stage text NOT NULL DEFAULT 'queued',
 UNIQUE(owner_user_id,idempotency_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_customer_assessment ON spectraplan.assessment_jobs(owner_user_id)
 WHERE status IN ('queued','running');
REVOKE ALL ON spectraplan.assessment_jobs FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON spectraplan.assessment_jobs TO spectraplan_backend;
