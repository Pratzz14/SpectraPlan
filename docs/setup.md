# Setup

Use Python 3.12 and Node 22.12+ (or the compatible versions in `frontend/package.json`). Commands below run in PowerShell from the repository root.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path frontend/.env.local)) { Copy-Item frontend/.env.example frontend/.env.local }
Push-Location frontend
npm ci
Pop-Location
```

## Configure accounts

In Supabase, enable Email under Authentication → Sign In / Providers and allow new signups. For the current email/password flow without SMTP, turn **Confirm email off**. Emails are then unverified. Public confirmation and password-reset email delivery require custom SMTP; password reset is not offered in this version.

Copy the Project URL and publishable key from Connect or Settings → API Keys. Find admin UUIDs under Authentication → Users; each admin needs an email/password account.

Set in the root `.env`:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_example
ADMIN_USER_IDS=administrator-user-uuid
DASHSCOPE_API_KEY=your_dashscope_api_key_here
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
PROVIDER_MODEL=qwen3.8-flash
QWEN_EXTRACTION_MODEL=qwen3.8-flash
```

Set in `frontend/.env.local`:

```dotenv
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_example
```

Separate multiple admin UUIDs with commas. The allowlist grants application access independently of Supabase organization roles. Local-only persistence needs only Auth credentials; cloud persistence additionally needs the backend-only database and Storage configuration in [Supabase migration](supabase.md). Only the URL and publishable key belong in frontend configuration. Environment files are ignored by Git; preserve existing credentials when editing them.

Assessment and ingestion use DashScope with no automatic fallback or startup probes. A workspace-specific DashScope endpoint may replace the public endpoint. Restart the backend after changing `.env`; restart Vite or rebuild after changing frontend variables. See `.env.example` for timeouts, file limits and local storage paths.

## Restore knowledge and start

For local persistence, obtain the originals separately and restore the saved corpus using [operations](operations.md#knowledge). For migrated cloud persistence, follow [Supabase migration](supabase.md) and retain the local embedding-model cache; local originals and Qdrant indexes are not required for normal browsing/search. Supabase is required for login; model credentials are needed only for assessment or ingestion, not search.

Run in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
Push-Location frontend
npm run dev
```

Open [SpectraPlan](http://127.0.0.1:5173). Customers see Assessment; admins also see Search sources, Extracted knowledge, Leads and Workspace. Use **New enquiry** to start a separate lead. A saved Assessment URL restores its result after refresh, subject to ownership checks.

## Troubleshooting

| Symptom | Check |
|---|---|
| Sign-in is not configured | Both frontend variables are set; restart Vite. |
| Account created but confirmation required | Confirm email is still enabled in Supabase. |
| Login succeeds but verification fails | Root Supabase values, backend connectivity and `/api/me`. |
| Expected admin tools are missing | UUID is in `ADMIN_USER_IDS`; restart backend, then sign in again. |
| Search or analysis has no knowledge | Active corpus pointer, source hashes and [validation](operations.md#knowledge). |
| Analysis fails | DashScope credentials, endpoint, quota and shared request deadline. Workspace readiness does not probe the provider. |
| Qdrant reports a lock | Stop other processes using the same embedded index; use one backend worker. |

Run the [checks](operations.md#checks) before reporting a setup as verified.
