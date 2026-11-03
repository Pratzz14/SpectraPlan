# Assessment provider

Assessment uses Alibaba Cloud Model Studio through its OpenAI-compatible DashScope endpoint, with `qwen3.8-flash` as the only configured model. There is no provider selection, startup probe, cooldown cache or fallback provider.

```dotenv
DASHSCOPE_API_KEY=your_dashscope_api_key_here
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
PROVIDER_NAME=dashscope
PROVIDER_MODEL=qwen3.8-flash
QWEN_EXTRACTION_MODEL=qwen3.8-flash
```

A workspace-specific Singapore URL can replace the public endpoint; local `.env` preserves the existing workspace URL. Assessment defaults to `DASHSCOPE_BASE_URL`; `PROVIDER_BASE_URL` can explicitly override it. Never put keys in frontend variables. Restart the backend after updating `.env`.

Assessment extraction and synthesis use strict JSON Schema with `enable_thinking=false`, `max_tokens`, and Pydantic validation. The shared request deadline, bounded transport retries, and one content-repair attempt are retained. Failures are returned explicitly; requests never switch providers or models. Knowledge ingestion uses the same DashScope credential and its own extraction settings.

Health reads local configuration/corpus only; it does not check provider access or remaining quota. Configure **Free Quota Only** in Alibaba's console to stop requests when free quota expires.

Offline checks: `python -m pytest -q` and `python -m evaluation.search_smoke`. The explicit `python -m backend.cli.smoke_provider` command makes a live request and consumes quota; it is never run automatically.

Historical model identities remain accepted in saved assessment envelopes and the History UI. This is read compatibility, not runtime provider support. Archived outputs and snapshots are unchanged.

References: [structured output](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output), [free quota](https://www.alibabacloud.com/help/en/model-studio/new-free-quota).

The default shared request budget is 240 seconds and each provider attempt is capped at 90 seconds. Extraction, retrieval, synthesis, retries and content repair share the same request deadline; the budget is never reset between stages. A ledger without an eligible method restricts synthesis to insufficient-information/out-of-scope decisions with clarification questions.
