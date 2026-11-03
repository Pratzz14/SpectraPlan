"""Local dense retrieval plus lexical BM25, fused at evidence-record level."""

import importlib.metadata
from contextvars import ContextVar
import re
import threading
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from rank_bm25 import BM25Okapi

from backend.evidence import CorpusUnavailable, CorpusSnapshot, load_snapshot
from backend.knowledge_store import active_directory, digest, file_hash, load_records, read_json, validate_corpus, write_json
from backend.models import CaseFacts
from backend.retrieval_models import (
    CandidateDecision, EvidenceCoverage, EvidenceGap, EvidenceMatch, LedgerEntry, QueryTrace, RetrievalResult,
)

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
COLLECTION = "afs_evidence"
SEARCH_LOCK = threading.RLock()
RETRIEVAL_EVENTS = ContextVar("retrieval_events", default=None)
# Domain synonyms, independent of any development or final scenario.
SYNONYMS = {"mir": ["mid", "infrared", "ftir"], "ftir": ["mir", "infrared"],
            "nir": ["near", "infrared"], "atr": ["attenuated", "total", "reflection"],
            "api": ["active", "pharmaceutical", "ingredient"], "fluo": ["fluorescence", "fluorimetry"],
            "fluorescence": ["fluorimetry"], "moisture": ["water"], "water": ["moisture"]}
SYNONYMS.update({"fiber": ["fibre"], "fibre": ["fiber"],
                 "reflectance": ["reflection"], "reflection": ["reflectance"]})


def tokens(text: str) -> list[str]:
    return re.findall(r"[\wµμ]+", text.casefold())


def query_tokens(query: str) -> list[str]:
    original = tokens(query)
    return original + [syn for term in original for syn in SYNONYMS.get(term, [])]


class Embedder:
    def __init__(self, cache: Path, *, local_only=False):
        from fastembed import TextEmbedding
        from tokenizers import Tokenizer

        cache.mkdir(parents=True, exist_ok=True)
        self.model = TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=str(cache), threads=2, local_files_only=local_only)
        tokenizers = list(cache.rglob("tokenizer.json"))
        if len(tokenizers) != 1:
            raise ValueError("Expected one pinned embedding tokenizer in dedicated cache")
        model_root = tokenizers[0].parent
        self.tokenizer = Tokenizer.from_file(str(tokenizers[0]))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.artifacts = {p.relative_to(model_root).as_posix(): file_hash(p) for p in sorted(model_root.rglob("*"))
                          if p.is_file() and ".cache" not in p.relative_to(model_root).parts and not p.name.endswith(".lock")}
        self.fingerprint = digest({"model": EMBEDDING_MODEL, "artifacts": self.artifacts})

    def count(self, text: str) -> int:
        return len(self.tokenizer.encode(text).ids)

    def vectors(self, texts: list[str], *, query=False) -> list[list[float]]:
        prepared = [QUERY_PREFIX + t if query else t for t in texts]
        if any(self.count(t) > 512 for t in prepared):
            raise ValueError("Embedding input exceeds 512 tokens; truncation is forbidden")
        vectors = [v.tolist() for v in self.model.embed(prepared, batch_size=32)]
        if len(vectors) != len(texts) or any(len(v) != 384 for v in vectors):
            raise ValueError("Unexpected embedding dimensions/count")
        return vectors


def index_text(record: dict) -> str:
    knowledge = record.get("knowledge")
    if not knowledge:
        return record["text"]
    return "\n\n".join(str(knowledge.get(k) or "") for k in ("claim", "support_quote", "relevance", "caveat"))


def make_segments(records: list[dict], count) -> list[dict]:
    segments = []
    for record in records:
        if not record["retrieval_eligible"]:
            continue
        heading = record["section"].strip()
        prefix = heading + "\n" if heading else ""
        # Sentence/paragraph boundaries preserve quantities and qualifiers together.
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n\s*\n", index_text(record))
        if record.get("content_kind") == "extracted_text":
            expanded=[]
            for sentence in sentences:
                while count(prefix+sentence)>448:
                    low,high=1,len(sentence)
                    while low<high:
                        middle=(low+high+1)//2
                        if count(prefix+sentence[:middle])<=448: low=middle
                        else: high=middle-1
                    cut=sentence.rfind(" ",0,low+1)
                    if cut<=0: cut=low
                    expanded.append(sentence[:cut])
                    sentence=sentence[cut:].lstrip()
                expanded.append(sentence)
            sentences=expanded
        parts, current = [], ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if count(prefix + sentence) > 448:
                raise ValueError(f"Overlength indivisible source sentence: {record['evidence_id']}")
            trial = current + ("\n\n" if current else "") + sentence
            if current and count(prefix + trial) > 448:
                parts.append(current)
                current = sentence
            else:
                current = trial
        if current:
            parts.append(current)
        for index, part in enumerate(parts):
            text = prefix + part
            sid = str(uuid5(NAMESPACE_URL, f"spectraplan/{record['evidence_id']}/{digest(text)}"))
            segments.append({"id": sid, "evidence_id": record["evidence_id"], "segment": index,
                             "text": text, "token_count": count(text)})
    return segments


def build_indexes(directory: Path, records: list[dict], version: str, embedder: Embedder, *, allow_empty=False):
    from qdrant_client import QdrantClient, models

    segments = make_segments(records, embedder.count)
    if not segments and not allow_empty:
        raise ValueError("No eligible evidence to index")
    vectors = embedder.vectors([s["text"] for s in segments]) if segments else []
    database = directory / "qdrant"
    client = QdrantClient(path=str(database))
    try:
        client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
        for start in range(0, len(segments), 64):
            client.upsert(COLLECTION, [models.PointStruct(id=s["id"], vector=v, payload={"evidence_id": s["evidence_id"]})
                                      for s, v in zip(segments[start:start + 64], vectors[start:start + 64], strict=True)])
        if client.count(COLLECTION, exact=True).count != len(segments):
            raise ValueError("Qdrant index lost segments")
    finally:
        client.close()
    eligible = [r for r in records if r["retrieval_eligible"]]
    write_json(directory / "segments.json", segments)
    write_json(directory / "bm25.json", {"corpus_version": version, "documents": [
        {"evidence_id": r["evidence_id"], "tokens": tokens(r["section"] + " " + index_text(r))} for r in eligible]})
    write_json(directory / "index_manifest.json", {"corpus_version": version, "embedding_model": EMBEDDING_MODEL,
               "embedding_fingerprint": embedder.fingerprint, "embedding_artifacts": embedder.artifacts,
               "dimensions": 384, "distance": "cosine", "segment_count": len(segments), "rrf_k": 60,
               "query_instruction": QUERY_PREFIX, "qdrant_files": {
                   p.relative_to(directory).as_posix(): file_hash(p) for p in sorted(database.rglob("*"))
                   if p.is_file() and p.name != ".lock"},
               "packages": {n: importlib.metadata.version(n) for n in ["qdrant-client", "fastembed", "tokenizers", "onnxruntime", "rank-bm25"]}})


def fuse(lexical: list[str], dense: list[str], limit=8) -> list[tuple[str, float]]:
    scores = {}
    for ranking in (lexical, dense):
        seen = set()
        for rank, evidence_id in enumerate(ranking, 1):
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            scores[evidence_id] = scores.get(evidence_id, 0) + 1 / (60 + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]


def search(root: Path, embedding_cache: Path, query: str, limit=8) -> dict:
    from qdrant_client import QdrantClient

    if not query.strip() or not 1 <= limit <= 8:
        raise ValueError("Supply a nonempty query and limit between 1 and 8")
    directory = active_directory(root)
    validate_corpus(directory)
    manifest, passages, methods = load_records(directory)
    index = read_json(directory / "index_manifest.json")
    embedder = Embedder(embedding_cache)
    if embedder.fingerprint != index["embedding_fingerprint"]:
        raise ValueError("Embedding model artifacts changed; rebuild before searching")
    bm25 = read_json(directory / "bm25.json")
    if bm25["corpus_version"] != manifest["corpus_version"]:
        raise ValueError("BM25/corpus revision mismatch")
    docs = bm25["documents"]
    scores = BM25Okapi([d["tokens"] for d in docs]).get_scores(query_tokens(query))
    lexical = [docs[i]["evidence_id"] for i in sorted(range(len(docs)), key=lambda i: (-scores[i], docs[i]["evidence_id"]))
               if scores[i] > 0][:20]
    client = QdrantClient(path=str(directory / "qdrant"))
    try:
        dense_points = client.query_points(COLLECTION, query=embedder.vectors([query], query=True)[0], limit=20).points
    finally:
        client.close()
    dense = [p.payload["evidence_id"] for p in dense_points]
    records = {r["evidence_id"]: r for r in [*passages, *methods] if r["retrieval_eligible"]}
    if any(eid not in records for eid in lexical + dense):
        raise ValueError("Index contains unknown or excluded evidence")
    return {"corpus_version": manifest["corpus_version"], "query": query, "ranking": "BM25 + cosine, RRF k=60",
            "results": [{"score": score, "branches": [name for name, ids in [("bm25", lexical), ("qdrant", dense)] if eid in ids],
                         "evidence": records[eid]} for eid, score in fuse(lexical, dense, limit)]}


# Assessment retrieval deliberately has stricter admission than the manual workbench.
RETRIEVAL_VERSION = "context-hybrid-v1"
FACETS = ("application", "geometry", "compatibility", "limitations")
# These words alone cannot make a lexical result relevant to a customer context.
GENERIC = set("""a an the and or of for to in on with by from as at is are be it its we our us
    this that these those not no do does can could would should will want need requested
    request whether how what which unknown unspecified specific information missing
    sample samples material product target measurement measurements measure measuring
    analysis analyze analytical spectroscopy spectral method methods process online inline
    concentration changes composition required range error response time name list type
    initial concept compare comparison reasonable options production equipment results
    laboratory checks earlier practical experiment retaining assess follow during through
    into containing spectroscopy based have has had been being was were there their they them
    he she you your my me mine ours theirs all any some more most less much many such also
    only other another each every both either neither same different well very just already
    still otherwise before after between within without over under up down out off than then
    so if because while although about regarding concerning like using used use uses earlier
    current currently new first next possible possibility desired design supplied stated
    given please help tell determine information per e g""".split())
FACET_TERMS = {
    "application": [],
    "geometry": ["probe", "geometry", "transmission", "reflection", "ATR"],
    "compatibility": ["fiber", "cable", "compatibility", "spectral", "range"],
    "limitations": ["calibration", "validation", "limitations", "interference"],
}
METHOD_PATTERNS = {
    "nir": r"\bnir\b|near[ -]+infrared",
    "mir": r"\b(?:mir|ftir|ir)\b|mid[ -]+infrared",
    "raman": r"\braman\b",
    "uv": r"\buv\b|ultraviolet|uv/visible",
    "fluorescence": r"\b(?:fluorescence|fluorimetry|fluorimetric)\b",
}
HARDWARE = {"fiber", "fibre", "cable", "probe", "spectrometer", "instrument", "hardware", "compatible"}
LIMITATION_WORDS = {"calibration", "validation", "limitations", "limitation", "limited", "insufficient",
                    "interference", "overlap", "variability",
                    "fails", "fail", "cannot", "uncertain", "uncertainty"}
GEOMETRY_WORDS = {"probe", "probes", "geometry", "transmission", "transflection", "reflectance", "reflection",
                  "atr", "cuvette", "sphere", "depth"}


class RetrievalTimeout(Exception):
    pass


def _check_deadline(deadline):
    if time.monotonic() >= deadline:
        raise RetrievalTimeout("Evidence retrieval deadline expired")


def _meaningful(text):
    return [t for t in dict.fromkeys(query_tokens(text)) if t not in GENERIC and not t.isdigit() and len(t) > 1]


def _methods(text):
    return {name for name, pattern in METHOD_PATTERNS.items() if re.search(pattern, text, re.I)}


def _context_fields(context, facts):
    statements = [s.model_dump() for s in facts.customer_claims_and_requests
                  if not s.context_ids or context.context_id in s.context_ids]
    fields = {"target": context.target_analytes, "matrix": [context.sample_matrix or ""],
              "phase_appearance": [context.sample_phase or "", context.appearance or ""],
              "goals": context.measurement_goals, "process": context.process_constraints,
              "shared_constraints": facts.shared_constraints,
              "statements": [s["text"] for s in statements],
              "unknowns": context.missing_information + facts.missing_information}
    # A label is useful for a sparse context, but never implies a missing phase/value.
    if not any(fields[k] for k in ("target", "goals", "process")) and not context.sample_matrix:
        fields["label"] = [context.label]
    return {k: [v for v in values if v] for k, values in fields.items()}, statements


def _compact_query(fields, embedder, facet="context"):
    # Round-robin fields keep a verbose goal from crowding out matrix or unknowns.
    groups = [tokens(" ".join(values)) for values in fields.values()]
    ordered = list(dict.fromkeys(term for i in range(max(map(len, groups), default=0))
                                 for group in groups if i < len(group) for term in [group[i]]))
    extras = [t.casefold() for t in FACET_TERMS.get(facet, [])]
    chosen, omitted = [], []
    for term in list(dict.fromkeys(extras + ordered)):
        if embedder.count(QUERY_PREFIX + " ".join(chosen + [term])) <= 512:
            chosen.append(term)
        else:
            omitted.append(term)
    return " ".join(chosen), omitted


def _record_facets(record, fields, facet, *, semantic_only=False):
    words = set(tokens(record["text"]))
    categories = {f["category"] for f in record.get("facts", [])}
    facets = set()
    matrix = set(_meaningful(" ".join(fields.get("matrix", []) + fields.get("label", []))))
    target = set(_meaningful(" ".join(fields.get("target", []))))
    if record["content_kind"] != "method_row" and (
        matrix & words or (not matrix and target & words) or
        (semantic_only and facet in {"context", "application"} and record["evidence_scope"] == "application_example")
    ):
        facets.add("application")
    if record["content_kind"] == "method_row" or "geometry" in categories or GEOMETRY_WORDS & words:
        facets.add("geometry")
    if record["content_kind"] != "method_row" and (HARDWARE & words or "equipment" in categories):
        facets.add("compatibility")
    if record["content_kind"] != "method_row" and (
        LIMITATION_WORDS & words or categories & {"limitation", "calibration"}
    ):
        facets.add("limitations")
    return [f for f in FACETS if f in facets]


def _required_facets(fields):
    text = " ".join(v for values in fields.values() for v in values)
    required = ["application", "geometry", "limitations"]
    if HARDWARE & set(tokens(text)) or _methods(text):
        required.insert(2, "compatibility")
    return required


def lexical_candidates(documents, query, limit=20):
    """Deterministic BM25 scores over the snapshot's already validated documents."""
    if not documents or not tokens(query):
        return []
    scores = BM25Okapi([d["tokens"] for d in documents]).get_scores(query_tokens(query))
    ordered = sorted(range(len(documents)), key=lambda i: (-scores[i], documents[i]["evidence_id"]))
    return [(documents[i]["evidence_id"], float(scores[i])) for i in ordered if scores[i] > 0][:limit]


class CaseRetrievalService:
    def __init__(self, settings):
        self.settings = settings
        self.embedder = None

    def retrieve_case(self, facts: CaseFacts, deadline: float | None = None) -> RetrievalResult:
        ids = [c.context_id for c in facts.contexts]
        if len(ids) != len(set(ids)):
            raise ValueError("Context IDs must be unique")
        if any(set(s.context_ids) - set(ids) for s in [*facts.customer_claims_and_requests, *facts.fact_provenance]):
            raise ValueError("Statements must reference existing contexts")
        deadline = min(deadline if deadline is not None else float("inf"),
                       time.monotonic() + self.settings.request_deadline_s)
        _check_deadline(deadline)
        if not SEARCH_LOCK.acquire(timeout=min(30, max(0, deadline - time.monotonic()))):
            _check_deadline(deadline)
            raise CorpusUnavailable("Evidence search is busy; try again shortly")
        try:
            _check_deadline(deadline)
            snapshot = load_snapshot(self.settings.corpus_dir)
            _check_deadline(deadline)
            if not facts.contexts:
                return self._result(snapshot, [], [], [], [EvidenceGap(
                    reason="missing_context", message="No measurement contexts were supplied")], 0)
            if self.embedder is None:
                self.embedder = Embedder(self.settings.embedding_cache_dir, local_only=True)
            index = read_json(snapshot.directory / "index_manifest.json")
            if self.embedder.fingerprint != index["embedding_fingerprint"]:
                raise CorpusUnavailable("Embedding artifacts differ from the pinned corpus index")
            _check_deadline(deadline)
            from qdrant_client import QdrantClient
            client = QdrantClient(path=str(snapshot.directory / "qdrant"))
            try:
                return self._retrieve(facts, snapshot, client, deadline)
            finally:
                client.close()
        except (OSError, RuntimeError, KeyError, IndexError, TypeError, ValueError, ImportError):
            raise CorpusUnavailable("Local retrieval indexes or embeddings are unavailable or invalid") from None
        finally:
            SEARCH_LOCK.release()

    def _search(self, snapshot, client, trace, fields, documents, by_segment, deadline):
        _check_deadline(deadline)
        trace.bm25_tokens = query_tokens(trace.query)
        trace.embedding_input = QUERY_PREFIX + trace.query
        sink = RETRIEVAL_EVENTS.get()
        if sink:
            sink({"stage":"retrieval", "event_type":"search_started", "payload":{
                "corpus_version":snapshot.version, "collection":COLLECTION,
                "embedding_model":EMBEDDING_MODEL, "embedding_fingerprint":getattr(self.embedder,"fingerprint",None),
                "query":trace.model_dump(mode="json")}})
        lexical = lexical_candidates(documents, trace.query)
        vector = self.embedder.vectors([trace.query], query=True)[0]
        _check_deadline(deadline)
        # Fetch all children so duplicate segments cannot crowd distinct parents out.
        points = client.query_points(COLLECTION, query=vector, limit=len(by_segment)).points
        _check_deadline(deadline)
        dense = {}
        for point in sorted(points, key=lambda p: (-p.score, str(p.id))):
            segment = by_segment[str(point.id)]
            eid = point.payload["evidence_id"]
            if segment["evidence_id"] != eid or eid not in snapshot.records:
                raise CorpusUnavailable("Dense index contains unknown or excluded evidence")
            if eid not in dense:
                dense[eid] = (float(point.score), segment["text"])
            if len(dense) == 20:
                break
        bm25 = dict(lexical)
        lexical_ranks = {eid: i for i, (eid, _) in enumerate(lexical, 1)}
        dense_ranks = {eid: i for i, eid in enumerate(dense, 1)}
        def branch_row(eid, score, rank):
            record = snapshot.records[eid]
            return {"evidence_id": eid, "source_id": record["source_id"], "file_name": record["file_name"],
                    "score": score, "rank": rank}
        trace.branch_rankings = {
            "bm25": [branch_row(eid, score, rank) for rank, (eid, score) in enumerate(lexical, 1)],
            "qdrant": [branch_row(eid, value[0], dense_ranks[eid]) for eid, value in dense.items()],
            "hybrid": [branch_row(eid, score, rank) for rank, (eid, score) in
                       enumerate(fuse(list(bm25), list(dense), limit=40), 1)]}
        focus = set(_meaningful(" ".join(v for values in fields.values() for v in values)))
        for eid, score in fuse(list(bm25), list(dense), limit=40):
            record = snapshot.records[eid]
            words = set(tokens(record["section"] + " " + record["text"]))
            matched = sorted(focus & words)
            lexical_ok = eid in bm25 and bool(matched)
            semantic_ok = eid in dense and dense[eid][0] >= self.settings.retrieval_semantic_min_score
            semantic_only = not lexical_ok
            facets = _record_facets(record, fields, trace.facet, semantic_only=semantic_only)
            admitted = (lexical_ok or semantic_ok) and bool(facets) and record["content_kind"] != "method_row"
            match = EvidenceMatch(query_id=trace.query_id, context_id=trace.context_id, facets=facets,
                admission="lexical" if lexical_ok else "semantic_only", bm25_score=bm25.get(eid),
                bm25_rank=lexical_ranks.get(eid), cosine_score=dense.get(eid, (None, None))[0],
                dense_rank=dense_ranks.get(eid), rrf_score=score, matched_terms=matched,
                matching_segment=dense.get(eid, (None, None))[1])
            trace.candidates.append(CandidateDecision(evidence_id=eid, admitted=admitted, match=match,
                source_id=record["source_id"], file_name=record["file_name"],
                reason=("meaningful_keyword_match" if lexical_ok else "semantic_threshold") if admitted
                else "requires_structured_context_match" if record["content_kind"] == "method_row"
                else "no_relevant_facet" if lexical_ok or semantic_ok else "below_relevance_gate"))
        if sink:
            sink({"stage":"retrieval", "event_type":"search_finished", "payload":trace.model_dump(mode="json")})

    def _method_lookup(self, snapshot, context, fields, queries):
        text = " ".join(v for values in fields.values() for v in values)
        method_names = _methods(text)
        application_candidates = []
        # Discover methods only in application evidence actually admitted for this context.
        for trace in queries:
            if trace.context_id != context.context_id:
                continue
            for candidate in trace.candidates:
                record = snapshot.records[candidate.evidence_id]
                if candidate.admitted and "application" in candidate.match.facets and _methods(record["text"]):
                    application_candidates.append((record["evidence_scope"] == "application_example",
                                                   candidate.match.rrf_score, candidate.evidence_id))
        source_ids = []
        geometry_hints = tokens(text)
        if application_candidates:
            _, _, source_id = min(application_candidates, key=lambda c: (-c[0], -c[1], c[2]))
            source_ids.append(source_id)
            source_text = snapshot.records[source_id]["text"]
            method_names.update(_methods(source_text))
            geometry_hints += query_tokens(source_text)
        phase = set(_meaningful(context.sample_phase or ""))
        candidates = []
        for eid, record in snapshot.records.items():
            if record["content_kind"] != "method_row":
                continue
            raw = record["raw_values"]
            method_match = _methods(record["method"]) & method_names
            phase_match = phase & set(query_tokens(raw["sample_type"]))
            if phase and not phase_match:
                continue
            if method_match or phase_match:
                geometry_match = set(query_tokens(record["geometry"])) & {
                    "atr", "reflection", "reflectance", "transmission", "transflection", "cuvette", "sphere"}
                geometry_weight = sum(geometry_hints.count(t) for t in geometry_match)
                candidates.append((eid, (bool(method_match), geometry_weight, bool(phase_match)),
                                   sorted(method_match | phase_match | (geometry_match & set(geometry_hints)))))
        trace = QueryTrace(query_id=f"methods_{context.context_id}", context_id=context.context_id,
            facet="method_table", round=1, query="structured method/geometry/sample-type lookup",
            source_fields={"methods": sorted(method_names), "explicit_phase": [context.sample_phase] if context.sample_phase else [],
                           "application_evidence_ids": source_ids})
        ordered = sorted(candidates, key=lambda c: (tuple(-x for x in c[1]), c[0]))
        diverse, seen_methods = [], set()
        for candidate in ordered:
            family = _methods(snapshot.records[candidate[0]]["method"])
            if family - seen_methods:
                diverse.append(candidate)
                seen_methods.update(family)
        diverse += [c for c in ordered if c not in diverse]
        for rank, (eid, _, matched) in enumerate(diverse[:3], 1):
            trace.candidates.append(CandidateDecision(evidence_id=eid, admitted=True, reason="structured_method_or_sample_match",
                source_id=snapshot.records[eid]["source_id"], file_name=snapshot.records[eid]["file_name"],
                match=EvidenceMatch(query_id=trace.query_id, context_id=context.context_id, facets=["geometry"],
                    admission="structured", rrf_score=1 / (60 + rank), matched_terms=matched)))
        return trace

    def _select(self, snapshot: CorpusSnapshot, queries, required, fields_by_id):
        pooled = {}
        for trace in queries:
            for candidate in trace.candidates:
                if candidate.admitted:
                    pooled.setdefault(candidate.evidence_id, []).append(candidate.match)
        # Collapse exact duplicate passages on the same source/page, but never distinct rows.
        aliases, unique, canonical_ids = {}, {}, {}
        for eid in sorted(pooled):
            r = snapshot.records[eid]
            key = ((r["source_sha256"], r["sheet"], r["row"]) if r["content_kind"] == "method_row" else
                   (r["source_sha256"], r["page"], r["content_kind"], r["evidence_scope"], " ".join(r["text"].split())))
            canonical = aliases.setdefault(key, eid)
            canonical_ids[eid] = canonical
            unique.setdefault(canonical, []).extend(pooled[eid])
        def score(eid):
            return max(m.rrf_score for m in unique[eid])
        def pairs(eid):
            return {(m.context_id, f) for m in unique[eid] for f in m.facets if f in required[m.context_id]}
        def affinity(eid):
            words = set(tokens(snapshot.records[eid]["text"]))
            return max(2 * bool(words & set(_meaningful(" ".join(fields_by_id[m.context_id].get("matrix", []))))) +
                       bool(words & set(_meaningful(" ".join(fields_by_id[m.context_id].get("target", [])))))
                       for m in unique[eid])
        selected, reasons = [], {}
        def add(eid, reason):
            if eid not in selected and len(selected) < 8:
                selected.append(eid)
                reasons[eid] = [reason]
        for context_id in required:
            available = [eid for eid in unique if (context_id, "application") in pairs(eid)]
            if available:
                add(min(available, key=lambda eid: (-affinity(eid),
                    snapshot.records[eid]["evidence_scope"] != "application_example", -score(eid), eid)),
                    f"application candidate for {context_id}")
        for context_id in required:
            available = [eid for eid in unique if snapshot.records[eid]["content_kind"] == "method_row"
                         and any(m.context_id == context_id and m.admission == "structured" for m in unique[eid])]
            if available:
                for trace in queries:
                    if trace.context_id == context_id and trace.facet == "method_table":
                        for source_id in trace.source_fields.get("application_evidence_ids", []):
                            if source_id in canonical_ids:
                                add(canonical_ids[source_id], f"source passage for method lookup in {context_id}")
                add(min(available, key=lambda eid: (-max(m.rrf_score for m in unique[eid] if m.admission == "structured"), eid)),
                    f"structured method geometry for {context_id}")
        while len(selected) < 8:
            remaining = [eid for eid in unique if eid not in selected]
            if not remaining:
                break
            covered = set().union(*(pairs(eid) for eid in selected))
            selected_methods = set().union(*(_methods(snapshot.records[eid].get("method", "")) for eid in selected))
            def new_method(eid):
                return bool(_methods(snapshot.records[eid].get("method", "")) - selected_methods)
            eid = min(remaining, key=lambda eid: (-len(pairs(eid) - covered), -new_method(eid), -affinity(eid), -score(eid), eid))
            # Four is a target, never a floor; additional records must add coverage.
            if len(selected) >= 4 and not pairs(eid) - covered and not new_method(eid):
                break
            add(eid, "adds context/facet coverage" if pairs(eid) - covered else "additional admitted relevant evidence")
        entries = [LedgerEntry(evidence=snapshot.resolve(eid), score=score(eid),
            context_ids=sorted({m.context_id for m in unique[eid]}),
            facets=[f for f in FACETS if any(f in m.facets for m in unique[eid])],
            matches=unique[eid], selection_reasons=reasons[eid]) for eid in selected]
        coverage, gaps = [], []
        for context_id, facets in required.items():
            for facet in facets:
                ids = [eid for eid in selected if (context_id, facet) in pairs(eid)]
                coverage.append(EvidenceCoverage(context_id=context_id, facet=facet,
                    status="candidate_found" if ids else "gap", evidence_ids=ids))
                if not ids:
                    budget = any((context_id, facet) in pairs(eid) for eid in unique)
                    gaps.append(EvidenceGap(context_id=context_id, facet=facet,
                        reason="budget_limit" if budget else "no_relevant_evidence",
                        message="Relevant candidates exceed the eight-record budget" if budget else
                                "No admitted source evidence was found for this context/facet"))
        return entries, coverage, gaps

    def _retrieve(self, facts, snapshot, client, deadline):
        documents = read_json(snapshot.directory / "bm25.json")["documents"]
        if (len({d["evidence_id"] for d in documents}) != len(documents) or
            any(d["tokens"] != tokens(snapshot.records[d["evidence_id"]]["section"] + " " +
                                      snapshot.records[d["evidence_id"]]["text"]) for d in documents)):
            raise CorpusUnavailable("Lexical index documents differ from pinned source records")
        by_segment = {s["id"]: s for s in read_json(snapshot.directory / "segments.json")}
        queries, required, fields_by_id, statements_by_id, input_gaps = [], {}, {}, {}, []
        for context in facts.contexts:
            _check_deadline(deadline)
            fields, statements = _context_fields(context, facts)
            fields_by_id[context.context_id], statements_by_id[context.context_id] = fields, statements
            required[context.context_id] = _required_facets(fields)
            # Missing-information boilerplate alone must not invent a technical topic.
            grounded = " ".join(v for k, values in fields.items() if k != "unknowns" for v in values)
            if not _meaningful(grounded):
                input_gaps.append(EvidenceGap(context_id=context.context_id, reason="unspecified_input",
                    message="No substantive target, matrix, process, or requested method was supplied"))
                continue
            query, omitted = _compact_query(fields, self.embedder)
            trace = QueryTrace(query_id=f"initial_{context.context_id}", context_id=context.context_id,
                facet="context", round=1, query=query, source_fields=fields, statements=statements,
                omitted_terms=omitted, expanded_terms=sorted(set(query_tokens(query)) - set(tokens(query))))
            self._search(snapshot, client, trace, fields, documents, by_segment, deadline)
            queries.append(trace)
            queries.append(self._method_lookup(snapshot, context, fields, queries))
        entries, coverage, gaps = self._select(snapshot, queries, required, fields_by_id)
        retry_gap = next((g for g in gaps if g.reason == "no_relevant_evidence"
                          and any(q.context_id == g.context_id and q.facet == "context" for q in queries)), None)
        rounds = 1 if queries else 0
        if retry_gap is not None:
            context_id = retry_gap.context_id
            fields = fields_by_id[context_id]
            # Broaden by retaining target/matrix/phase but dropping incidental process wording.
            broad = {k: fields[k] for k in ("target", "matrix", "phase_appearance", "label") if k in fields}
            if not _meaningful(" ".join(v for values in broad.values() for v in values)):
                broad = fields
            query, omitted = _compact_query(broad, self.embedder, retry_gap.facet)
            trace = QueryTrace(query_id="followup", context_id=context_id, facet=retry_gap.facet, round=2,
                query=query, source_fields=broad, statements=statements_by_id[context_id], omitted_terms=omitted,
                expanded_terms=sorted(set(query_tokens(query)) - set(tokens(query))))
            self._search(snapshot, client, trace, fields, documents, by_segment, deadline)
            queries.append(trace)
            entries, coverage, gaps = self._select(snapshot, queries, required, fields_by_id)
            rounds = 2
        _check_deadline(deadline)
        return self._result(snapshot, entries, queries, coverage, input_gaps + gaps, rounds)

    def _result(self, snapshot, entries, queries, coverage, gaps, rounds):
        return RetrievalResult(corpus_version=snapshot.version, retrieval_version=RETRIEVAL_VERSION,
            semantic_min_score=self.settings.retrieval_semantic_min_score, search_rounds=rounds,
            evidence=entries, queries=queries, coverage=coverage, gaps=gaps,
            warnings=["Coverage identifies relevant candidates, not verified scientific claim support.",
                      "Semantic-only matches use a heuristic cosine threshold; inspect source text and evidence scope.",
                      "Automated source checks do not imply human verification or AFS approval."])
