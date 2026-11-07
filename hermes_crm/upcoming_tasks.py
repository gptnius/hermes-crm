"""Small UI-only summaries of saved agent work, never live execution evidence."""
import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from .domain import CRMError, settings
from .native_work import (EXECUTION_SOURCE, INVALID, SCHEMA_VERSION, TOOLSETS,
                          NativeWorkStore, assignments)

SUMMARY_LIMIT = 3
STATES = {'pending', 'create_unknown', 'resume_unknown', 'unknown', 'bound_paused',
          'scheduled', 'result_reported', *INVALID}


def _summary(row, task, workspace, profile):
    """Validate the bounded saved payload, but expose no instructions or results."""
    payload = json.loads(row['payload'])
    if (hashlib.sha256(row['payload'].encode()).hexdigest() != row['digest']
            or not isinstance(payload, dict) or payload.get('schema_version') != SCHEMA_VERSION
            or payload.get('workspace') != workspace or payload.get('profile') != profile
            or payload.get('task_id') != task['id'] or payload.get('task_status') != 'open'
            or type(payload.get('task_version')) is not int or payload['task_version'] < 1
            or payload.get('action') != 'internal_crm_analysis'
            or payload.get('execution_source') != EXECUTION_SOURCE
            or payload.get('enabled_toolsets') != list(TOOLSETS)
            or payload.get('generation') != 1 or row['state'] not in STATES
            or not isinstance(payload.get('human_owner'), str)
            or not payload['human_owner'].strip() or len(payload['human_owner']) > 160
            or (row['state'] == 'pending' and (row['reason'] != 'not_scheduled' or row['job_id']))):
        raise CRMError('Saved agent-work summary is unavailable', 503)
    return dict(id=row['id'], human_owner=payload['human_owner'], executor='Hermes',
                state=row['state'], source_task_current=task['version'] == payload['task_version'])


def add_assignment_summaries(crm, conn, task_rows):
    """Use the overview's existing snapshot, at most six tasks/three intents each.

    Exact counts include all history; recent summaries are not a selected current
    assignee. No event/report text, scheduler call, new token or schema creation.
    A missing store means no saved work. Incompatible/corrupt evidence is unknown.
    """
    if not task_rows:
        return
    if len(task_rows) > 6:
        raise ValueError('Overview task summary limit exceeded')
    for task in task_rows:
        task['agent_work'] = dict(status='unavailable', total=None, items=[])
    try:
        workspace = conn.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar()
        # An empty explicit value prevents NativeWorkStore bootstrapping a token.
        store = NativeWorkStore(crm, initialize=False, connection=conn, workspace=workspace or '')
        if store.available and not workspace:
            return
        if not store.available:
            for task in task_rows:
                task['agent_work'] = dict(status='available', total=0, items=[])
            return
        for task in task_rows:
            scope = (assignments.c.workspace == workspace, assignments.c.profile == crm.profile,
                     assignments.c.task_id == task['id'])
            total = conn.execute(select(func.count()).select_from(assignments).where(*scope)).scalar_one()
            rows = conn.execute(select(assignments.c.id, assignments.c.payload, assignments.c.digest,
                assignments.c.state, assignments.c.reason, assignments.c.job_id).where(*scope)
                .order_by(assignments.c.created_at.desc(), assignments.c.id.desc()).limit(SUMMARY_LIMIT)).mappings()
            try:
                items = [_summary(row, task, workspace, crm.profile) for row in rows]
            except (CRMError, ValueError, TypeError, KeyError, AttributeError):
                continue
            task['agent_work'] = dict(status='available', total=total, items=items)
    except (CRMError, SQLAlchemyError):
        # Do not let an optional summary make a healthy-looking unassigned claim.
        for task in task_rows:
            task['agent_work'] = dict(status='unavailable', total=None, items=[])
