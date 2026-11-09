"""Offline snapshot consistency checks; never rebind or activate execution.

Historical target/task versions need not equal current versions. Reports and
source packets remain unverified claims even in authenticated content exports.
"""
import json
import re
import uuid
from sqlalchemy import Integer,String
from .domain import CRMError
from .scheduled_research import TABLES,MODE,HOST_SHA,ResearchIntent,digest,job_name
from .native_work import _instant
from .research_validation import response as research_response


def _invalid(): raise CRMError('Invalid scheduled research export family',422)
def _json(raw):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:_invalid()
            result[k]=v
        return result
    value=json.loads(raw,object_pairs_hook=pairs)
    if not isinstance(value,dict):_invalid()
    return value

def _id(value):
    if not isinstance(value,str) or str(uuid.UUID(value))!=value:_invalid()

def validate_snapshot(tables,*,scope,profile):
    """Validate an optional complete scoped family and its historical links."""
    try:_validate(tables,scope,profile)
    except CRMError:raise
    except Exception:raise CRMError('Invalid scheduled research export family',422) from None

def _validate(tables,scope,profile):
    names={t.name for t in TABLES}
    if not names & tables.keys():return
    if not names <= tables.keys():_invalid()
    for table in TABLES:
        keys=set()
        for row in tables[table.name]:
            if set(row)!=set(table.c.keys()) or row['scope']!=scope:_invalid()
            for col in table.c:
                v=row[col.name]
                if v is None:
                    if not col.nullable:_invalid()
                elif isinstance(col.type,Integer):
                    if type(v) is not int or not -(2**63)<=v<2**63:_invalid()
                elif isinstance(col.type,String):
                    if not isinstance(v,str) or (col.type.length and len(v)>col.type.length):_invalid()
                else:_invalid()
            key=tuple(row[c.name] for c in table.primary_key)
            if key in keys:_invalid()
            keys.add(key)
            if not re.fullmatch('[0-9a-f]{64}',row['digest']):_invalid()
    task_index={r['id']:r for r in tables.get('crm_tasks',[])}
    targets={'contacts':{r['id']:r for r in tables.get('crm_contacts',[])},
             'companies':{r['id']:r for r in tables.get('crm_companies',[]) if r['scope']==scope}}
    source_index={r['id']:r for r in tables.get('crm_research_evidence',[]) if r['scope']==scope}
    proposal_index={r['id']:r for r in tables.get('crm_research_proposals',[]) if r['scope']==scope}
    by_id={};payloads={}
    for row in tables[TABLES[0].name]:
        _id(row['id']);p=_json(row['payload'])
        if set(p)!=set(ResearchIntent.model_fields)|{'mode','generation','profile','host_sha','task_due_at'}:_invalid()
        ResearchIntent.model_validate({k:p[k] for k in ResearchIntent.model_fields})
        if p['mode']!=MODE or type(p['generation']) is not int or p['generation']!=1 or p['profile']!=profile or p['host_sha']!=HOST_SHA:_invalid()
        if digest(p)!=row['digest'] or row['version']<1:_invalid()
        if p['task_due_at'] is not None:_instant(p['task_due_at'],'task_due_at')
        for key in ('created_at','updated_at'):_instant(row[key],key)
        task=task_index.get(p['task_id']);target=targets[p['target_kind']].get(p['target_id'])
        if task is None or target is None or task['version']<p['task_version'] or target['version']<p['target_version']:_invalid()
        if row['state'] not in {'pending','create_unknown','bound_paused','resume_unknown','scheduled','result_reported','cancelled'}:_invalid()
        if row['state'] in {'bound_paused','resume_unknown','scheduled','result_reported'} and not row['job_id']:_invalid()
        if row['execution_id'] is not None and not row['job_id']:_invalid()
        by_id[row['id']]=row;payloads[row['id']]=p
    groups={id:[] for id in by_id}
    for op in tables[TABLES[1].name]:
        row=by_id.get(op['assignment_id'])
        if row is None:_invalid()
        p=payloads[row['id']];value=_json(op['response']);kind=op['kind'];groups[row['id']].append(op)
        if kind=='create':
            if not op['key'].startswith('create:') or len(op['key'])<=7 or value!={'id':row['id']}:_invalid()
            if op['digest']!=digest({k:v for k,v in p.items() if k!='task_due_at'}):_invalid()
            continue
        if not re.fullmatch('run:[0-9a-f]{64}',op['key']) or not row['execution_id'] or not row['job_id']:_invalid()
        if kind in ('evidence','proposal'):
            value=research_response(op['response'])
            if value['target_kind']!=p['target_kind'] or value['target_id']!=p['target_id'] or value['target_version']!=p['target_version']:_invalid()
            if kind=='evidence':
                source=source_index.get(value['id'])
                if source is None or source['digest']!=value['digest']:_invalid()
                if source['recorded_actor']!='scheduled_research:'+row['id']:_invalid()
            else:
                proposal=proposal_index.get(value['id'])
                if not p['propose_note'] or proposal is None or proposal['proposal_digest']!=value['proposal_digest']:_invalid()
                if proposal['created_actor']!='scheduled_research:'+row['id'] or value['status']!='pending':_invalid()
                source=source_index.get(value['evidence_id'])
                if source is None or source['recorded_actor']!='scheduled_research:'+row['id']:_invalid()
        elif kind=='report':
            expected={'assignment_id','generation','identity','summary','outcome','provenance','awaiting_human_review','host_terminal_success_verified','source_current','source_reason'}
            if set(value)!=expected or value['assignment_id']!=row['id'] or type(value['generation']) is not int or value['generation']!=1:_invalid()
            identity=value['identity']
            if set(identity)!={'job_id','job_name','execution_id','source','scheduled_instant','started_at','profile'}:_invalid()
            if identity['job_id']!=row['job_id'] or identity['job_name']!=job_name(row) or identity['execution_id']!=row['execution_id'] or identity['source']!='builtin' or identity['profile']!=profile or identity['scheduled_instant']!=p['run_at']:_invalid()
            if identity['started_at'] is not None:_instant(identity['started_at'],'started_at')
            if value['outcome'] not in ('completed','blocked','failed') or not isinstance(value['summary'],str) or not value['summary'].strip() or len(value['summary'])>10000:_invalid()
            if type(value['source_current']) is not bool:_invalid()
            if value['source_current']:
                if value['source_reason'] is not None:_invalid()
            elif value['outcome'] not in ('blocked','failed') or value['source_reason'] not in {'source_task_changed_or_closed','research_target_changed_or_archived','source_record_missing'}:_invalid()
            if value['provenance']!='native_run_reported' or value['awaiting_human_review'] is not True or value['host_terminal_success_verified'] is not False:_invalid()
            if op['key']!='run:'+digest([row['id'],row['execution_id'],'result']):_invalid()
            if op['digest']!=digest(['report',{k:value[k] for k in ('summary','outcome')},identity]):_invalid()
        else:_invalid()
    for id,ops in groups.items():
        counts={k:sum(o['kind']==k for o in ops) for k in ('create','evidence','proposal','report')}
        if counts['create']!=1 or counts['evidence']>payloads[id]['max_sources'] or counts['proposal']>1 or counts['report']>1:_invalid()
        if by_id[id]['state']=='result_reported' and counts['report']!=1:_invalid()
        evidence_ids={_json(o['response'])['id'] for o in ops if o['kind']=='evidence'}
        for o in ops:
            if o['kind']=='proposal' and _json(o['response'])['evidence_id'] not in evidence_ids:_invalid()
