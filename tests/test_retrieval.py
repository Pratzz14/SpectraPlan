import asyncio
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from backend.core.config import Settings
from backend.services.search.evidence import CorpusUnavailable, EvidenceNotFound, EvidenceRevisionMismatch, load_snapshot
from backend.services.knowledge.knowledge_store import digest, read_json, write_json
from backend.main import create_app
from backend.schemas.models import CaseFacts, CustomerStatement, MeasurementContext
from backend.services.search.retrieval import (
    QUERY_PREFIX, CaseRetrievalService, RetrievalTimeout, _compact_query, _context_fields,
    build_indexes, lexical_candidates, query_tokens, tokens,
)
from tests.corpus_fixture import FakeEmbedder, make_corpus, rehash


class OrthogonalEmbedder(FakeEmbedder):
    @staticmethod
    def vectors(texts, *, query=False):
        return [[0.0, 1.0, *([0.0] * 382)] for _ in texts] if query else FakeEmbedder.vectors(texts)


def case(*contexts, statements=(), shared=()):
    return CaseFacts(contexts=[MeasurementContext(**c) for c in contexts],
                     customer_claims_and_requests=[CustomerStatement(**s) for s in statements],
                     shared_constraints=list(shared))


def powder_case():
    return case({"context_id": "stream_1", "label": "powder blend", "target_analytes": ["API"],
                 "sample_matrix": "powder blend", "sample_phase": "powder"})


def rebuild(directory):
    manifest = read_json(directory / "source_manifest.json")
    passages = [json.loads(line) for line in (directory / "passages.jsonl").read_text(encoding="utf-8").splitlines()]
    shutil.rmtree(directory / "qdrant")
    build_indexes(directory, passages + read_json(directory / "methods.json"), manifest["corpus_version"], FakeEmbedder())
    rehash(directory)


def add_passages(directory, specs):
    if (directory / "source_manifest.json").exists():
        base = json.loads((directory / "passages.jsonl").read_text(encoding="utf-8").splitlines()[0])
    else:
        _, base, _ = make_corpus(directory)
    raw = read_json(directory / "raw_pages.json")
    records = [base]
    for i, spec in enumerate(specs):
        spec = dict(spec)
        text = spec.pop("text")
        page = spec.pop("page", 1)
        block_id = f"extra{i}"
        raw[page - 1]["blocks"].append({"block_id": block_id, "text": text, "bbox": [0, 0, 1, 1]})
        record = {**base, "evidence_id": f"S01:p{page:03}:extra{i}", "page": page,
                  "revision": digest(text)[:24], "section": "Test source", "text": text,
                  "source_spans": [{"block_id": block_id, "quote": text, "start": 0,
                                    "end": len(text), "bbox": [0, 0, 1, 1]}], **spec}
        records.append(record)
    write_json(directory / "raw_pages.json", raw)
    (directory / "passages.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    rebuild(directory)
    return records


def set_version(directory, version):
    for name in ("source_manifest.json", "index_manifest.json", "bm25.json"):
        value = read_json(directory / name)
        value["corpus_version"] = version
        write_json(directory / name, value)
    rehash(directory)


@pytest.fixture
def local(tmp_path, monkeypatch):
    config = Settings(_env_file=None, corpus_dir=tmp_path / "knowledge", embedding_cache_dir=tmp_path / "models")
    make_corpus(config.corpus_dir)
    monkeypatch.setattr("backend.services.search.retrieval.Embedder", lambda *a, **k: OrthogonalEmbedder())
    return config, CaseRetrievalService(config)


def test_lexical_determinism_synonyms_and_no_match():
    docs = [{"evidence_id": "b", "tokens": tokens("water in powder")},
            {"evidence_id": "a", "tokens": tokens("water in powder")},
            {"evidence_id": "c", "tokens": tokens("protein milk fluorescence")},
            {"evidence_id": "d", "tokens": tokens("cable mirror laser")},
            {"evidence_id": "e", "tokens": tokens("tissue tumor kidney")}]
    assert [eid for eid, score in lexical_candidates(docs, "moisture") if score > 0] == ["a", "b"]
    assert lexical_candidates(docs, "no_matching_token_zz") == []
    assert "ftir" in query_tokens("MIR") and "fibre" in query_tokens("fiber")


def test_queries_retain_context_fields_and_customer_attribution():
    facts = case({"context_id": "stream_1", "label": "powder", "target_analytes": ["API"],
                  "sample_matrix": "excipients", "sample_phase": "powder", "process_constraints": ["feed frame"],
                  "missing_information": ["Required error", "Matrix interference"]}, shared=["keep laboratory checks"],
                 statements=[{"text": "Fluorescence might measure API", "kind": "customer_claim",
                              "context_ids": ["stream_1"], "input_quote": "Fluorescence might measure API"}])
    fields, statements = _context_fields(facts.contexts[0], facts)
    query, omitted = _compact_query(fields, FakeEmbedder())
    assert {"api", "excipients", "powder", "feed", "frame", "fluorescence", "interference"} <= set(tokens(query))
    assert "stream_1" not in query and not omitted
    assert statements[0]["kind"] == "customer_claim"
    assert fields["shared_constraints"] == ["keep laboratory checks"]


def test_long_query_compaction_is_logged_and_token_safe():
    fields = {"target": [" ".join(f"analyte{i}" for i in range(900))], "matrix": ["powder"]}
    query, omitted = _compact_query(fields, FakeEmbedder())
    assert "powder" in query and omitted
    assert FakeEmbedder.count(QUERY_PREFIX + query) <= 512


def test_combined_ledger_is_repeatable_balanced_and_traceable(local):
    config, service = local
    add_passages(config.corpus_dir, [
        {"text": "API powder blend uses Raman probes for calibration validation.", "evidence_scope": "application_example"},
        {"text": "Opaque milk fat protein uses NIR reflection geometry.", "evidence_scope": "application_example"},
        {"text": "Milk variability requires matrix-specific calibration."},
        {"text": "Raman fiber probes have a limited cable range."},
    ])
    facts = case(*powder_case().model_dump()["contexts"],
                 {"context_id": "stream_2", "label": "milk", "target_analytes": ["fat", "protein"],
                  "sample_matrix": "milk", "appearance": "opaque"})
    result = service.retrieve_case(facts)
    assert result == service.retrieve_case(facts)
    assert 1 <= len(result.evidence) <= 8
    assert len({e.evidence.evidence_id for e in result.evidence}) == len(result.evidence)
    assert any(e.evidence.content_kind == "method_row" for e in result.evidence)
    for context_id in ("stream_1", "stream_2"):
        application = next(c for c in result.coverage if c.context_id == context_id and c.facet == "application")
        assert application.status == "candidate_found"
    for entry in result.evidence:
        assert entry.matches and entry.selection_reasons and entry.evidence.evidence_url
        resolved = load_snapshot(config.corpus_dir).resolve(entry.evidence.evidence_id, entry.evidence.revision)
        assert resolved == entry.evidence
        assert resolved.human_review_status == "not_reviewed"
    rows = [e.evidence for e in result.evidence if e.evidence.content_kind == "method_row"]
    assert rows[0].workbook_notes and rows[0].model_extra["underlying_citation"]["page"] == 6
    assert result.model_calls == 0


def test_search_trace_preserves_exact_inputs_branch_rankings_and_filenames(local):
    from backend.services.search.retrieval import RETRIEVAL_EVENTS
    _, service = local
    seen=[]; token=RETRIEVAL_EVENTS.set(seen.append)
    try:
        result=service.retrieve_case(powder_case())
    finally:
        RETRIEVAL_EVENTS.reset(token)
    searched=[q for q in result.queries if q.facet != "method_table"]
    assert searched and seen[0]["event_type"] == "search_started"
    assert any(e["event_type"] == "search_finished" for e in seen)
    for query in searched:
        assert query.bm25_tokens == query_tokens(query.query)
        assert query.embedding_input == QUERY_PREFIX+query.query
        assert set(query.branch_rankings) == {"bm25","qdrant","hybrid"}
        assert all(row["file_name"] and row["rank"] > 0 for rows in query.branch_rankings.values() for row in rows)
        assert all(c.file_name and c.source_id for c in query.candidates)


def test_empty_search_is_successful_gap_and_only_one_followup(local):
    _, service = local
    facts = case({"context_id": "stream_1", "label": "unfindablezzzz", "target_analytes": ["unfindablezzzz"]},
                 {"context_id": "stream_2", "label": "unfindableyyyy", "target_analytes": ["unfindableyyyy"]})
    result = service.retrieve_case(facts)
    assert result.status == "ok" and result.evidence == [] and result.gaps
    assert result.search_rounds == 2
    assert sum(q.round == 2 for q in result.queries) == 1
    assert all(not d.admitted for q in result.queries for d in q.candidates)


def test_equipment_requirements_alone_do_not_cover_limitations(local):
    config, service = local
    add_passages(config.corpus_dir, [{"text": "Powder Raman analysis requires a probe during experimental action.",
        "evidence_scope": "application_example", "facts": [{"category": "experimental_scope",
            "statement": "Powder Raman analysis uses a probe", "support_quotes": ["Powder Raman analysis"], "quantities": []}]}])
    result = service.retrieve_case(powder_case())
    assert any(g.facet == "limitations" and g.reason == "no_relevant_evidence" for g in result.gaps)
    assert result.search_rounds == 2


def test_semantic_rows_require_structured_context_match(local):
    _, service = local
    service.embedder = FakeEmbedder()  # every row has cosine=1, but no method or sample match
    result = service.retrieve_case(case({"context_id": "stream_1", "label": "unfindablezzzz",
                                         "target_analytes": ["unfindablezzzz"]}))
    assert result.evidence == []
    assert any(c.reason == "requires_structured_context_match" for q in result.queries for c in q.candidates)


def test_no_context_and_underspecified_context_do_not_invent_support(local):
    _, service = local
    result = service.retrieve_case(CaseFacts())
    assert result.evidence == [] and result.search_rounds == 0 and result.gaps[0].reason == "missing_context"
    sparse = service.retrieve_case(case({"context_id": "stream_1", "label": "unknown sample",
                                         "missing_information": ["Required error", "Measurement method"]}))
    assert sparse.evidence == [] and sparse.search_rounds == 0
    assert any(g.reason == "unspecified_input" for g in sparse.gaps)


@pytest.mark.parametrize("cosine,admitted", [(0.649, False), (0.65, True), (0.7, True)])
def test_semantic_only_boundary_and_scope(local, cosine, admitted):
    from types import SimpleNamespace
    config, service = local
    records = add_passages(config.corpus_dir, [{"text": "Opaque dairy calibration requires validation.",
                                             "evidence_scope": "research_demonstration"}])
    snapshot = load_snapshot(config.corpus_dir)
    segment = next(s for s in read_json(snapshot.directory / "segments.json") if s["evidence_id"] == records[-1]["evidence_id"])
    class Client:
        def query_points(self, *a, **k):
            return SimpleNamespace(points=[SimpleNamespace(id=segment["id"], score=cosine,
                payload={"evidence_id": records[-1]["evidence_id"]})])
    from backend.schemas.retrieval_models import QueryTrace
    trace = QueryTrace(query_id="test", context_id="stream_1", facet="limitations", round=1,
                       query="unfindablezzzz", source_fields={"target": ["unfindablezzzz"]})
    service.embedder = OrthogonalEmbedder()
    service._search(snapshot, Client(), trace, trace.source_fields,
                    read_json(snapshot.directory / "bm25.json")["documents"], {segment["id"]: segment}, time.monotonic() + 30)
    candidate = trace.candidates[0]
    assert candidate.admitted is admitted and candidate.match.admission == "semantic_only"
    assert candidate.match.matched_terms == [] and candidate.match.cosine_score == cosine
    assert snapshot.resolve(candidate.evidence_id).evidence_scope == "research_demonstration"


def test_cap_exposes_omitted_contexts_and_duplicates_do_not_spend_budget(local):
    config, service = local
    specs = [{"text": f"Chemicalword{i} matrixword{i} uses a cuvette.", "evidence_scope": "application_example"}
             for i in range(10)]
    specs.append(dict(specs[0]))
    add_passages(config.corpus_dir, specs)
    facts = case(*[{"context_id": f"stream_{i+1}", "label": f"matrixword{i}",
                    "target_analytes": [f"chemicalword{i}"], "sample_matrix": f"matrixword{i}"} for i in range(10)])
    result = service.retrieve_case(facts)
    assert len(result.evidence) == 8
    assert len({e.evidence.text for e in result.evidence}) == 8
    assert any(g.reason == "budget_limit" and g.facet == "application" for g in result.gaps)
    assert sum(q.round == 2 for q in result.queries) <= 1


def test_rejects_broken_indexes_and_embeddings_instead_of_empty(local, monkeypatch):
    config, service = local
    (config.corpus_dir / "bm25.json").write_text("broken", encoding="utf-8")
    with pytest.raises(CorpusUnavailable):
        service.retrieve_case(powder_case())
    make_corpus(config.corpus_dir.parent / "other")
    service.settings = Settings(_env_file=None, corpus_dir=config.corpus_dir.parent / "other")
    def missing(*a, **k):
        raise ValueError("private local model path")
    monkeypatch.setattr("backend.services.search.retrieval.Embedder", missing)
    with pytest.raises(CorpusUnavailable) as error:
        service.retrieve_case(powder_case())
    assert "private" not in str(error.value)
    service.embedder = FakeEmbedder()
    service.embedder.fingerprint = "wrong"
    with pytest.raises(CorpusUnavailable, match="Embedding artifacts"):
        service.retrieve_case(powder_case())


def test_deadline_and_busy_lock_paths(local, monkeypatch):
    _, service = local
    with pytest.raises(RetrievalTimeout):
        service.retrieve_case(powder_case(), deadline=time.monotonic() - 1)
    class Busy:
        def acquire(self, **kwargs):
            return False
    with monkeypatch.context() as m:
        m.setattr("backend.services.search.retrieval.SEARCH_LOCK", Busy())
        with pytest.raises(CorpusUnavailable, match="busy"):
            service.retrieve_case(powder_case())
    calls = []
    def expire(*args):
        calls.append(1)
        raise RetrievalTimeout("Evidence retrieval deadline expired")
    with monkeypatch.context() as m:
        m.setattr(service, "_search", expire)
        with pytest.raises(RetrievalTimeout):
            service.retrieve_case(powder_case())
    assert len(calls) == 1
    assert service.retrieve_case(powder_case()).status == "ok"  # client closed and lock released


def test_slow_embedding_consumes_shared_deadline_without_another_search(local, monkeypatch):
    from types import SimpleNamespace
    _, service = local
    clock, calls = [100.0], []
    class Slow(OrthogonalEmbedder):
        @staticmethod
        def vectors(texts, **kwargs):
            calls.append(texts)
            clock[0] = 102.0
            return OrthogonalEmbedder.vectors(texts, **kwargs)
    monkeypatch.setattr("backend.services.search.retrieval.time", SimpleNamespace(monotonic=lambda: clock[0]))
    service.embedder = Slow()
    with pytest.raises(RetrievalTimeout):
        service.retrieve_case(powder_case(), deadline=101.0)
    assert len(calls) == 1


def test_concurrent_requests_are_serialized(local):
    _, service = local
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.retrieve_case(powder_case()), range(2)))
    assert results[0] == results[1]


def test_resolution_excludes_unverified_and_rejected_but_allows_automated_review(local):
    config, _ = local
    records = add_passages(config.corpus_dir, [
        {"text": "Unverified powder claim.", "retrieval_eligible": False, "verification": {}},
        {"text": "Rejected powder claim.", "retrieval_eligible": False, "human_review_status": "rejected"},
        {"text": "Flagged powder claim.", "retrieval_eligible": False, "validation_status": "flagged", "issues": ["unclear"]},
        {"text": "Business powder claim.", "retrieval_eligible": False, "evidence_scope": "business_context"},
    ])
    snapshot = load_snapshot(config.corpus_dir)
    for record in records[1:]:
        with pytest.raises(EvidenceNotFound):
            snapshot.resolve(record["evidence_id"])
    assert snapshot.resolve(records[0]["evidence_id"]).human_review_status == "not_reviewed"
    with pytest.raises(EvidenceRevisionMismatch):
        snapshot.resolve(records[0]["evidence_id"], "wrong-revision")


def test_exact_figure_resolution(local):
    config, _ = local
    records = add_passages(config.corpus_dir, [{"text": "Raman wavelength 785 nm", "content_kind": "figure_transcription",
        "transcription": "Raman wavelength 785 nm", "region": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9, "label": "Figure 1"}}])
    record = load_snapshot(config.corpus_dir).resolve(records[-1]["evidence_id"])
    assert record.text == record.model_extra["transcription"]
    assert record.model_extra["region"]["label"] == "Figure 1"


def test_revision_pinning_survives_current_pointer_change(tmp_path, monkeypatch):
    first, second = "corpus-" + "a" * 20, "corpus-" + "b" * 20
    for version, revision in ((first, "content-v1"), (second, "content-v2")):
        directory = tmp_path / "versions" / version
        make_corpus(directory, revision=revision)
        set_version(directory, version)
    write_json(tmp_path / "current.json", {"corpus_version": first, "directory": f"versions/{first}"})
    pinned = load_snapshot(tmp_path).resolve("T01:method_comparison:r002")
    write_json(tmp_path / "current.json", {"corpus_version": second, "directory": f"versions/{second}"})
    assert load_snapshot(tmp_path, first).resolve(pinned.evidence_id, pinned.revision) == pinned
    assert load_snapshot(tmp_path).resolve(pinned.evidence_id).revision == "content-v2"
    for invalid in ("../.env", "corpus-" + "c" * 20):
        with pytest.raises(EvidenceNotFound):
            load_snapshot(tmp_path, invalid)
    # Switching the pointer between retrieval rounds cannot mix generations.
    write_json(tmp_path / "current.json", {"corpus_version": first, "directory": f"versions/{first}"})
    service = CaseRetrievalService(Settings(_env_file=None, corpus_dir=tmp_path))
    service.embedder = OrthogonalEmbedder()
    search = service._search
    def change_pointer(*args):
        search(*args)
        write_json(tmp_path / "current.json", {"corpus_version": second, "directory": f"versions/{second}"})
    monkeypatch.setattr(service, "_search", change_pointer)
    result = service.retrieve_case(powder_case())
    assert result.corpus_version == first and result.search_rounds == 2
    assert all(e.evidence.revision == "content-v1" for e in result.evidence)


@pytest.mark.parametrize("mutation", ["duplicate", "wrong_tokens"])
def test_lexical_index_content_inconsistency_fails_closed(local, mutation):
    config, service = local
    path = config.corpus_dir / "bm25.json"
    index = read_json(path)
    if mutation == "duplicate":
        index["documents"].append(index["documents"][0])
    else:
        index["documents"][0]["tokens"] = ["inventedzzzz"]
    write_json(path, index)
    rehash(config.corpus_dir)
    with pytest.raises(CorpusUnavailable, match="Lexical index"):
        service.retrieve_case(powder_case())


def test_api_retrieval_evidence_and_input_errors(local, monkeypatch):
    config, _ = local
    app = create_app(config)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/retrieve", json=powder_case().model_dump())
            assert response.status_code == 200 and response.json()["evidence"]
            response = await client.get("/api/evidence/T01:method_comparison:r002")
            assert response.status_code == 200 and response.json()["sheet"] == "method_comparison"
            assert len(response.json()["workbook_notes"]) == 7
            assert (await client.get("/api/evidence/S01:p006:test", params={"revision": "wrong"})).status_code == 409
            assert (await client.get("/api/evidence/not-an-id")).status_code == 404
            assert (await client.get("/api/evidence/.env")).status_code == 404
            assert (await client.get("/api/evidence/S01:p006:test", params={"corpus_version": "../.env"})).status_code == 404
            duplicate = powder_case().model_dump()
            duplicate["contexts"].append(duplicate["contexts"][0])
            assert (await client.post("/api/retrieve", json=duplicate)).status_code == 422
            invalid = powder_case().model_dump()
            invalid["customer_claims_and_requests"] = [{"text": "Raman", "kind": "proposed_approach",
                "context_ids": ["stream_2"], "input_quote": "Raman"}]
            assert (await client.post("/api/retrieve", json=invalid)).status_code == 422
            assert (await client.post("/api/retrieve", json={"description": "powder"})).status_code == 422
            def timeout(*a, **k):
                raise RetrievalTimeout("Evidence retrieval deadline expired")
            monkeypatch.setattr(app.state.retrieval_service, "retrieve_case", timeout)
            assert (await client.post("/api/retrieve", json=powder_case().model_dump())).status_code == 504
    asyncio.run(run())


def test_api_corrupt_corpus_is_503_without_paths(local):
    config, _ = local
    (config.corpus_dir / "methods.json").write_text("broken", encoding="utf-8")
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(config)), base_url="http://test") as client:
            for response in (await client.post("/api/retrieve", json=powder_case().model_dump()),
                             await client.get("/api/evidence/S01:p006:test")):
                assert response.status_code == 503 and str(config.corpus_dir) not in response.text
    asyncio.run(run())
