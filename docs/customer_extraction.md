# Customer enquiry extraction

F03 converts an enquiry into customer-supplied facts before technical retrieval or assessment. Extraction uses the configured model provider and does not require a knowledge corpus. A reported fact records what the customer says; it is not independently verified.

## API and Python interface

`POST /api/extract` accepts one required field:

```json
{"description": "We want to measure moisture in a powder. We have not defined an error limit."}
```

Descriptions must contain non-whitespace text and be at most 20,000 characters. Unknown request properties and invalid types return HTTP 422. The original description is preserved, including whitespace, for quotation checks.

The response is `CaseFacts`: `contexts`, `customer_claims_and_requests`, `shared_constraints`, `missing_information` and `fact_provenance`. The API is available in FastAPI's [interactive documentation](http://127.0.0.1:8000/docs). F03 does not add a dedicated frontend.

The same stage is callable from Python:

```python
from backend.agent import extract_case
from backend.config import Settings

facts = await extract_case(description, Settings())
```

Callers composing a pipeline can supply an absolute `time.monotonic()` deadline. Tests can inject a `Provider` with an HTTP mock transport. Extraction does not invoke search, crawling or technical assessment.

## Facts and provenance

Each context has a generated `stream_1`-style ID, label, targets, measurement goals, sample properties, stated conditions, reference assays, process constraints and missing information. Multiple analytes can share one context. Independent streams retain separate contexts; genuinely shared requirements belong once at case level.

Unknown scalar values are `null`; absent collections are empty lists. Structured text values are verbatim excerpts, preserving sample form, raw ranges, units, pressure basis and concentration basis. `response_time_raw` preserves the stated time phrase. `response_time_s` is populated only for an exact unqualified number explicitly in seconds; bounds, ranges, other units and unspecified units retain `null` without conversion.

Each stated scalar and each list item has a `FactProvenance` record with a JSON Pointer `field_path`, applicable `context_ids` and exact `input_quote`. For example, `/contexts/0/sample_phase` references the first context's sample form. Case-wide constraints use `/shared_constraints/0` and empty `context_ids`. Generated IDs and missing-information questions do not require invented supporting quotes.

Customer statements carry their own quotes and use four kinds: `reported_fact`, `requested_outcome`, `proposed_approach` and `customer_claim`. A requested technique remains a proposal. Instrument ownership does not verify analyte-measurement capability.

## Validation and failures

The provider receives a strict schema derived from the Pydantic models. Each stated context value is returned with its own `input_quote`; Python constructs the public provenance pointers and context associations deterministically. The model does not generate pointer strings or maintain a separate provenance list. Every wire property must be explicitly present; nullable values and empty lists are permitted. Local models retain independent collection defaults.

Validation rejects malformed structures, unknown fields, duplicate or dangling context IDs, untraceable quotes, missing fact provenance, unsupported text substitutions and unsupported response-time conversions. Reuse of one unique quote for the same constraint in multiple contexts is rejected: the model must retain the shared requirement once or provide separately scoped input evidence.

If a material description explicitly contains a single supported form word (`powder`, `slurry`, `liquid`, `gas` or `solid`), leaving its sample form unknown is rejected. This narrow completeness check copies no facts automatically and does not infer a phase from a product name.

One repair is allowed for malformed generated JSON or failed local validation. It receives the original enquiry and validation errors, within the original deadline. LLMTech also receives its previous response to support targeted correction; Groq regenerates without replaying the large response to limit request size. There is no automatic provider fallback. Provider transport retries remain separately bounded by existing configuration. The extraction output ceiling defaults to `EXTRACTION_MAX_COMPLETION_TOKENS=3072`, capped by `PROVIDER_MAX_COMPLETION_TOKENS`.

Exhausted validation returns HTTP 502 with `extraction_invalid_response`. Provider timeouts return HTTP 504; configuration, authentication, quota and availability failures use the existing sanitized provider status mapping. Invalid output and detailed diagnostics are never returned as successful facts. The manual diagnostic runner may retain invalid output locally for inspection.

These checks establish structural validity and quotation traceability. They do not prove semantic completeness, correct attribution or scientific truth. Review extracted facts against their input before treating a new prompt/provider configuration as validated.

## Development checks

`evaluation/development.json` contains only the exact D01/D02 enquiry paragraphs and their original document hash. Organizer worked answers and development inputs remain excluded from technical retrieval. D03-D08 and the full evaluation runner are later evaluation work.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extraction.py -q --basetemp tmp/f03-tests
.\.venv\Scripts\python.exe -m backend.smoke_extraction
```

An explicit run-only LLMTech override is available:

```powershell
.\.venv\Scripts\python.exe -m backend.smoke_extraction --provider llmtech --public-trial
```

This uses an existing backend-only LLMTech key when supplied, otherwise retrieves the documented public trial key at runtime. It never writes the key to results or changes `.env`. To select one input, append `--case D02`; the three additional synthetic IDs are `multi_stream`, `capability_claim` and `ambiguous_units`.

The runner saves timestamped outputs under `outputs/extraction/`, including prompt/model identity, settings, available token usage and sanitized failures. A mechanical pass is labeled separately from manual semantic review. These development outputs are not scientific feasibility assessments.

On 2026-10-17, all 122 backend tests passed. Final `extraction-v6` outputs for D01, D02 and the three synthetic enquiries passed mechanical checks and agent comparison against their original text using LLMTech `nvidia/Qwen3.8-27B-NVFP4`. The [review record](../outputs/extraction/review.json) identifies the exact outputs and their limitations. Earlier Groq request-size/rate-limit failures and earlier extraction defects remain available as historical diagnostics. This does not establish independent human validation or spectroscopy performance.

To use LLMTech for the API itself, configure backend-only `LLMTECH_API_KEY`, `PROVIDER_NAME=llmtech`, `PROVIDER_BASE_URL=https://api.llmtech.eu/v1` and `PROVIDER_MODEL=nvidia/Qwen3.8-27B-NVFP4`, then restart the backend. Public-trial discovery is restricted to the explicit diagnostic command.
