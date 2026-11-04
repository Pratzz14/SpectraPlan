"""Authorization checks use the production app; never the domain-test admin helper."""
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api.auth import Identity, get_current_user
from backend.core.config import Settings
from backend.main import create_app
from backend.services.history.explainability import ExplainabilityStore

OWNER = Identity("11111111-1111-4111-8111-111111111111", "Alice@Example.test")
OTHER = Identity("22222222-2222-4222-8222-222222222222", "bob@example.test")
ADMIN = Identity("33333333-3333-4333-8333-333333333333", "admin@example.test", "admin")


def client_for(tmp_path, identity=None):
    app = create_app(Settings(_env_file=None, explainability_db_path=tmp_path / "history.sqlite"))
    if identity:
        app.dependency_overrides[get_current_user] = lambda: identity
    return TestClient(app), app.state.explainability_store


def seed(store, owner=OWNER):
    run = store.begin("Measure moisture in powder", [], owner_user_id=owner.user_id if owner else None,
                      customer_email=owner.email if owner else None)
    store.append(run["run_id"], {"stage": "provider", "event_type": "provider_response",
                                 "payload": {"raw_content": "private provider response"}})
    store.finish(run["run_id"], {"run_status": "incomplete", "assessment": None,
        "metadata": {"provider_trace": [{"raw_content": "private provider response"}]},
        "errors": [], "warnings": []})
    return run


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/me"), ("GET", "/api/enquiries"), ("POST", "/api/assess"),
    ("POST", "/api/extract"), ("POST", "/api/retrieve"), ("GET", "/api/search/status"),
    ("POST", "/api/search"), ("GET", "/api/evidence/example"), ("GET", "/api/health"),
    ("GET", "/api/knowledge/inspection"), ("POST", "/api/knowledge/ingest?filename=a.pdf"),
    ("GET", "/api/knowledge/ingest/status"), ("GET", "/api/knowledge/report"),
    ("GET", "/api/knowledge/versions/corpus-" + "a" * 20 + "/review.html"),
    ("GET", "/api/knowledge/versions/corpus-" + "a" * 20 + "/source/s01/original"),
    ("GET", "/api/knowledge/versions/corpus-" + "a" * 20 + "/source/s01.pdf"),
    ("GET", "/api/assess/" + "a" * 32),
    ("GET", "/api/assess/" + "a" * 32 + "/explainability"),
    ("GET", "/api/assess/" + "a" * 32 + "/report.pdf"),
    ("GET", "/api/enquiries/" + "a" * 32),
])
def test_anonymous_cannot_access_business_api(tmp_path, method, path):
    client, _ = client_for(tmp_path)
    response = client.request(method, path, json={})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/enquiries"), ("GET", "/api/health"),
    ("GET", "/api/knowledge/inspection"), ("GET", "/api/search/status"),
    ("GET", "/api/evidence/example"), ("POST", "/api/search"),
    ("POST", "/api/extract"), ("POST", "/api/retrieve"),
    ("POST", "/api/knowledge/ingest?filename=a.pdf"),
    ("GET", "/api/knowledge/versions/corpus-" + "a" * 20 + "/source/s01/original"),
    ("GET", "/api/knowledge/versions/corpus-" + "a" * 20 + "/assets/page.png"),
])
def test_customer_cannot_access_admin_api(tmp_path, method, path):
    client, _ = client_for(tmp_path, OWNER)
    assert client.request(method, path, json={}).status_code == 403


def test_owner_results_reports_and_cross_account_isolation(tmp_path):
    client, store = client_for(tmp_path, OWNER)
    own, other, legacy = seed(store), seed(store, OTHER), seed(store, None)
    response = client.get(f"/api/assess/{own['run_id']}")
    assert response.status_code == 200
    assert "events" not in response.json()
    assert response.json()["run"]["metadata"]["provider_trace"] == []
    assert "private provider response" not in response.text
    assert client.get(f"/api/enquiries/{own['enquiry_id']}").json()["customer_email"] == OWNER.email
    assert client.get(f"/api/assess/{own['run_id']}/report.pdf").content.startswith(b"%PDF-")
    assert client.get(f"/api/assess/{own['run_id']}/report.pdf?audience=trace").status_code == 403
    assert client.get(f"/api/assess/{own['run_id']}/explainability").status_code == 403
    for record in (other, legacy):
        for suffix in ("", "/report.pdf"):
            assert client.get(f"/api/assess/{record['run_id']}{suffix}").status_code == 404
        assert client.get(f"/api/enquiries/{record['enquiry_id']}").status_code == 404
        assert client.post("/api/assess", json={"description": "new round", "enquiry_id": record["enquiry_id"],
            "parent_run_id": record["run_id"]}).status_code == 404
    assert len(store.enquiry(other["enquiry_id"])["runs"]) == 1


def test_admin_filters_all_pages_and_sees_raw_traces(tmp_path):
    client, store = client_for(tmp_path, ADMIN)
    first = seed(store)
    seed(store, OTHER)
    seed(store, OWNER)
    seed(store, None)
    assert len(client.get("/api/enquiries").json()) == 4
    a = client.get("/api/enquiries?email=ALICE%40EXAMPLE&limit=1").json()
    b = client.get("/api/enquiries?email=alice%40example&limit=1&offset=1").json()
    assert len(a) == len(b) == 1 and a[0]["enquiry_id"] != b[0]["enquiry_id"]
    assert client.get("/api/enquiries?email=missing").json() == []
    assert client.get("/api/enquiries?email=%25").json() == []  # substring, not SQL wildcard
    trace = client.get(f"/api/assess/{first['run_id']}/explainability")
    assert trace.status_code == 200 and "private provider response" in trace.text
    assert client.get(f"/api/assess/{first['run_id']}/report.pdf?audience=trace").content.startswith(b"%PDF-")
    # Continuing an enquiry as an admin preserves customer attribution.
    store.begin("clarification", [], enquiry_id=first["enquiry_id"], parent_run_id=first["run_id"],
                owner_user_id=ADMIN.user_id, customer_email=ADMIN.email)
    enquiry = store.enquiry(first["enquiry_id"])
    assert enquiry["owner_user_id"] == OWNER.user_id and enquiry["customer_email"] == OWNER.email


def test_new_assessment_identity_is_derived_from_session(monkeypatch, tmp_path):
    from tests.test_assessment import draft, ledger
    from tests.test_assessment_api import provider_for, mock_retrieval
    from tests.test_extraction import powder, wire_for
    text = "A powder; measure moisture."
    adapter, calls = provider_for([wire_for(powder(text).model_dump()), draft(empty=True)])
    mock_retrieval(monkeypatch, ledger(empty=True))
    monkeypatch.setattr("backend.pipelines.assessment.pipeline.Provider", lambda _: adapter)
    app = create_app(adapter.settings)
    app.dependency_overrides[get_current_user] = lambda: OWNER
    client = TestClient(app)
    response = client.post("/api/assess", json={"description": text, "owner_user_id": ADMIN.user_id})
    assert response.status_code == 422 and calls == []
    response = client.post("/api/assess", json={"description": text})
    assert response.status_code == 200
    run = response.json()
    assert run["metadata"]["provider_trace"] == []
    record = app.state.explainability_store.enquiry(run["metadata"]["enquiry_id"])
    assert record["owner_user_id"] == OWNER.user_id and record["customer_email"] == OWNER.email


def test_legacy_database_migration_preserves_history(tmp_path):
    path = tmp_path / "history.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE enquiries (enquiry_id TEXT PRIMARY KEY, original_description TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
        db.execute("CREATE TABLE explainability_runs (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, description TEXT NOT NULL, clarification_answers TEXT NOT NULL, run_json TEXT NOT NULL)")
        db.execute("INSERT INTO explainability_runs VALUES (?, ?, ?, ?, ?)", ("a" * 32, "old date", "old enquiry", "[]", '{"run_status":"complete"}'))
    store = ExplainabilityStore(path)
    records = store.list_enquiries()
    assert len(records) == 1 and records[0]["original_description"] == "old enquiry"
    assert records[0]["owner_user_id"] is None and records[0]["customer_email"] is None
    assert store.read("a" * 32)["run"]["run_status"] == "complete"
    assert len(ExplainabilityStore(path).list_enquiries()) == 1


def auth_client(monkeypatch, tmp_path, handler, **options):
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    config = Settings(_env_file=None, explainability_db_path=tmp_path / "history.sqlite",
                      supabase_url="https://project.supabase.co", supabase_publishable_key="public-test-key", **options)
    return TestClient(create_app(config))


def test_verified_identity_and_backend_only_admin_role(monkeypatch, tmp_path):
    def handler(request):
        assert str(request.url) == "https://project.supabase.co/auth/v1/user"
        assert request.headers["authorization"] == "Bearer user-token"
        assert request.headers["apikey"] == "public-test-key"
        return httpx.Response(200, json={"id": OWNER.user_id, "email": OWNER.email,
            "email_confirmed_at": None, "user_metadata": {"role": "admin"}})
    client = auth_client(monkeypatch, tmp_path, handler)
    response = client.get("/api/me", headers={"Authorization": "Bearer user-token"})
    assert response.json() == {"id": OWNER.user_id, "email": OWNER.email, "role": "customer"}
    client.app.state.settings.admin_user_ids = OWNER.user_id
    assert client.get("/api/me", headers={"Authorization": "Bearer user-token"}).json()["role"] == "admin"


@pytest.mark.parametrize("upstream,expected", [(401,401), (403,401), (500,503), (429,503)])
def test_auth_failure_mapping(monkeypatch, tmp_path, upstream, expected):
    client = auth_client(monkeypatch, tmp_path, lambda _: httpx.Response(upstream))
    assert client.get("/api/me", headers={"Authorization": "Bearer expired"}).status_code == expected


def test_missing_configuration_and_network_outage_fail_closed(monkeypatch, tmp_path):
    client, _ = client_for(tmp_path)
    assert client.get("/api/me", headers={"Authorization": "Bearer token"}).status_code == 503
    def unavailable(request):
        raise httpx.ConnectError("offline", request=request)
    client = auth_client(monkeypatch, tmp_path, unavailable)
    assert client.get("/api/me", headers={"Authorization": "Bearer token"}).status_code == 503


@pytest.mark.parametrize("payload", [{}, {"id": "invalid", "email": "a@b.test"},
    {"id": OWNER.user_id, "email": ""}, {"id": OWNER.user_id, "email": OWNER.email, "is_anonymous": True}])
def test_malformed_or_anonymous_identity_rejected(monkeypatch, tmp_path, payload):
    client = auth_client(monkeypatch, tmp_path, lambda _: httpx.Response(200, json=payload))
    assert client.get("/api/me", headers={"Authorization": "Bearer token"}).status_code == 401
