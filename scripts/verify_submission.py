"""Verify the saved final batch; never generate, publish or edit answers.

Run from the repository root: python scripts/verify_submission.py
Use --portable to check only the self-contained archived artifacts.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.run_evaluation import audit_final_inputs, load_final_cases, verify_manifest
from backend.core.config import Settings


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def credential_scan():
    """Report locations only. Never print a key or matched source content."""
    from dotenv import dotenv_values

    values = dotenv_values(ROOT / ".env") if (ROOT / ".env").exists() else {}
    import os
    secret_suffixes = ("_API_KEY", "_SECRET_KEY", "_ACCESS_TOKEN")
    values.update({key: value for key, value in os.environ.items() if key.endswith(secret_suffixes)})
    secrets = {str(value).encode() for key, value in values.items()
               if key.endswith(secret_suffixes) and value and len(str(value)) >= 16
               and not str(value).lower().startswith(("your_", "test", "fake", "placeholder"))}
    names = subprocess.check_output(
        ["git", "-c", "core.fsmonitor=false", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT).decode("utf-8").split("\0")
    findings, count = [], 0
    for name in sorted(set(filter(None, names))):
        path = ROOT / name
        if not path.is_file():
            continue
        content = path.read_bytes()
        count += 1
        if any(secret in content for secret in secrets):
            findings.append({"path": name, "reason": "configured secret found"})
        # High-specificity token formats; source/tests may contain placeholders.
        for token in re.findall(rb"(?:AIza[0-9A-Za-z_-]{35}|gsk_[0-9A-Za-z]{40,}|sk-proj-[0-9A-Za-z_-]{40,}|sb_secret_[0-9A-Za-z_-]{20,})", content):
            if len(set(token)) > 12:
                findings.append({"path": name, "reason": "provider-token-shaped value; inspect privately"})
                break
        if path.name.startswith(".env") and not path.name.endswith(".example"):
            findings.append({"path": name, "reason": "environment file in submission inventory"})
        if path.suffix in {".sqlite", ".sqlite3", ".db"}:
            findings.append({"path": name, "reason": "local database in submission inventory"})
    return {"scope": "tracked and nonignored untracked files; configured key equality and selected token formats",
            "files_scanned": count, "findings": findings,
            "limitation": "Not a complete secret detector or a scan of Git history."}


def check(manifest_path, portable=False):
    manifest, errors = verify_manifest(manifest_path)
    receipt = {"checked_at": datetime.now(timezone.utc).isoformat(),
               "batch_id": manifest.get("batch_id"), "configuration_id": manifest.get("configuration_id"),
               "manifest_sha256": sha256(manifest_path), "mechanical_errors": errors,
               "scope": "saved-artifact integrity and provenance; no new model calls or scientific validation"}
    base = manifest_path.parent
    batch_manifest = base / manifest["published_from"] if "published_from" in manifest else manifest_path
    batch = json.loads(batch_manifest.read_text(encoding="utf-8"))
    supporting_errors = []
    local_pdf_derivatives = []
    for record in batch["cases"]:
        for key, name in record.items():
            if key.endswith("_path") and isinstance(name, str):
                expected = record.get(key[:-5] + "_sha256")
                if not expected:
                    continue
                target = (batch_manifest.parent / name).resolve()
                if key == "trace_pdf_path" and not target.exists():
                    local_pdf_derivatives.append({"case_id": record["case_id"], "path": name,
                                                  "sha256": expected,
                                                  "note": "Optional local PDF rendering; complete trace JSON is required and verified."})
                    continue
                if not target.is_relative_to(batch_manifest.parent.resolve()) or not target.is_file() \
                        or sha256(target) != expected:
                    supporting_errors.append(f"{record['case_id']}: supporting artifact mismatch: {key}")
    receipt["supporting_artifact_errors"] = supporting_errors
    receipt["optional_local_pdf_derivatives"] = local_pdf_derivatives
    errors += supporting_errors
    receipt["verifier_sha256"] = sha256(Path(__file__))
    receipt["cases"] = [{key: record.get(key) for key in (
        "case_id", "http_status", "run_status", "decision_status", "run_id", "enquiry_id",
        "input_sha256", "output_sha256", "stage_providers", "returned_models", "repair_counts")}
        for record in batch["cases"]]
    receipt["frozen_settings"] = batch["settings"]
    receipt["implementation"] = batch["implementation"]
    receipt["archived_case_audit"] = batch["case_audit"]
    if not portable:
        source, cases = load_final_cases()
        receipt["original_input_check"] = {"status": "passed", "source_sha256": source["source_sha256"],
                                            "case_ids": [case["case_id"] for case in cases]}
        drift = [name for name, expected in batch["configuration"]["source_sha256"].items()
                 if not (ROOT / name).is_file() or sha256(ROOT / name) != expected]
        receipt["captured_source_drift"] = drift
        # Fresh-install packaging correction only: the archived answer environment
        # already had 16.1.1. Never accept a different runtime source as this batch.
        original_requirements = batch_manifest.parent / "source_snapshot/requirements.txt"
        packaging_only = (drift == ["requirements.txt"] and
            (ROOT / "requirements.txt").read_bytes() == original_requirements.read_bytes().replace(
                b"websockets==17.2", b"websockets==16.1.1"))
        receipt["setup_dependency_correction"] = {
            "status": "documented" if packaging_only else "not_applicable",
            "note": "Archived requirements pin 17.2 conflicts with google-genai; setup pins 16.1.1, the version installed when checked. Archived files and answers remain unchanged.",
            "current_requirements_sha256": sha256(ROOT / "requirements.txt"),
            "archived_requirements_sha256": sha256(original_requirements)}
        receipt["runtime_case_audit"] = audit_final_inputs(cases, Settings())
        receipt["credential_scan"] = credential_scan()
        # The copy excludes every database and includes no separately supplied originals
        # or live indexes. Verification is also run with HTTP and SQLite disabled.
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="f09-portable-", dir=ROOT / "tmp") as temp:
            destination = Path(temp) / "submission"
            archived = destination / "runs" / batch_manifest.parent.name
            shutil.copytree(batch_manifest.parent, archived,
                            ignore=shutil.ignore_patterns("*.sqlite*", "*.db", "*.log"))
            if "published_from" in manifest:
                shutil.copy2(manifest_path, destination / "run_manifest.json")
                for record in batch["cases"]:
                    shutil.copy2(base / f"{record['case_id']}.json", destination / f"{record['case_id']}.json")
                portable_manifest = destination / "run_manifest.json"
            else:
                portable_manifest = archived / "manifest.json"
            with patch("sqlite3.connect", side_effect=AssertionError("SQLite forbidden")), \
                 patch("httpx.Client.send", side_effect=AssertionError("HTTP forbidden")), \
                 patch("httpx.AsyncClient.send", side_effect=AssertionError("HTTP forbidden")):
                _, portable_errors = verify_manifest(portable_manifest)
            receipt["portable_verification"] = {"errors": portable_errors, "sqlite_and_http_disabled": True,
                                                "originals_and_live_indexes_in_copy": False}
        errors += portable_errors
        if drift and not packaging_only:
            errors.append("Current captured execution files differ from the saved batch")
        if receipt["credential_scan"]["findings"]:
            errors.append("Submission credential/inventory scan has findings")
    receipt["status"] = "passed" if not errors else "failed"
    receipt["errors"] = errors
    receipt["scientific_review"] = {"status": "known_content_failures",
        "review": "docs/quality.md#historical-results", "implementation_review": "docs/quality.md#known-limitations",
        "note": "Complete envelopes do not establish adequate answers, entailment or spectroscopy performance."}
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "outputs/run_manifest.json")
    parser.add_argument("--portable", action="store_true", help="Skip current inputs/runtime/credential inventory checks")
    parser.add_argument("--receipt", type=Path, help="Write a separate receipt; archived files are never changed")
    args = parser.parse_args()
    try:
        result = check(args.manifest.resolve(), args.portable)
    except (OSError, ValueError, KeyError, AssertionError) as error:
        # Error values from credential scanning are deliberately never emitted.
        result = {"status": "failed", "error_type": type(error).__name__}
    if args.receipt:
        destination = args.receipt.resolve()
        # Receipts must stay outside canonical answers and immutable batch directories.
        if destination == args.manifest.resolve() or destination == ROOT / "outputs/run_manifest.json" \
                or destination == ROOT / "evaluation/final.json" \
                or destination.is_relative_to(ROOT / "outputs/runs") \
                or re.fullmatch(r"H0[1-6]\.json", destination.name):
            parser.error("Receipt path would overwrite protected evaluation material")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result.get(key) for key in ("status", "batch_id", "errors", "error_type")
                      if key in result}, indent=2))
    return int(result["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
