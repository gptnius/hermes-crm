"""UI-only, workspace-bound CSV operations. No agent tools or automatic replay."""
import json
from typing import Literal
from fastapi import APIRouter, Request, Response, Query, HTTPException
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from .domain import CRMError, validate_query
from .contact_transfer import ContactTransfer, MAX_BYTES, MAX_ROWS


class Scope(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)


class Preview(Scope):
    csv_text: str = Field(max_length=MAX_BYTES)
    mapping: dict[str, str | None] | None = None
    spreadsheet_safe: Literal[False] = False


class Import(Preview):
    mapping: dict[str, str | None]
    batch_id: str = Field(min_length=36, max_length=36)
    expected_fingerprint: str = Field(min_length=64, max_length=64)
    approved_rows: list[int] = Field(min_length=1, max_length=MAX_ROWS)
    duplicate_policy: Literal['skip', 'reject'] = 'skip'


class Export(Scope):
    operation_id: str = Field(min_length=36, max_length=36)
    columns: list[str] | None = Field(default=None, max_length=106)
    filters: dict = Field(default_factory=dict)
    spreadsheet_safe: Literal[True] = True


class TransferRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def protected(request):
            headers = {'Cache-Control': 'no-store', 'Pragma': 'no-cache'}
            try:
                if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                    raw = await request.body()
                    # JSON escaping may expand a bounded UTF-8 CSV up to sixfold.
                    if len(raw) > MAX_BYTES * 6 + 100000: raise CRMError('Contact transfer request exceeds limit', 413)
                    def unique(pairs):
                        result = {}
                        for key, value in pairs:
                            if key in result: raise ValueError()
                            result[key] = value
                        return result
                    try: json.loads(raw, object_pairs_hook=unique)
                    except Exception: raise CRMError('Invalid contact transfer request', 422) from None
                response = await handler(request)
                response.headers.update(headers)
                return response
            except RequestValidationError:
                return JSONResponse({'error': 'Invalid contact transfer request'}, status_code=422, headers=headers)
            except CRMError as error:
                return JSONResponse({'error': error.message}, status_code=error.status, headers=headers)
            except HTTPException as error:
                return JSONResponse({'error': 'Contact transfer request denied'}, status_code=error.status_code, headers=headers)
            except Exception:
                return JSONResponse({'error': 'Contact transfer unavailable; check the original operation outcome before retrying'}, status_code=503, headers=headers)
        return protected


def build_router(service, require_workspace):
    router = APIRouter(route_class=TransferRoute)
    def check(request, crm, token, *allowed):
        validate_query(request.query_params, {'profile', *allowed})
        require_workspace(crm, token)

    @router.get('/contact-transfer/catalog')
    def catalog(request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token')
            return ContactTransfer(crm).catalog()

    @router.post('/contact-transfer/preview')
    def preview(body: Preview, request: Request):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return ContactTransfer(crm).preview(**body.model_dump(exclude={'workspace_token'}))

    @router.post('/contact-transfer/import')
    def commit(body: Import, request: Request):
        with service() as crm:
            check(request, crm, body.workspace_token)
            return ContactTransfer(crm).commit(**body.model_dump(exclude={'workspace_token'}))

    @router.get('/contact-transfer/imports/{batch_id}')
    def receipt(batch_id: str, request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token')
            return ContactTransfer(crm).receipt(batch_id)

    @router.post('/contact-transfer/export')
    def export(body: Export, request: Request):
        from .contact_transfer_runtime import export_artifact
        with service() as crm:
            check(request, crm, body.workspace_token)
            return export_artifact(ContactTransfer(crm), body.operation_id, columns=body.columns, filters=body.filters)

    @router.get('/contact-transfer/export/operations/{operation_id}')
    def export_status(operation_id: str, request: Request, workspace_token: str = Query(..., min_length=1, max_length=80)):
        from .contact_transfer_runtime import export_operation_status
        with service() as crm:
            check(request, crm, workspace_token, 'workspace_token')
            return export_operation_status(ContactTransfer(crm), operation_id)

    return router
