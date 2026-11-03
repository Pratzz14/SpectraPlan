import pytest
from backend.core.config import Settings
from evaluation import search_smoke

def test_smoke_exercises_each_mode_without_providers(monkeypatch):
    calls=[]
    class Service:
        def __init__(self,settings): pass
        def compare(self,statement,**kwargs):
            calls.append(kwargs["mode"])
            return {"rankings":{kwargs["mode"]:[{"rank":1,"score":0.1,"evidence":{"evidence_id":"e1","source_id":"S01"}}]},"versions":{"technical":"test"},"model_calls":0}
    monkeypatch.setattr(search_smoke,"SearchService",Service)
    assert search_smoke.run(Settings(_env_file=None),["test statement"])["passed"]
    assert calls==["bm25","qdrant","hybrid"]

@pytest.mark.parametrize("failure",["empty","unavailable"])
def test_smoke_fails_for_missing_results_or_prerequisites(monkeypatch,failure):
    class Service:
        def __init__(self,settings): pass
        def compare(self,statement,**kwargs):
            if failure=="unavailable": raise search_smoke.SearchUnavailable("Missing local model")
            return {"rankings":{kwargs["mode"]:[]},"versions":{"technical":"test"},"model_calls":0}
    monkeypatch.setattr(search_smoke,"SearchService",Service)
    assert not search_smoke.run(Settings(_env_file=None),["test"])["passed"]
