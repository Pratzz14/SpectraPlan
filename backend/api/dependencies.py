"""Request-scoped access to application-owned services; override in tests."""
from fastapi import Request

def get_settings(request: Request):
    return request.app.state.settings

def get_search(request: Request):
    return request.app.state.search_service

def get_retrieval(request: Request):
    return request.app.state.retrieval_service

def get_history(request: Request):
    return request.app.state.explainability_store
