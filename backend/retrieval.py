"""Local dense retrieval plus lexical BM25, fused at evidence-record level."""

import importlib.metadata
import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from rank_bm25 import BM25Okapi

from backend.knowledge_store import active_directory, digest, file_hash, load_records, read_json, validate_corpus, write_json

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
COLLECTION = "afs_evidence"
# Domain synonyms, independent of any development or final scenario.
SYNONYMS = {"mir": ["mid", "infrared", "ftir"], "ftir": ["mir", "infrared"],
            "nir": ["near", "infrared"], "atr": ["attenuated", "total", "reflection"],
            "api": ["active", "pharmaceutical", "ingredient"], "fluo": ["fluorescence", "fluorimetry"],
            "fluorescence": ["fluorimetry"], "moisture": ["water"], "water": ["moisture"]}


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


def make_segments(records: list[dict], count) -> list[dict]:
    segments = []
    for record in records:
        if not record["retrieval_eligible"]:
            continue
        heading = record["section"].strip()
        prefix = heading + "\n" if heading else ""
        # Sentence/paragraph boundaries preserve quantities and qualifiers together.
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n\s*\n", record["text"])
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


def build_indexes(directory: Path, records: list[dict], version: str, embedder: Embedder):
    from qdrant_client import QdrantClient, models

    segments = make_segments(records, embedder.count)
    if not segments:
        raise ValueError("No eligible evidence to index")
    vectors = embedder.vectors([s["text"] for s in segments])
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
        {"evidence_id": r["evidence_id"], "tokens": tokens(r["section"] + " " + r["text"])} for r in eligible]})
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
