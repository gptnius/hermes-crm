"""Authenticated desktop-only acknowledgement routes; no model-facing tools."""
from typing import Literal
from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import Field
from .customization_api import unique_json
from .domain import validate_query
from .report_reviews import ReportReviewStore, ReviewRequest

class ReviewBody(ReviewRequest):
    workspace_token: str = Field(min_length=1,max_length=80)
    idempotency_key: str = Field(min_length=1,max_length=160)


def build_router(service,require_workspace):
    router=APIRouter(dependencies=[Depends(unique_json)])
    @router.get('/report-reviews/{family}/{assignment_id}/{report_id}')
    def read(request:Request,family:Literal['native','scheduled_research'],
             assignment_id:str=Path(...,min_length=36,max_length=36),
             report_id:str=Path(...,min_length=1,max_length=160),
             workspace_token:str=Query(...,min_length=1,max_length=80)):
        with service() as crm:
            validate_query(request.query_params,{'profile','workspace_token'})
            require_workspace(crm,workspace_token)
            return ReportReviewStore(crm).get(family,assignment_id,report_id)

    @router.post('/report-reviews/{family}/{assignment_id}/{report_id}/{action}')
    def write(request:Request,body:ReviewBody,family:Literal['native','scheduled_research'],
              action:Literal['acknowledge','revoke'],assignment_id:str=Path(...,min_length=36,max_length=36),
              report_id:str=Path(...,min_length=1,max_length=160)):
        with service() as crm:
            validate_query(request.query_params,{'profile'})
            require_workspace(crm,body.workspace_token)
            return ReportReviewStore(crm).write(family,assignment_id,report_id,action,
                body.model_dump(exclude={'workspace_token','idempotency_key'}),key=body.idempotency_key)
    return router
