"""Read-only evidence queue, not an execution monitor or an autonomous-work policy.

This prototype classifies the complete stored history in one read snapshot before
filtering/paging. It is O(tasks + assignment history), not a 500/100-row cache.
Each returned item is one contact gap, task gap, or exact assignment. Totals count
these evidence items, not unique leads. Offset pages are deterministic for an
unchanged database; a later request is a new snapshot, not a frozen cursor.
"""
from collections import defaultdict
from datetime import datetime
import hashlib
import json

from sqlalchemy import func, or_, select

from .domain import CRMError, contacts, deals, now, tasks
from .native_work import (INVALID, SCHEMA_VERSION, NativeWorkStore, assignments,
                          events, read_snapshot, reports)

STATUSES = ('any', 'missing_next_action', 'overdue', 'agent_not_scheduled',
            'needs_scheduling_review', 'run_time_passed', 'reported_blocked_failed', 'awaiting_review')


def _age(observed_at, timestamp):
    return max(0, int((datetime.fromisoformat(timestamp) - datetime.fromisoformat(observed_at)).total_seconds()))


def _inactive_observation(event, evidence):
    """A contract-checked completed one-shot, never a pause or run-success claim."""
    try:
        if datetime.fromisoformat(event['created_at']).tzinfo is None: return False
    except (TypeError, ValueError): return False
    kind = event['kind']
    return (evidence.get('source') == 'public_job_list'
            and type(event['version']) is int and event['version'] > 0
            and evidence.get('future_schedule_inactive') is True
            and evidence.get('state') == 'completed' and evidence.get('enabled') is False
            and 'next_run_at' in evidence and evidence['next_run_at'] is None
            and (kind == 'job_observed' or (kind == 'inactive_schedule_observed'
                 and evidence.get('pause_attempted') is False
                 and evidence.get('running_execution_cancelled') is False)))


def _assignment(row, task, history, results, timestamp, reviews=None):
    """Keep separate saved intent, latest exact-job observation, and reports."""
    payload = json.loads(row['payload'])
    if (hashlib.sha256(row['payload'].encode()).hexdigest() != row['digest']
            or payload.get('schema_version') != SCHEMA_VERSION):
        raise CRMError('Native-work intent integrity check failed', 503)
    if row['state'] not in {'pending', 'create_unknown', 'resume_unknown', 'unknown',
                             'bound_paused', 'scheduled', 'result_reported', *INVALID}:
        raise CRMError('Unrecognized saved assignment state', 503)
    if any(r['outcome'] not in {'completed', 'blocked', 'failed'} for r in results):
        raise CRMError('Unrecognized saved report outcome', 503)
    current = task['status'] == 'open' and task['version'] == payload['task_version']
    invalid = row['state'] in INVALID
    host = None
    pause = None
    inactive = None
    observation_key = None
    previous_pause = previous_inactive = False
    attempted = False
    invalidated_version = max((e['version'] for e in history if e['kind'] == 'intent_invalidated'), default=0)
    invalidated_index = max((i for i, e in enumerate(history) if e['kind'] == 'intent_invalidated'), default=-1)
    for index, event in enumerate(history):
        evidence = json.loads(event['evidence'])
        kind = event['kind']
        if kind == 'create_started': attempted = True
        if kind == 'job_observed' and row['job_id'] and evidence.get('job_id') == row['job_id']:
            host = dict(job_id=row['job_id'], state=evidence.get('state')
                if evidence.get('state') in {'paused', 'scheduled', 'running', 'completed', 'failed'} else 'unknown',
                enabled=evidence.get('enabled'), source=evidence.get('source'),
                observed_at=event['created_at'], age_seconds=_age(event['created_at'], timestamp))
        if event['version'] < invalidated_version or index <= invalidated_index:
            continue
        if kind in {'job_observed', 'pause_observed', 'pause_unknown', 'inactive_schedule_observed'} \
                and row['job_id'] and evidence.get('job_id') == row['job_id']:
            pause = dict(observed=(kind == 'pause_observed' and evidence.get('future_schedule_paused') is True)
                         or (kind == 'job_observed' and evidence.get('state') == 'paused' and evidence.get('enabled') is False),
                         observed_at=event['created_at'])
            inactive = dict(observed=invalid and invalidated_index >= 0 and _inactive_observation(event, evidence),
                            observed_at=event['created_at'])
            # UUIDs only stabilize presentation order. They cannot establish
            # which of two contradictory same-time observations happened last.
            key = (event['version'], event['created_at'])
            if key == observation_key:
                pause['observed'] = pause['observed'] and previous_pause
                inactive['observed'] = inactive['observed'] and previous_inactive
            if invalidated_index >= 0 and key == (invalidated_version, history[invalidated_index]['created_at']):
                inactive['observed'] = False
            observation_key = key
            previous_pause, previous_inactive = pause['observed'], inactive['observed']
        elif kind in {'reconcile_unknown', 'reconcile_stale', 'reconciled_unbound', 'resume_unknown'}:
            # Later failed observations revoke both kinds of historical safety evidence.
            pause = dict(observed=False, observed_at=event['created_at'])
            inactive = None
            observation_key = (event['version'], event['created_at'])
            previous_pause = previous_inactive = False
    from .report_reviews import projection, report_binding
    review_states = {r['id']:projection(reviews or {},'native',row['id'],r['id'],r['digest'],binding=report_binding('native',row,r,workspace=row['workspace'],profile=row['profile']) if (reviews or {}).get(('native',row['id'],r['id'])) else None) for r in results}
    latest_report = None
    if results:
        last = results[-1]
        identity = json.loads(last['identity'])
        latest_report = dict(id=last['id'], outcome=last['outcome'], created_at=last['created_at'],
            age_seconds=_age(last['created_at'], timestamp), provenance='native_run_reported',
            review_status='reviewed_in_crm' if review_states[last['id']]['status']=='reviewed_in_crm' else 'awaiting_human_review',
            review=review_states[last['id']],
            identity={key: identity.get(key) for key in ('job_id', 'job_name', 'execution_id', 'source',
                                                       'scheduled_instant', 'started_at', 'profile')})
    summary = {key: row[key] for key in ('id', 'idempotency_key', 'version', 'generation', 'state', 'reason',
                                       'job_id', 'created_at', 'updated_at')}
    summary.update(task_version=payload['task_version'], run_at=payload['run_at'], human_owner=payload['human_owner'],
        source_task_current=current, latest_host_observation=host, latest_report=latest_report,
        report_count=len(results), report_outcomes=sorted({r['outcome'] for r in results}),
        future_schedule_pause_observed=bool(pause and pause['observed']),
        pause_observed_at=pause['observed_at'] if pause and not (inactive and inactive['observed']) else None,
        future_schedule_inactive_observed=bool(inactive and inactive['observed']),
        inactive_observed_at=inactive['observed_at'] if inactive and inactive['observed'] else None,
        business_task_completed=task['status'] == 'done', business_task_completed_by_report=False,
        host_terminal_success_verified=False)
    flags = set()
    if row['state'] == 'pending': flags.add('intent_not_scheduled')
    if not current:
        flags.add('stale_source')
        # Safe invalidated history without a report is history, not a live risk.
        if not invalid or results: flags.add('needs_scheduling_review')
    if row['state'] in {'unknown', 'create_unknown', 'resume_unknown', 'bound_paused'}:
        flags.add('needs_scheduling_review')
    if invalid and (row['job_id'] or attempted) and not (summary['future_schedule_pause_observed']
                                                       or summary['future_schedule_inactive_observed']):
        flags.update(('unverified_pause', 'needs_scheduling_review'))
    if row['state'] == 'bound_paused' and payload['run_at'] < timestamp:
        flags.add('run_time_elapsed_while_paused')
    if not invalid and payload['run_at'] < timestamp and not results:
        flags.add('run_time_passed')
    if any(review['status']=='awaiting_review' for review in review_states.values()):
        flags.add('awaiting_review')
    if any(r['outcome'] in {'blocked', 'failed'} for r in results): flags.add('reported_blocked_failed')
    if host and host['state'] == 'unknown' and not invalid:
        flags.add('needs_scheduling_review')
    if host and host['state'] == 'failed':
        flags.add('host_observed_failed')
        if not invalid: flags.add('needs_scheduling_review')
    return summary, flags


def coverage_report(crm, *, q='', status='any', limit=50, offset=0):
    crm._integer(limit, 'limit', 1, 100)
    crm._integer(offset, 'offset')
    escaped = crm._text_filter(q, 'Search')
    if status not in STATUSES: raise CRMError('Invalid coverage status')
    workspace = crm.workspace_token()
    timestamp = now()
    result = dict(items=[], total=0, limit=limit, offset=offset, observed_at=timestamp,
                  workspace_token=workspace, profile=crm.profile, total_unit='evidence_items')
    with read_snapshot(crm) as conn:
        store = NativeWorkStore(crm, initialize=False, connection=conn, workspace=workspace)
        # Always read all links/tasks, even for a text-filtered result. Searching
        # must not manufacture a missing follow-up by hiding a nonmatching task.
        contact_rows = {r['id']: dict(r) for r in conn.execute(select(
            contacts.c.id, contacts.c.name, contacts.c.company)).mappings()}
        deal_contacts = dict(conn.execute(select(deals.c.id, deals.c.contact_id)).all())
        task_rows = {r['id']: dict(r) for r in conn.execute(select(
            tasks.c.id, tasks.c.title, tasks.c.version, tasks.c.status, tasks.c.due_at,
            tasks.c.contact_id, tasks.c.deal_id)).mappings()}
        contact_matches = task_matches = None
        if escaped:
            pattern = f'%{escaped}%'
            contact_matches = set(conn.execute(select(contacts.c.id).where(or_(
                func.lower(contacts.c.name).like(pattern, escape='\\'),
                func.lower(contacts.c.company).like(pattern, escape='\\')))).scalars())
            task_matches = set(conn.execute(select(tasks.c.id).where(
                func.lower(tasks.c.title).like(pattern, escape='\\'))).scalars())
        from .report_reviews import load_reviews
        reviews = load_reviews(crm,conn)
        native_rows, history, results = [], defaultdict(list), defaultdict(list)
        if store.available:
            scope = [assignments.c.workspace == store.workspace, assignments.c.profile == store.profile]
            native_rows = [dict(r) for r in conn.execute(select(assignments).where(*scope)
                .order_by(assignments.c.created_at, assignments.c.id)).mappings()]
            # Subquery keeps all reads scoped without huge IN lists or arbitrary caps.
            scoped_ids = select(assignments.c.id).where(*scope)
            for row in conn.execute(select(events).where(events.c.assignment_id.in_(scoped_ids))
                    .order_by(events.c.version, events.c.created_at, events.c.id)).mappings():
                history[row['assignment_id']].append(row)
            for row in conn.execute(select(reports).where(reports.c.assignment_id.in_(scoped_ids),
                    reports.c.workspace == store.workspace, reports.c.profile == store.profile)
                    .order_by(reports.c.created_at, reports.c.id)).mappings():
                results[row['assignment_id']].append(row)

        linked, open_contacts = {}, set()
        for task in task_rows.values():
            ids = {task['contact_id'], deal_contacts.get(task['deal_id'])} - {None}
            linked[task['id']] = sorted(ids)
            if task['status'] == 'open': open_contacts.update(ids)
        by_task = defaultdict(list)
        for row in native_rows:
            task = task_rows.get(row['task_id'])
            if task is None: raise CRMError('Assignment source task is unavailable', 503)
            summary, flags = _assignment(row, task, history[row['id']], results[row['id']], timestamp,reviews)
            by_task[task['id']].append((summary, flags))

        items = []
        for task in sorted(task_rows.values(), key=lambda t: (t['due_at'], t['id'])):
            task_id = task['id']
            ids = linked[task_id]
            if escaped and task_id not in task_matches and not contact_matches.intersection(ids): continue
            associations = [dict(id=cid, name=contact_rows[cid]['name']) for cid in ids]
            task_summary = {key: task[key] for key in ('id', 'title', 'version', 'status', 'due_at')}
            current = [a for a, _ in by_task[task_id] if a['source_task_current'] and a['state'] not in INVALID]
            covered = any(a['state'] == 'scheduled' or a['report_count'] for a in current)
            coverage = dict(current_assignment_count=len(current),
                current_scheduled_or_reported_count=sum(a['state'] == 'scheduled' or a['report_count'] > 0 for a in current),
                agent_intent_saved=bool(current))
            common = dict(task=task_summary, contacts=associations, coverage=coverage)
            overdue = task['status'] == 'open' and task['due_at'] < timestamp
            if task['status'] == 'open' and not current:
                flags = ['agent_not_scheduled', 'no_current_assignment'] + (['overdue'] if overdue else [])
                items.append(dict(common, id='task:'+task_id, kind='unassigned_task', row_kind='task',
                    assignment=None, risk_flags=flags, next_action='open_task'))
            for assignment, flags in by_task[task_id]:
                if overdue: flags.add('overdue')
                if assignment in current and not covered: flags.add('agent_not_scheduled')
                items.append(dict(common, id='assignment:'+assignment['id'], kind='assignment', row_kind='assignment',
                    assignment=assignment, risk_flags=sorted(flags), next_action='open_assignment'))
        for contact in sorted(contact_rows.values(), key=lambda c: (c['name'].lower(), c['id'])):
            if contact['id'] in open_contacts: continue
            if escaped and contact['id'] not in contact_matches: continue
            items.append(dict(id='contact:'+contact['id'], kind='missing_next_action', row_kind='contact', task=None,
                contacts=[dict(id=contact['id'], name=contact['name'])], assignment=None, coverage=None,
                risk_flags=['missing_next_action'], next_action='open_contact'))
        filtered = [row for row in items if status == 'any' or status in row['risk_flags']]
        result.update(total=len(filtered), items=filtered[offset:offset+limit])
    return result
