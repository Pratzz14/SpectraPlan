"""Explicit authenticated app for domain tests; auth tests use backend.main directly."""
from backend.main import create_app as production_app
from backend.api.auth import Identity, get_current_user


def create_app(settings=None):
    app = production_app(settings)
    app.dependency_overrides[get_current_user] = lambda: Identity(
        "52e2a437-d536-4c24-b328-e593e4336c50", "admin@example.test", "admin")
    return app
