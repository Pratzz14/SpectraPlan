"""Submission inventory must report secret locations without exposing values."""
import json

import pytest

import scripts.verify_submission as verifier


def inventory(monkeypatch, tmp_path, content):
    target = tmp_path / "config.txt"
    target.write_text(content, encoding="utf-8")
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    monkeypatch.setattr(verifier.subprocess, "check_output", lambda *args, **kwargs: b"config.txt\0")
    return verifier.credential_scan()


def test_supabase_secret_format_is_reported_without_echoing_key(monkeypatch, tmp_path):
    secret = "sb_secret_" + "AbCdEfGhIjKlMnOpQrStUvWxYz012345"
    result = inventory(monkeypatch, tmp_path, secret)
    assert result["findings"] and result["findings"][0]["path"] == "config.txt"
    assert secret not in json.dumps(result)


@pytest.mark.parametrize("name", ["SUPABASE_SECRET_KEY", "SUPABASE_ACCESS_TOKEN", "DASHSCOPE_API_KEY"])
def test_configured_secret_types_are_checked(monkeypatch, tmp_path, name):
    secret = "private-credential-value-for-inventory"
    monkeypatch.setenv(name, secret)
    result = inventory(monkeypatch, tmp_path, secret)
    assert {"path": "config.txt", "reason": "configured secret found"} in result["findings"]
    assert secret not in json.dumps(result)


def test_publishable_supabase_key_is_allowed(monkeypatch, tmp_path):
    public = "sb_publishable_AbCdEfGhIjKlMnOpQrStUvWxYz012345"
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", public)
    assert inventory(monkeypatch, tmp_path, public)["findings"] == []
