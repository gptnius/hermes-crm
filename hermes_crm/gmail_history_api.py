"""Authenticated Desktop-only email routes; never exported as model tools."""
from typing import Literal
from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from .domain import CRMError, validate_query
from .gmail_history import GmailHistoryStore


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(ge=0)


class VerifyRequest(RevisionRequest):
    operation_id: str = Field(min_length=36, max_length=36)
    mailbox: str = Field(min_length=3, max_length=254)
    consent: Literal[True]


class SyncRequest(RevisionRequest):
    operation_id: str = Field(min_length=36, max_length=36)
    contact_id: str = Field(min_length=1, max_length=36)
    expected_contact_version: int = Field(ge=1)
    days: Literal[7, 30]
    consent: Literal[True]


class LocalRequest(RevisionRequest):
    operation_id: str = Field(min_length=36, max_length=36)


class ClearRequest(LocalRequest):
    confirm: Literal[True]


def build_router(service, require_workspace, runtime_factory):
    """runtime_factory(crm) supplies trusted enabled, reader and profile guard.

    Factory must not perform provider reads or authorization on construction.
    The host routing profile may be present in query; never forward it to reader.
    """
    router = APIRouter()

    def checked(request, crm, token, allowed=()):
        validate_query(request.query_params, {'profile', *allowed})
        require_workspace(crm, token)

    @router.get('/email/status')
    def status(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            checked(request, crm, workspace_token, {'workspace_token'})
            runtime = runtime_factory(crm)
            return GmailHistoryStore(crm).status(enabled=runtime['enabled'])

    @router.get('/email/setup')
    def setup(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            checked(request, crm, workspace_token, {'workspace_token'})
            return dict(enabled=runtime_factory(crm)['enabled'], provider='Google Gmail',
                mode='Manual own-mailbox contact metadata only', windows=[7, 30],
                authorization='Host-managed optional CRM-owned OAuth grant; this endpoint does not authorize or discover accounts.',
                scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/gmail.readonly'],
                warning='Gmail readonly can read bodies, although this application requests selected metadata only. No sending or drafting.',
                retention='Local metadata persists until explicitly cleared. Disconnect does not revoke Google authorization.',
                continuity='Before/after identity checks do not prove atomic grant continuity. Do not change grants or profiles during a read.')

    @router.get('/email/operations/{operation_id}')
    def operation(request: Request, operation_id: str = Path(..., min_length=36, max_length=36),
                  workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            checked(request, crm, workspace_token, {'workspace_token'})
            return GmailHistoryStore(crm).operation(operation_id)

    @router.get('/email/contacts/{contact_id}')
    def history(request: Request, contact_id: str = Path(..., min_length=1, max_length=36),
                workspace_token: str = Query(..., min_length=1, max_length=80),
                limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        with service() as crm:
            checked(request, crm, workspace_token, {'workspace_token', 'limit', 'offset'})
            return GmailHistoryStore(crm).page(contact_id, limit=limit, offset=offset)

    def run(request, body, kind):
        with service() as crm:
            checked(request, crm, body.workspace_token)
            runtime = runtime_factory(crm)
            if not runtime['enabled'] or runtime.get('reader') is None or not callable(runtime.get('guard')):
                raise CRMError('Optional Gmail reads are disabled or not configured', 503)
            store = GmailHistoryStore(crm, initialize=True)
            operation = store.run(kind=kind, reader=runtime['reader'], guard=runtime['guard'],
                **body.model_dump(exclude={'workspace_token', 'consent'}))
            return dict(store.status(enabled=True), operation=operation)

    @router.post('/email/verify')
    def verify(request: Request, body: VerifyRequest):
        return run(request, body, 'verify')

    @router.post('/email/sync')
    def sync(request: Request, body: SyncRequest):
        return run(request, body, 'sync')

    def local(request, body, kind):
        with service() as crm:
            checked(request, crm, body.workspace_token)
            runtime = runtime_factory(crm)
            store = GmailHistoryStore(crm, initialize=True)
            operation = store.mutate_local(kind, body.expected_revision, body.operation_id)
            return dict(store.status(enabled=runtime['enabled']), operation=operation)

    @router.post('/email/disconnect')
    def disconnect(request: Request, body: LocalRequest):
        return local(request, body, 'disconnect')

    @router.post('/email/clear')
    def clear(request: Request, body: ClearRequest):
        return local(request, body, 'clear')

    return router
