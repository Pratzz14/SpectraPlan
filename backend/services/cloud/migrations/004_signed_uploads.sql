CREATE TABLE IF NOT EXISTS spectraplan.uploads (
 upload_id text PRIMARY KEY, owner_user_id text NOT NULL, filename text NOT NULL,
 role text NOT NULL, object_key text NOT NULL, expected_bytes bigint NOT NULL,
 expires_at timestamptz NOT NULL DEFAULT now()+interval '2 hours', job_id text
);
REVOKE ALL ON spectraplan.uploads FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON spectraplan.uploads TO spectraplan_backend;
