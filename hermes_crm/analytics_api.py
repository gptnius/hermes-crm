"""Authenticated native reports, saved dashboards and authored contact logs.

These routes never read Gmail, dispatch agents, send messages or export SQL.
The host supplies the profile; workspace tokens only reject stale clients.
"""
from typing import Any
from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from .domain import CRMError, validate_query
from .reports import ReportEngine
from .report_store import ReportStore
from .report_interactions import InteractionStore
from .report_tools import current_report


class ScopedBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)


class RunBody(ScopedBody):
    definition: dict[str, Any]
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=2_000_000_000)
    evaluated_at: str | None = Field(default=None, max_length=80)


class SavedRunBody(ScopedBody):
    expected_version: int = Field(ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=2_000_000_000)
    evaluated_at: str | None = Field(default=None, max_length=80)


class CreateReportBody(ScopedBody):
    title: str = Field(min_length=1, max_length=160)
    definition: dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=160)


class UpdateReportBody(CreateReportBody):
    expected_version: int = Field(ge=1)


class VersionBody(ScopedBody):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=160)


class DashboardBody(ScopedBody):
    expected_version: int = Field(ge=0)
    cards: list[dict[str, Any]] = Field(max_length=12)
    idempotency_key: str = Field(min_length=1, max_length=160)


class InteractionBody(ScopedBody):
    data: dict[str, Any]
    expected_contact_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=160)


class VoidBody(VersionBody):
    reason: str = Field(min_length=1, max_length=500)


def build_router(service, require_workspace):
    router = APIRouter()

    def check(request, crm, token, *allowed):
        validate_query(request.query_params, {'profile', *allowed})
        require_workspace(crm, token)

    @router.get('/analytics/catalog')
    def catalog(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token')
            return ReportEngine(crm).catalog()

    @router.post('/analytics/run')
    def run(request: Request, body: RunBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return ReportEngine(crm).run(**body.model_dump(exclude={'workspace_token'}))

    @router.get('/analytics/reports')
    def reports(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80),
                include_archived: bool = False, limit: int = Query(50, ge=1, le=100),
                offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'include_archived', 'limit', 'offset')
            return ReportStore(crm).list(include_archived=include_archived, limit=limit, offset=offset)

    @router.get('/analytics/reports/{report_id}')
    def get_report(request: Request, report_id: str = Path(..., min_length=1, max_length=36),
                   workspace_token: str = Query(..., min_length=1, max_length=80),
                   version: int | None = Query(None, ge=1)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'version')
            return current_report(crm, report_id, version)

    @router.post('/analytics/reports', status_code=201)
    def create_report(request: Request, body: CreateReportBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return ReportStore(crm).create(body.title, body.definition, body.idempotency_key)

    @router.patch('/analytics/reports/{report_id}')
    def update_report(request: Request, body: UpdateReportBody, report_id: str = Path(..., min_length=1, max_length=36)):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return ReportStore(crm).update(report_id, body.title, body.definition, body.expected_version, body.idempotency_key)

    @router.post('/analytics/reports/{report_id}/archive')
    def archive_report(request: Request, body: VersionBody, report_id: str = Path(..., min_length=1, max_length=36)):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return ReportStore(crm).archive(report_id, body.expected_version, body.idempotency_key)

    @router.post('/analytics/reports/{report_id}/restore')
    def restore_report(request: Request, body: VersionBody, report_id: str = Path(..., min_length=1, max_length=36)):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return ReportStore(crm).restore(report_id, body.expected_version, body.idempotency_key)

    @router.post('/analytics/reports/{report_id}/run')
    def saved_run(request: Request, body: SavedRunBody, report_id: str = Path(..., min_length=1, max_length=36)):
        with service() as crm:
            check(request, crm, body.workspace_token)
            row = current_report(crm, report_id, body.expected_version)
            if row['archived_at'] is not None:
                raise CRMError('This report is archived. Restore it before running.', 409)
            return ReportEngine(crm).run(row['definition'], limit=body.limit, offset=body.offset, evaluated_at=body.evaluated_at)

    @router.get('/analytics/dashboard')
    def dashboard(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token')
            return ReportStore(crm).get_dashboard()

    @router.put('/analytics/dashboard')
    def save_dashboard(request: Request, body: DashboardBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return ReportStore(crm).save_dashboard(body.cards, body.expected_version, body.idempotency_key)

    @router.get('/interactions')
    def interactions(request: Request, contact_id: str = Query(..., min_length=1, max_length=36),
                     workspace_token: str = Query(..., min_length=1, max_length=80),
                     include_voided: bool = False, limit: int = Query(50, ge=1, le=100),
                     offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token', 'contact_id', 'include_voided', 'limit', 'offset')
            return InteractionStore(crm).list(contact_id, include_voided=include_voided, limit=limit, offset=offset)

    @router.post('/interactions', status_code=201)
    def log_interaction(request: Request, body: InteractionBody):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return InteractionStore(crm).create(body.data, body.expected_contact_version, 'desktop', body.idempotency_key)

    @router.post('/interactions/{interaction_id}/void')
    def void_interaction(request: Request, body: VoidBody, interaction_id: str = Path(..., min_length=1, max_length=36)):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return InteractionStore(crm).void(interaction_id, body.expected_version, body.reason, 'desktop', body.idempotency_key)

    return router
