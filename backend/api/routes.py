"""HTTP router composition; domain routes own their dependencies."""
from fastapi import APIRouter, Depends, Response
from backend.api.auth import Identity, get_current_user
from backend.api.routers import assessment, history, search, knowledge, health

def create_router():
    router = APIRouter()
    @router.get("/api/me")
    def me(response: Response, user: Identity = Depends(get_current_user)):
        response.headers["Cache-Control"] = "no-store"
        return {"id": user.user_id, "email": user.email, "role": user.role}
    for module in (assessment, history, search, knowledge, health):
        router.include_router(module.create_router())
    return router
