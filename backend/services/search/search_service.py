"""Local retrieval comparison; website claims remain a separate context dataset."""
import time

from backend.services.knowledge.knowledge_store import active_directory, load_records, read_json, validate_corpus
from backend.services.search.retrieval import COLLECTION, QUERY_PREFIX, SEARCH_LOCK, Embedder, fuse, query_tokens, tokens
from backend.pipelines.website.ingest import validate_web, web_directory

class SearchUnavailable(Exception):
    pass


class SearchQueryError(ValueError):
    pass


class SearchService:
    def __init__(self, settings):
        self.settings, self.embedder = settings, None

    def status(self):
        result = {}
        for kind in ("technical", "website"):
            try:
                directory, records, metadata = self._dataset(kind)
                result[kind] = {"status": "ready", "corpus_version": metadata["corpus_version"], "records": len(records)}
                if kind == "website":
                    result[kind].update(pages=metadata["page_count"], seed_url=metadata["seed_url"], fetched_at=metadata["fetched_at"])
            except (OSError, ValueError, KeyError):
                result[kind] = {"status": "unavailable", "records": 0}
        return result

    def _dataset(self, kind):
        if kind in {"technical", "inspection"}:
            directory = active_directory(self.settings.corpus_dir)
            validate_corpus(directory)
            manifest, passages, methods = load_records(directory)
            records = [r for r in passages + methods if r.get("search_eligible", True)] if kind == "inspection" else [r for r in passages + methods if r["retrieval_eligible"]]
            if kind == "inspection" and (directory / "inspection").is_dir():
                directory = directory / "inspection"
        else:
            directory = web_directory(self.settings.web_corpus_dir)
            validate_web(directory)
            manifest = read_json(directory / "manifest.json")
            records = [r for r in read_json(directory / "records.json") if r["context_search_eligible"]]
        return directory, records, manifest

    def compare(self, query, *, mode="compare", dataset="technical", limit=6, expand_synonyms=True, source_id=None):
        if mode not in {"compare", "bm25", "qdrant", "hybrid"} or dataset not in {"technical", "website", "all", "inspection"}:
            raise ValueError("Unknown search mode or dataset")
        if not query.strip() or len(query) > 2000 or not 1 <= limit <= 8:
            raise ValueError("Supply a query of 1–2000 characters and a result limit of 1–8")
        if not SEARCH_LOCK.acquire(timeout=30):
            raise SearchUnavailable("Search is busy. Try again shortly.")
        try:
            return self._compare(query.strip(), mode, dataset, limit, expand_synonyms, source_id)
        finally:
            SEARCH_LOCK.release()

    def _compare(self, query, mode, dataset, limit, expand_synonyms, source_id=None):
        from rank_bm25 import BM25Okapi
        started = time.monotonic()
        selected = ["technical", "website"] if dataset == "all" else [dataset]
        loaded, versions, records = [], {}, {}
        try:
            for kind in selected:
                directory, rows, manifest = self._dataset(kind)
                loaded.append((kind, directory))
                versions[kind] = manifest["corpus_version"]
                records.update({r["evidence_id"]: {**r, "dataset": kind} for r in rows if not source_id or r["source_id"] == source_id})
        except (OSError, ValueError, KeyError):
            raise SearchUnavailable("The selected dataset is unavailable or failed validation. Check corpus readiness.") from None
        terms = query_tokens(query) if expand_synonyms else tokens(query)
        original_terms = tokens(query)
        lexical, dense, lexical_scores, dense_scores, segments = [], [], {}, {}, {}
        if mode in {"compare", "bm25", "hybrid"}:
            documents = [d for _, directory in loaded for d in read_json(directory / "bm25.json")["documents"]]
            if documents:
                scores = BM25Okapi([d["tokens"] for d in documents]).get_scores(terms)
                for i in sorted(range(len(documents)), key=lambda i: (-scores[i], documents[i]["evidence_id"])):
                    if scores[i] > 0 and (not source_id or documents[i]["evidence_id"] in records):
                        eid = documents[i]["evidence_id"]
                        lexical_scores[eid] = float(scores[i])
                        lexical.append(eid)
                    if len(lexical) == 20:
                        break
        if records and mode in {"compare", "qdrant", "hybrid"}:
            from qdrant_client import QdrantClient
            try:
                if self.embedder is None:
                    self.embedder = Embedder(self.settings.embedding_cache_dir, local_only=True)
                if self.embedder.count(QUERY_PREFIX + query) > 512:
                    raise SearchQueryError("The semantic query exceeds 512 tokens. Use a shorter query.")
                vector = self.embedder.vectors([query], query=True)[0]
                points = []
                for _, directory in loaded:
                    index = read_json(directory / "index_manifest.json")
                    if self.embedder.fingerprint != index["embedding_fingerprint"]:
                        raise SearchUnavailable("Embedding artifacts differ from the selected index. Rebuild it before searching.")
                    by_segment = {s["id"]: s for s in read_json(directory / "segments.json")}
                    client = QdrantClient(path=str(directory / "qdrant"))
                    try:
                        for point in client.query_points(COLLECTION, query=vector, limit=max(20,len(by_segment)) if source_id else 20).points:
                            if source_id and point.payload["evidence_id"] not in records:
                                continue
                            points.append((point.payload["evidence_id"], float(point.score), by_segment[str(point.id)]["text"]))
                    finally:
                        client.close()
                for eid, score, segment in sorted(points, key=lambda p: (-p[1], p[0])):
                    if eid not in dense_scores:
                        dense_scores[eid], segments[eid] = score, segment
                        dense.append(eid)
                    if len(dense) == 20:
                        break
            except SearchQueryError:
                raise
            except (OSError, RuntimeError, ValueError, KeyError):
                raise SearchUnavailable("Local embeddings or Qdrant are unavailable or in use by another process.") from None
        if any(eid not in records for eid in lexical + dense):
            raise SearchUnavailable("Search index membership differs from the selected corpus.")

        def result(eid, score, rank):
            record = records[eid]
            words = set(tokens(record["section"] + " " + record["text"]))
            return {"rank": rank, "score": score, "bm25_score": lexical_scores.get(eid), "qdrant_score": dense_scores.get(eid),
                "branches": [name for name, ranking in (("bm25", lexical), ("qdrant", dense)) if eid in ranking],
                "matched_terms": list(dict.fromkeys(term for term in terms if term in words)),
                "matching_segment": segments.get(eid), "evidence": record}

        rankings = {}
        if mode in {"compare", "bm25"}:
            rankings["bm25"] = [result(eid, lexical_scores[eid], i) for i, eid in enumerate(lexical[:limit], 1)]
        if mode in {"compare", "qdrant"}:
            rankings["qdrant"] = [result(eid, dense_scores[eid], i) for i, eid in enumerate(dense[:limit], 1)]
        if mode in {"compare", "hybrid"}:
            rankings["hybrid"] = [result(eid, score, i) for i, (eid, score) in enumerate(fuse(lexical, dense, limit), 1)]
        warnings = ["Website results are vendor/business context, not independently validated technical evidence."] if dataset in {"website", "all"} else []
        if dataset == "inspection":
            warnings.append("Inspection includes development examples and business context. These are excluded from assessment retrieval.")
        if not any(rankings.values()):
            warnings.append("No searchable records match the selected dataset and source." if not records else "No positive keyword matches were found. Try different words or semantic search.")
        return {"query": query, "mode": mode, "dataset": dataset, "versions": versions, "limit": limit,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1), "query_terms": list(dict.fromkeys(original_terms)),
            "expanded_terms": list(dict.fromkeys(t for t in terms if t not in original_terms)),
            "rankings": rankings, "warnings": warnings, "model_calls": 0}
