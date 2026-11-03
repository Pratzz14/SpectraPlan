import asyncio
import json
from types import SimpleNamespace
import pytest
import zipfile

import openpyxl
import pymupdf

from backend.core.config import Settings
from backend.pipelines.document_comparison.pipeline import GeminiExtractionError, compare_original_extraction, extract_with_gemini
from backend.services.knowledge.knowledge_store import extract_original_documents


def make_docx(path):
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:t>Water content is measured.</w:t></w:r></w:p></w:body>
    </w:document>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


class FakeInteractions:
    async def create(self, **kwargs):
        assert kwargs["model"] == "gemini-3.8-flash"
        assert kwargs["generation_config"]["thinking_level"] == "medium"
        assert kwargs["response_format"]["mime_type"] == "application/json"
        assert kwargs["store"] is False
        text = kwargs["input"][0]["text"]
        document = json.loads(text.split("\n\n", 1)[1])
        return {"output_text": json.dumps({"source_id": document["source_id"],
                "claims": ["Water content is measured."], "facts": [], "unknowns": [],
                "source_locations": [document["blocks"][0]["location"]]}), "status":"completed"}


class FakeClient:
    aio = SimpleNamespace(interactions=FakeInteractions())


def test_original_docx_extraction_preserves_locations(tmp_path):
    path = tmp_path / "sample.docx"
    make_docx(path)
    documents = extract_original_documents(tmp_path, [{
        "source_id": "D01_DOC", "file_name": path.name, "sha256": "a" * 64, "role": "development"
    }])
    assert documents[0]["format"] == "docx"
    assert documents[0]["blocks"][0]["text"] == "Water content is measured."
    assert documents[0]["blocks"][0]["location"] == "paragraph:1"


def test_original_pdf_and_xlsx_extraction_preserves_locations(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((40, 60), "Water content")
    pdf.save(pdf_path)
    pdf.close()
    xlsx_path = tmp_path / "sample.xlsx"
    book = openpyxl.Workbook()
    book.active.title = "Results"
    book.active.append(["Analyte", "Value"])
    book.active.append(["Water", "0.2 %"])
    book.save(xlsx_path)
    documents = extract_original_documents(tmp_path, [
        {"source_id": "S01", "file_name": pdf_path.name, "sha256": "a" * 64, "role": "technical"},
        {"source_id": "T01", "file_name": xlsx_path.name, "sha256": "b" * 64, "role": "method_table"},
    ])
    assert documents[0]["blocks"][0]["location"] == "page:1"
    assert documents[1]["blocks"][1]["location"] == "sheet:Results!2"
    assert documents[1]["blocks"][1]["text"] == "Water\t0.2 %"
    assert "ReadOnlyCell" not in str(documents[1])


def test_gemini_structured_output_is_validated(tmp_path):
    path = tmp_path / "sample.docx"
    make_docx(path)
    document = extract_original_documents(tmp_path, [{
        "source_id": "D01_DOC", "file_name": path.name, "sha256": "a" * 64, "role": "development"
    }])[0]
    settings = Settings(_env_file=None, gemini_api_key="test")
    result = asyncio.run(extract_with_gemini(document, settings, client=FakeClient()))
    assert result.source_id == "D01_DOC"
    assert result.source_locations == ["paragraph:1"]


def test_comparison_keeps_baseline_and_gemini_results(monkeypatch, tmp_path):
    document = {"source_id": "S01", "file_name": "source.pdf", "format": "pdf",
                "blocks": [{"location": "page:1", "text": "Water"}]}
    monkeypatch.setattr("backend.pipelines.document_comparison.pipeline.inventory", lambda _: [])
    monkeypatch.setattr("backend.pipelines.document_comparison.pipeline.extract_original_documents", lambda *_: [document])
    settings = Settings(_env_file=None, gemini_api_key="test")
    result = asyncio.run(compare_original_extraction(settings, client=FakeClient()))
    assert result["source_count"] == 1
    assert result["results"][0]["baseline"]["facts"] == ["Water"]
    assert result["results"][0]["gemini"]["claims"] == ["Water content is measured."]
    assert result["succeeded"] == 1 and result["errors"] == 0
    with pytest.raises(ValueError, match="Unknown"):
        asyncio.run(compare_original_extraction(settings, client=FakeClient(), source_ids={"UNKNOWN"}))


@pytest.mark.parametrize("source,location",[("WRONG","page:1"),("S01","page:999")])
def test_unknown_source_or_location_is_not_a_success(source,location):
    class Bad(FakeInteractions):
        async def create(self, **kwargs):
            return {"output_text":json.dumps({"source_id":source,"claims":[],"facts":[],"unknowns":[],"source_locations":[location]})}
    client=SimpleNamespace(aio=SimpleNamespace(interactions=Bad()))
    document={"source_id":"S01","file_name":"source.pdf","format":"pdf","blocks":[{"location":"page:1","text":"Water"}]}
    with pytest.raises(GeminiExtractionError, match="unknown source"):
        asyncio.run(extract_with_gemini(document,Settings(_env_file=None,gemini_api_key="test"),client=client))


def test_comparison_endpoint_rejects_stale_or_malformed_artifacts(monkeypatch,tmp_path):
    import httpx
    from backend.main import create_app
    from backend.services.knowledge.knowledge_store import write_json
    settings=Settings(_env_file=None,smoke_output_dir=tmp_path)
    monkeypatch.setattr("backend.api.routers.knowledge.inventory",lambda _:[{"source_id":"S01","sha256":"a"*64}])
    app=create_app(settings)
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            return await client.get("/api/knowledge/gemini-comparison")
    path=tmp_path/"gemini_complete_comparison.json"
    payload={"model":settings.gemini_model,"source_count":1,"succeeded":1,"errors":0,"results":[{"source_id":"S01"}]}
    write_json(path,payload);assert asyncio.run(request()).status_code == 404
    payload["results"][0]["source_sha256"]="a"*64
    write_json(path,payload);assert asyncio.run(request()).status_code == 200
    payload["results"]=[None]
    write_json(path,payload);assert asyncio.run(request()).status_code == 404


@pytest.mark.parametrize("errors",[0,1])
def test_comparison_command_publishes_canonical_artifact_and_signals_failure(monkeypatch,tmp_path,errors):
    from backend.cli import smoke_gemini_extraction as command
    async def compare(*args,**kwargs):
        return {"errors":errors,"succeeded":1-errors,"results":[]}
    monkeypatch.setattr(command,"Settings",lambda:Settings(_env_file=None,smoke_output_dir=tmp_path))
    monkeypatch.setattr(command,"compare_original_extraction",compare)
    monkeypatch.setattr("sys.argv",["comparison"])
    assert asyncio.run(command.main()) == int(bool(errors))
    assert json.loads((tmp_path/"gemini_complete_comparison.json").read_text(encoding="utf-8"))["errors"] == errors
