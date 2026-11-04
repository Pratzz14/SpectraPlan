"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

from backend.api.dependencies import get_history
from backend.api.auth import Identity, get_current_user, require_admin, require_owner, customer_run

import re
import sqlite3
from typing import Literal

from fastapi import Depends, APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.services.history.explainability import ExplainabilityStore


def create_router():
    router = APIRouter(tags=["Leads"], dependencies=[Depends(get_current_user)])
    def history_read(method, *args):
        try:
            value = method(*args)
        except (OSError, sqlite3.Error):
            raise HTTPException(503, {"code":"explainability_unavailable","message":"Enquiry history is unavailable."}) from None
        if value is None:
            raise HTTPException(404, {"code":"history_not_found","message":"Saved history was not found."})
        return value


    @router.get("/api/assess/{run_id}/explainability", dependencies=[Depends(require_admin)])
    def explainability(run_id: str, explainability_store: ExplainabilityStore = Depends(get_history)):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise HTTPException(422, {"code":"invalid_run_id","message":"Invalid assessment run ID."})
        return history_read(explainability_store.read, run_id)


    @router.get("/api/enquiries", dependencies=[Depends(require_admin)])
    def enquiries(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0), email: str = Query(default="", max_length=320), explainability_store: ExplainabilityStore = Depends(get_history)):
        return history_read(explainability_store.list_enquiries, limit, offset, email)

    @router.get("/api/assess/{run_id}")
    def saved_assessment(run_id: str, user: Identity = Depends(get_current_user), explainability_store: ExplainabilityStore = Depends(get_history)):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise HTTPException(422, "Invalid assessment run ID.")
        trace = history_read(explainability_store.read, run_id)
        require_owner(history_read(explainability_store.enquiry, trace["enquiry_id"]), user)
        # Explicit projection: do not expose event payloads or future trace fields.
        return {**{key: trace[key] for key in ("run_id", "enquiry_id", "parent_run_id", "status", "round_no", "draft_description", "description", "clarification_answers", "questions")},
                "run": customer_run(trace["run"])}


    @router.get("/api/assess/{run_id}/report.pdf")
    def saved_report(run_id: str, audience: Literal['chemist', 'trace'] = 'chemist', explainability_store: ExplainabilityStore = Depends(get_history), user: Identity = Depends(get_current_user)):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise HTTPException(422, {"code": "invalid_run_id", "message": "Invalid assessment run ID."})
        from backend.services.history.history_pdf import history_pdf, chemist_pdf
        trace = history_read(explainability_store.read, run_id)
        require_owner(history_read(explainability_store.enquiry, trace["enquiry_id"]), user)
        if audience == 'trace' and user.role != 'admin':
            raise HTTPException(403, "Administrator access required.")
        return Response((history_pdf if audience == 'trace' else chemist_pdf)(trace), media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="spectraplan-{run_id}.pdf"',
            "Cache-Control": "no-store"})


    @router.get("/api/enquiries/{enquiry_id}")
    def enquiry(enquiry_id: str, explainability_store: ExplainabilityStore = Depends(get_history), user: Identity = Depends(get_current_user)):
        if not re.fullmatch(r"[0-9a-f]{32}", enquiry_id):
            raise HTTPException(422, {"code":"invalid_enquiry_id","message":"Invalid enquiry ID."})
        return require_owner(history_read(explainability_store.enquiry, enquiry_id), user)

    return router
