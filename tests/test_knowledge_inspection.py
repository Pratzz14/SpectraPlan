"""Read-only inspection transport; scientific eligibility is retained, not reassessed."""
import asyncio
import json

import httpx
import pytest

from backend.core.config import Settings
from backend.services.knowledge.knowledge_store import write_json
from backend.main import create_app


def request(root):
    async def run():
        app = create_app(Settings(_env_file=None, corpus_dir=root))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/api/knowledge/inspection")
    return asyncio.run(run())


def test_inspection_retains_excluded_records_review_labels_and_pinned_artifacts(tmp_path):
    version = "corpus-" + "a" * 20
    directory = tmp_path / "versions" / version
    directory.mkdir(parents=True)
    record = {"evidence_id": "S01:p1:test", "text": "</script><script>untrusted</script>",
              "validation_status": "flagged", "human_review_status": "not_reviewed", "retrieval_eligible": False}
    write_json(directory / "source_manifest.json", {"corpus_version": version, "sources": [], "coverage": []})
    (directory / "passages.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    write_json(directory / "methods.json", [])
    write_json(directory / "method_notes.json", [{"sheet": "notes", "row": 1, "text": "Original workbook note"}])
    write_json(directory / "raw_pages.json", [{"source_id": "S01", "page": 1, "image": "assets/p1.jpg"}])
    write_json(tmp_path / "current.json", {"directory": f"versions/{version}", "corpus_version": version})
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    response = request(tmp_path)
    assert response.status_code == 200
    data = response.json()
    assert data["records"] == [record]
    assert data["artifact_base"] == f"/api/knowledge/versions/{version}/"
    assert data["notes"][0]["text"] == "Original workbook note"
    assert data["pages"][0]["image"] == "assets/p1.jpg"
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


@pytest.mark.parametrize("pointer", [None, {"directory": "../../outside", "corpus_version": "unpublished"}])
def test_missing_or_invalid_published_corpus_returns_actionable_503(tmp_path, pointer):
    if pointer:
        write_json(tmp_path / "current.json", pointer)
    response = request(tmp_path)
    assert response.status_code == 503
    assert "workspace status" in response.json()["detail"]
