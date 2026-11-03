# Refactor verification — 2026-11-03

| Check | Result |
|---|---|
| Backend contracts, excluding evaluation runner | 332 passed |
| Evaluation runner, integrity and tamper detection | 17 passed |
| Final prompt/provider/recovery checks | 47 passed |
| Final HTTP endpoint checks | 108 passed |
| Python dependency consistency | Passed (`pip check`) |
| Frontend Vitest, including navigation preservation | 21 passed |
| Frontend Hooks/Fast Refresh lint | Passed |
| TypeScript and Vite production build | Passed |
| Real technical corpus search: four statements × three modes | 12 passed; zero generative-model calls |
| Primary extraction/synthesis/PDF/Office prompt hashes | Match original revision |
| Archived submission portable integrity verification | Passed; batch 4c14fccd1a3d4eadb672c14de91c142e |
| Production npm dependency audit | Zero advisories |

Backend commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_evaluation_runner.py --basetemp=tmp/contracts
.\.venv\Scripts\python.exe -m pytest -q tests/test_evaluation_runner.py --basetemp=tmp/evaluation
.\.venv\Scripts\python.exe -m pytest -q tests/test_provider_routing.py tests/test_prompt_resources.py tests/test_extraction_recovery.py --basetemp=tmp/prompts
.\.venv\Scripts\python.exe -m evaluation.search_smoke
.\.venv\Scripts\python.exe -m scripts.verify_submission --portable
```

Frontend commands, from `frontend`: `npm test`, `npm run lint`, `npm run build`, `npm audit --omit=dev`.

External HTTP is prohibited by backend test fixtures; providers are mocked. Search checks use local cached embeddings and embedded Qdrant. Windows asyncio requires loopback access even for mocked HTTP tests; the restricted sandbox prevented event-loop initialization, so backend tests ran outside that sandbox.

The evaluation tests use small valid PDFs for batch integrity checks; dedicated PDF tests retain actual content and pagination coverage. Historical final answers were neither regenerated nor edited. Passing operational checks does not establish relevance, entailment, scientific accuracy or expert approval.

The full npm audit has seven moderate development-tool advisories through ESLint/minimatch, with no compatible fix reported by npm. Production dependencies are clear. A Starlette/httpx TestClient deprecation warning remains; its suggested migration is separate from this refactor.

Deployment remains one worker on a trusted local workstation; see [architecture](architecture.md) and [operations](operations.md).
