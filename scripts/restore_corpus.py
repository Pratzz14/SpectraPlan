"""Restore local images, report and indexes from the saved canonical evidence.

Requires separately supplied originals. No model extraction is performed.
Publishes a NEW corpus identity and preserves evidence IDs/revisions and old runs.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings
from backend.knowledge_report import render_report
from backend.knowledge_store import (active_directory, extract_pages, file_hash, load_records,
                                     publish, validate_corpus, write_json)
from backend.retrieval import Embedder, build_indexes


def restore(settings, canonical, *, local_model_only=False):
    original, passages, methods = load_records(canonical)
    for name in ("passages.jsonl", "methods.json", "method_notes.json"):
        if file_hash(canonical / name) != original["artifacts"][name]:
            raise ValueError(f"Saved evidence checksum mismatch: {name}")
    for source in original["sources"]:
        if file_hash(settings.source_dir / source["file_name"]) != source["sha256"]:
            raise ValueError(f"Original source differs: {source['file_name']}")
    staged = settings.corpus_dir / ".staging" / ("restore-" + uuid4().hex)
    staged.mkdir(parents=True)
    for name in ("passages.jsonl", "methods.json", "method_notes.json"):
        shutil.copyfile(canonical / name, staged / name)
    print("Rendering source PDF pages...", flush=True)
    pages = extract_pages(settings.source_dir, original["sources"], staged)
    write_json(staged / "raw_pages.json", pages)
    # A restored local vector database has its own binary hashes. Never relabel it
    # as the original final-evaluation index or overwrite the old generation.
    manifest = deepcopy(original)
    manifest["corpus_version"] = "corpus-" + uuid4().hex[:20]
    manifest["restoration"] = {"from_corpus": original["corpus_version"],
        "from_manifest_sha256": file_hash(canonical / "source_manifest.json"),
        "restored_at": datetime.now(timezone.utc).isoformat(), "model_calls": 0,
        "method": "saved canonical evidence; original PDF rendering; local reindex",
        "script_sha256": file_hash(Path(__file__))}
    print("Rebuilding local BGE/Qdrant/BM25 indexes...", flush=True)
    embedder = Embedder(settings.embedding_cache_dir, local_only=local_model_only)
    build_indexes(staged, passages + methods, manifest["corpus_version"], embedder)
    manifest["artifacts"] = {}
    write_json(staged / "source_manifest.json", manifest)
    render_report(staged)
    names = ("passages.jsonl", "methods.json", "method_notes.json", "raw_pages.json",
             "segments.json", "bm25.json", "index_manifest.json", "review.html")
    manifest["artifacts"] = {name: file_hash(staged / name) for name in names}
    write_json(staged / "source_manifest.json", manifest)
    print("Checking source, artifact and index integrity...", flush=True)
    validation = validate_corpus(staged, source_dir=settings.source_dir, deep=True)
    write_json(staged / "validation_report.json", validation)
    manifest["artifacts"]["validation_report.json"] = file_hash(staged / "validation_report.json")
    write_json(staged / "source_manifest.json", manifest)
    final = publish(settings.corpus_dir, staged, manifest)
    return final, validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-generation", type=Path,
                        help="Saved generation directory; defaults to the configured active generation")
    parser.add_argument("--local-model-only", action="store_true",
                        help="Require an existing matching embedding cache; do not download model files")
    args = parser.parse_args()
    settings = Settings()
    try:
        canonical = args.from_generation.resolve() if args.from_generation else active_directory(settings.corpus_dir)
        directory, validation = restore(settings, canonical, local_model_only=args.local_model_only)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Restore failed ({type(error).__name__}): {error}\n")
    import json
    print(json.dumps({"directory": str(directory), "validation": validation, "model_calls": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
