"""Offline operational search checks; no provider initialization or downloads."""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from backend.core.config import Settings, PROJECT_ROOT
from backend.services.search.search_service import SearchService, SearchUnavailable

def run(settings, statements):
    service = SearchService(settings)
    checks = []
    for statement in statements:
        for mode in ("bm25", "qdrant", "hybrid"):
            item = {"statement": statement, "mode": mode, "passed": False}
            try:
                result = service.compare(statement, mode=mode, dataset="technical", limit=6)
                hits = result["rankings"][mode]
                ids = [h["evidence"]["evidence_id"] for h in hits]
                valid = bool(hits) and len(ids) == len(set(ids)) and len(hits) <= 6
                valid = valid and result["model_calls"] == 0 and bool(result["versions"])
                valid = valid and all(h["rank"] == i and math.isfinite(h["score"]) and h["evidence"]["source_id"] for i,h in enumerate(hits,1))
                item.update(passed=bool(valid), result=result)
            except (OSError, ValueError, RuntimeError, KeyError, SearchUnavailable) as error:
                item["error"] = type(error).__name__ + ": " + str(error)
            checks.append(item)
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "model_calls": 0, "passed": bool(checks) and all(c["passed"] for c in checks), "checks": checks, "limitation": "Operational checks do not establish source relevance or scientific correctness."}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("search_cases.json"))
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT/"outputs"/"search_smoke")
    args = parser.parse_args()
    statements = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(statements,list) or not statements or any(not isinstance(s,str) or not s.strip() for s in statements):
        parser.error("Input must be a nonempty JSON array of statements")
    report = run(Settings(), statements)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".json")
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"{sum(c['passed'] for c in report['checks'])}/{len(report['checks'])} passed; {path}")
    return 0 if report["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
