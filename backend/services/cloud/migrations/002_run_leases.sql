-- A crash between run creation and its first event must still leave an expiring lease.
ALTER TABLE spectraplan.explainability_runs ALTER COLUMN lease_until
 SET DEFAULT (now()+interval '10 minutes');
UPDATE spectraplan.explainability_runs SET lease_until=now()
 WHERE status='running' AND lease_until IS NULL;
