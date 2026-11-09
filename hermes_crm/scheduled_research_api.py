"""Profile-bound saved intent and observations. No host context or dispatch routes."""
from fastapi import APIRouter, Request, Query, Path
from pydantic import BaseModel, ConfigDict, Field
from .domain import validate_query
from .scheduled_research import ResearchIntent, ScheduledResearchStore

class SaveResearch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=1, max_length=120)
    data: ResearchIntent

def build_router(service, require_workspace):
    router = APIRouter()

    @router.get('/scheduled-research')
    def history(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80),
                task_id: str | None = Query(None, min_length=36, max_length=36),
                limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            validate_query(request.query_params, {'profile', 'workspace_token', 'task_id', 'limit', 'offset'})
            require_workspace(crm, workspace_token)
            return ScheduledResearchStore(crm, initialize=False).page(task_id=task_id, limit=limit, offset=offset)

    @router.get('/scheduled-research/{assignment_id}')
    def detail(request: Request, assignment_id: str = Path(..., min_length=36, max_length=36),
               workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            validate_query(request.query_params, {'profile', 'workspace_token'})
            require_workspace(crm, workspace_token)
            return ScheduledResearchStore(crm, initialize=False).get(assignment_id)

    @router.post('/scheduled-research', status_code=201)
    def save(request: Request, body: SaveResearch):
        with service() as crm:
            validate_query(request.query_params, {'profile'})
            require_workspace(crm, body.workspace_token)
            return ScheduledResearchStore(crm).create(body.data.model_dump(), idempotency_key=body.idempotency_key)

    return router
