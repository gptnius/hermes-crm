"""Atomic relationship writes, scoped receipts and read-only schema detection."""
import hashlib
import json
import uuid
from contextlib import nullcontext
from sqlalchemy import select, func
from .domain import CRMError, settings
from .report_store import canonical, scope_for, transaction
from .relationship_schema import check_schema, operations

class RelationshipStore:
    def __init__(self,crm): self.crm=crm
    def exists(self,conn=None):
        with (nullcontext(conn) if conn is not None else self.crm._read_connection()) as c: return check_schema(self.crm,c)
    @staticmethod
    def _version(value):
        if type(value) is not int or value<1: raise CRMError('A current integer version is required',409)
    @staticmethod
    def _actor(value):
        if not isinstance(value,str) or not value.strip() or len(value)>160: raise CRMError('A trusted actor is required')
        return value.strip()
    @staticmethod
    def _decode(row,include_text=False):
        result=dict(row); result.pop('scope',None)
        if not include_text:
            for field in ('notes','outcome_summary'): result.pop(field,None)
        return result
    def _write(self,key,payload,action):
        if not isinstance(key,str) or not key.strip() or len(key)>160: raise CRMError('A nonempty idempotency key of at most 160 characters is required')
        digest=hashlib.sha256(canonical(payload).encode()).hexdigest()
        with transaction(self.crm) as conn:
            # Shared catalog lock precedes schema, receipt and entity locks everywhere.
            self.crm._catalog_lock(conn)
            check_schema(self.crm,conn,write=True)
            token=conn.execute(select(settings.c.value).where(settings.c.key=='workspace_id')).scalar()
            if token is None: conn.execute(settings.insert().values(key='workspace_id',value=str(uuid.uuid4())))
            scope=scope_for(self.crm,connection=conn)
            old=conn.execute(select(operations).where(operations.c.scope==scope,operations.c.key==key)).mappings().first()
            if old:
                if old['digest']!=digest: raise CRMError('Idempotency key already used for different data',409)
                return json.loads(old['response'])
            result=action(conn,scope)
            conn.execute(operations.insert().values(scope=scope,key=key,digest=digest,response=canonical(result)))
            return result
    def _get(self,conn,scope,record_id,include_text=True):
        row=conn.execute(select(self.table).where(self.table.c.scope==scope,self.table.c.id==record_id)).mappings().first()
        if row is None: raise CRMError('Record not found',404)
        return self._decode(row,include_text)
    def get(self,record_id,include_text=False,conn=None):
        with (nullcontext(conn) if conn is not None else self.crm._read_connection()) as c:
            if not check_schema(self.crm,c): raise CRMError('Record not found',404)
            return self._get(c,scope_for(self.crm,connection=c),record_id,include_text)
    def _page(self,conn,stmt,limit,offset,include_text=False):
        self.crm._integer(limit,'limit',1,100); self.crm._integer(offset,'offset')
        total=conn.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        return dict(items=[self._decode(r,include_text) for r in conn.execute(stmt.limit(limit).offset(offset)).mappings()],total=total,limit=limit,offset=offset)
