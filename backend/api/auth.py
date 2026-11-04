"""Supabase identity verification and application-owned authorization."""

from dataclasses import dataclass
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.api.dependencies import get_settings
from backend.core.config import Settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    user_id: str
    email: str
    role: str = "customer"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    config: Settings = Depends(get_settings),
) -> Identity:
    if credentials is None:
        raise HTTPException(401, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    if not config.supabase_url or not config.supabase_publishable_key:
        raise HTTPException(503, "Authentication is not configured.")
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(
                config.supabase_url.rstrip("/") + "/auth/v1/user",
                headers={"apikey": config.supabase_publishable_key,
                         "Authorization": "Bearer " + credentials.credentials},
            )
    except httpx.RequestError:
        raise HTTPException(503, "Authentication is temporarily unavailable.") from None
    if response.status_code in (401, 403):
        raise HTTPException(401, "Your session has expired. Sign in again.",
                            headers={"WWW-Authenticate": "Bearer"})
    if response.status_code != 200:
        raise HTTPException(503, "Authentication is temporarily unavailable.")
    try:
        user = response.json()
        user_id = str(UUID(user["id"]))
        email = user["email"].strip()
        if not email or user.get("is_anonymous"):
            raise ValueError("Email account required")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(401, "Invalid sign-in session.") from None
    # Email confirmation is deliberately optional for the initial password flow.
    admins = {value.strip() for value in config.admin_user_ids.split(",") if value.strip()}
    allowed={value.strip() for value in config.allowed_user_ids.split(',') if value.strip()}
    if allowed and user_id not in allowed | admins:
        raise HTTPException(403,'This account has not been granted application access.')
    return Identity(user_id, email, "admin" if user_id in admins else "customer")


def require_admin(user: Identity = Depends(get_current_user)) -> Identity:
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required.")
    return user


def require_owner(enquiry, user: Identity):
    if enquiry is None or (user.role != "admin" and enquiry.get("owner_user_id") != user.user_id):
        raise HTTPException(404, "Saved enquiry was not found.")
    return enquiry


def customer_run(run):
    """Copy a saved run without the raw provider messages retained for admins."""
    from copy import deepcopy
    result = deepcopy(run)
    if result:
        result.setdefault("metadata", {})["provider_trace"] = []
    return result
