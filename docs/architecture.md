# Architecture

SpectraPlan turns customer enquiries into provisional, source-grounded spectroscopy assessments. React calls local FastAPI. In cloud mode Supabase supplies authentication, Postgres history/corpora/pgvector and private Storage; local Python runs assessment, BM25, embeddings, extraction and reports. See [Supabase migration](supabase.md).

## Code map

| Location | Responsibility |
|---|---|
| `backend/api` | HTTP contracts, verified identity, role and ownership checks. |
| `backend/core`, `schemas`, `providers` | Settings, typed contracts and bounded DashScope transport. |
| `backend/pipelines` | Assessment, PDF/Office extraction and optional website ingestion. |
| `backend/services` | Search/evidence, corpus publication, SQLite history and PDFs. |
| `backend/prompts`, `templates` | Versioned model instructions and generated knowledge report template. |
| `backend/cli`, `evaluation`, `scripts` | Explicit diagnostics, scenario runs, restoration and verification. |
| `frontend/src/app` | Authenticated shell, navigation and page lifecycle. |
| `frontend/src/features` | Assessment, auth, leads, knowledge, search and workspace UI, with feature-owned styles. |
| `frontend/src/shared` | Authenticated transport, response checks and reusable UI. |
| `tests`, `frontend/tests` | Isolated backend and frontend regression tests. |

## Data flow

1. **Sign in:** Supabase verifies an email/password and issues a session. The frontend sends its access token as a Bearer header. FastAPI checks `/auth/v1/user`; `/api/me` returns the application role from the backend UUID allowlist.
2. **Assess:** save the enquiry and owner → extract attributed facts → retrieve local evidence → synthesize a study proposal → validate → save the result and chronological events. All model stages share one request deadline. Incomplete processing has `assessment=null`; a complete insufficient-information decision is a different outcome.
3. **Clarify:** answers retain question and originating-run IDs. Each rerun becomes a new round under the same enquiry. **New enquiry** clears that context and creates a separate lead. Admin continuation preserves the original customer attribution.
4. **Prepare knowledge:** hash originals → render PDF images/read Office locations → Qwen extraction with bounded retries → local text/OCR recovery → preserve workbook rows → validate and index → publish a generation through `knowledge/current.json`. Source locations, revisions and scope accompany evidence.

BM25 provides lexical search; cached BGE embeddings and embedded Qdrant provide semantic search; hybrid combines them. Business/development material remains inspectable but is excluded from technical assessment evidence. Optional website snapshots are a separate dataset; ordinary assessment does not crawl the web.

## Access and API contracts

All `/api/*` routes require authentication and return `Cache-Control: no-store`. Missing/invalid sessions return 401, unavailable auth 503, admin-only operations 403, and another customer's or unowned legacy record 404. Roles never come from editable user metadata.

| Audience | Interfaces |
|---|---|
| Signed-in users | `GET /api/me`; `POST /api/assess`; own `GET /api/assess/{run_id}`, `/api/enquiries/{id}` and ordinary assessment PDF. |
| Admins | All enquiries with `GET /api/enquiries?email=...&limit=50&offset=0`; full explainability/trace exports; search, evidence lookup, source files, uploads and Workspace status. |

Customer saved results omit raw events and provider traces. Protected images/files use authenticated fetches and blob URLs; tokens never enter URLs. Leads email filtering is a trimmed, case-insensitive literal substring match before pagination. Ownership is a stable user ID; the displayed email is captured at enquiry creation.

Use the running [OpenAPI schema](http://127.0.0.1:8000/docs) for exact HTTP shapes and `backend/schemas` for domain types. These replace the old duplicate tool catalog; no separate agent-tool registration is implied.

## Storage and lifecycle

`EXPLAINABILITY_DB_PATH` controls SQLite enquiries, append-only rounds and events. Additive migration leaves pre-auth records unowned and admin-only. Local databases are ignored by Git. Logout/account changes unmount private UI and invalidate stale responses. Secondary admin pages load lazily and remain mounted while visited.

The legacy local backend uses embedded Qdrant and one backend worker. Cloud mode uses exact pgvector search and immutable verified corpus caches; each assessment pins its corpus version. Blocking cloud assessment persistence runs outside the API event loop. Ingestion uses a separate local Python worker, durable checkpoint objects and a fenced Postgres lease. API routes preserve existing ownership and role checks; schema and buckets have no browser access. Public hosting still needs background assessment jobs, HTTPS, same-origin routing and usage controls. See [operations](operations.md) and [quality](quality.md).
