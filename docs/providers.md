# Gemini, LLMTech and Groq provider selection

The API, extraction, assessment, ingestion and general diagnostic tools share the same backend provider configuration. `PROVIDER_NAME=auto` is the default. Credentials stay in the ignored root `.env` or environment variables; frontend code receives only sanitized status and model identity.

```dotenv
PROVIDER_NAME=auto
PROVIDER_ORDER=gemini,llmtech,groq
LLMTECH_API_KEY=your_llmtech_api_key_here
GROQ_API_KEY=your_groq_api_key_here
LLMTECH_BASE_URL=https://api.llmtech.eu/v1
LLMTECH_MODEL=nvidia/Qwen3.8-27B-NVFP4
GEMINI_API_KEY=local-only-key
GEMINI_MODEL=models/gemini-3.8-flash
GEMINI_BASE_URL=https://generativelanguage.googleapis.com
GEMINI_MAX_OUTPUT_TOKENS=2048
GEMINI_THINKING_LEVEL=medium
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=qwen/qwen3.8-27b
```

Provide one or more keys. Blank and placeholder keys are skipped. `PROVIDER_ORDER` contains all three names exactly once and controls priority. Set `PROVIDER_NAME=gemini`, `llmtech` or `groq` to pin one provider and disable automatic switching. Provider-specific endpoints/models keep credentials and request formats separate. Existing two-provider order settings are upgraded by prepending Gemini; the configured Qwen order is preserved. Legacy `PROVIDER_BASE_URL` and `PROVIDER_MODEL` overrides remain supported only in pinned mode; automatic mode uses the provider-specific fields.

## Local setup

To fill a missing LLMTech key from its documented public trial, enable automatic mode and check connectivity:

```powershell
.\.venv\Scripts\python.exe -m backend.cli.provider_setup --public-trial --check
```

This preserves an existing usable LLMTech key and the Groq key. It writes `PROVIDER_NAME=auto` and the trial credential to local `.env`, never to source control or diagnostic output. A public trial is not a personal long-term credential and can expire or run out of quota. Replace `LLMTECH_API_KEY` with your own key when available. Public-trial discovery happens only during explicit setup/diagnostic commands; normal application requests never download or replace credentials. Restart the backend after changing `.env`.

## Automatic operation

On backend startup, a small synthetic structured-output request checks configured providers in priority order until one works. The first model request also performs selection if startup was not run, as in an embedded API client. Probes contain no customer enquiry or corpus content.

The working selection is cached for 300 seconds. Failed providers have a 30-second cooldown. A lock prevents concurrent requests from duplicating the same availability probe. After the cache expires, priority selection is checked again. `GET /api/health` and the UI's Refresh status action read cached availability without making provider calls. An `unchecked` candidate has not been tested by that application process; it is not evidence of failure.

Authentication, missing configuration, quota/rate limits, network/service failures and request/schema incompatibility can select the other configured provider. Each logical payload call makes one transport attempt per provider in automatic mode. Availability failures immediately try the next provider within the original deadline. Pinned mode retains its configured transport retry budget. Invalid JSON/content and failed mechanical stage validation receive at most one repair per provider. After that bounded repair, automatic mode tries the next provider against the same original input and evidence. Pinned mode returns an error after repair. A fallback result must pass the same validators; switching providers never overrides a scientific decision or admits unsupported claims.

All probes, waits, payload calls and content repair consume the original shared request deadline. Defaults remain 30 seconds per payload call and 90 seconds total. Probe timeout is 8 seconds (`PROVIDER_PROBE_TIMEOUT_S`); cache/cooldown are configurable with `PROVIDER_HEALTH_TTL_S` and `PROVIDER_FAILURE_TTL_S`. If neither provider works, existing incomplete/error contracts apply; a failed run never becomes a recommendation.

Assessment metadata records `provider_mode`, actual `stage_providers`, sanitized `provider_attempts`, requested/returned model IDs and the last selected endpoint. Extraction and synthesis can use different providers when one becomes unavailable. Attempts identify synthetic probes separately from payload calls and contain no prompts or credentials. Ingestion fingerprints include both profiles in automatic mode, and per-record provenance retains the actual extraction/verification identities, including cache reuse.

## Commands

```powershell
# Automatic live assessment of D01/D02, using stored keys
.\.venv\Scripts\python.exe -m backend.cli.smoke_assessment --api --request-deadline-s 90 --call-timeout-s 30

# Check each configured provider with synthetic content
.\.venv\Scripts\python.exe -m backend.cli.smoke_provider --all

# Pin a diagnostic run without changing saved settings
.\.venv\Scripts\python.exe -m backend.cli.smoke_assessment --provider groq --api

# Extraction and corpus tools use the same profiles and selection policy
.\.venv\Scripts\python.exe -m backend.cli.smoke_extraction --provider auto
.\.venv\Scripts\python.exe -m backend.cli.ingest pilot --provider auto
```

Full ingestion sends source-page text/images to the selected provider and can make many calls. It remains an explicit build/pilot action. Provider-specific vision/schema limitations still need inspection; a small successful probe does not establish every model capability or scientific correctness.

## Gemini original-file extraction comparison

Gemini 3.8 Flash is the first provider in automatic mode for customer extraction,
assessment synthesis, and source-page extraction/verification. LLMTech Qwen and
Groq Qwen remain fallbacks. The backend uses the asynchronous native Interactions
HTTP API with explicit timeouts, JSON schemas, inline source images, and
`store=false`. It records returned model IDs and usage. Thinking levels are
`low`, `medium`, or `high`; unsupported sampling parameters are omitted.

The original-file comparison is a separate review tool. It sends deterministic
text extracted from PDF, DOCX and XLSX files and validates returned source IDs and
locations. It does not publish summaries into the technical corpus. Active
corpus builds retain their canonical page/evidence schemas and atomic publication.

Run it explicitly:

```powershell
.\.venv\Scripts\python.exe -m backend.cli.smoke_gemini_extraction
```

For a low-cost first check, process one source:

```powershell
.\.venv\Scripts\python.exe -m backend.cli.smoke_gemini_extraction --limit 1 --output outputs/provider_smoke/gemini_one_file.json
```

Rerun only selected failed sources with `--source-id`, for example:

```powershell
.\.venv\Scripts\python.exe -m backend.cli.smoke_gemini_extraction --source-id T01 --source-id S05
```

The result contains baseline and Gemini outputs per source, source IDs and
format metadata. It is a review artifact and does not publish Gemini output into
the active retrieval corpus. The comparison requires a backend Gemini API key with access to the configured model. A full run writes `outputs/provider_smoke/gemini_complete_comparison.json`, including source hashes and success/error counts. Partial runs use timestamped files or the explicit `--output` path. The UI rejects artifacts without current source hashes; older comparison receipts must be regenerated.

The [verification receipt](../outputs/provider_smoke/gemini_history_review.json) separates mocked failover/deadline tests, live provider checks, live assessments, the staged source pilot, rendered UI checks and Gemini quota limits. Earlier F06 receipts describe the implementation at their recorded hashes; the current routing change has its own receipt.

## Validation and data handling

Model requests contain enquiry text or supplied source material. Native Gemini,
LLMTech and Groq requests remain backend-only; configured keys never enter the UI.
Synthetic provider smoke checks do not read the corpus. Full assessment and
source-extraction diagnostics send the selected development/source content to the
configured provider chain. Corpus pilot builds stay under `.staging`; a complete
build switches the active corpus only after source and index validation passes.
