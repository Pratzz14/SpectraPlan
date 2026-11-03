"""Synthetic corpus fixtures; never copied into the application's knowledge directory."""

from pathlib import Path

from backend.services.knowledge.knowledge_store import digest, file_hash, write_json
from backend.services.search.retrieval import build_indexes


class FakeEmbedder:
    fingerprint = "synthetic-test-embedding"
    artifacts = {"test": "synthetic"}

    @staticmethod
    def count(text):
        return len(text.split()) + 2

    @staticmethod
    def vectors(texts, **kwargs):
        return [[1.0, *([0.0] * 383)] for _ in texts]


def make_corpus(directory: Path, *, eligible=True, revision="content-v1"):
    directory.mkdir(parents=True, exist_ok=True)
    sources = [{"source_id": "S01", "file_name": "test.pdf", "sha256": "a" * 64, "page_count": 6, "technical_eligible": True},
               {"source_id": "T01", "file_name": "test.xlsx", "sha256": "b" * 64, "page_count": None, "technical_eligible": True}]
    raw_pages = [{"source_id": "S01", "page": i, "blocks": [{"block_id": "b001", "text": "Synthetic powder Raman evidence.", "bbox": [0, 0, 1, 1]}],
                  "image": f"assets/p{i}.jpg", "image_sha256": digest(b"test image"), "width": 1, "height": 1} for i in range(1, 7)]
    for page in raw_pages:
        path = directory / page["image"]
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"test image")
    common = {"revision": revision, "section": "Synthetic test", "validation_status": "passed", "human_review_status": "not_reviewed",
              "retrieval_eligible": eligible, "issues": [], "evidence_scope": "general_method"}
    passage = {**common, "evidence_id": "S01:p006:test", "source_id": "S01", "file_name": "test.pdf", "source_sha256": "a" * 64,
               "page": 6, "text": "Synthetic powder Raman evidence.", "content_kind": "verbatim_text",
               "verification": {"status": "supported", "reason": "Synthetic test source"}, "source_spans": [
                   {"block_id": "b001", "quote": "Synthetic powder Raman evidence.", "start": 0, "end": len("Synthetic powder Raman evidence."), "bbox": [0, 0, 1, 1]}]}
    methods = [{**common, "evidence_id": f"T01:method_comparison:r{i:03}", "source_id": "T01", "file_name": "test.xlsx",
                "source_sha256": "b" * 64, "page": 6, "sheet": "method_comparison", "row": i, "method": "Raman", "geometry": f"test geometry {i}",
                "content_kind": "method_row", "text": f"Synthetic Raman method geometry {i}.", "raw_values": {
                    "method_no": 3, "method": "Raman", "measurement_technique": f"test geometry {i}", "physical_phenomenon": "scattering",
                    "sample_type": "powder", "optical_path_or_depth": "2-5 mm", "sensitivity": "average", "selectivity": "high", "cost": "high"},
                "underlying_citation": {"source_id": "S01", "page": 6, "table": "Table 1", "sha256": "a" * 64}} for i in range(2, 21)]
    # Build a valid index even for an all-ineligible fixture, then let membership validation catch it.
    build_indexes(directory, [passage, *methods] if eligible else [{**passage, "retrieval_eligible": True}], "corpus-v1", FakeEmbedder())
    write_json(directory / "raw_pages.json", raw_pages)
    write_json(directory / "method_notes.json", [{"source_id": "T01", "sheet": "notes", "row": i, "text": f"Synthetic note {i}"} for i in range(1, 8)])
    write_json(directory / "methods.json", methods)
    import json
    (directory / "passages.jsonl").write_text(json.dumps(passage) + "\n", encoding="utf-8")
    manifest = {"corpus_version": "corpus-v1", "sources": sources, "coverage": [{"source_id": "S01", "page": i} for i in range(1, 7)],
                "artifacts": {name: file_hash(directory / name) for name in ["passages.jsonl", "methods.json", "method_notes.json", "raw_pages.json", "index_manifest.json", "segments.json", "bm25.json"]}}
    write_json(directory / "source_manifest.json", manifest)
    return manifest, passage, methods


def rehash(directory: Path):
    from backend.services.knowledge.knowledge_store import read_json
    manifest = read_json(directory / "source_manifest.json")
    manifest["artifacts"] = {name: file_hash(directory / name) for name in manifest["artifacts"]}
    write_json(directory / "source_manifest.json", manifest)
