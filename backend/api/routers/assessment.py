"""Run from the repository root: python -m uvicorn backend.main:app --reload."""

from backend.api.dependencies import get_settings, get_retrieval, get_history
from backend.api.auth import Identity, get_current_user, require_admin, require_owner, customer_run

import sqlite3

from fastapi import Depends, APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse

from backend.core.config import Settings
from backend.pipelines.assessment.pipeline import extract_case, assess_case
from backend.schemas.models import CaseFacts, ExtractionRequest, AssessmentRequest, AssessmentRun
from backend.providers.provider import ProviderError
from backend.services.search.retrieval import CaseRetrievalService
from backend.services.history.explainability import ExplainabilityStore, HistoryConflict, DescriptionTooLong, compose_description, question_id


def create_router():
    router = APIRouter(tags=["Assessment"], dependencies=[Depends(get_current_user)])
    @router.post("/api/assess", response_model=AssessmentRun,
                      responses={202: {"description": "Assessment queued; poll the returned status URL"}, 422: {"description": "Invalid enquiry"},
                                 502: {"model": AssessmentRun}, 503: {"model": AssessmentRun},
                                 504: {"model": AssessmentRun}})
    async def assess(request: AssessmentRequest, config: Settings = Depends(get_settings), retrieval_service: CaseRetrievalService = Depends(get_retrieval), explainability_store: ExplainabilityStore = Depends(get_history), user: Identity = Depends(get_current_user), idempotency_key: str | None = Header(default=None)):
        if config.background_assessments:
            if not idempotency_key or len(idempotency_key)>100:
                raise HTTPException(422,'A valid Idempotency-Key is required.')
            import asyncio
            from backend.services.cloud.assessments import AssessmentJobs
            try:
                value=await asyncio.to_thread(AssessmentJobs(explainability_store.database).submit,request,user,idempotency_key,config)
                return JSONResponse(value,status_code=202)
            except HistoryConflict as error:raise HTTPException(409,str(error)) from None
            except DescriptionTooLong as error:raise HTTPException(422,str(error)) from None
        if config.storage_backend == 'supabase':
            import asyncio
            return await asyncio.to_thread(lambda: asyncio.run(run_assessment(request,config,retrieval_service,explainability_store,user)))
        return await run_assessment(request,config,retrieval_service,explainability_store,user)

    async def run_assessment(request, config, retrieval_service, explainability_store, user):
        answers = [answer.model_dump(mode="json") for answer in request.clarification_answers]
        effective = compose_description(request.description, answers)
        if len(effective) > config.assessment_max_description_chars:
            raise HTTPException(422, {"code":"description_too_long",
                "message":f"Enquiry including clarifications exceeds {config.assessment_max_description_chars} characters."})
        identity = None
        try:
            if request.enquiry_id:
                require_owner(explainability_store.enquiry(request.enquiry_id), user)
            identity = explainability_store.begin(request.description, answers,
                enquiry_id=request.enquiry_id, parent_run_id=request.parent_run_id,
                owner_user_id=user.user_id, customer_email=user.email,
                max_description_chars=config.assessment_max_description_chars)
            run_id = identity["run_id"]
            def record_event(event):
                explainability_store.append(run_id, event)
            def record_stage(stage, value):
                record_event({"stage":stage,"event_type":"validated_stage","payload":value.model_dump(mode="json")})
            result = await assess_case(identity["effective_description"], config, retrieval_service=retrieval_service,
                on_stage=record_stage, on_event=record_event, run_id=run_id)
            result.metadata.enquiry_id = identity["enquiry_id"]
            result.metadata.parent_run_id = identity["parent_run_id"]
            result.metadata.round_no = identity["round_no"]
            result.metadata.question_ids = [question_id(run_id, q.model_dump())
                for q in result.assessment.clarification_questions] if result.assessment else []
            explainability_store.finish(run_id, result.model_dump(mode="json"))
        except DescriptionTooLong as error:
            raise HTTPException(422, {"code":"description_too_long","message":str(error)}) from None
        except HistoryConflict as error:
            raise HTTPException(409, {"code":"history_conflict","message":str(error)}) from None
        except (OSError, sqlite3.Error):
            raise HTTPException(503, {"code":"explainability_unavailable",
                "message":"Assessment history could not be stored. Retry when storage is available."}) from None
        except BaseException:
            if identity:
                explainability_store.interrupt(identity["run_id"])
            raise
        status = result.errors[0].http_status if result.facts is None and result.errors else 200
        return JSONResponse(customer_run(result.model_dump(mode="json")), status_code=status,
                            headers={"Cache-Control": "no-store"})


    @router.get('/api/assess/{run_id}/status')
    def assessment_status(run_id: str, user: Identity=Depends(get_current_user), store=Depends(get_history)):
        if not __import__('re').fullmatch(r'[0-9a-f]{32}',run_id):raise HTTPException(422,'Invalid run ID')
        saved=store.read(run_id)
        if not saved:raise HTTPException(404,'Assessment not found')
        require_owner(store.enquiry(saved['enquiry_id']),user)
        stage=saved['status']
        if hasattr(store,'database'):
            with store.database.connection() as c:
                row=c.execute('SELECT stage FROM spectraplan.assessment_jobs WHERE run_id=%s',(run_id,)).fetchone()
                if row:stage=row[0]
        return {'run_id':run_id,'enquiry_id':saved['enquiry_id'],'status':saved['status'],'stage':stage}

    @router.post("/api/extract", response_model=CaseFacts, dependencies=[Depends(require_admin)])
    async def extract(request: ExtractionRequest, config: Settings = Depends(get_settings)):
        try:
            return await extract_case(request.description, config)
        except ProviderError as error:
            raise HTTPException(error.http_status, {"code": error.code, "message": str(error)}) from None

    return router
