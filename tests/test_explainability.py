import json
import sqlite3

import pytest

from backend.services.history.explainability import ExplainabilityStore, HistoryConflict, question_id


def test_explainability_store_round_trips_full_trace(tmp_path):
    store = ExplainabilityStore(tmp_path / "traces.sqlite")
    run = {
        "run_status": "complete",
        "metadata": {"run_id": "a" * 32, "provider_trace": [{"raw_content": '{"ok": true}'}]},
        "retrieval": {"queries": [{"query": "moisture powder", "candidates": [
            {"match": {"bm25_score": 2.1, "cosine_score": 0.8, "rrf_score": 0.03}}
        ]}]},
    }
    events = [{"stage": "retrieval", "event_type": "validated_stage",
               "payload": {"selected_file": "source.pdf"}}]
    store.save("a" * 32, "A powder enquiry", [{"question": "What error?", "context": "stream_1", "answer": "1%"}],
               run, events)

    trace = store.read("a" * 32)

    assert trace is not None
    assert trace["draft_description"] == "A powder enquiry"
    assert "Answer: 1%" in trace["description"]
    assert trace["clarification_answers"][0]["answer"] == "1%"
    assert trace["run"]["metadata"]["provider_trace"][0]["raw_content"] == '{"ok": true}'
    assert next(e for e in trace["events"] if e["stage"] == "retrieval")["payload"]["selected_file"] == "source.pdf"
    assert store.read("b" * 32) is None


def test_explainability_store_keeps_unicode_json(tmp_path):
    store = ExplainabilityStore(tmp_path / "traces.sqlite")
    store.save("b" * 32, "Échantillon", [], {"text": "μm"}, [])

    raw = json.dumps(store.read("b" * 32), ensure_ascii=False)

    assert "Échantillon" in raw and "μm" in raw


def test_rounds_keep_original_input_parent_questions_and_answers(tmp_path):
    store = ExplainabilityStore(tmp_path / "history.sqlite")
    first = store.begin("An opaque milk stream", [])
    question = {"question":"What error is required?", "context_ids":["stream_1"]}
    run = {"run_status":"complete", "facts":{"contexts":[{"context_id":"stream_1","label":"milk"}]},
           "assessment":{"clarification_questions":[question]}}
    store.finish(first["run_id"],run)
    answer = {"question":question["question"],"answer":"1%","context":"forged context", "origin_run_id":first["run_id"],
              "question_id":question_id(first["run_id"],question)}
    second = store.begin("An opaque milk stream", [answer],enquiry_id=first["enquiry_id"],parent_run_id=first["run_id"])
    assert second["round_no"] == 2 and "Context: milk" in second["effective_description"]
    assert "Answer: 1%" in second["effective_description"]
    store.finish(second["run_id"],run)
    assert store.enquiry(first["enquiry_id"])["original_description"] == "An opaque milk stream"
    assert len(store.enquiry(first["enquiry_id"])["runs"]) == 2
    trace = store.read(second["run_id"])
    assert trace["parent_run_id"] == first["run_id"] and trace["draft_description"] == "An opaque milk stream"
    assert trace["questions"][0]["origin_run_id"] == second["run_id"]
    assert len(store.list_enquiries()) == 1 and store.list_enquiries()[0]["rounds"] == 2


def test_answer_or_parent_from_another_enquiry_is_rejected_without_creating_run(tmp_path):
    store = ExplainabilityStore(tmp_path / "history.sqlite")
    one = store.begin("One", []); two = store.begin("Two", [])
    for identity in (one,two):
        store.finish(identity["run_id"],{"run_status":"incomplete"})
    with pytest.raises(HistoryConflict):
        store.begin("One",[],enquiry_id=one["enquiry_id"],parent_run_id=two["run_id"])
    with pytest.raises(HistoryConflict):
        store.begin("One",[{"question":"q","context":"c","answer":"a","origin_run_id":two["run_id"],"question_id":"f"*24}],
                    enquiry_id=one["enquiry_id"],parent_run_id=one["run_id"])
    assert len(store.enquiry(one["enquiry_id"])["runs"]) == 1


def test_interrupted_run_retains_chronological_partial_events_and_reopens(tmp_path):
    path = tmp_path / "history.sqlite";store=ExplainabilityStore(path)
    identity=store.begin("A sample",[])
    store.append(identity["run_id"],{"stage":"extraction","event_type":"provider_response","payload":{"raw_content":"invalid"}})
    restarted=ExplainabilityStore(path);restarted.recover_interrupted()
    trace=restarted.read(identity["run_id"])
    assert trace["run"] is None and trace["status"] == "interrupted"
    assert [e["event_type"] for e in trace["events"]] == ["run_started","provider_response","run_interrupted"]
    assert [e["created_at"] for e in trace["events"]] == sorted(e["created_at"] for e in trace["events"])
    assert store.begin("A sample",[],enquiry_id=identity["enquiry_id"],parent_run_id=identity["run_id"])["round_no"] == 2


def test_old_database_migrates_without_inventing_links_or_rewriting_events(tmp_path):
    path=tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE explainability_runs(run_id TEXT PRIMARY KEY,created_at TEXT NOT NULL,description TEXT NOT NULL,clarification_answers TEXT NOT NULL,run_json TEXT NOT NULL)")
        c.execute("INSERT INTO explainability_runs VALUES(?,?,?,?,?)",("a"*32,"2026-01-01","Original","[]",'{"run_status":"incomplete"}'))
    store=ExplainabilityStore(path);trace=store.read("a"*32)
    assert trace["enquiry_id"] == "a"*32 and trace["parent_run_id"] is None
    assert trace["status"] == "incomplete" and trace["created_at"] == "2026-01-01"
    assert trace["events"] == [] and store.list_enquiries()[0]["rounds"] == 1


def test_completed_round_cannot_be_overwritten(tmp_path):
    store=ExplainabilityStore(tmp_path / "history.sqlite")
    identity=store.begin("One",[])
    store.finish(identity["run_id"],{"run_status":"complete","value":"original"})
    with pytest.raises(HistoryConflict):
        store.finish(identity["run_id"],{"run_status":"complete","value":"replacement"})
    assert store.read(identity["run_id"])["run"]["value"] == "original"
