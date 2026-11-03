# Architecture

## Backend

`backend.main` assembles the app. `api/routers` owns HTTP contracts; `api/dependencies` exposes application-scoped settings and services through FastAPI dependency injection. Override these dependencies in focused tests. Domain code does not import HTTP routers.

`core` owns environment settings and root-relative paths. `schemas` owns Pydantic contracts. `providers` owns structured model transport, retries and the single DashScope model. `services/search` owns BM25, embeddings, embedded Qdrant and evidence resolution; `services/knowledge` owns corpus storage and reports; `services/history` owns SQLite rounds and PDF exports. `pipelines` orchestrates assessment, document comparison, source extraction and website ingestion. `cli` contains explicit operational entrypoints.

`prompts` contains model instructions loaded with `importlib.resources`; original extraction/synthesis prompt hashes are protected by tests. `templates` contains the static knowledge report. New evaluation snapshots include nested prompts and templates. Archived snapshots are immutable.

Synchronous search and report routes run in FastAPI's worker thread pool. Model transport remains async. Search locks preserve embedded-Qdrant access; one application worker is supported. Readiness does not prove source relevance. No startup provider probes or model fallback are performed.

## Frontend

`app` owns navigation and page loading. `features` groups assessment, search, knowledge, history and workspace UI. `shared/ui` contains reusable presentation and `shared/api` provides typed transport and response validation. Components import their owning modules directly. Secondary pages use React lazy/Suspense; visited pages remain mounted to retain drafts/results. Navigation effects clean up their listeners. Requests retain cancellation/stale-response checks.

ESLint enforces Hooks dependencies and Fast Refresh boundaries. Vitest imports TypeScript directly; jsdom covers hash navigation and visited-page state. Production build includes strict TypeScript checks.

## Verification boundaries

Backend tests block external HTTP transports and use isolated history. Search smoke bypasses application startup, reads the active technical generation, and checks all three ranking modes using cached local embeddings. It never publishes a corpus. Existing extraction tests validate schema/provenance/recovery with mocked model responses; no new LLM evaluation is performed.

## References

- [FastAPI multiple-file applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [FastAPI dependency injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [React custom hooks](https://react.dev/learn/reusing-logic-with-custom-hooks)
- [React lazy loading](https://react.dev/reference/react/lazy)
- [React Hooks lint](https://react.dev/reference/eslint-plugin-react-hooks)
