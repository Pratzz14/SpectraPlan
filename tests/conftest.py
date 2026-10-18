"""All tests use disposable history; no synthetic run enters the local enquiry store."""

import pytest


@pytest.fixture(autouse=True)
def isolated_history(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPLAINABILITY_DB_PATH", str(tmp_path / "history.sqlite"))
