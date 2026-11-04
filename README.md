# SpectraPlan

Source-grounded spectroscopy assessments with customer login and an admin lead inbox.

Customers describe a measurement problem, answer clarification questions and export a provisional assessment. Admins also browse/upload sources, search extracted knowledge and review leads by email. Scientific recommendations require independent validation.

## Start here

| Guide | Contents |
|---|---|
| [Setup](docs/setup.md) | Install, Supabase email/password login, DashScope configuration and startup. |
| [Architecture](docs/architecture.md) | Code map, assessment/ingestion flows, access rules and API contracts. |
| [Operations](docs/operations.md) | Checks, knowledge restoration, live commands, evaluation and backups. |
| [Quality](docs/quality.md) | Known limitations, historical results and evidence boundaries. |
| [Supabase migration](docs/supabase.md) | Cloud data/files with React, FastAPI and ingestion processing on your PC. |

## Run locally

Complete [setup](docs/setup.md) first. From the repository root, start the backend and frontend in separate PowerShell terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
Push-Location frontend
npm run dev
```

Open [SpectraPlan](http://127.0.0.1:5173); [API documentation](http://127.0.0.1:8000/docs) describes exact request/response shapes. Startup makes no model calls. Assessment and ingestion send content to the configured DashScope endpoint and consume quota.

With `STORAGE_BACKEND=supabase`, also start the local ingestion worker in a third terminal:

```powershell
.\.venv\Scripts\python.exe -m backend.cli.worker
```

## Repository

- `backend/`, `frontend/`: application code; `tests/`, `frontend/tests/`: regression tests.
- `knowledge/`: source corpus and local indexes. Originals are supplied separately.
- `evaluation/`, `scripts/`: scenario execution, offline checks and restoration.
- `outputs/`: saved evidence and local work; read the [artifact map](outputs/README.md) before cleanup.

The [Supabase configuration](docs/supabase.md) stores history, published knowledge, vectors, documents and ingestion jobs in the cloud while Python and React stay local. The legacy local backend remains available for diagnostics and manual rollback; cloud mode never silently falls back to it. Public hosting also needs HTTPS, same-origin routing, background assessment jobs and usage controls. Environment files, databases, caches and build output stay out of Git.

The previous 20 documentation files are preserved in one [checksum-verified archive](outputs/documentation_archive.zip). Archived answers and execution snapshots remain historical evidence, not proof of current scientific adequacy.

## License

Project code: [MIT](LICENSE). Third-party source materials retain their own rights.
