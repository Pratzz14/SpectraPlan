"""Offline development inspection using accepted, hash-pinned F03 facts; no provider calls."""

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.core.config import PROJECT_ROOT, Settings
from backend.services.knowledge.knowledge_store import digest, file_hash, write_json
from backend.schemas.models import CaseFacts, MeasurementContext
from backend.services.search.retrieval import CaseRetrievalService


def run_smoke(settings: Settings) -> dict:
    review_path = PROJECT_ROOT / "outputs/extraction/review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    service = CaseRetrievalService(settings)
    cases = []
    for item in review["cases"]:
        path = review_path.parent / item["record"]
        if path.parent.resolve() != review_path.parent.resolve() or file_hash(path) != item["record_sha256"]:
            raise ValueError("Accepted F03 output is missing or changed")
        saved = json.loads(path.read_text(encoding="utf-8"))
        original = next(c for c in saved["cases"] if c["case_id"] == item["case_id"])
        facts = CaseFacts.model_validate(original["facts"])
        result = service.retrieve_case(facts)
        snapshot_evidence = [e.evidence.model_dump() for e in result.evidence]
        cases.append({"case_id": item["case_id"], "input_facts_sha256": digest(facts.model_dump()),
                      "extraction_record": item["record"], "extraction_record_sha256": item["record_sha256"],
                      "retrieval": result.model_dump(), "resolved_evidence_sha256": digest(snapshot_evidence)})
    unsupported = CaseFacts(contexts=[MeasurementContext(context_id="stream_1", label="unfindablezzzz",
                                                        target_analytes=["unfindablezzzz"])])
    cases.append({"case_id": "unsupported_target", "input_facts_sha256": digest(unsupported.model_dump()),
                  "retrieval": service.retrieve_case(unsupported).model_dump()})
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "retrieval_code_sha256": file_hash(PROJECT_ROOT / "backend/services/search/retrieval.py"),
            "validation_kind": "local_real_corpus_retrieval; no provider calls",
            "review_status": "pending_source_relevance_inspection", "cases": cases,
            "limitations": ["Candidate relevance and automated provenance do not prove scientific claim support.",
                            "Cosine threshold is a project heuristic, not a calibrated probability."]}


def main():
    result = run_smoke(Settings(_env_file=None))
    output = PROJECT_ROOT / "outputs/retrieval" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    write_json(output, result)
    print(output)
    for case in result["cases"]:
        r = case["retrieval"]
        print(f"{case['case_id']}: {len(r['evidence'])} records; {len(r['gaps'])} gaps; {r['search_rounds']} rounds")


if __name__ == "__main__":
    main()
