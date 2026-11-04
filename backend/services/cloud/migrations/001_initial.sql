CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS spectraplan;
REVOKE ALL ON SCHEMA spectraplan FROM PUBLIC, anon, authenticated;

DO $$ BEGIN
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='spectraplan_backend') THEN
  CREATE ROLE spectraplan_backend NOLOGIN;
 END IF;
END $$;

CREATE TABLE IF NOT EXISTS spectraplan.enquiries (
 enquiry_id text PRIMARY KEY, original_description text NOT NULL,
 created_at text NOT NULL, updated_at text NOT NULL, owner_user_id text, customer_email text
);
CREATE INDEX IF NOT EXISTS enquiries_owner ON spectraplan.enquiries(owner_user_id);
CREATE TABLE IF NOT EXISTS spectraplan.explainability_runs (
 run_id text PRIMARY KEY, created_at text NOT NULL, description text NOT NULL,
 clarification_answers jsonb NOT NULL, run_json jsonb NOT NULL,
 enquiry_id text NOT NULL REFERENCES spectraplan.enquiries(enquiry_id),
 parent_run_id text REFERENCES spectraplan.explainability_runs(run_id),
 status text NOT NULL, round_no integer NOT NULL, draft_description text NOT NULL,
 lease_until timestamptz, UNIQUE(enquiry_id, round_no)
);
CREATE TABLE IF NOT EXISTS spectraplan.explainability_events (
 run_id text REFERENCES spectraplan.explainability_runs(run_id), sequence integer NOT NULL,
 stage text NOT NULL, event_type text NOT NULL, created_at text NOT NULL, payload_json jsonb NOT NULL,
 PRIMARY KEY(run_id,sequence)
);
CREATE TABLE IF NOT EXISTS spectraplan.corpus_versions (
 version text PRIMARY KEY, dataset text NOT NULL CHECK(dataset IN ('technical','website')),
 manifest jsonb NOT NULL, digest text NOT NULL, ready boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS spectraplan.active_corpora (
 dataset text PRIMARY KEY, version text NOT NULL REFERENCES spectraplan.corpus_versions(version)
);
CREATE TABLE IF NOT EXISTS spectraplan.corpus_documents (
 version text REFERENCES spectraplan.corpus_versions(version), path text NOT NULL,
 body text NOT NULL, sha256 text NOT NULL, PRIMARY KEY(version,path)
);
CREATE TABLE IF NOT EXISTS spectraplan.evidence (
 version text REFERENCES spectraplan.corpus_versions(version), evidence_id text NOT NULL,
 payload jsonb NOT NULL, PRIMARY KEY(version,evidence_id)
);
CREATE TABLE IF NOT EXISTS spectraplan.source_revisions (
 version text REFERENCES spectraplan.corpus_versions(version), source_id text NOT NULL,
 payload jsonb NOT NULL, PRIMARY KEY(version,source_id)
);
CREATE TABLE IF NOT EXISTS spectraplan.source_locations (
 version text REFERENCES spectraplan.corpus_versions(version), unit_id text NOT NULL,
 payload jsonb NOT NULL, PRIMARY KEY(version,unit_id)
);
CREATE TABLE IF NOT EXISTS spectraplan.embedding_segments (
 version text NOT NULL REFERENCES spectraplan.corpus_versions(version), purpose text NOT NULL,
 segment_id text NOT NULL, evidence_id text NOT NULL, text text NOT NULL,
 embedding extensions.vector(384) NOT NULL,
 PRIMARY KEY(version,purpose,segment_id),
 FOREIGN KEY(version,evidence_id) REFERENCES spectraplan.evidence(version,evidence_id)
);
CREATE TABLE IF NOT EXISTS spectraplan.corpus_files (
 version text REFERENCES spectraplan.corpus_versions(version), path text NOT NULL,
 reference jsonb NOT NULL, PRIMARY KEY(version,path)
);
CREATE TABLE IF NOT EXISTS spectraplan.app_state (key text PRIMARY KEY, payload jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS spectraplan.ingestion_jobs (
 job_id text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(), status text NOT NULL,
 filename text NOT NULL, role text NOT NULL, input jsonb NOT NULL,
 state jsonb NOT NULL, checkpoint jsonb, claim_token text, lease_until timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_ingestion ON spectraplan.ingestion_jobs((true))
 WHERE status IN ('queued','running');

REVOKE ALL ON ALL TABLES IN SCHEMA spectraplan FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA spectraplan, extensions TO spectraplan_backend;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA spectraplan TO spectraplan_backend;
-- Login provisioning is separate: CREATE ROLE ... LOGIN PASSWORD ... IN ROLE spectraplan_backend.
-- Runtime connections must not use the project postgres/admin role.
