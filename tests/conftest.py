"""All tests use disposable history; no synthetic run enters the local enquiry store."""

import pytest
import os

# The user's .env may point at live Supabase after cutover. Ordinary tests and
# the module-level ASGI app must never inherit that persistence mode.
os.environ['STORAGE_BACKEND'] = 'local'


@pytest.fixture(autouse=True)
def isolated_history(monkeypatch, tmp_path):
    monkeypatch.setenv('STORAGE_BACKEND', 'local')
    monkeypatch.setenv("EXPLAINABILITY_DB_PATH", str(tmp_path / "history.sqlite"))


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch):
    """Tests must explicitly inject a mock transport, never contact providers."""
    import httpx
    def forbidden(*args, **kwargs):
        raise AssertionError("External HTTP is forbidden in tests; inject MockTransport")
    async def forbidden_async(*args, **kwargs):
        forbidden()
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden_async)
