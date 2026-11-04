import pymupdf
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.services.history.explainability import ExplainabilityStore
from tests.auth_helpers import create_app


def test_saved_pdf_download_is_paginated_and_preserves_trace(tmp_path):
    settings = Settings(explainability_db_path=tmp_path / "history.sqlite")
    store = ExplainabilityStore(settings.explainability_db_path)
    identity = store.begin("Water < 2% in an échantillon", [
        {"question": "Required accuracy?", "context": "stream", "answer": "0.1%"}])
    for index in range(20):
        store.append(identity["run_id"], {"stage": "retrieval", "event_type": "search",
            "payload": {"query": f"moisture {index}", "source": "source.pdf", "output": "Evidence " * 60}})
    store.finish(identity["run_id"], {"run_status": "incomplete", "errors": [{"message": "No assessment"}]})
    client = TestClient(create_app(settings))
    response = client.get(f"/api/assess/{identity['run_id']}/report.pdf?audience=trace")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    with pymupdf.open(stream=response.content, filetype="pdf") as document:
        assert len(document) > 1
        text = "".join(page.get_text() for page in document)
        for expected in ["Water < 2%", "échantillon", "Required accuracy?", "0.1%", "moisture 19", "source.pdf", "incomplete"]:
            assert expected in text
        assert f"Page {len(document)} of {len(document)}" in document[-1].get_text()
    assert len(store.list_enquiries()) == 1
    assert client.get('/api/assess/' + 'f' * 32 + '/report.pdf').status_code == 404
    assert client.get('/api/assess/invalid/report.pdf').status_code == 422


def test_default_pdf_is_for_chemist_and_excludes_diagnostics(tmp_path):
    settings = Settings(explainability_db_path=tmp_path / 'history.sqlite')
    store = ExplainabilityStore(settings.explainability_db_path)
    identity = store.begin('Measure water in a powder.', [])
    store.append(identity['run_id'], {'stage': 'retrieval', 'event_type': 'search',
                                     'payload': {'query': 'BM25 secret diagnostic'}})
    store.finish(identity['run_id'], {'run_status': 'complete', 'metadata': {'model': 'private-model'},
        'retrieval': {'evidence': [{'evidence': {'evidence_id': 'source-1',
                       'text': 'NIR source excerpt.', 'workbook_notes': None}}]},
        'assessment': {'decision_status': 'insufficient_information',
            'source_index': [{'evidence_id': 'source-1', 'citation': 'S01, page 6'}],
            'case_summary': 'The target accuracy must be agreed.', 'decision_reason': 'A reference assay is needed.',
            'requirements': {'unknowns': ['Required error']}, 'recommendations': [], 'clarification_questions': [],
            'experiment': {'objective': 'Compare against a reference assay.',
                           'decision_criteria': 'Agree acceptance criteria.'}}})
    response = TestClient(create_app(settings)).get(f"/api/assess/{identity['run_id']}/report.pdf")
    assert response.status_code == 200
    with pymupdf.open(stream=response.content, filetype='pdf') as document:
        text = ''.join(page.get_text() for page in document)
    for expected in ['Measure water', 'target accuracy', 'reference assay', 'Go / no-go', 'S01, page 6', 'NIR source excerpt.']:
        assert expected in text
    for excluded in ['BM25', 'private-model', 'Chronological', 'Run:', identity['run_id']]:
        assert excluded not in text
