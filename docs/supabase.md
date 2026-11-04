# Supabase persistence with local Python and React

React/Vite, FastAPI, the Python ingestion worker, BGE embeddings, OCR and PDF generation run on your PC. Supabase supplies Auth, Postgres/pgvector and private file Storage. Model inference still uses the configured DashScope endpoint when you explicitly assess or ingest a file.

## Credentials

Keep credentials in the ignored root `.env`. The frontend needs only its existing project URL and publishable key. Never put database passwords or backend Storage secrets in a `VITE_*` variable.

1. In the existing Supabase project, choose **Connect → Session pooler**. Replace the password placeholder and set `SUPABASE_MIGRATION_DATABASE_URL`. This admin connection is used only by the migration CLI.
2. Download the project CA certificate from **Database → Settings → SSL configuration / Connection info**. Keep it in `.local/supabase-ca.crt` and set `DATABASE_SSL_ROOT_CERT` to its full local path. Connections enforce certificate and hostname verification. Keep this certificate when clearing temporary caches.
3. Set `SUPABASE_SECRET_KEY` to a backend secret from **Settings → API Keys**. A legacy service-role JWT is also supported. This key is used only by Python for private Storage operations.
4. Run `create-login` below to generate a restricted database login and save `DATABASE_URL` locally without displaying its password. Existing runtime credentials are never overwritten by this command.

The app schema is private and is not added to the Data API exposed schemas. Browser roles have no schema/table grants or Storage policies for these buckets. Backend routes enforce verified identity, enquiry ownership, and the existing admin UUID allowlist. The runtime database role cannot perform DDL or delete tables. It must not be the project admin role.

## One-time migration

Stop the backend and ingestion processes before taking the backup and importing. Leave `STORAGE_BACKEND=local` until activation and verification succeed. From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.cli.supabase preflight
.\.venv\Scripts\python.exe -m backend.cli.supabase backup --output tmp/supabase-backup
.\.venv\Scripts\python.exe -m backend.cli.supabase provision
.\.venv\Scripts\python.exe -m backend.cli.supabase create-login
.\.venv\Scripts\python.exe -m backend.cli.supabase import
.\.venv\Scripts\python.exe -m backend.cli.supabase activate
.\.venv\Scripts\python.exe -m backend.cli.supabase_smoke --compare-local --output tmp/supabase-smoke.json
```

Choose a new backup path each time; existing backups are never overwritten. `activate` rechecks history, every imported document, file checksum and embedding before switching cloud corpus pointers. `verify` performs those checks without switching pointers. These commands make no Qwen calls and reuse existing Qdrant vectors. Imports are idempotent; conflicting content is rejected.

The import includes all available published technical/website versions, source originals used by those versions, images, generated knowledge reports, source registration state, and current SQLite enquiries/runs/events. Historical evaluation bundles, diagnostic directories and model caches remain local. Missing historical generations cannot be reconstructed from a citation; keep the preflight report and the local backup.

The initial local inventory has 371 active technical evidence/method records, four available corpus versions, and no SQLite enquiries. Imported historical records retain their IDs, source hashes, scopes, ownership and original payloads. Unowned enquiries remain admin-only. New imports never assign a historical record to an arbitrary account.

Once activated, set:

```dotenv
STORAGE_BACKEND=supabase
```

Restart FastAPI. Supabase is then authoritative. The app does not fall back to SQLite or local indexes if Supabase is unavailable; it reports an error. `tmp/supabase-cache` is a verified, disposable cache, not an offline database. Preserve `outputs/embedding_models`, or restore that pinned embedding cache separately; query embedding generation stays local.

## Start locally

Run these in three PowerShell terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
.\.venv\Scripts\python.exe -m backend.cli.worker
```

```powershell
Set-Location frontend
npm run dev
```

Open <http://127.0.0.1:5173>. React continues to call the local API through Vite. Sign-in, Leads, saved assessments, clarifications, PDFs, evidence drawers, original-source links, knowledge inspection and search retain their existing HTTP interfaces.

Search uses Python BM25 plus exact pgvector cosine similarity, the existing 384-dimensional BGE model, its pinned fingerprint and existing RRF rules. `qdrant` names remain compatibility aliases in existing API fields and traces; the UI calls this branch Semantic search. No local Qdrant database is needed at runtime.

## Ingestion and publication

Uploads enter private Storage and a durable Postgres queue. One local Python worker processes one ingestion at a time, sends a heartbeat every 15 seconds, and checkpoints completed extraction results in private Storage. A running job with no heartbeat for ten minutes is failed; resubmitting the same file explicitly resumes its matching failed checkpoint. Queued jobs wait for the worker. A fenced-out worker cannot activate its output.

Existing knowledge remains active until the new corpus, vectors and files verify. Corpus activation and job success commit together. Published generations are retained for saved evidence references.

The existing CLI adapts to cloud mode:

```powershell
python -m backend.cli.ingest add --file "C:\path\source.pdf" --role technical
python -m backend.cli.ingest build --source S04
python -m backend.cli.ingest validate
python -m backend.cli.ingest search --query "powder moisture"
```

`add`, `build`, and `pilot` enqueue work; run the local worker to process it. `add --prepare-only` enqueues local preparation without extraction-model calls or publication. `publish` retries publication from the last failed batch checkpoint. Website crawl remains an explicit live HTTP operation and publishes its separate cloud dataset only after validation.

Do not run initial migration imports while the application is accepting writes. Initial import/activation uses the original local snapshot; after cutover use the worker for new knowledge, not a repeated activation of the old local snapshot.

## Backup, tests, and rollback

Export all cloud working data and referenced objects to a new directory:

```powershell
python -m backend.cli.supabase export --output tmp/supabase-export
```

This is a consistent logical database snapshot plus checksum-verified Storage objects, including job checkpoints. It is not an automatic import into the legacy application. Preserve and reconcile post-cutover exports before a manual rollback. A rollback uses the previous application version, `STORAGE_BACKEND=local`, and the pre-migration backup; never silently discard new cloud records.

Run the normal backend/frontend checks in [Operations](operations.md#checks). SQL integration tests are opt-in and refuse remote databases. For an isolated local Postgres with pgvector:

```powershell
$env:SPECTRAPLAN_TEST_DATABASE_URL="postgresql://postgres:local-test-password@127.0.0.1:55439/postgres"
python -m pytest tests/test_supabase.py -q
```

Each integration test creates and removes a unique test schema. Unit tests mock Storage HTTP and make no model calls. Live model tests require a separate explicit command.

Heroku deployment and background assessment API jobs are a later phase. The current assessment HTTP flow still waits for the result, so the Heroku request-timeout change remains outstanding.
