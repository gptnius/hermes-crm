"""Local, explicitly reported Events. No provider or scheduler side effects."""
import json
import uuid
from contextlib import nullcontext
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select, update, delete, func
from .domain import CRMError, StrictModel, TaskInput, contacts, deals, tasks, now, normalize_utc
from .report_store import scope_for, canonical
from .relationship_schema import events,event_revisions,event_tasks,companies,check_schema
from .relationship_store import RelationshipStore

def timestamp(value):
    if not isinstance(value,str): raise ValueError('Time must be an ISO timestamp with explicit offset')
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None or dt.utcoffset() is None: raise ValueError('Time must include an explicit offset')
    return normalize_utc(dt)

class EventInput(StrictModel):
    title: str = Field(min_length=1,max_length=200)
    kind: Literal['appointment','call']
    starts_at: str
    ends_at: str
    timezone: str = Field(max_length=100)
    contact_id: str | None = None
    deal_id: str | None = None
    company_id: str | None = None
    notes: str = Field(default='',max_length=10000)
    @field_validator('title')
    @classmethod
    def title_nonblank(cls,value):
        if not value.strip(): raise ValueError('Title must not be blank')
        return value.strip()
    @field_validator('starts_at','ends_at')
    @classmethod
    def times(cls,value): return timestamp(value)
    @field_validator('timezone')
    @classmethod
    def zone(cls,value):
        try: ZoneInfo(value)
        except (ValueError,ZoneInfoNotFoundError): raise ValueError('A valid IANA timezone is required')
        return value
    @field_validator('contact_id','deal_id','company_id')
    @classmethod
    def identifier(cls,value):
        if value is not None and str(uuid.UUID(value))!=value: raise ValueError('Use exact canonical UUID identifiers')
        return value
    @model_validator(mode='after')
    def ordered(self):
        if self.ends_at<=self.starts_at: raise ValueError('End must follow start')
        return self

class CompletionInput(StrictModel):
    outcome_happened_at: str
    outcome_summary: str = Field(min_length=1,max_length=10000)
    @field_validator('outcome_happened_at')
    @classmethod
    def past(cls,value):
        value=timestamp(value)
        if value>now(): raise ValueError('Future occurrence cannot be recorded')
        return value
    @field_validator('outcome_summary')
    @classmethod
    def summary(cls,value):
        if not value.strip(): raise ValueError('An outcome summary is required')
        return value.strip()

class EventStore(RelationshipStore):
    table=events
    def _references(self,conn,scope,values,previous_company_id=None):
        for name,table in (('contact_id',contacts),('deal_id',deals),('company_id',companies)):
            identifier=values.get(name)
            if identifier is None: continue
            stmt=select(table.c.id,table.c.archived_at) if table is companies else select(table.c.id)
            stmt=stmt.where(table.c.id==identifier)
            if table is companies: stmt=stmt.where(table.c.scope==scope)
            row=conn.execute(stmt).mappings().first()
            if row is None: raise CRMError('Related record not found',404)
            if table is companies and row['archived_at'] and identifier!=previous_company_id:
                raise CRMError('Archived Company cannot receive links',409)
    def _revision(self,conn,scope,record,reason,actor):
        conn.execute(event_revisions.insert().values(scope=scope,event_id=record['id'],version=record['version'],record=canonical(record),reason=reason,actor=actor,created_at=now()))
    def list(self,q='',status=None,kind=None,contact_id=None,company_id=None,deal_id=None,starts_from=None,starts_before=None,limit=50,offset=0,*,conn=None):
        self.crm._integer(limit,'limit',1,100);self.crm._integer(offset,'offset');q=self.crm._text_filter(q,'q')
        if status is not None and status not in ('scheduled','completed','cancelled','needs_rescheduling'): raise CRMError('Invalid Event status')
        if kind is not None and kind not in ('appointment','call'): raise CRMError('Invalid Event kind')
        try:
            starts_from=timestamp(starts_from) if starts_from is not None else None
            starts_before=timestamp(starts_before) if starts_before is not None else None
        except ValueError as error: raise CRMError(str(error))
        with (nullcontext(conn) if conn is not None else self.crm._read_connection()) as c:
            if not check_schema(self.crm,c): return dict(items=[],total=0,limit=limit,offset=offset)
            stmt=select(events).where(events.c.scope==scope_for(self.crm,connection=c))
            for key,value in [('status',status),('kind',kind),('contact_id',contact_id),('company_id',company_id),('deal_id',deal_id)]:
                if value is not None: stmt=stmt.where(events.c[key]==value)
            if q: stmt=stmt.where(events.c.title.ilike('%'+q+'%',escape='\\'))
            if starts_from: stmt=stmt.where(events.c.starts_at>=starts_from)
            if starts_before: stmt=stmt.where(events.c.starts_at<starts_before)
            return self._page(c,stmt.order_by(events.c.starts_at,events.c.id),limit,offset)
    def create(self,data,*,actor,key):
        values=EventInput.model_validate(data).model_dump();actor=self._actor(actor)
        def action(conn,scope):
            self._references(conn,scope,values);stamp=now()
            record=dict(id=str(uuid.uuid4()),version=1,created_at=stamp,updated_at=stamp,**values,status='scheduled',outcome_happened_at=None,recorded_at=None,outcome_summary=None,source='local',outcome_provenance=None)
            conn.execute(events.insert().values(scope=scope,**record));self._revision(conn,scope,record,'created',actor);self.crm._audit(conn,'events',record,'created',actor);return record
        return self._write(key,['event_create',values,actor],action)
    def _save(self,conn,scope,old,values,reason,actor,operation=None):
        record=dict(old,**values);record.update(version=old['version']+1,updated_at=now())
        result=conn.execute(update(events).where(events.c.scope==scope,events.c.id==old['id'],events.c.version==old['version']).values(**record))
        if result.rowcount!=1: raise CRMError('Event changed; refresh before editing',409)
        self._revision(conn,scope,record,reason,actor);self.crm._audit(conn,'events',record,operation or reason,actor)
        return record
    def _change(self,event_id,data,expected_version,actor,key,operation,reason=''):
        self._version(expected_version);actor=self._actor(actor)
        if operation in ('cancel','reopen','needs_rescheduling') and (not isinstance(reason,str) or not reason.strip() or len(reason)>2000): raise CRMError('A reason of at most 2000 characters is required')
        if not isinstance(data,dict): raise CRMError('Event data must be an object')
        if operation in ('updated','reschedule') and set(data)-set(EventInput.model_fields): raise CRMError('Unknown or immutable Event fields')
        if operation=='complete': data=CompletionInput.model_validate(data).model_dump()
        def action(conn,scope):
            old=self._get(conn,scope,event_id)
            if old['version']!=expected_version: raise CRMError('Event changed; refresh before editing',409)
            terminal=old['status'] in ('completed','cancelled')
            if operation=='reopen':
                if not terminal: raise CRMError('Only completed or cancelled Events can reopen',409)
                values=dict(status='scheduled',outcome_happened_at=None,outcome_summary=None,outcome_provenance=None,recorded_at=None)
            else:
                if terminal: raise CRMError('Reopen this Event before changing it',409)
                if operation in ('updated','reschedule'):
                    values=EventInput.model_validate({k:old[k] for k in EventInput.model_fields}|data).model_dump();self._references(conn,scope,values,previous_company_id=old['company_id'])
                    if operation=='reschedule':
                        if not {'starts_at','ends_at','timezone'}.issubset(data): raise CRMError('Rescheduling requires reviewed start, end and timezone')
                        values['status']='scheduled'
                elif operation=='complete': values=dict(data,status='completed',recorded_at=now(),outcome_provenance='self_reported')
                else: values=dict(status='cancelled' if operation=='cancel' else 'needs_rescheduling')
            return self._save(conn,scope,old,values,reason.strip() or operation,actor,operation)
        return self._write(key,['event_'+operation,event_id,data,expected_version,reason,actor],action)
    def update(self,event_id,data,*,expected_version,actor,key): return self._change(event_id,data,expected_version,actor,key,'updated')
    def complete(self,event_id,data,*,expected_version,actor,key): return self._change(event_id,data,expected_version,actor,key,'complete')
    def cancel(self,event_id,reason,*,expected_version,actor,key): return self._change(event_id,{},expected_version,actor,key,'cancel',reason)
    def reopen(self,event_id,reason,*,expected_version,actor,key): return self._change(event_id,{},expected_version,actor,key,'reopen',reason)
    def needs_rescheduling(self,event_id,reason,*,expected_version,actor,key): return self._change(event_id,{},expected_version,actor,key,'needs_rescheduling',reason)
    def reschedule(self,event_id,data,*,expected_version,actor,key): return self._change(event_id,data,expected_version,actor,key,'reschedule')
    def revisions(self,event_id,limit=50,offset=0,*,include_text=False,conn=None):
        self.crm._integer(limit,'limit',1,100);self.crm._integer(offset,'offset')
        with (nullcontext(conn) if conn is not None else self.crm._read_connection()) as c:
            self.get(event_id,conn=c);scope=scope_for(self.crm,connection=c)
            stmt=select(event_revisions).where(event_revisions.c.scope==scope,event_revisions.c.event_id==event_id)
            total=c.execute(select(func.count()).select_from(stmt.subquery())).scalar_one();items=[]
            for row in c.execute(stmt.order_by(event_revisions.c.version.desc()).limit(limit).offset(offset)).mappings():
                item=dict(row);item.pop('scope');item['record']=self._decode(json.loads(item['record']),include_text)
                if not include_text: item.pop('reason')
                items.append(item)
            return dict(items=items,total=total,limit=limit,offset=offset)
    def create_task(self,event_id,data,*,expected_version,actor,key):
        self._version(expected_version);actor=self._actor(actor)
        if not isinstance(data,dict): raise CRMError('Task data must be an object')
        raw=dict(data);custom=raw.pop('custom_fields',{});values=TaskInput.model_validate(raw).model_dump();values.update(schedule_status='none',scheduler_job_id=None)
        def action(conn,scope):
            event=self._get(conn,scope,event_id)
            if event['version']!=expected_version: raise CRMError('Event changed; refresh before adding a task',409)
            task=self.crm._insert_created(conn,'tasks',values,custom,actor)
            stamp=now();conn.execute(event_tasks.insert().values(scope=scope,task_id=task['id'],event_id=event_id,created_at=stamp,updated_at=stamp))
            event=self._save(conn,scope,event,{},'task_created',actor)
            return dict(event=event,task=task,event_id=event_id,task_id=task['id'])
        return self._write(key,['event_create_task',event_id,values,custom,expected_version,actor],action)
    def link_task(self,event_id,task_id,*,expected_version,expected_task_version,actor,key):
        self._version(expected_version);self._version(expected_task_version);actor=self._actor(actor)
        def action(conn,scope):
            event=self._get(conn,scope,event_id);task=self.crm._get(conn,'tasks',task_id)
            if event['version']!=expected_version or task['version']!=expected_task_version: raise CRMError('Event or task changed; refresh before linking',409)
            clause=(event_tasks.c.scope==scope,event_tasks.c.task_id==task_id)
            old=conn.execute(select(event_tasks).where(*clause)).mappings().first()
            if old and old['event_id']==event_id: return dict(event=event,task=task,event_id=event_id,task_id=task_id)
            if old: raise CRMError('Task already linked to another Event; explicitly unlink first',409)
            stamp=now();conn.execute(event_tasks.insert().values(scope=scope,task_id=task_id,event_id=event_id,created_at=stamp,updated_at=stamp))
            changed=conn.execute(update(tasks).where(tasks.c.id==task_id,tasks.c.version==expected_task_version).values(version=expected_task_version+1,updated_at=stamp))
            if changed.rowcount!=1: raise CRMError('Task changed; refresh before linking',409)
            task.update(version=expected_task_version+1,updated_at=stamp);self.crm._audit(conn,'tasks',task,'event_linked',actor)
            event=self._save(conn,scope,event,{},'task_linked',actor)
            return dict(event=event,task=task,event_id=event_id,task_id=task_id)
        return self._write(key,['event_link_task',event_id,task_id,expected_version,expected_task_version,actor],action)
    def unlink_task(self,task_id,*,event_id,expected_version,expected_task_version,actor,key):
        self._version(expected_version);self._version(expected_task_version);actor=self._actor(actor)
        def action(conn,scope):
            target=self._get(conn,scope,event_id);task=self.crm._get(conn,'tasks',task_id)
            if target['version']!=expected_version or task['version']!=expected_task_version: raise CRMError('Event or task changed; refresh before unlinking',409)
            clause=(event_tasks.c.scope==scope,event_tasks.c.task_id==task_id)
            old=conn.execute(select(event_tasks).where(*clause)).mappings().first()
            event=None
            if old:
                if old['event_id']!=event_id: raise CRMError('Task is linked to a different Event; refresh before unlinking',409)
                conn.execute(delete(event_tasks).where(*clause));stamp=now()
                changed=conn.execute(update(tasks).where(tasks.c.id==task_id,tasks.c.version==expected_task_version).values(version=expected_task_version+1,updated_at=stamp))
                if changed.rowcount!=1: raise CRMError('Task changed; refresh before unlinking',409)
                task.update(version=expected_task_version+1,updated_at=stamp);self.crm._audit(conn,'tasks',task,'event_unlinked',actor)
                event=self._save(conn,scope,target,{},'task_unlinked',actor)
            return dict(event=event,task=task,event_id=None,task_id=task_id)
        return self._write(key,['event_unlink_task',task_id,event_id,expected_version,expected_task_version,actor],action)

Events=EventStore
