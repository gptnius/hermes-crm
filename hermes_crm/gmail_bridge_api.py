"""Authenticated native-only existing connection controls; no ambient routing."""
from typing import Annotated, Literal
import time
from fastapi import APIRouter, Request, Query, Path
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .domain import CRMError, validate_query
from .gmail_bridge_store import GmailBridgeStore
from .gmail_bridge_runtime import gmail_bridge_runtime
from .gmail_incremental import DAY_MS

Mailbox = Annotated[str, Field(min_length=3, max_length=254)]


class Operation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(ge=0)
    operation_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,120}$')

class Verify(Operation):
    own_mailbox: str = Field(min_length=3, max_length=254)
    own_aliases: list[Mailbox] = Field(default_factory=list, max_length=20)
    consent: Literal[True]

    @field_validator('consent', mode='before')
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError('Explicit consent required')
        return value

class Sync(Operation):
    mode: Literal['incremental', '7days', '30days'] = 'incremental'
    trigger: Literal['manual', 'poll'] = 'manual'
    consent: Literal[True]

    @field_validator('consent', mode='before')
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError('Explicit consent required')
        return value

class Control(Operation):
    action: Literal['pause', 'resume', 'disconnect', 'clear', 'start_polling', 'stop_polling']
    confirm: bool = False

class Aliases(Operation):
    contact_id: str = Field(min_length=1, max_length=36)
    contact_version: int = Field(ge=1)
    aliases: list[Mailbox] = Field(max_length=20)


def public_receipt(value):
    if value is None:
        return None
    # Never expose lease tokens, scope, selector fingerprints or private paths.
    result = {k: value[k] for k in ('revision', 'account_namespace', 'enabled', 'outcome', 'status') if k in value}
    if 'lease' in value and not value.get('outcome'):
        result['status'] = 'unknown' if value['lease']['expires_at'] <= time.time() else 'running'
    return result


def build_router(service, require_workspace, runtime_factory=gmail_bridge_runtime):
    router = APIRouter(prefix='/email-bridge')

    def checked(request, crm, token, allowed=()):
        try:
            # Reserved host routing query is accepted but never used here.
            # The trusted service determines profile; workspace token still fences it.
            validate_query(request.query_params, {'profile', *allowed})
        except CRMError:
            raise CRMError('Invalid Gmail bridge query') from None
        require_workspace(crm, token)

    @router.get('/setup')
    def setup(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            checked(request, crm, workspace_token, {'workspace_token'})
            return runtime_factory(crm).setup()

    @router.get('/status')
    def status(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            checked(request, crm, workspace_token, {'workspace_token'})
            return dict(GmailBridgeStore(crm).status(), runtime=runtime_factory(crm).setup())

    @router.get('/operations/{key}')
    def operation(request: Request, key: str = Path(..., pattern=r'^[A-Za-z0-9_-]{1,120}$'),
                  workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            checked(request, crm, workspace_token, {'workspace_token'})
            return public_receipt(GmailBridgeStore(crm).operation_receipt(key))

    @router.get('/contacts/{contact_id}')
    def history(request: Request, contact_id: str = Path(..., min_length=1, max_length=36),
                workspace_token: str = Query(..., min_length=1, max_length=80),
                limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
        with service() as crm:
            checked(request, crm, workspace_token, {'workspace_token', 'limit', 'offset'})
            return GmailBridgeStore(crm).page(contact_id=contact_id, limit=limit, offset=offset)

    @router.get('/companies/{company_id}')
    def company_history(request: Request, company_id: str = Path(..., min_length=1, max_length=36),
                        workspace_token: str = Query(..., min_length=1, max_length=80),
                        limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
        with service() as crm:
            checked(request, crm, workspace_token, {'workspace_token', 'limit', 'offset'})
            return GmailBridgeStore(crm).page(company_id=company_id, limit=limit, offset=offset)

    @router.get('/unresolved')
    def unresolved(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80),
                   limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
        with service() as crm:
            checked(request, crm, workspace_token, {'workspace_token', 'limit', 'offset'})
            return GmailBridgeStore(crm).page(unresolved=True, limit=limit, offset=offset)

    @router.post('/control')
    def control(request: Request, body: Control):
        with service() as crm:
            checked(request, crm, body.workspace_token)
            if body.action == 'clear' and body.confirm is not True:
                raise CRMError('Explicit clear confirmation required')
            return GmailBridgeStore(crm).control(body.operation_key, action=body.action, expected_revision=body.expected_revision)

    @router.post('/aliases')
    def aliases(request: Request, body: Aliases):
        with service() as crm:
            checked(request, crm, body.workspace_token)
            return GmailBridgeStore(crm).set_contact_aliases(body.operation_key, contact_id=body.contact_id,
                contact_version=body.contact_version, aliases=body.aliases, expected_revision=body.expected_revision)

    @router.post('/verify')
    def verify(request: Request, body: Verify):
        with service() as crm:
            checked(request, crm, body.workspace_token)
            runtime, store = runtime_factory(crm), GmailBridgeStore(crm)
            runtime.guard()
            intent = dict(selector_fingerprint=runtime.selector_fingerprint, mailbox=body.own_mailbox,
                          own_aliases=body.own_aliases, expected_revision=body.expected_revision)
            reservation = store.reserve_verify(body.operation_key, **intent)
            if not reservation:
                return public_receipt(store.operation_receipt(body.operation_key))
            try:
                with runtime.reader(body.own_mailbox, lease_guard=lambda: store.status()['revision'] == body.expected_revision) as (reader, guard):
                    verified = reader.verify_mailbox(body.own_mailbox, guard=guard)
                result = store.complete_verify(body.operation_key, **intent,
                    initial_checkpoint=verified.checkpoint, check_guard=runtime.host_guard)
                return public_receipt(result)
            except Exception:
                store.fail_verify(body.operation_key, **intent)
                return public_receipt(store.operation_receipt(body.operation_key))

    @router.post('/sync')
    def sync(request: Request, body: Sync):
        with service() as crm:
            checked(request, crm, body.workspace_token)
            runtime, store = runtime_factory(crm), GmailBridgeStore(crm)
            runtime.guard()
            if body.trigger == 'poll' and not store.status().get('polling_enabled', False):
                raise CRMError('App-open polling has not been approved', 409)
            lease = store.begin_sync_once(body.operation_key, expected_revision=body.expected_revision, mode=body.mode, trigger=body.trigger)
            if lease is None:
                return public_receipt(store.operation_receipt(body.operation_key))
            try:
                if lease.selector_fingerprint != runtime.selector_fingerprint:
                    raise CRMError('Selected connection changed', 409)
                with runtime.reader(lease.mailbox, lease_guard=lambda: store.validate_lease(lease)) as (reader, guard):
                    if body.mode == 'incremental':
                        if lease.checkpoint is None:
                            raise CRMError('Choose an explicit new start or historical window', 409)
                        result = reader.incremental(lease.mailbox, lease.checkpoint, guard=guard)
                    else:
                        end = int(runtime.clock() * 1000)
                        days = 7 if body.mode == '7days' else 30
                        result = reader.bootstrap(lease.mailbox, end - days * DAY_MS, end, guard=guard)
                store.finish_sync(lease, result, check_guard=runtime.host_guard)
            except Exception:
                try:
                    store.fail_sync(lease, unknown=True)
                except CRMError:
                    pass  # Local control may already have fenced and cancelled it.
            return public_receipt(store.operation_receipt(body.operation_key))

    return router
