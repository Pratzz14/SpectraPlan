"""Resolve evidence from a validated, pinned technical corpus, never a caller path."""

import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, quote

from backend.schemas.knowledge_models import Evidence
from backend.services.knowledge.knowledge_store import active_directory, inside, load_records, read_json, validate_corpus


class CorpusUnavailable(Exception):
    pass


class EvidenceNotFound(Exception):
    pass


class EvidenceRevisionMismatch(Exception):
    pass


class ResolvedEvidence(Evidence):
    corpus_version: str
    evidence_url: str
    workbook_notes: list[dict] | None = None


@dataclass
class CorpusSnapshot:
    directory: Path
    version: str
    records: dict[str, dict]
    notes: list[dict]

    def resolve(self, evidence_id: str, revision: str | None = None) -> ResolvedEvidence:
        record = self.records.get(evidence_id)
        if record is None:
            raise EvidenceNotFound("Unknown or excluded technical evidence")
        if revision is not None and revision != record["revision"]:
            raise EvidenceRevisionMismatch("Evidence revision does not match the requested corpus")
        result = deepcopy(record)
        result.update(corpus_version=self.version, evidence_url=(
            f"/api/evidence/{quote(evidence_id, safe='')}?" + urlencode({
                "corpus_version": self.version, "revision": record["revision"]})))
        if record["content_kind"] == "method_row":
            result["workbook_notes"] = deepcopy(self.notes)
        return ResolvedEvidence.model_validate(result)


def load_snapshot(root: Path, corpus_version: str | None = None) -> CorpusSnapshot:
    if corpus_version is not None and not re.fullmatch(r"corpus-[a-f0-9]{20}", corpus_version):
        raise EvidenceNotFound("Unknown corpus version")
    try:
        directory = (inside(root, f"versions/{corpus_version}") if corpus_version else active_directory(root))
        if corpus_version is not None and not directory.exists():
            raise EvidenceNotFound("Unknown corpus version")
        validate_corpus(directory)
        manifest, passages, methods = load_records(directory)
        if corpus_version is not None and manifest["corpus_version"] != corpus_version:
            raise ValueError("Pinned corpus version mismatch")
        return CorpusSnapshot(directory, manifest["corpus_version"], {
            r["evidence_id"]: r for r in passages + methods if r["retrieval_eligible"]
        }, read_json(directory / "method_notes.json"))
    except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration):
        raise CorpusUnavailable("Technical corpus or indexes are unavailable or failed validation") from None
