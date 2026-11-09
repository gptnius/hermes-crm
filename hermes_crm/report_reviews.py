"""Local UI acknowledgement only. No agent tools or execution side effects."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .domain import CRMError, contacts, tasks, settings, now
from .native_work import read_snapshot
from .report_store import canonical, scope_for, transaction, advisory_lock, schema_name
from .report_review_schema import TABLES, events, operations, check_schema

FAMILIES = ('native', 'scheduled_research')


def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()

def workspace_for(conn):
    return conn.execute(select(settings.c.value).where(settings.c.key=='workspace_id')).scalar()


def invalid(): raise CRMError('Report review evidence is inconsistent or unsupported', 503)


def parse(value):
    def pairs(items):
        result = {}
        for key, entry in items:
            if key in result: invalid()
            result[key] = entry
        return result
    try:
        return json.loads(value, object_pairs_hook=pairs)
    except (TypeError, ValueError): invalid()


def identifier(value):
    try:
        if str(uuid.UUID(value)) != value: invalid()
    except (ValueError, TypeError, AttributeError): invalid()


def instant(value):
    try:
        if not isinstance(value, str) or datetime.fromisoformat(value).tzinfo is None: invalid()
    except (ValueError, TypeError): invalid()


def integer(value, minimum=1):
    if type(value) is not int or value < minimum: invalid()


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    context_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_review_version: int = Field(ge=0)
    acknowledge_stale: bool = False


def report_binding(family, assignment, report, *, workspace, profile):
    """Validate immutable report evidence before using it as review authority."""
    try:
        p = parse(assignment['payload'])
        if digest(p) != assignment['digest'] or p['profile'] != profile: invalid()
        identifier(assignment['id'])
        integer(p['generation'])
        if family == 'native':
            integer(report['generation'])
            if (assignment['workspace'] != workspace or assignment['profile'] != profile
                    or report['workspace'] != workspace or report['profile'] != profile
                    or report['assignment_id'] != assignment['id']
                    or report['generation'] != p['generation']
                    or p['schema_version'] != 1 or p['workspace'] != workspace or p['task_id'] != assignment['task_id']
                    or p['execution_source'] != 'builtin' or p['generation'] != 1 or report['operation_id'] != 'result'): invalid()
            # Invalidation fences future writes by advancing the mutable assignment
            # generation. The original report remains bound to its frozen occurrence.
            expected_generation = p['generation'] + (1 if assignment['state'] in ('cancelled','superseded') else 0)
            if type(assignment['generation']) is not int or assignment['generation'] != expected_generation: invalid()
            identity = parse(report['identity'])
            value = {k: report[k] for k in ('assignment_id', 'generation', 'operation_id', 'outcome', 'summary')}
            value['identity'] = identity
            if digest(value) != report['digest'] or identity['execution_id'] != report['execution_id']: invalid()
            report_id, report_digest = report['id'], report['digest']
            identifier(report_id)
            expected_name = f"CRM work {assignment['id']} g{p['generation']}"
            task_id = assignment['task_id']
            target = None
        elif family == 'scheduled_research':
            from .scheduled_research import MODE, HOST_SHA, job_name
            if p['mode'] != MODE or p['host_sha'] != HOST_SHA or p['generation'] != 1: invalid()
            if assignment['scope'] != digest([workspace, profile]) or report['scope'] != assignment['scope']: invalid()
            value = parse(report['response'])
            expected = {'assignment_id','generation','identity','summary','outcome','provenance',
                        'awaiting_human_review','host_terminal_success_verified','source_current','source_reason'}
            if (set(value) != expected or report['kind'] != 'report' or report['assignment_id'] != assignment['id']
                    or value['assignment_id'] != assignment['id'] or value['generation'] != 1
                    or value['provenance'] != 'native_run_reported' or value['awaiting_human_review'] is not True
                    or value['host_terminal_success_verified'] is not False): invalid()
            integer(value['generation'])
            identity = value['identity']
            if identity['execution_id'] != assignment['execution_id']: invalid()
            if report['key'] != 'run:' + digest([assignment['id'], identity['execution_id'], 'result']): invalid()
            if report['digest'] != digest(['report', {k:value[k] for k in ('summary','outcome')}, identity]): invalid()
            if type(value['source_current']) is not bool: invalid()
            if value['source_current']:
                if value['source_reason'] is not None: invalid()
            elif value['outcome'] not in ('blocked', 'failed') or value['source_reason'] not in (
                    'source_task_changed_or_closed','research_target_changed_or_archived','source_record_missing'): invalid()
            report_id, report_digest = report['key'], digest(value)
            expected_name = job_name(assignment)
            task_id = p['task_id']
            target = {k:p[k] for k in ('target_kind','target_id','target_version')}
        else: invalid()
        if (set(identity) != {'job_id','job_name','execution_id','source','scheduled_instant','started_at','profile'}
                or identity['job_id'] != assignment['job_id'] or identity['job_name'] != expected_name
                or identity['source'] != 'builtin' or identity['profile'] != profile
                or identity['scheduled_instant'] != p['run_at']): invalid()
        for key in ('job_id','job_name','execution_id','profile'):
            if not isinstance(identity[key],str) or not identity[key] or len(identity[key])>160: invalid()
        instant(identity['scheduled_instant'])
        if identity['started_at'] is not None: instant(identity['started_at'])
        if value['outcome'] not in ('completed','blocked','failed') or not isinstance(value['summary'],str) or not value['summary'].strip() or len(value['summary'])>10000: invalid()
        integer(p['task_version']); identifier(task_id)
        return dict(family=family, assignment_id=assignment['id'], report_id=report_id,
            assignment_digest=assignment['digest'], generation=p['generation'], report_digest=report_digest,
            identity=identity, summary=value['summary'], outcome=value['outcome'],
            task_id=task_id, task_version=p['task_version'], target=target)
    except (KeyError, TypeError, ValueError): invalid()


def validate_context(context):
    """Historical snapshots are structurally validated, not compared to today's rows."""
    try:
        if set(context) != {'report','assignment_version','assignment_state','task','target','source_current','source_reason'}: invalid()
        b = context['report']
        if set(b) != {'family','assignment_id','report_id','assignment_digest','generation','report_digest','identity','summary','outcome','task_id','task_version','target'}: invalid()
        if b['family'] not in FAMILIES: invalid()
        integer(context['assignment_version']); integer(b['generation']); integer(b['task_version'])
        if b['generation'] != 1: invalid()
        if b['family']=='native': identifier(b['report_id'])
        elif not isinstance(b['report_id'],str) or len(b['report_id'])!=68 or not b['report_id'].startswith('run:') or any(c not in '0123456789abcdef' for c in b['report_id'][4:]): invalid()
        if b['outcome'] not in ('completed','blocked','failed') or not isinstance(b['summary'],str) or not b['summary'].strip() or len(b['summary'])>10000: invalid()
        identity=b['identity']
        if set(identity) != {'job_id','job_name','execution_id','source','scheduled_instant','started_at','profile'} or identity['source']!='builtin': invalid()
        for key in ('job_id','job_name','execution_id','profile'):
            if not isinstance(identity[key],str) or not identity[key] or len(identity[key])>160: invalid()
        instant(identity['scheduled_instant'])
        if identity['started_at'] is not None: instant(identity['started_at'])
        if (b['family']=='native') != (b['target'] is None): invalid()
        identifier(b['assignment_id']); identifier(b['task_id'])
        for field in ('assignment_digest','report_digest'):
            if not isinstance(b[field],str) or len(b[field]) != 64 or any(c not in '0123456789abcdef' for c in b[field]): invalid()
        allowed_states = {'pending','create_unknown','resume_unknown','unknown','bound_paused','scheduled','result_reported','cancelled','superseded'}
        if context['assignment_state'] not in allowed_states: invalid()
        task = context['task']
        if set(task) != {'id','assigned_version','current_version','current_status'} or task['id'] != b['task_id'] or task['assigned_version'] != b['task_version']: invalid()
        if task['current_version'] is None:
            if task['current_status'] is not None: invalid()
        else:
            integer(task['current_version'])
            if task['current_status'] not in ('open','done'): invalid()
        target = context['target']
        if b['target'] is None:
            if target is not None: invalid()
        else:
            wanted = b['target']
            if set(wanted) != {'target_kind','target_id','target_version'} or wanted['target_kind'] not in ('contacts','companies'): invalid()
            identifier(wanted['target_id']); integer(wanted['target_version'])
            if set(target) != {'kind','id','assigned_version','current_version','archived'}: invalid()
            if (target['kind'],target['id'],target['assigned_version']) != (wanted['target_kind'],wanted['target_id'],wanted['target_version']): invalid()
            if target['current_version'] is not None: integer(target['current_version'])
            if type(target['archived']) is not bool: invalid()
            if (target['current_version'] is None or target['kind']=='contacts') and target['archived']: invalid()
        current, reason = source_status(task,target)
        if type(context['source_current']) is not bool or (context['source_current'],context['source_reason']) != (current,reason): invalid()
    except (KeyError,TypeError,ValueError): invalid()


def source_status(task,target):
    if task['current_version'] is None or (target is not None and target['current_version'] is None):
        return False, 'source_record_missing'
    if task['current_version'] != task['assigned_version'] or task['current_status'] != 'open':
        return False, 'source_task_changed_or_closed'
    if target is not None and (target['current_version'] != target['assigned_version'] or target['archived']):
        return False, 'research_target_changed_or_archived'
    return True, None


def event_view(row):
    value = {k:v for k,v in row.items() if k != 'scope'}
    value['context'] = parse(value['context'])
    return value


def review_view(history, include_history=False):
    latest = history[-1] if history else None
    value = dict(status='reviewed_in_crm' if latest and latest['action']=='acknowledge' else 'awaiting_review',
                 version=latest['version'] if latest else 0, latest_event=latest)
    if include_history: value.update(history=history[-50:],history_total=len(history),history_truncated=len(history)>50)
    return value


def validate_ledger(event_rows, operation_rows, scope):
    """A complete append-only sequence, one immutable receipt per event."""
    groups, by_id = {}, {}
    try:
        for row in event_rows:
            if set(row) != set(events.c.keys()) or row['scope'] != scope: invalid()
            identifier(row['id']); instant(row['created_at']); integer(row['version'])
            if row['actor'] != 'desktop' or row['action'] not in ('acknowledge','revoke') or row['id'] in by_id: invalid()
            event = event_view(row); context = event['context']; validate_context(context)
            if digest(context) != row['context_digest']: invalid()
            binding = context['report']
            key = (row['family'],row['assignment_id'],row['report_id'])
            if key != tuple(binding[k] for k in ('family','assignment_id','report_id')): invalid()
            groups.setdefault(key,[]).append(event); by_id[event['id']] = event
        for history in groups.values():
            history.sort(key=lambda e:e['version'])
            binding = history[0]['context']['report']
            for i,e in enumerate(history):
                if e['version'] != i+1 or e['action'] != ('acknowledge' if i%2==0 else 'revoke') or e['context']['report'] != binding: invalid()
        seen, keys = set(), set()
        for row in operation_rows:
            if set(row) != set(operations.c.keys()) or row['scope'] != scope or row['key'] in keys or not isinstance(row['key'],str) or not row['key'].strip() or len(row['key'])>160: invalid()
            keys.add(row['key']); request=parse(row['request']); response=parse(row['response'])
            if digest(request) != row['digest'] or set(request) != {'family','assignment_id','report_id','action','context_digest','expected_review_version','acknowledge_stale'}: invalid()
            ReviewRequest.model_validate({k:request[k] for k in ReviewRequest.model_fields})
            if set(response) != {'event','review'}: invalid()
            e=response['event']
            if e != by_id.get(e['id']) or e['id'] in seen: invalid()
            seen.add(e['id'])
            if any(request[k] != e[k] for k in ('family','assignment_id','report_id','action','context_digest')): invalid()
            if request['expected_review_version'] != e['version']-1: invalid()
            if not e['context']['source_current'] and not request['acknowledge_stale']: invalid()
            if response['review'] != dict(status='reviewed_in_crm' if e['action']=='acknowledge' else 'awaiting_review',version=e['version']): invalid()
        if seen != set(by_id): invalid()
        return groups
    except (KeyError,TypeError,ValueError): invalid()


def load_reviews(crm,conn):
    if not check_schema(crm,conn): return {}
    scope=scope_for(crm,connection=conn)
    return validate_ledger([dict(r) for r in conn.execute(select(events).where(events.c.scope==scope)).mappings()],
        [dict(r) for r in conn.execute(select(operations).where(operations.c.scope==scope)).mappings()],scope)


def projection(groups,family,assignment_id,report_id,report_digest=None,include_history=False,binding=None):
    history=groups.get((family,assignment_id,report_id),[])
    if history and report_digest is not None and history[0]['context']['report']['report_digest'] != report_digest: invalid()
    if history and binding is not None and history[0]['context']['report'] != binding: invalid()
    return review_view(history,include_history)


class ReportReviewStore:
    def __init__(self,crm): self.crm=crm

    def _context(self,c,family,assignment_id,report_id,lock=False):
        from .native_work import NativeWorkStore, assignments as native_assignments, reports as native_reports
        from .scheduled_research import ScheduledResearchStore, assignments as research_assignments, operations as research_operations
        from .relationship_schema import companies
        if family not in FAMILIES: raise CRMError('Unsupported report family',422)
        workspace=workspace_for(c)
        if workspace is None: raise CRMError('Workspace unavailable',409)
        scope=digest([workspace,self.crm.profile])
        if family=='native':
            store=NativeWorkStore(self.crm,initialize=False,connection=c,workspace=workspace)
            if not store.available: raise CRMError('Report not found',404)
            a=store._row(c,assignment_id)
            table=native_assignments
            report=c.execute(select(native_reports).where(native_reports.c.id==report_id,
                native_reports.c.assignment_id==assignment_id,native_reports.c.workspace==store.workspace,
                native_reports.c.profile==self.crm.profile)).mappings().first()
        else:
            store=ScheduledResearchStore(self.crm,initialize=False,connection=c)
            a=store._row(c,assignment_id); table=research_assignments
            report=c.execute(select(research_operations).where(research_operations.c.scope==scope,
                research_operations.c.assignment_id==assignment_id,research_operations.c.key==report_id,
                research_operations.c.kind=='report')).mappings().first()
        if report is None: raise CRMError('Report not found',404)
        binding=report_binding(family,a,report,workspace=workspace,profile=self.crm.profile)
        query=select(tasks.c.version,tasks.c.status).where(tasks.c.id==binding['task_id'])
        task=c.execute(query.with_for_update() if lock else query).mappings().first()
        task_context=dict(id=binding['task_id'],assigned_version=binding['task_version'],
                          current_version=task['version'] if task else None,current_status=task['status'] if task else None)
        target_context=None
        if binding['target']:
            t=binding['target']; target_table=contacts if t['target_kind']=='contacts' else companies
            query=select(target_table.c.version, *([] if t['target_kind']=='contacts' else [target_table.c.archived_at])).where(target_table.c.id==t['target_id'])
            if t['target_kind']=='companies': query=query.where(target_table.c.scope==scope)
            target=c.execute(query.with_for_update() if lock else query).mappings().first()
            target_context=dict(kind=t['target_kind'],id=t['target_id'],assigned_version=t['target_version'],
                current_version=target['version'] if target else None,archived=bool(target and target.get('archived_at')))
        if lock:
            query=select(table).where(table.c.id==assignment_id)
            query=query.where(table.c.scope==scope) if family!='native' else query.where(table.c.workspace==workspace,table.c.profile==self.crm.profile)
            locked=c.execute(query.with_for_update()).mappings().first()
            if locked is None or locked['version'] != a['version']: raise CRMError('Assignment changed; refresh review context',409)
        current,reason=source_status(task_context,target_context)
        context=dict(report=binding,assignment_version=a['version'],assignment_state=a['state'],task=task_context,
                     target=target_context,source_current=current,source_reason=reason)
        validate_context(context)
        return context

    def get(self,family,assignment_id,report_id):
        if self.crm.existing_workspace_token() is None: raise CRMError('Report not found',404)
        with read_snapshot(self.crm) as c:
            context=self._context(c,family,assignment_id,report_id)
            groups=load_reviews(self.crm,c)
            return dict(**context['report'],context=context,context_digest=digest(context),
                review=projection(groups,family,assignment_id,report_id,context['report']['report_digest'],include_history=True,binding=context['report']))

    def write(self,family,assignment_id,report_id,action,data,*,key):
        request=ReviewRequest.model_validate(data).model_dump()
        if family not in FAMILIES or action not in ('acknowledge','revoke'): raise CRMError('Unsupported review action',422)
        if not isinstance(key,str) or not key.strip() or len(key)>160: raise CRMError('A nonempty idempotency key is required',422)
        request.update(family=family,assignment_id=assignment_id,report_id=report_id,action=action)
        with transaction(self.crm) as c:
            check_schema(self.crm,c,write=True)
            scope=scope_for(self.crm,connection=c)
            if scope is None: raise CRMError('Workspace unavailable',409)
            if self.crm.backend=='postgres':
                advisory_lock(c,['crm-report-review-write',schema_name(self.crm),scope])
            groups=load_reviews(self.crm,c)
            previous=c.execute(select(operations).where(operations.c.scope==scope,operations.c.key==key)).mappings().first()
            if previous:
                if previous['digest'] != digest(request): raise CRMError('Idempotency key already used for different data',409)
                return parse(previous['response'])
            from .customization import state as catalog_state
            c.execute(select(catalog_state.c.id).where(catalog_state.c.id==1).with_for_update()).scalar_one()
            context=self._context(c,family,assignment_id,report_id,lock=True)
            if digest(context) != request['context_digest']: raise CRMError('Report or source context changed; refresh before reviewing',409)
            if not context['source_current'] and not request['acknowledge_stale']:
                raise CRMError('Explicit acknowledgement of changed source context is required',409)
            review=projection(groups,family,assignment_id,report_id,context['report']['report_digest'],binding=context['report'])
            if request['expected_review_version'] != review['version']: raise CRMError('Review changed; refresh before reviewing',409)
            if (action=='acknowledge') == (review['status']=='reviewed_in_crm'):
                raise CRMError('Report is already reviewed' if action=='acknowledge' else 'Report is not currently reviewed',409)
            row=dict(scope=scope,id=str(uuid.uuid4()),family=family,assignment_id=assignment_id,report_id=report_id,
                version=review['version']+1,action=action,context=canonical(context),context_digest=digest(context),
                actor='desktop',created_at=now())
            response=dict(event=event_view(row),review=dict(status='reviewed_in_crm' if action=='acknowledge' else 'awaiting_review',version=row['version']))
            c.execute(events.insert().values(**row))
            c.execute(operations.insert().values(scope=scope,key=key,request=canonical(request),digest=digest(request),response=canonical(response)))
            return response
