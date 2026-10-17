# Saved extraction checkpoint

**Historical snapshot:** F02 has since been completed and published as `corpus-4aac882441587796afe5`. Open [the current published report](../versions/corpus-4aac882441587796afe5/review.html) or run `python -m backend.ingest report` from the project root. Counts and pending pages below describe this earlier snapshot only; its report and model responses are preserved unchanged.

Saved on 2026-10-17 to preserve progress with limited remaining Codex usage.

- All 64 PDF pages: original extracted blocks, source locations, rendered images and verified image hashes.
- Received Qwen extraction responses for all 64 pages; 59 pages have completed usable extraction/verification stages. Five require retry or verification: S03 pages 12, 15, 16, 17 and S04 page 6. This includes bibliography handling; it does not mean five technical pages are missing.
- 149 deduplicated evidence records, 75 eligible before publication, 67 flagged; all 19 method rows and seven workbook notes preserved.
- `pages.jsonl` contains one entry per source page. `model_responses/` preserves cached responses, including failed/partial stages. `checkpoint.json` gives exact counts. `review.html` is an unpublished inspection report.
- Live extraction was stopped while saving this checkpoint. No complete corpus or Qdrant index has been published. Human review and AFS approval are not implied.
- Provider support, resume fixes and source inspection guards are saved in the workspace. Latest regression suite: 66 passed. Frontend typecheck/build passed.

Resume from the project root:

```powershell
.\.venv\Scripts\python.exe -m backend.ingest build --provider llmtech --public-trial
```

This resumes compatible cached stages, then validates and publishes the corpus and local Qdrant/BM25 indexes. Do not use `--refresh` unless a full model rerun is intended. Prompts and extraction response fingerprints are preserved. LLMTech ingestion overrides leave the interactive Groq configuration unchanged.
