"""Workspace-checked human policy review, separate from assignment execution."""
from fastapi import APIRouter, Depends, Query, Request
from .customization_api import CreateBody, unique_json
from .domain import validate_query
from .task_ownership import TaskOwnership

def build_router(service, require_workspace):
    router = APIRouter(dependencies=[Depends(unique_json)])
    @router.get('/task-owner-policy')
    def get_policy(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        validate_query(request.query_params, {'workspace_token','profile'})
        with service() as crm:
            require_workspace(crm, workspace_token)
            return TaskOwnership(crm).policy()
    @router.patch('/task-owner-policy')
    def set_policy(request: Request, body: CreateBody):
        validate_query(request.query_params, {'profile'})
        with service() as crm:
            require_workspace(crm, body.workspace_token)
            return TaskOwnership(crm).set_policy(body.data, key=body.idempotency_key, actor='ui')
    return router
