"""UI-facing routes; no agent tools. Mount inside authenticated native router."""
from typing import Literal
from fastapi import APIRouter, Request, Query, Response, HTTPException
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
import json
from pydantic import BaseModel, ConfigDict, Field
from .domain import CRMError, validate_query
from .protection import ProtectionStore

Kind = Literal['contacts','deals','tasks']

class WorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    workspace_token: str = Field(min_length=1, max_length=80)

class ExportRequest(WorkspaceRequest):
    operation_id: str = Field(min_length=36, max_length=36)

class SaveRequest(WorkspaceRequest):
    operation_id: str = Field(min_length=36, max_length=36)
    expected_record_version: int = Field(ge=1)
    expected_note_version: int = Field(ge=0)
    plaintext: str = Field(max_length=16000)


class ProtectedRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def protected(request):
            headers = {'Cache-Control':'no-store','Pragma':'no-cache'}
            try:
                if request.method in ('POST','PUT','PATCH'):
                    raw = await request.body()
                    if len(raw) > 150000: raise CRMError('Protection request exceeds size limit', 413)
                    def unique(pairs):
                        data = {}
                        for key,value in pairs:
                            if key in data: raise ValueError()
                            data[key] = value
                        return data
                    try: json.loads(raw, object_pairs_hook=unique)
                    except Exception: raise CRMError('Invalid protection request', 422) from None
                response = await handler(request)
                response.headers.update(headers)
                return response
            except RequestValidationError:
                return JSONResponse({'error':'Invalid protection request'}, status_code=422, headers=headers)
            except ResponseValidationError:
                return JSONResponse({'error':'Protection response unavailable'}, status_code=503, headers=headers)
            except HTTPException as error:
                messages = {400:'Invalid protection request',401:'Authentication required',403:'Protection access denied',404:'Protection record not found',409:'Protection operation conflict; refresh or check the original outcome',413:'Protection payload exceeds limit',422:'Invalid protection request',503:'Protection operation unavailable'}
                status = error.status_code if error.status_code in messages else 503
                return JSONResponse({'error':messages[status]}, status_code=status, headers=headers)
            except CRMError as error:
                return JSONResponse({'error':error.message}, status_code=error.status, headers=headers)
            except Exception:
                return JSONResponse({'error':'Protection operation unavailable'}, status_code=503, headers=headers)
        return protected


def build_router(service, require_workspace, key_resolver):
    router = APIRouter(route_class=ProtectedRoute)
    def checked(request, crm, token, response, allowed=()):
        try: validate_query(request.query_params, {'profile', *allowed})
        except CRMError: raise CRMError('Invalid protection query') from None
        require_workspace(crm, token)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'

    @router.get('/protection/status')
    def status(request: Request, response: Response, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            checked(request,crm,workspace_token,response,{'workspace_token'})
            result = {}
            for purpose in ('notes','backup'):
                try: key_resolver(purpose); result[purpose+'_enabled'] = True
                except CRMError: result[purpose+'_enabled'] = False
            return result

    @router.get('/protection/notes/{kind}/{record_id}')
    def note_status(kind: Kind, record_id: str, request: Request, response: Response, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            checked(request,crm,workspace_token,response,{'workspace_token'})
            return ProtectionStore(crm).status(kind,record_id)

    @router.get('/protection/notes/{kind}/{record_id}/operations/{operation_id}')
    def operation(kind: Kind, record_id: str, operation_id: str, request: Request, response: Response, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            checked(request,crm,workspace_token,response,{'workspace_token'})
            return ProtectionStore(crm).operation(kind,record_id,operation_id)

    @router.post('/protection/notes/{kind}/{record_id}/reveal')
    def reveal(kind: Kind, record_id: str, body: WorkspaceRequest, request: Request, response: Response):
        with service() as crm:
            checked(request,crm,body.workspace_token,response)
            return ProtectionStore(crm).reveal(kind,record_id,key_resolver('notes'))

    @router.put('/protection/notes/{kind}/{record_id}')
    def save(kind: Kind, record_id: str, body: SaveRequest, request: Request, response: Response):
        with service() as crm:
            checked(request,crm,body.workspace_token,response)
            return ProtectionStore(crm).save(kind,record_id,ring=key_resolver('notes'),**body.model_dump(exclude={'workspace_token'}))

    @router.get('/protection/export/operations/{operation_id}')
    def export_operation(operation_id: str, request: Request, response: Response, workspace_token: str = Query(..., min_length=1, max_length=80)):
        with service() as crm:
            checked(request,crm,workspace_token,response,{'workspace_token'})
            from .protection_runtime import export_operation_status
            return export_operation_status(ProtectionStore(crm), key_resolver('backup'), operation_id)

    @router.post('/protection/export')
    def export(body: ExportRequest, request: Request, response: Response):
        with service() as crm:
            checked(request,crm,body.workspace_token,response)
            from .protection_runtime import export_artifact
            return export_artifact(ProtectionStore(crm), key_resolver('backup'), body.operation_id)
    return router
