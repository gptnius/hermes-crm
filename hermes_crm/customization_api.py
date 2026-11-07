"""Workspace-guarded schema editing; no scheduler or profile-selection authority."""
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from .domain import validate_query


class SchemaBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)
    data: dict[str, Any]


class CreateBody(SchemaBody):
    idempotency_key: str = Field(min_length=1, max_length=160)


async def unique_json(request: Request):
    """Reject duplicate keys at every depth instead of silently taking the last."""
    if request.method not in ('POST', 'PATCH'):
        return
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Repeated JSON field')
            result[key] = value
        return result
    try:
        json.loads(await request.body(), object_pairs_hook=pairs)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, detail={'error': 'Invalid JSON or repeated JSON field.'}) from None


def build_router(service, require_workspace):
    router = APIRouter(dependencies=[Depends(unique_json)])

    def check(request, crm, token, *allowed):
        validate_query(request.query_params, {'profile', *allowed})
        require_workspace(crm, token)

    @router.get('/customization/catalog')
    def catalog(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token')
            return crm.catalog()

    @router.post('/customization/stages', status_code=201)
    def create_stage(request: Request, body: CreateBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return crm.create_stage(body.data, actor='desktop', key=body.idempotency_key)

    @router.patch('/customization/stages/{stage_key}')
    def update_stage(request: Request, body: SchemaBody, stage_key: str = Path(..., pattern=r'^[a-z][a-z0-9_]{0,19}$')):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return crm.update_stage(stage_key, body.data, actor='desktop')

    @router.post('/customization/fields/{kind}', status_code=201)
    def create_field(request: Request, body: CreateBody, kind: Literal['contacts', 'deals', 'tasks']):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return crm.create_field(kind, body.data, actor='desktop', key=body.idempotency_key)

    @router.patch('/customization/fields/{kind}/{field_key}')
    def update_field(request: Request, body: SchemaBody, kind: Literal['contacts', 'deals', 'tasks'],
                     field_key: str = Path(..., pattern=r'^[a-z][a-z0-9_]{0,63}$')):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return crm.update_field(kind, field_key, body.data, actor='desktop')

    return router
