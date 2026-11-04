"""History endpoints use the real assessment pipeline with synthetic model responses."""

import asyncio
import json

import httpx

from tests.auth_helpers import create_app
from backend.services.history.explainability import ExplainabilityStore
from tests.test_assessment import draft, ledger
from tests.test_assessment_api import mock_retrieval, provider_for
from tests.test_extraction import powder, wire_for


def test_analysis_and_clarification_share_history_and_server_composes_input(monkeypatch):
    text="A powder; measure moisture."
    data=draft(empty=True)
    adapter,calls=provider_for([wire_for(powder(text).model_dump()),data])
    mock_retrieval(monkeypatch,ledger(empty=True))
    monkeypatch.setattr("backend.pipelines.assessment.pipeline.Provider",lambda _:adapter)
    app=create_app(adapter.settings)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
            first=await client.post("/api/assess",json={"description":text})
            assert first.status_code == 200
            result=first.json();identity=result["metadata"]
            assert result["metadata"]["provider_trace"] == []
            trace=(await client.get(f"/api/assess/{identity['run_id']}/explainability")).json()
            types=[e["event_type"] for e in trace["events"]]
            assert types.index("provider_response") < types.index("validated_stage")
            assert types[0] == "run_started" and types[-1] == "run_finished"
            assert identity["question_ids"] == [q["question_id"] for q in trace["questions"]]
            enquiry=(await client.get(f"/api/enquiries/{identity['enquiry_id']}")).json()
            assert enquiry["original_description"] == text and len(enquiry["runs"]) == 1
            assert len((await client.get("/api/enquiries")).json()) == 1
            assert (await client.get("/api/enquiries?limit=0")).status_code == 422
            assert (await client.get("/api/enquiries/invalid")).status_code == 422
            assert (await client.get('/api/enquiries/'+'f'*32)).status_code == 404
            # A failing next extraction still persists its input and parent link.
            failing,_=provider_for(["invalid","invalid"])
            monkeypatch.setattr("backend.pipelines.assessment.pipeline.Provider",lambda _:failing)
            q=trace["questions"][0]
            body={"description":text,"enquiry_id":identity["enquiry_id"],"parent_run_id":identity["run_id"],
                  "clarification_answers":[{"question":q["question"],"question_id":q["question_id"],
                    "origin_run_id":identity["run_id"],"context":"customer supplied label","answer":"1%"}]}
            second=await client.post("/api/assess",json=body)
            assert second.status_code == 502
            saved=(await client.get(f"/api/assess/{second.json()['metadata']['run_id']}/explainability")).json()
            assert "Answer: 1%" in saved["description"]
            assert saved["round_no"] == 2 and saved["parent_run_id"] == identity["run_id"]
            assert sum(e["event_type"] == "provider_response" for e in saved["events"]) == 2
    asyncio.run(run())


def test_storage_failure_prevents_unlogged_provider_work(monkeypatch):
    adapter,calls=provider_for([])
    monkeypatch.setattr("backend.pipelines.assessment.pipeline.Provider",lambda _:adapter)
    def unavailable(*args,**kwargs):
        raise OSError("disk unavailable")
    monkeypatch.setattr(ExplainabilityStore,"begin",unavailable)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(adapter.settings)),base_url="http://test") as c:
            response=await c.post("/api/assess",json={"description":"A sample"})
            assert response.status_code == 503 and calls == []
    asyncio.run(run())


def test_restored_clarification_labels_obey_length_limit_before_saving(monkeypatch):
    from backend.core.config import Settings
    from backend.services.history.explainability import question_id
    from fastapi.testclient import TestClient

    app = create_app(Settings(_env_file=None, assessment_max_description_chars=140))
    store = app.state.explainability_store
    parent = store.begin("A sample", [])
    question = {"question": "What precision?", "context_ids": ["stream_1"]}
    store.finish(parent["run_id"], {
        "run_status": "complete",
        "facts": {"contexts": [{"context_id": "stream_1", "label": "long sample label " * 20}]},
        "assessment": {"clarification_questions": [question]},
    })
    calls = []

    async def unexpected_assessment(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Oversized input must not start an assessment")

    monkeypatch.setattr("backend.api.routers.assessment.assess_case", unexpected_assessment)
    response = TestClient(app).post("/api/assess", json={
        "description": "A sample", "enquiry_id": parent["enquiry_id"],
        "parent_run_id": parent["run_id"], "clarification_answers": [{
            "question": question["question"], "context": "x", "answer": "1%",
            "origin_run_id": parent["run_id"], "question_id": question_id(parent["run_id"], question),
        }],
    })
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "description_too_long"
    assert calls == []
    assert len(store.enquiry(parent["enquiry_id"])["runs"]) == 1
