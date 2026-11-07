from __future__ import annotations
import argparse
from pathlib import Path
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .domain import CRM, CRMError, CONTACT_REPORT_FILTERS, LIST_FILTERS, validate_query

def create_app(crm=None):
    crm = crm or CRM()
    app = FastAPI(title='Hermes CRM', docs_url='/api/docs', redoc_url=None)
    app.state.crm = crm
    # Loopback-only service: not a multi-user public API.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1','localhost','[::1]','testserver'])
    @app.middleware('http')
    async def local_origin(request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET','HEAD','OPTIONS'):
            # Every browser write must be same-origin. CLI requests without Origin are permitted locally.
            if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
                return JSONResponse({'error':'Cross-origin writes are not allowed'},status_code=403)
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'error':'Cross-site writes are not allowed'},status_code=403)
            if 'application/json' not in request.headers.get('content-type',''):
                return JSONResponse({'error':'Content-Type application/json is required'},status_code=415)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response
    @app.exception_handler(CRMError)
    async def domain_error(request, exc): return JSONResponse({'error':exc.message},status_code=exc.status)
    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        errors = '; '.join(f"{'.'.join(map(str,e['loc']))}: {e['msg']}" for e in exc.errors())
        return JSONResponse({'error':errors},status_code=422)
    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse({'error':'The operation failed. No database credentials or internal paths are exposed.'},status_code=500)
    @app.get('/api/meta')
    def meta(): return crm.info()
    @app.get('/api/overview')
    def overview(): return crm.overview(include_task_assignments=True)
    @app.get('/api/activity')
    def activities(): return crm.activities()
    @app.get('/api/contacts/{record_id}')
    def contact_detail(record_id:str): return crm.contact_detail(record_id)
    @app.get('/api/reports/contacts')
    def contact_report(request: Request, q: str = '', stage: str | None = None, contact_type: str | None = None,
                       company: str = '', email: str = 'any', followup: str = 'any',
                       limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=2_000_000_000)):
        validate_query(request.query_params, CONTACT_REPORT_FILTERS)
        return crm.contact_report(q=q, stage=stage, contact_type=contact_type, company=company,
                                  email=email, followup=followup, limit=limit, offset=offset)
    @app.get('/api/{kind}')
    def listing(request:Request, kind:str, q:str='', stage:str|None=None, status:str|None=None,
                contact_type:str|None=None, company:str='', email:str='any', followup:str='any',
                min_value:int|None=None, max_value:int|None=None, priority:str|None=None, due:str='any'):
        if kind not in ('contacts','deals','tasks'): raise CRMError('Endpoint not found',404)
        validate_query(request.query_params, LIST_FILTERS)
        return crm.list(kind,q=q,stage=stage,status=status,contact_type=contact_type,company=company,
                        email=email,followup=followup,min_value=min_value,max_value=max_value,priority=priority,due=due)
    @app.get('/api/{kind}/{record_id}')
    def record(kind:str,record_id:str):
        if kind not in ('deals','tasks'): raise CRMError('Endpoint not found',404)
        return crm.get(kind,record_id)
    @app.post('/api/{kind}',status_code=201)
    async def create(kind:str,request:Request):
        if kind not in ('contacts','deals','tasks'): raise CRMError('Endpoint not found',404)
        try: data=await request.json()
        except ValueError: raise CRMError('Invalid JSON')
        return crm.create(kind,data,actor='ui',key=request.headers.get('idempotency-key'))
    @app.patch('/api/{kind}/{record_id}')
    async def patch(kind:str,record_id:str,request:Request):
        if kind not in ('contacts','deals','tasks'): raise CRMError('Endpoint not found',404)
        try: data=await request.json()
        except ValueError: raise CRMError('Invalid JSON')
        if not isinstance(data,dict): raise CRMError('Expected a JSON object')
        return crm.update(kind,record_id,data,actor='ui')
    static = Path(__file__).parent/'static'
    app.mount('/static',StaticFiles(directory=static),name='static')
    @app.get('/')
    def index(): return FileResponse(static/'index.html')
    return app

def main():
    parser=argparse.ArgumentParser(description='Local Hermes CRM. No public network binding.')
    parser.add_argument('--port',type=int,default=8742)
    parser.add_argument('--demo',action='store_true',help='Seed an empty workspace with synthetic data')
    args=parser.parse_args()
    crm=CRM()
    if args.demo:
        from .demo import seed
        seed(crm)
    import uvicorn
    uvicorn.run(create_app(crm),host='127.0.0.1',port=args.port)
if __name__=='__main__': main()
