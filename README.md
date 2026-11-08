# SpectraPlan

SpectraPlan helps teams explore spectroscopy methods for a measurement problem and trace the assessment back to its sources.

**[Watch the SpectraPlan demo on YouTube](https://youtu.be/QgQpxj_DmBA)**

Customers describe a measurement problem, answer clarification questions and export a provisional assessment. Admins also browse/upload sources, search extracted knowledge and review leads by email. Scientific recommendations require independent validation.

## Start here

| Guide | Contents |
|---|---|
| [Setup](docs/setup.md) | Install, Supabase email/password login, DashScope configuration and startup. |
| [Architecture](docs/architecture.md) | Code map, assessment/ingestion flows, access rules and API contracts. |
| [Operations](docs/operations.md) | Checks, knowledge restoration, live commands, evaluation and backups. |
| [Quality](docs/quality.md) | Known limitations and evaluation guidance. |
| [Supabase migration](docs/supabase.md) | Cloud data/files with React, FastAPI and ingestion processing on your PC. |
| [Heroku deployment](docs/heroku.md) | Fully hosted web/worker, Eco billing activation, cloud backups and recovery. |

## Run locally

Use Python 3.12 and Node.js 22.12 or later. Follow the [setup guide](docs/setup.md) to install dependencies and configure a Supabase project for sign-in. DashScope credentials are required for assessments and ingestion. Keep credentials in the local environment files described in the guide.

From the repository root, start the backend and frontend in separate PowerShell terminals.

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
Push-Location frontend
npm run dev
```

Open [SpectraPlan](http://127.0.0.1:5173); [API documentation](http://127.0.0.1:8000/docs) describes exact request/response shapes. Startup makes no model calls. Assessment and ingestion send content to the configured DashScope endpoint and consume quota.

With `STORAGE_BACKEND=supabase`, also start the local ingestion worker in a third terminal.

```powershell
.\.venv\Scripts\python.exe -m backend.cli.worker
```

## Repository

- `backend/` and `frontend/` contain the FastAPI and React applications.
- `tests/` and `frontend/tests/` contain regression tests. See [how to run the checks](docs/operations.md#checks).
- `knowledge/` contains extracted source records and indexes. Original documents are supplied separately.
- `evaluation/` and `scripts/` contain scenario runners, offline checks and corpus restoration tools.
- `outputs/` is the local destination for generated diagnostics, evaluation runs and runtime data. See the [artifact map](outputs/README.md).

Supabase mode stores enquiry history, published knowledge, source documents and ingestion jobs in the cloud. Local storage remains available for development and diagnostics. See the [deployment guide](docs/heroku.md) for the hosted configuration.

## License

The project code is available under the [MIT License](LICENSE). Third-party source materials and their extracts are subject to their respective rights and terms.
