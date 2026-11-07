"""Hermes' authenticated, profile-scoped plugin REST adapter.

This exports routes, never a server. Hermes owns authentication, admission and
profile/secret scope. Synchronous handlers run in its worker pool, not event loop.
"""
from contextlib import contextmanager
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .coverage import coverage_report
from .domain import CRMError, CONTACT_REPORT_FILTERS, LIST_FILTERS, validate_query
from .native_work import NativeWorkStore
from .native_work_operations import command_name
from .runtime import open_profile_crm

router = APIRouter()


class WriteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    data: dict[str, Any]
    workspace_token: str = Field(min_length=1, max_length=80)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirm: Literal[True]
    workspace_token: str = Field(min_length=1, max_length=80)


class WorkSaveRequest(BaseModel):
    """Reviewed local intent, never a dispatch request or caller-selected profile."""
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)
    task_id: str = Field(min_length=1, max_length=36)
    expected_task_version: int = Field(ge=1)
    human_owner: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=50000)
    success_criteria: str = Field(min_length=1, max_length=10000)
    run_at: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=1, max_length=160)


@contextmanager
def service():
    crm = None
    try:
        crm = open_profile_crm()
        yield crm
    except CRMError as exc:
        raise HTTPException(exc.status, detail={'error': exc.message}) from None
    except ValidationError as exc:
        message = '; '.join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise HTTPException(422, detail={'error': message}) from None
    except HTTPException:
        raise
    except Exception:
        # Do not echo database URLs, profile paths or credential-bearing exceptions.
        raise HTTPException(503, detail={'error': 'CRM backend unavailable. Check this profile’s plugin settings. No fallback was used.'}) from None
    finally:
        if crm is not None:
            crm.close()


def require_workspace(crm, supplied):
    if supplied != crm.workspace_token():
        raise CRMError('The workspace changed. Refresh and reopen the form before saving.', 409)


def metadata(crm):
    return dict(crm.info(), workspace_token=crm.workspace_token(),
                native_desktop=True, scheduler='existing-agent', api_version=1,
                work_command_name=command_name(crm.workspace_token(), crm.profile))


@router.get('/meta')
def meta():
    with service() as crm:
        return metadata(crm)


# Keep these fixed paths before the generic /{kind} routes. REST only prepares,
# observes and withdraws local operations; the real native command owns dispatch.
from .native_work_operations_api import build_router
router.include_router(build_router(service, require_workspace))

# Separate authenticated endpoints: mailbox metadata never enters crm_read or
# the ordinary contact/snapshot responses. Loading routes performs no OAuth.
from .gmail_history_api import build_router as build_email_router
from .gmail_runtime import gmail_runtime
router.include_router(build_email_router(service, require_workspace, gmail_runtime))

from .analytics_api import build_router as build_analytics_router
router.include_router(build_analytics_router(service, require_workspace))


@router.get('/snapshot')
def snapshot():
    # One factory call binds the whole refresh to one selected backend/workspace.
    with service() as crm:
        return dict(meta=metadata(crm), overview=crm.overview(),
                    contacts=crm.list('contacts'), deals=crm.list('deals'),
                    tasks=crm.list('tasks'), activity=crm.activities())


@router.get('/overview')
def overview():
    with service() as crm:
        return crm.overview()


@router.get('/activity')
def activity():
    with service() as crm:
        return crm.activities()


@router.get('/contacts/{record_id}')
def contact_detail(record_id: str, workspace_token: str | None = None):
    with service() as crm:
        if workspace_token is not None: require_workspace(crm, workspace_token)
        return crm.contact_detail(record_id)


@router.get('/reports/contacts')
def contact_report(request: Request, q: str = '', stage: str | None = None, contact_type: str | None = None,
                   company: str = '', email: str = 'any', followup: str = 'any',
                   limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000),
                   workspace_token: str | None = None):
    with service() as crm:
        if workspace_token is not None: require_workspace(crm, workspace_token)
        # Hermes may retain its already-resolved routing parameter for the serving
        # profile. Tolerate it here; only the host selects the active CRM workspace.
        validate_query(request.query_params, CONTACT_REPORT_FILTERS | {'workspace_token', 'profile'})
        return crm.contact_report(q=q, stage=stage, contact_type=contact_type, company=company,
                                  email=email, followup=followup, limit=limit, offset=offset)


@router.get('/reports/coverage')
def coverage(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80),
             q: str = Query('', max_length=200), status: str = 'any',
             limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
    with service() as crm:
        validate_query(request.query_params, {'workspace_token', 'profile', 'q', 'status', 'limit', 'offset'})
        require_workspace(crm, workspace_token)
        return coverage_report(crm, q=q, status=status, limit=limit, offset=offset)


@router.get('/reports/work')
def work_page(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80),
              task_id: str | None = Query(None, min_length=1, max_length=36),
              limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
    with service() as crm:
        validate_query(request.query_params, {'workspace_token', 'profile', 'task_id', 'limit', 'offset'})
        require_workspace(crm, workspace_token)
        return NativeWorkStore(crm, initialize=False).page(task_id=task_id, limit=limit, offset=offset)


@router.get('/work')
def work_history(request: Request,
                 workspace_token: str = Query(..., min_length=1, max_length=80),
                 task_id: str | None = Query(None, min_length=1, max_length=36),
                 limit: int = Query(100, ge=1, le=100)):
    """Local assignment observations only; REST never receives a tool context."""
    with service() as crm:
        # The host already resolved profile routing before calling this handler.
        # A query parameter is not authority to select another CRM database.
        validate_query(request.query_params, {'workspace_token', 'profile', 'task_id', 'limit'})
        require_workspace(crm, workspace_token)
        return NativeWorkStore(crm, initialize=False).list(task_id=task_id, limit=limit)


@router.get('/work/{assignment_id}')
def work_detail(request: Request, assignment_id: str = Path(..., min_length=1, max_length=36),
                workspace_token: str = Query(..., min_length=1, max_length=80)):
    with service() as crm:
        validate_query(request.query_params, {'workspace_token', 'profile'})
        require_workspace(crm, workspace_token)
        return NativeWorkStore(crm, initialize=False).get(assignment_id)


@router.post('/work', status_code=201)
def save_work(request: Request, body: WorkSaveRequest):
    """Save durable intent only. There is no native tool/cron/model context here."""
    with service() as crm:
        # Hermes resolves profile routing. No request field can choose a backend
        # or override that profile, and the captured token must match it.
        validate_query(request.query_params, {'profile'})
        require_workspace(crm, body.workspace_token)
        return NativeWorkStore(crm).create(**body.model_dump(exclude={'workspace_token'}))


@router.get('/{kind}')
def listing(request: Request, kind: Literal['contacts', 'deals', 'tasks'], q: str = Query('', max_length=200),
            stage: str | None = None, status: str | None = None, workspace_token: str | None = None,
            contact_type: str | None = None, company: str = '', email: str = 'any', followup: str = 'any',
            min_value: int | None = None, max_value: int | None = None,
            priority: str | None = None, due: str = 'any'):
    with service() as crm:
        if workspace_token is not None: require_workspace(crm, workspace_token)
        validate_query(request.query_params, LIST_FILTERS | {'workspace_token', 'profile'})
        return crm.list(kind, q=q, stage=stage, status=status, contact_type=contact_type,
                        company=company, email=email, followup=followup, min_value=min_value,
                        max_value=max_value, priority=priority, due=due)


@router.get('/{kind}/{record_id}')
def record(kind: Literal['deals', 'tasks'], record_id: str, workspace_token: str | None = None):
    with service() as crm:
        if workspace_token is not None: require_workspace(crm, workspace_token)
        return crm.get(kind, record_id)


@router.post('/demo')
def demo(body: DemoRequest):
    from .demo import seed
    with service() as crm:
        require_workspace(crm, body.workspace_token)
        seed(crm)
        return dict(crm.info(), workspace_token=crm.workspace_token())


@router.post('/{kind}', status_code=201)
def create(kind: Literal['contacts', 'deals', 'tasks'], body: WriteRequest):
    with service() as crm:
        require_workspace(crm, body.workspace_token)
        return crm.create(kind, body.data, actor='desktop', key=body.idempotency_key)


@router.patch('/{kind}/{record_id}')
def patch(kind: Literal['contacts', 'deals', 'tasks'], record_id: str, body: WriteRequest):
    with service() as crm:
        require_workspace(crm, body.workspace_token)
        if body.idempotency_key is not None:
            raise CRMError('Updates use record versions, not create idempotency keys')
        return crm.update(kind, record_id, body.data, actor='desktop')
