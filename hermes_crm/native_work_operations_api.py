"""REST preparation/status router. No host context or dispatch endpoint."""
from typing import Literal

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .domain import validate_query
from .native_work_operations import WorkOperationStore


class PrepareOperation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)
    verb: Literal['schedule', 'check', 'cancel']
    assignment_id: str = Field(min_length=1, max_length=36)
    expected_assignment_version: int = Field(ge=1)
    intended_session_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=160)


class WithdrawOperation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)


def build_router(service, require_workspace):
    router = APIRouter()

    @router.post('/work-operations', status_code=201)
    def prepare(request: Request, body: PrepareOperation):
        with service() as crm:
            validate_query(request.query_params, {'profile'})
            require_workspace(crm, body.workspace_token)
            return WorkOperationStore(crm, initialize=True).prepare(**body.model_dump(exclude={'workspace_token'}))

    @router.get('/work-operations')
    def page(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80),
             task_id: str | None = Query(None, min_length=1, max_length=36),
             limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            validate_query(request.query_params, {'workspace_token', 'profile', 'task_id', 'limit', 'offset'})
            require_workspace(crm, workspace_token)
            return WorkOperationStore(crm).page(task_id=task_id, limit=limit, offset=offset)

    @router.get('/work-operations/{operation_id}')
    def status(request: Request, operation_id: str = Path(..., min_length=36, max_length=36),
               workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            validate_query(request.query_params, {'workspace_token', 'profile'})
            require_workspace(crm, workspace_token)
            return WorkOperationStore(crm).get(operation_id)

    @router.post('/work-operations/{operation_id}/withdraw')
    def withdraw(request: Request, body: WithdrawOperation, operation_id: str = Path(..., min_length=36, max_length=36)):
        with service() as crm:
            validate_query(request.query_params, {'profile'})
            require_workspace(crm, body.workspace_token)
            return WorkOperationStore(crm).withdraw(operation_id)

    return router
