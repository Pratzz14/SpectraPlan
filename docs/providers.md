# LLMTech and Groq provider selection

The API, extraction, assessment, ingestion and general diagnostic tools share the same backend provider configuration. `PROVIDER_NAME=auto` is the default. Credentials stay in the ignored root `.env` or environment variables; frontend code receives only sanitized status and model identity.

```dotenv
PROVIDER_NAME=auto
PROVIDER_ORDER=llmtech,groq
LLMTECH_API_KEY=your_llmtech_api_key_here
GROQ_API_KEY=your_groq_api_key_here
LLMTECH_BASE_URL=https://api.llmtech.eu/v1
LLMTECH_MODEL=nvidia/Qwen3.8-27B-NVFP4
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=qwen/qwen3.8-27b
```

Provide either key or both. Blank and placeholder keys are skipped. `PROVIDER_ORDER` contains both names exactly once and controls priority. Set `PROVIDER_NAME=llmtech` or `groq` to pin one provider and disable automatic switching. Provider-specific endpoints/models prevent a Groq model ID or credential from being applied to LLMTech. Legacy `PROVIDER_BASE_URL` and `PROVIDER_MODEL` overrides remain supported only in pinned mode; automatic mode uses the provider-specific fields.

## Local setup

To fill a missing LLMTech key from its documented public trial, enable automatic mode and check connectivity:

```powershell
.\.venv\Scripts\python.exe -m backend.provider_setup --public-trial --check
```

This preserves an existing usable LLMTech key and the Groq key. It writes `PROVIDER_NAME=auto` and the trial credential to local `.env`, never to source control or diagnostic output. A public trial is not a personal long-term credential and can expire or run out of quota. Replace `LLMTECH_API_KEY` with your own key when available. Public-trial discovery happens only during explicit setup/diagnostic commands; normal application requests never download or replace credentials. Restart the backend after changing `.env`.

## Automatic operation

On backend startup, a small synthetic structured-output request checks configured providers in priority order until one works. The first model request also performs selection if startup was not run, as in an embedded API client. Probes contain no customer enquiry or corpus content.

The working selection is cached for 300 seconds. Failed providers have a 30-second cooldown. A lock prevents concurrent requests from duplicating the same availability probe. After the cache expires, priority selection is checked again. `GET /api/health` and the UI's Refresh status action read cached availability without making provider calls. An `unchecked` candidate has not been tested by that application process; it is not evidence of failure.

Authentication, missing configuration, quota/rate limits, network/service failures and request/schema incompatibility can select the other configured provider. Each logical call makes at most one payload attempt per provider in automatic mode, so retries cannot exhaust the deadline before fallback. Pinned mode retains its configured transport retry budget. Provider-specific `json_validate_failed` and locally invalid JSON/content stay on the existing bounded content-repair path, rather than silently changing models. Scientific or semantic validation failures are not availability signals.

All probes, waits, payload calls and content repair consume the original shared request deadline. Defaults remain 30 seconds per payload call and 90 seconds total. Probe timeout is 8 seconds (`PROVIDER_PROBE_TIMEOUT_S`); cache/cooldown are configurable with `PROVIDER_HEALTH_TTL_S` and `PROVIDER_FAILURE_TTL_S`. If neither provider works, existing incomplete/error contracts apply; a failed run never becomes a recommendation.

Assessment metadata records `provider_mode`, actual `stage_providers`, sanitized `provider_attempts`, requested/returned model IDs and the last selected endpoint. Extraction and synthesis can use different providers when one becomes unavailable. Attempts identify synthetic probes separately from payload calls and contain no prompts or credentials. Ingestion fingerprints include both profiles in automatic mode, and per-record provenance retains the actual extraction/verification identities, including cache reuse.

## Commands

```powershell
# Automatic live assessment of D01/D02, using stored keys
.\.venv\Scripts\python.exe -m backend.smoke_assessment --api --request-deadline-s 90 --call-timeout-s 30

# Check each configured provider with synthetic content
.\.venv\Scripts\python.exe -m backend.smoke_provider --all

# Pin a diagnostic run without changing saved settings
.\.venv\Scripts\python.exe -m backend.smoke_assessment --provider groq --api

# Extraction and corpus tools use the same profiles and selection policy
.\.venv\Scripts\python.exe -m backend.smoke_extraction --provider auto
.\.venv\Scripts\python.exe -m backend.ingest pilot --provider auto
```

Full ingestion sends source-page text/images to the selected provider and can make many calls. It remains an explicit build/pilot action. Provider-specific vision/schema limitations still need inspection; a small successful probe does not establish every model capability or scientific correctness.

The [verification receipt](../outputs/provider_smoke/automatic_provider_review.json) separates mocked failover/deadline tests, live provider checks, live API assessments and rendered UI checks. Earlier F06 receipts describe the implementation at their recorded hashes; the current routing change has its own receipt.
