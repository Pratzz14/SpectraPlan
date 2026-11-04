# Heroku + Supabase deployment

Production app: <https://spectraplan-pratik-ac2eb72200cd.herokuapp.com/>. Heroku hosts both the React/FastAPI web process and Python processing worker. Supabase remains authoritative for Auth, enquiries, assessment jobs, corpora, vectors, documents and checkpoints. DashScope supplies model inference. No running PC service is required.

## Budget and first launch

Use the personal-account Eco subscription, not Basic or Standard. Student credits do not activate Eco automatically: enable the $5/month Eco Dynos plan in Heroku Account settings → Billing. The 1,000 hours are shared by web and worker, and both can sleep when the web app is inactive. Do not add artificial keep-alive monitoring.

The Linux build runs the pinned embedding model, OCR and workbook probe and rejects peak RSS at or above 450 MiB. The first build measured 376.27 MiB and preserved the corpus embedding fingerprint. This is a representative resource gate, not a guarantee for arbitrarily complex uploaded files. Processing concurrency is one.

The first Heroku release may automatically start a Basic web process. Keep maintenance enabled during deployment and immediately verify process sizes; scale down if the account cannot select Eco. Never silently upgrade to a larger dyno.

```powershell
heroku ps:type eco -a spectraplan-pratik
heroku ps:scale web=1 worker=1 -a spectraplan-pratik
heroku ps -a spectraplan-pratik
```

## Configuration and access

Heroku Config Vars contain `STORAGE_BACKEND=supabase`, `BACKGROUND_ASSESSMENTS=true`, the restricted runtime `DATABASE_URL`, Supabase URL/publishable key/backend Storage secret, the admin and allowed-user UUID lists, and the existing DashScope key/endpoint/model settings. `DATABASE_POOL_SIZE=2` bounds each process pool.

The container supplies its public CA certificate and Linux cache/OCR paths. The embedding files are downloaded from a fixed public revision during the remote build and checksum-verified. Runtime model downloads are disabled. Do not copy `.env`, `.local`, model keys, the admin migration database URL, or local originals into the image.

React reads only the public Auth configuration injected into the hosted HTML. Hosted signup is hidden, and the API rejects identities outside `ALLOWED_USER_IDS` and `ADMIN_USER_IDS`. Add existing users deliberately through Config Vars when granting future access.

In Supabase Authentication settings, disable new signups and set Site URL to the production app URL above, with its HTTPS origin in allowed redirect URLs. Those project-management settings require Supabase dashboard access; the backend secret is not a project-management token. Existing email/password users remain unchanged.

## Build and release

`Dockerfile` and `heroku.yml` define the web/worker image and commands. Heroku builds remotely, including Node frontend compilation, Python dependencies, Tesseract, English OCR data, fonts and the pinned BGE artifacts. Your PC's Docker daemon is not a runtime or build requirement.

1. Apply additive SQL migrations with the existing admin migration CLI before releasing code that uses them. Never reimport or reactivate the old local corpus after cloud writes.
2. Run backend/frontend tests, lint and build. Tests force local persistence and use isolated schemas for SQL integration; they never inherit live app persistence.
3. Enable maintenance, commit the deployment changes, and push the reviewed commit to Heroku's Git remote.
4. Inspect build logs for the model fingerprint and passing memory probe. Verify Eco sizing and start one web and one worker.
5. Check HTTPS, existing-account login, ownership, knowledge/files, saved history, job progress and one explicitly authorized live demo assessment.
6. Run a cloud backup and disable maintenance after acceptance. Stop the previous PC services to avoid two workers processing the shared ingestion queue.

```powershell
heroku maintenance:on -a spectraplan-pratik
git push heroku HEAD:main
heroku logs --num 100 -a spectraplan-pratik
heroku maintenance:off -a spectraplan-pratik
```

## Jobs and recovery

`POST /api/assess` accepts an `Idempotency-Key` and returns 202 with the run/enquiry IDs and status URL. React polls the protected status route and can resume after refresh. Existing saved-result, PDF and explainability routes are retained. One account can have one queued/running assessment. Model failures preserve an incomplete result; interrupted work requires an explicit retry.

The worker selects queued tasks serially across assessment and ingestion queues, pins a corpus for each assessment, and fences writes using claim tokens. Checkpoints are stored in Supabase. On SIGTERM it marks active work interrupted/failed, keeps completed checkpoints and terminates within the shutdown allowance. It does not repeat uncertain paid requests automatically.

Hosted file uploads go straight to a scoped signed private Storage URL. Completion queues ingestion idempotently; the worker checks the actual bytes, size and file format before extraction. The previous corpus remains active until the replacement validates and commits successfully.

## Cloud backup and rollback

```powershell
heroku run --size eco "python -m backend.cli.cloud_backup" -a spectraplan-pratik
```

Backups are created inside an ephemeral Heroku dyno, then uploaded in 16 MiB chunks to private `spectraplan-backups`, avoiding Free Storage's per-object size limit. The `cloud_backups` state entry records checksums and keeps the last two completed bundles. Temporary files on the dyno are disposable; no PC copy is required.

To restore, concatenate the recorded parts in order after verifying each SHA-256, verify the ZIP export manifest, and restore the logical database and objects into an isolated project/schema before switching production. Do not overwrite live data without a reviewed restore procedure. Keep schema changes additive so `heroku rollback` can restore the previous app release without reverting customer data.

Use maintenance mode and scale processes to zero if deployment acceptance fails. Leave existing Supabase data intact. The old local deployment is a development fallback only, not a production dependency.
