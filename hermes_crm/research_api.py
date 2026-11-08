"""Shared workspace-token guarded research routes, no provider execution."""
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from .customization_api import CreateBody, unique_json
from .domain import validate_query
from .research_store import ResearchStore

def build_router(service, require_workspace, actor='ui'):
    router=APIRouter(dependencies=[Depends(unique_json)])
    def check(request,crm,token,read=False):
        allowed={'profile','workspace_token','target_kind','target_id','limit','offset'} if read else {'profile'}
        validate_query(request.query_params,allowed)
        require_workspace(crm,token)
    def add_list(kind):
        def listing(request:Request, target_kind:Literal['contacts','companies'],target_id:str=Query(...,min_length=36,max_length=36),workspace_token:str=Query(...,min_length=1,max_length=80),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=2_000_000_000)):
            with service() as crm:
                check(request,crm,workspace_token,True)
                return ResearchStore(crm).list(kind,target_kind,target_id,limit,offset)
        router.add_api_route('/research/'+kind,listing,methods=['GET'])
    for kind in ('evidence','proposals'): add_list(kind)
    def add_read(path,method):
        def read(request:Request,id:str,workspace_token:str=Query(...,min_length=1,max_length=80)):
            validate_query(request.query_params,{'profile','workspace_token'})
            with service() as crm:
                require_workspace(crm,workspace_token)
                return getattr(ResearchStore(crm),method)(id)
        router.add_api_route(path,read,methods=['GET'])
    add_read('/research/evidence/{id}','get_evidence')
    add_read('/research/proposals/{id}/preview','preview')
    add_read('/research/operations/{id}','receipt')
    def add_create(kind,method):
        def create(request:Request,body:CreateBody):
            with service() as crm:
                check(request,crm,body.workspace_token)
                return getattr(ResearchStore(crm),method)(body.data,key=body.idempotency_key,actor=actor)
        router.add_api_route('/research/'+kind,create,methods=['POST'],status_code=201)
    add_create('evidence','submit'); add_create('proposals','propose')
    def add_action(kind,action):
        def write(request:Request,id:str,body:CreateBody):
            with service() as crm:
                check(request,crm,body.workspace_token)
                store=ResearchStore(crm)
                if kind=='evidence': return store.lifecycle(id,body.data,archive=action=='archive',key=body.idempotency_key,actor=actor)
                return store.review(id,body.data,apply=action=='apply',key=body.idempotency_key,actor=actor)
        router.add_api_route('/research/'+kind+'/{id}/'+action,write,methods=['POST'])
    for action in ('archive','restore'): add_action('evidence',action)
    for action in ('apply','dismiss'): add_action('proposals',action)
    return router
