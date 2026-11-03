"""HTTP router composition; domain routes own their dependencies."""
from fastapi import APIRouter
from backend.api.routers import assessment, history, search, knowledge, health

def create_router():
    router = APIRouter()
    for module in (assessment, history, search, knowledge, health):
        router.include_router(module.create_router())
    return router
