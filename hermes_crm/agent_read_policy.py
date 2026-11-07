"""Data minimization for the base model-facing CRM tool surface.

This is a presentation policy, NOT record authorization or a DLP classifier.
Names, titles and ordinary structured business fields remain visible. A host
cron identity of None is also possible for delegated agents, so this module
never interprets absence of that identity as interactive permission. Human
REST/UI reads and the separately permissioned schema/report/work tools are
outside this projection. All custom values are omitted because the catalog
has no trusted field-level sensitivity classification.
"""
from copy import deepcopy
from collections.abc import Mapping

from .domain import CRMError

_COMMON = frozenset({'id', 'version', 'created_at', 'updated_at'})
_RECORD_FIELDS = {
    'contact': _COMMON | {'name', 'email', 'company', 'title', 'lifecycle'},
    'deal': _COMMON | {'title', 'contact_id', 'contact_name', 'value', 'currency',
                       'stage', 'probability', 'close_date'},
    'task': _COMMON | {'title', 'contact_id', 'contact_name', 'deal_id', 'due_at',
                       'priority', 'status', 'schedule_status', 'scheduler_job_id'},
}
_RECORD_TOOLS = {
    f'crm_{kind}_{operation}': (kind, operation)
    for kind in _RECORD_FIELDS for operation in ('get', 'list', 'create', 'update')
}
PROJECTED_TOOLS = frozenset(_RECORD_TOOLS) | {
    'crm_contact_report', 'crm_overview', 'crm_followup_schedule',
}


def _mapping(value):
    if not isinstance(value, Mapping):
        raise CRMError('Unexpected CRM projection shape', 503)
    return value


def _scalars(value, fields):
    """New fields and unexpected nested objects cannot silently expand output."""
    value = _mapping(value)
    return {key: item for key, item in value.items()
            if key in fields and (item is None or type(item) in (str, int, float, bool))}


def _records(value, kind):
    if not isinstance(value, list):
        raise CRMError('Unexpected CRM projection shape', 503)
    return [_scalars(item, _RECORD_FIELDS[kind]) for item in value]


def project_agent_result(tool_name, data):
    """Project a known base tool result; call only for PROJECTED_TOOLS.

    Fail closed on an unknown tool rather than treating a newly registered read
    surface as reviewed. These projections deliberately retain workspace-wide
    counts: they cannot be substituted for pre-query row scope predicates.
    """
    if tool_name in _RECORD_TOOLS:
        kind, operation = _RECORD_TOOLS[tool_name]
        return (_records(data, kind) if operation == 'list'
                else _scalars(data, _RECORD_FIELDS[kind]))
    if tool_name == 'crm_contact_report':
        data = _mapping(data)
        result = _scalars(data, {'total', 'limit', 'offset'})
        items = data.get('items', [])
        if not isinstance(items, list):
            raise CRMError('Unexpected CRM projection shape', 503)
        result['items'] = []
        for item in items:
            projected = _scalars(item, _RECORD_FIELDS['contact'] | {
                'deal_count', 'open_followup_count', 'overdue_followup_count', 'next_followup_at'})
            stages = item.get('deal_stages', [])
            if isinstance(stages, list) and all(type(stage) is str for stage in stages):
                projected['deal_stages'] = list(stages)
            result['items'].append(projected)
        return result
    if tool_name == 'crm_overview':
        data = _mapping(data)
        result = _scalars(data, {'contacts', 'open_deals', 'pipeline_value', 'weighted_value',
                                 'won_value', 'open_tasks', 'overdue_tasks'})
        result['tasks'] = _records(data.get('tasks', []), 'task')
        result['lead_attention'] = _scalars(data.get('lead_attention', {}),
                                            {'no_open_followup', 'overdue_followup'})
        stages = data.get('stages', [])
        if not isinstance(stages, list):
            raise CRMError('Unexpected CRM projection shape', 503)
        result['stages'] = [_scalars(stage, {'stage', 'label', 'outcome', 'probability',
                              'archived', 'contact_count', 'count', 'value'}) for stage in stages]
        return result
    if tool_name == 'crm_followup_schedule':
        data = _mapping(data)
        result = _scalars(data, {'already_scheduled', 'execution_verified', 'note'})
        result['task'] = _scalars(data.get('task', {}), _RECORD_FIELDS['task'])
        if 'scheduler' in data:
            # Do not echo host job prompts, arbitrary scheduler errors or metadata.
            result['scheduler'] = _scalars(data['scheduler'], {'success', 'job_id', 'gateway_running'})
        return deepcopy(result)
    raise CRMError('No reviewed agent projection for this tool', 503)


def read_record_fields(crm, *, kind, id, fields):
    """Explicit ordinary-data selection, not a user-consent or identity check.

    Only the ordinary record/catalog store is used. Protected notes, host state
    and arbitrary paths are deliberately not reachable through this function.
    A missing value for a known custom field is represented as null.
    """
    import re
    if kind not in {'contacts', 'deals', 'tasks'}:
        raise CRMError('Invalid record kind')
    if not isinstance(id, str) or not 1 <= len(id) <= 36:
        raise CRMError('Invalid record ID')
    if not isinstance(fields, list) or not 1 <= len(fields) <= 20:
        raise CRMError('Request between 1 and 20 exact field paths')
    if any(not isinstance(path, str) or not re.fullmatch(
            r'notes|custom\.[a-z][a-z0-9_]{0,63}', path) for path in fields):
        raise CRMError('Only notes or custom.<known field key> may be requested')
    if len(set(fields)) != len(fields):
        raise CRMError('Duplicate requested field paths')
    with crm._read_connection() as conn:
        known = {field['key'] for field in crm.catalog(conn)['fields'][kind]}
        if any(path.startswith('custom.') and path[7:] not in known for path in fields):
            raise CRMError('Unknown custom field requested')
        record = crm._get(conn, kind, id)
        values = {path: record['notes'] if path == 'notes' else record['custom_fields'].get(path[7:])
                  for path in fields}
        return dict(id=record['id'], version=record['version'], fields=values)
