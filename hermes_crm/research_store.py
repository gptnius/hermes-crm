"""Source references and atomic reviewed append operations; no external effects."""
import hashlib, json, uuid
from sqlalchemy import select, update, func
from .domain import CRMError, contacts, settings, now
from .companies import CompanyStore
from .relationship_store import RelationshipStore
from .relationship_schema import companies
from .report_store import canonical, scope_for, transaction
from .research_schema import evidence, proposals, operations, check_schema
from .research_models import EvidenceInput, ProposalInput, Review, Apply, Lifecycle, Target
from .research_validation import evidence_row, proposal_row, response as stored_response

def hashed(text): return hashlib.sha256(text.encode()).hexdigest()
def append(before, addition): return before + ('\n\n' if before else '') + addition
def public(row):
    result=dict(row); result.pop('scope',None); return result

class ResearchStore:
    def __init__(self,crm): self.crm=crm
    def _write(self,key,payload,action):
        if not isinstance(key,str) or not key.strip() or len(key)>160: raise CRMError('A nonempty idempotency key of at most 160 characters is required')
        digest=hashed(canonical(payload))
        with transaction(self.crm) as conn:
            self.crm._catalog_lock(conn)
            check_schema(self.crm,conn,write=True)
            if conn.execute(select(settings.c.value).where(settings.c.key=='workspace_id')).scalar() is None:
                conn.execute(settings.insert().values(key='workspace_id',value=str(uuid.uuid4())))
            scope=scope_for(self.crm,connection=conn)
            prior=conn.execute(select(operations).where(operations.c.scope==scope,operations.c.key==key)).mappings().first()
            if prior:
                if prior['digest']!=digest: raise CRMError('Idempotency key already used for different data',409)
                return stored_response(prior['response'])
            result=action(conn,scope)
            conn.execute(operations.insert().values(scope=scope,key=key,digest=digest,response=canonical(result)))
            return result
    def _get(self,c,scope,table,id):
        row=c.execute(select(table).where(table.c.scope==scope,table.c.id==id)).mappings().first()
        if row is None: raise CRMError('Research record not found',404)
        result=public(row)
        if table is proposals: proposal_row(result)
        if table is evidence: evidence_row(result)
        return result
    def _target(self,c,kind,id):
        if kind=='contacts': return self.crm._get(c,'contacts',id)
        return CompanyStore(self.crm).get(id,include_text=True,conn=c)
    def _live(self,target):
        if target.get('archived_at'): raise CRMError('Archived Company cannot receive a note proposal',409)
    def submit(self,data,*,key,actor='local'):
        actor=RelationshipStore._actor(actor)
        value=EvidenceInput.model_validate(data).model_dump()
        def action(c,scope):
            target=self._target(c,value['target_kind'],value['target_id']); self._live(target)
            if target['version']!=value['target_version']: raise CRMError('Target changed; refresh',409)
            row=dict(id=str(uuid.uuid4()),target_kind=value['target_kind'],target_id=value['target_id'],packet=canonical(value),digest=hashed(canonical(value)),lifecycle_version=1,archived_at=None,recorded_at=now(),recorded_actor=actor)
            c.execute(evidence.insert().values(scope=scope,**row))
            return self._evidence(row,full=False)
        return self._write(key,['submit',value,actor],action)
    def _evidence(self,row,full=False):
        row,packet=evidence_row(row)
        if full: row.update(packet)
        return row
    def get_evidence(self,id):
        with self.crm._read_connection() as c:
            if not check_schema(self.crm,c): raise CRMError('Research record not found',404)
            return self._evidence(self._get(c,scope_for(self.crm,connection=c),evidence,id),True)
    def lifecycle(self,id,data,*,archive,key,actor='ui'):
        values=Lifecycle.model_validate(data).model_dump()
        def action(c,scope):
            old=self._get(c,scope,evidence,id)
            if old['lifecycle_version']!=values['lifecycle_version']: raise CRMError('Evidence lifecycle changed',409)
            if bool(old['archived_at'])==archive: raise CRMError('Evidence already in that lifecycle state',409)
            changes=dict(lifecycle_version=old['lifecycle_version']+1,archived_at=now() if archive else None)
            c.execute(update(evidence).where(evidence.c.scope==scope,evidence.c.id==id,evidence.c.lifecycle_version==old['lifecycle_version']).values(**changes))
            return self._evidence(dict(old,**changes))
        return self._write(key,['lifecycle',id,values,archive,actor],action)
    def propose(self,data,*,key,actor='local'):
        actor=RelationshipStore._actor(actor)
        value=ProposalInput.model_validate(data).model_dump()
        def action(c,scope):
            source=self._get(c,scope,evidence,value['evidence_id']); self._evidence(source)
            if source['archived_at'] or source['digest']!=value['evidence_digest'] or source['lifecycle_version']!=value['evidence_lifecycle_version']: raise CRMError('Evidence changed or archived',409)
            target=self._target(c,source['target_kind'],source['target_id']); self._live(target)
            if target['version']!=value['target_version']: raise CRMError('Target changed; refresh',409)
            candidate=append(target['notes'],value['addition'])
            if len(candidate)>10000: raise CRMError('Proposed notes exceed 10000 characters')
            row=dict(value,id=str(uuid.uuid4()),target_kind=source['target_kind'],target_id=source['target_id'],proposal_version=1,status='pending',before_hash=hashed(target['notes']),after_hash=hashed(candidate),created_at=now(),created_actor=actor)
            row['proposal_digest']=hashed(canonical(row)); row['receipt']=None
            c.execute(proposals.insert().values(scope=scope,**row))
            return self._proposal(row)
        return self._write(key,['propose',value,actor],action)
    def _proposal(self,row,addition=True):
        row=proposal_row(row)
        if not addition: row.pop('addition',None)
        return row
    def _fresh(self,c,scope,row):
        source=self._get(c,scope,evidence,row['evidence_id']); self._evidence(source)
        if source['archived_at'] or source['digest']!=row['evidence_digest'] or source['lifecycle_version']!=row['evidence_lifecycle_version']: return None,'evidence_changed'
        try: target=self._target(c,row['target_kind'],row['target_id'])
        except CRMError as exc:
            if exc.status==404: return None,'target_missing'
            raise
        if target.get('archived_at'): return None,'target_archived'
        if target['version']!=row['target_version'] or hashed(target['notes'])!=row['before_hash']: return None,'target_changed'
        if hashed(append(target['notes'],row['addition']))!=row['after_hash']: raise CRMError('Proposal integrity mismatch',409)
        return target,None
    def preview(self,id):
        with self.crm._read_connection() as c:
            if not check_schema(self.crm,c): raise CRMError('Research record not found',404)
            scope=scope_for(self.crm,connection=c); row=self._get(c,scope,proposals,id); result=self._proposal(row)
            target,reason=self._fresh(c,scope,row)
            result.update(stale=reason is not None,stale_reason=reason)
            if target is not None and row['status']=='pending': result.update(current_notes=target['notes'],proposed_notes=append(target['notes'],row['addition']))
            return result
    def list(self,kind,target_kind,target_id,limit=50,offset=0):
        Target.model_validate(dict(target_kind=target_kind,target_id=target_id))
        self.crm._integer(limit,'limit',1,100); self.crm._integer(offset,'offset',0,2_000_000_000)
        table=evidence if kind=='evidence' else proposals
        with self.crm._read_connection() as c:
            self._target(c,target_kind,target_id)
            if not check_schema(self.crm,c): return dict(items=[],total=0,limit=limit,offset=offset)
            scope=scope_for(self.crm,connection=c)
            stmt=select(table).where(table.c.scope==scope,table.c.target_kind==target_kind,table.c.target_id==target_id)
            total=c.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            stamp=table.c.recorded_at if kind=='evidence' else table.c.created_at
            result=[]
            for row in c.execute(stmt.order_by(stamp,table.c.id).limit(limit).offset(offset)).mappings():
                if kind=='evidence': item=self._evidence(row)
                else:
                    item=self._proposal(row,False); _,reason=self._fresh(c,scope,row); item.update(stale=reason is not None,stale_reason=reason)
                result.append(item)
            return dict(items=result,total=total,limit=limit,offset=offset)
    def review(self,id,data,*,apply,key,actor='ui'):
        actor=RelationshipStore._actor(actor)
        value=(Apply if apply else Review).model_validate(data).model_dump()
        def action(c,scope):
            row=self._get(c,scope,proposals,id)
            if row['status']!='pending': raise CRMError('Proposal already '+row['status']+'; inspect proposal receipt',409)
            for k,v in value.items():
                if row[k]!=v: raise CRMError('Reviewed proposal identity or version changed',409)
            stamp=now()
            receipt=dict(proposal_id=id,proposal_digest=row['proposal_digest'],proposal_version=row['proposal_version']+1,evidence_id=row['evidence_id'],evidence_digest=row['evidence_digest'],evidence_lifecycle_version=row['evidence_lifecycle_version'],target_kind=row['target_kind'],target_id=row['target_id'],target_version=row['target_version'],before_hash=row['before_hash'],after_hash=row['after_hash'],status='applied' if apply else 'dismissed',actor=actor,recorded_at=stamp)
            if apply:
                target,reason=self._fresh(c,scope,row)
                if reason: raise CRMError('Proposal is stale: '+reason,409)
                self._live(target); candidate=append(target['notes'],row['addition'])
                if len(candidate)>10000: raise CRMError('Proposed notes exceed 10000 characters')
                table=contacts if row['target_kind']=='contacts' else companies
                clause=[table.c.id==row['target_id'],table.c.version==row['target_version'],table.c.notes==target['notes']]
                if row['target_kind']=='companies': clause.append(table.c.scope==scope)
                changed=c.execute(update(table).where(*clause).values(notes=candidate,version=row['target_version']+1,updated_at=stamp))
                if changed.rowcount!=1: raise CRMError('Target changed; refresh',409)
                receipt['applied_target_version']=row['target_version']+1
                self.crm._audit(c,row['target_kind'],target,'research_note_appended',actor)
            changed=c.execute(update(proposals).where(proposals.c.scope==scope,proposals.c.id==id,proposals.c.status=='pending',proposals.c.proposal_version==row['proposal_version']).values(status=receipt['status'],proposal_version=receipt['proposal_version'],receipt=canonical(receipt)))
            if changed.rowcount!=1: raise CRMError('Proposal changed; refresh',409)
            return receipt
        return self._write(key,['apply' if apply else 'dismiss',id,value,actor],action)
    def receipt(self,key):
        if not isinstance(key,str) or not 1<=len(key)<=160: raise CRMError('Invalid operation key')
        with self.crm._read_connection() as c:
            if not check_schema(self.crm,c): return dict(state='unknown')
            row=c.execute(select(operations.c.response).where(operations.c.scope==scope_for(self.crm,connection=c),operations.c.key==key)).scalar()
            return dict(state='committed',receipt=stored_response(row)) if row else dict(state='unknown')
