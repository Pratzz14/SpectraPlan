"""Per-configuration availability cache. Probes contain synthetic content only."""

import asyncio
import time

from pydantic import BaseModel, ConfigDict


class AvailabilityProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    ok: bool


class ProviderRouter:
    def __init__(self, settings):
        self.settings = settings
        self.selected = None
        self.states = {}
        self.lock = asyncio.Lock()

    def mark(self, name, ok, code=None):
        now = time.monotonic()
        ttl = self.settings.provider_health_ttl_s if ok else self.settings.provider_failure_ttl_s
        self.states[name] = {"available": ok, "code": code, "checked_at": now, "expires_at": now + ttl}
        if ok:
            self.selected = name
        elif self.selected == name:
            self.selected = None

    def snapshot(self):
        now = time.monotonic()
        profiles = []
        for name in self.settings.provider_names:
            state = self.states.get(name, {})
            configured = self.settings.usable_key(getattr(self.settings, f"{name}_api_key"))
            fresh = state.get("expires_at", 0) > now
            profiles.append({"name": name, "configured": configured,
                "status": "not_configured" if not configured else
                          "working" if fresh and state["available"] else
                          "unavailable" if fresh else "unchecked",
                "error_code": state.get("code") if fresh else None})
        selected = next((p["name"] for p in profiles if p["name"] == self.selected and p["status"] == "working"), None)
        return {"selected": selected, "candidates": profiles}

    async def select(self, deadline, probe, excluded=()):
        # Waiting for another request's probe also consumes this request's deadline.
        async with asyncio.timeout(max(0, deadline - time.monotonic())):
            async with self.lock:
                from backend.provider import ProviderError
                for name in self.settings.provider_names:
                    if name in excluded:
                        continue
                    config = self.settings.for_provider(name)
                    if not config.provider_configured:
                        continue
                    state = self.states.get(name)
                    if state and state["expires_at"] > time.monotonic():
                        if state["available"]:
                            self.selected = name
                            return config
                        continue
                    try:
                        await probe(config, min(deadline, time.monotonic() + self.settings.provider_probe_timeout_s))
                    except ProviderError as error:
                        self.mark(name, False, error.code)
                    else:
                        self.mark(name, True)
                        return config
                if time.monotonic() >= deadline:
                    raise ProviderError("provider_timeout", "Provider selection deadline expired.", 504)
                failures = [self.states.get(name, {}) for name in self.settings.provider_names
                            if self.settings.usable_key(getattr(self.settings, f"{name}_api_key"))]
                if failures and all(state.get("code") == "provider_timeout" for state in failures):
                    raise ProviderError("provider_timeout", "Configured provider availability checks timed out.", 504)
                code = "provider_unavailable" if self.settings.provider_configured else "provider_not_configured"
                raise ProviderError(code, "No configured provider is currently available.")
