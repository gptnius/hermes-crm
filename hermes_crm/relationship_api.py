"""Shared local relationship HTTP contract. Hosts retain authentication and scope."""
from typing import Any, Literal
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from .domain import CRMError, settings, validate_query
from .companies import CompanyStore
from .events import EventStore
from .relationship_queries import RelationshipQueries


class ScopedBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=1, max_length=160)


class CreateBody(ScopedBody):
    data: dict[str, Any]


class UpdateBody(CreateBody):
    expected_version: int = Field(ge=1)


class VersionBody(ScopedBody):
    expected_version: int = Field(ge=1)


class LinkBody(ScopedBody):
    expected_contact_version: int = Field(ge=1)
    company_id: str | None = Field(..., min_length=1, max_length=36)


class ReasonBody(VersionBody):
    reason: str = Field(min_length=1, max_length=2000)


class CompleteBody(UpdateBody):
    pass


class TaskLinkBody(VersionBody):
    event_id: str = Field(min_length=1, max_length=36)
    expected_task_version: int = Field(ge=1)


class TaskUnlinkBody(TaskLinkBody):
    pass


def build_router(service, require_workspace, actor='desktop'):
    router = APIRouter()

    def check(request, crm, token, *allowed):
        validate_query(request.query_params, {'profile', *allowed})
        # Host callbacks historically bootstrap tokens. A relationship read must
        # never initialize storage or a workspace, even for a stale/forged token.
        with crm.engine.connect() as conn:
            current = conn.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar()
        if current is None or current != token:
            raise CRMError('The workspace changed. Refresh before continuing.', 409)
        require_workspace(crm, token)

    @router.get('/companies')
    def companies(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80),
                  q: str = '', include_archived: bool = False,
                  limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'q', 'include_archived', 'limit', 'offset')
            return CompanyStore(crm).list(q=q, include_archived=include_archived, limit=limit, offset=offset)

    @router.get('/companies/{record_id}')
    def company(request: Request, record_id: str, workspace_token: str):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token')
            return RelationshipQueries(crm).company_detail(record_id)

    @router.get('/companies/{record_id}/records/{kind}')
    def company_records(request: Request, record_id: str, kind: Literal['contacts', 'deals', 'tasks', 'events'],
                        workspace_token: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'limit', 'offset')
            return RelationshipQueries(crm).company_records(record_id, kind, limit=limit, offset=offset)

    @router.post('/companies', status_code=201)
    def create_company(request: Request, body: CreateBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return CompanyStore(crm).create(body.data, actor=actor, key=body.idempotency_key)

    @router.patch('/companies/{record_id}')
    def update_company(request: Request, record_id: str, body: UpdateBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return CompanyStore(crm).update(record_id, body.data, expected_version=body.expected_version, actor=actor, key=body.idempotency_key)

    @router.post('/companies/{record_id}/archive')
    def archive_company(request: Request, record_id: str, body: VersionBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return CompanyStore(crm).archive(record_id, expected_version=body.expected_version, actor=actor, key=body.idempotency_key)

    @router.post('/companies/{record_id}/restore')
    def restore_company(request: Request, record_id: str, body: VersionBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return CompanyStore(crm).restore(record_id, expected_version=body.expected_version, actor=actor, key=body.idempotency_key)

    @router.get('/contacts/{record_id}/company')
    def contact_company(request: Request, record_id: str, workspace_token: str):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token')
            return CompanyStore(crm).get_contact_company(record_id)

    @router.put('/contacts/{record_id}/company')
    def link_company(request: Request, record_id: str, body: LinkBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return CompanyStore(crm).set_contact_company(record_id, body.company_id, expected_contact_version=body.expected_contact_version, actor=actor, key=body.idempotency_key)

    @router.get('/events')
    def events(request: Request, workspace_token: str, q: str = '', kind: Literal['appointment', 'call'] | None = None,
               starts_from: str | None = None, starts_before: str | None = None, contact_id: str | None = None, deal_id: str | None = None,
               company_id: str | None = None, status: Literal['scheduled', 'needs_rescheduling', 'completed', 'cancelled'] | None = None,
               limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'q', 'kind', 'starts_from', 'starts_before', 'contact_id', 'deal_id', 'company_id', 'status', 'limit', 'offset')
            return EventStore(crm).list(q=q, kind=kind, starts_from=starts_from, starts_before=starts_before, contact_id=contact_id, deal_id=deal_id, company_id=company_id, status=status, limit=limit, offset=offset)

    @router.get('/events/{record_id}')
    def event(request: Request, record_id: str, workspace_token: str):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token')
            return EventStore(crm).get(record_id, include_text=True)

    @router.post('/events', status_code=201)
    def create_event(request: Request, body: CreateBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return EventStore(crm).create(body.data, actor=actor, key=body.idempotency_key)

    @router.patch('/events/{record_id}')
    def update_event(request: Request, record_id: str, body: UpdateBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return EventStore(crm).update(record_id, body.data, expected_version=body.expected_version, actor=actor, key=body.idempotency_key)

    @router.post('/events/{record_id}/complete')
    def complete_event(request: Request, record_id: str, body: CompleteBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return EventStore(crm).complete(record_id, body.data, expected_version=body.expected_version, actor=actor, key=body.idempotency_key)

    @router.post('/events/{record_id}/cancel')
    def cancel_event(request: Request, record_id: str, body: ReasonBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return EventStore(crm).cancel(record_id, body.reason, expected_version=body.expected_version, actor=actor, key=body.idempotency_key)

    @router.post('/events/{record_id}/reopen')
    def reopen_event(request: Request, record_id: str, body: ReasonBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return EventStore(crm).reopen(record_id, body.reason, expected_version=body.expected_version, actor=actor, key=body.idempotency_key)

    @router.get('/events/{record_id}/revisions')
    def revisions(request: Request, record_id: str, workspace_token: str,
                  limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'limit', 'offset')
            return EventStore(crm).revisions(record_id, limit=limit, offset=offset, include_text=True)

    @router.get('/relationship-activities')
    def activities(request: Request, workspace_token: str, company_id: str | None = None,
                   contact_id: str | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'company_id', 'contact_id', 'limit', 'offset')
            return RelationshipQueries(crm).relationship_activities(company_id=company_id, contact_id=contact_id, limit=limit, offset=offset)

    @router.get('/record-history')
    def history(request: Request, workspace_token: str, entity_type: str | None = None, entity_id: str | None = None,
                limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'entity_type', 'entity_id', 'limit', 'offset')
            return RelationshipQueries(crm).record_history(kind=entity_type, record_id=entity_id, limit=limit, offset=offset)

    @router.post('/events/{record_id}/needs-rescheduling')
    def needs_rescheduling(request: Request, record_id: str, body: ReasonBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return EventStore(crm).needs_rescheduling(record_id, body.reason, expected_version=body.expected_version, actor=actor, key=body.idempotency_key)

    @router.post('/events/{record_id}/reschedule')
    def reschedule(request: Request, record_id: str, body: UpdateBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return EventStore(crm).reschedule(record_id, body.data, expected_version=body.expected_version, actor=actor, key=body.idempotency_key)

    @router.get('/events/{record_id}/tasks')
    def event_tasks(request: Request, record_id: str, workspace_token: str,
                    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'limit', 'offset')
            return RelationshipQueries(crm).event_tasks(record_id, limit=limit, offset=offset)

    @router.post('/events/{record_id}/tasks', status_code=201)
    def create_event_task(request: Request, record_id: str, body: UpdateBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return EventStore(crm).create_task(record_id, body.data, expected_version=body.expected_version, actor=actor, key=body.idempotency_key)

    @router.put('/tasks/{record_id}/event')
    def link_event_task(request: Request, record_id: str, body: TaskLinkBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return EventStore(crm).link_task(body.event_id, record_id, expected_version=body.expected_version, expected_task_version=body.expected_task_version, actor=actor, key=body.idempotency_key)

    @router.post('/tasks/{record_id}/event/unlink')
    def unlink_event_task(request: Request, record_id: str, body: TaskUnlinkBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return EventStore(crm).unlink_task(record_id, event_id=body.event_id, expected_version=body.expected_version, expected_task_version=body.expected_task_version, actor=actor, key=body.idempotency_key)

    @router.get('/contacts/{record_id}/relationship-tasks')
    def contact_tasks(request: Request, record_id: str, workspace_token: str,
                      limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'limit', 'offset')
            return RelationshipQueries(crm).contact_tasks(record_id, limit=limit, offset=offset)

    @router.get('/relationship-selectors/{kind}')
    def selectors(request: Request, kind: Literal['contacts', 'deals', 'tasks'], workspace_token: str,
                  q: str = '', limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'q', 'limit', 'offset')
            return RelationshipQueries(crm).selectors(kind, q=q, limit=limit, offset=offset)

    return router
