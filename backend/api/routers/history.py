"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

from backend.api.dependencies import get_history

import re
import sqlite3
from typing import Literal

from fastapi import Depends, APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.services.history.explainability import ExplainabilityStore


def create_router():
    router = APIRouter(tags=["History"])
    def history_read(method, *args):
        try:
            value = method(*args)
        except (OSError, sqlite3.Error):
            raise HTTPException(503, {"code":"explainability_unavailable","message":"Enquiry history is unavailable."}) from None
        if value is None:
            raise HTTPException(404, {"code":"history_not_found","message":"Saved history was not found."})
        return value


    @router.get("/api/assess/{run_id}/explainability")
    def explainability(run_id: str, explainability_store: ExplainabilityStore = Depends(get_history)):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise HTTPException(422, {"code":"invalid_run_id","message":"Invalid assessment run ID."})
        return history_read(explainability_store.read, run_id)


    @router.get("/api/enquiries")
    def enquiries(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0), explainability_store: ExplainabilityStore = Depends(get_history)):
        return history_read(explainability_store.list_enquiries, limit, offset)


    @router.get("/api/assess/{run_id}/report.pdf")
    def saved_report(run_id: str, audience: Literal['chemist', 'trace'] = 'chemist', explainability_store: ExplainabilityStore = Depends(get_history)):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise HTTPException(422, {"code": "invalid_run_id", "message": "Invalid assessment run ID."})
        from backend.services.history.history_pdf import history_pdf, chemist_pdf
        trace = history_read(explainability_store.read, run_id)
        return Response((history_pdf if audience == 'trace' else chemist_pdf)(trace), media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="spectraplan-{run_id}.pdf"',
            "Cache-Control": "no-store"})


    @router.get("/api/enquiries/{enquiry_id}")
    def enquiry(enquiry_id: str, explainability_store: ExplainabilityStore = Depends(get_history)):
        if not re.fullmatch(r"[0-9a-f]{32}", enquiry_id):
            raise HTTPException(422, {"code":"invalid_enquiry_id","message":"Invalid enquiry ID."})
        return history_read(explainability_store.enquiry, enquiry_id)

    return router
