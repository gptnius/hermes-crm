"""Dedicated Company/Event tools. No scheduled crm_read authority is expanded."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from .companies import CompanyStore
from .events import EventStore
from .relationship_queries import RelationshipQueries


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Page(Strict):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=2_000_000_000)


class Companies(Page):
    q: str = Field(default='', max_length=500)
    include_archived: bool = False


class Get(Strict):
    record_id: str = Field(min_length=1, max_length=36)


class Related(Get, Page):
    kind: Literal['contacts', 'deals', 'tasks', 'events']


class Create(Strict):
    data: dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=160)


class ContactCreate(Create):
    company_id: str | None = Field(default=None, min_length=1, max_length=36)
    expected_company_version: int | None = Field(default=None, ge=1)


class Version(Get):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=160)


class Update(Version):
    data: dict[str, Any]


class Link(Get):
    expected_contact_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=160)
    company_id: str | None = Field(..., min_length=1, max_length=36)


class Reason(Version):
    reason: str = Field(min_length=1, max_length=2000)


class Complete(Update):
    pass


class Events(Page):
    q: str = Field(default='', max_length=500)
    kind: Literal['appointment','call'] | None = None
    starts_from: str | None = None
    starts_before: str | None = None
    contact_id: str | None = None
    deal_id: str | None = None
    company_id: str | None = None
    status: Literal['scheduled', 'needs_rescheduling', 'completed', 'cancelled'] | None = None


class RecordPage(Get, Page):
    pass


class TaskLink(Version):
    task_id: str = Field(min_length=1, max_length=36)
    expected_task_version: int = Field(ge=1)


class TaskUnlink(Version):
    event_id: str = Field(min_length=1, max_length=36)
    expected_task_version: int = Field(ge=1)


class Activities(Page):
    contact_id: str | None = None
    company_id: str | None = None


# Explicit allowlists, including nested records, avoid leaking ordinary plaintext
# notes or future schema fields through agent responses.
COMPANY_FIELDS = frozenset(('id','name','domain','version','created_at','updated_at','archived_at'))
EVENT_FIELDS = frozenset(('id','title','kind','status','version','starts_at','ends_at','timezone','contact_id','deal_id','company_id','created_at','updated_at','recorded_at','completed_at','cancelled_at','outcome_happened_at','source','outcome_provenance'))
CORE_FIELDS = frozenset(('id','name','title','email','company','company_id','company_name','company_archived','company_link_basis','contact_id','deal_id','version','status','priority','stage','value','currency','due_at','created_at','updated_at','event_id','event_title','event_status','event_contact_id','event_company_id','event_company_name','event_link_basis'))
LINK_FIELDS = frozenset(('contact_id','contact_version','company_id','company_name','company_archived','company_link_basis'))
ACTIVITY_FIELDS = frozenset(('id','record_id','record_type','title','kind','contact_id','company_id','happened_at','recorded_at','source','provenance','timestamp_basis','source_type','source_id','display_timestamp','time_basis','relationship_basis'))


def project(row, fields):
    return {key: value for key, value in row.items() if key in fields and (value is None or type(value) in (str, int, float, bool))}


def page(result, fields):
    return {**{k:result[k] for k in ('total','limit','offset')}, 'items':[project(row, fields) for row in result['items']]}


def revisions(crm, args):
    result=EventStore(crm).revisions(args['record_id'],limit=args.get('limit',50),offset=args.get('offset',0))
    return {**{k:result[k] for k in ('total','limit','offset')}, 'items':[
        {**project(row,frozenset(('event_id','version','created_at','actor'))), 'record':project(row['record'],EVENT_FIELDS)} for row in result['items']]}


def contact_receipt(result):
    return dict(contact=project(result['contact'],CORE_FIELDS), company_link=project(result['company_link'],LINK_FIELDS))


def task_receipt(result):
    return dict(event=project(result['event'],EVENT_FIELDS) if result['event'] is not None else None, task=project(result['task'],CORE_FIELDS), event_id=result['event_id'], task_id=result['task_id'])


def detail(crm, record_id):
    result = RelationshipQueries(crm).company_detail(record_id)
    return dict(company=project(result['company'], COMPANY_FIELDS), counts={k:result['counts'][k] for k in ('contacts','deals','tasks','events')}, relationship_semantics=result['relationship_semantics'])


def register_relationship_tools(register):
    def tool(name, description, model, toolset, operation):
        schema = model.model_json_schema()
        register(name, description, schema['properties'], schema.get('required', []),
                 lambda crm, args, context: operation(crm, args), toolset=toolset, argument_model=model)

    tool('crm_company_list', 'List explicit Company identities. Duplicate names remain distinct; no legacy text matching.', Companies, 'crm_company_read',
         lambda crm,a: page(CompanyStore(crm).list(**a), COMPANY_FIELDS))
    tool('crm_company_get', 'Read Company details and distinct current relationship counts, without ordinary notes.', Get, 'crm_company_read', lambda crm,a: detail(crm,a['record_id']))
    tool('crm_company_records', 'Page exact-ID current Company records with full totals. No historical ownership claim.', Related, 'crm_company_read',
         lambda crm,a: page(RelationshipQueries(crm).company_records(a['record_id'],a['kind'],limit=a.get('limit',50),offset=a.get('offset',0)), EVENT_FIELDS if a['kind']=='events' else CORE_FIELDS))
    tool('crm_contact_company_get', 'Read the explicit primary Company link without changing legacy company text.', Get, 'crm_company_read', lambda crm,a: project(CompanyStore(crm).get_contact_company(a['record_id']),LINK_FIELDS))
    tool('crm_company_create', 'Create an explicitly requested Company identity with a stable retry key. Never infer or match by name.', Create, 'crm_company_write', lambda crm,a: project(CompanyStore(crm).create(a['data'],actor='hermes',key=a['idempotency_key']),COMPANY_FIELDS))
    tool('crm_contact_create_with_company', 'Create a contact with an optional exact reviewed Company ID and current Company version. Never infer a link or overwrite legacy company text. Retry with the original payload and key.', ContactCreate, 'crm_company_write', lambda crm,a: contact_receipt(CompanyStore(crm).create_contact(a['data'],a.get('company_id'),a.get('expected_company_version'),actor='hermes',key=a['idempotency_key'])))
    tool('crm_company_update', 'Update an exact Company at its reviewed current version.', Update, 'crm_company_write', lambda crm,a: project(CompanyStore(crm).update(a['record_id'],a['data'],expected_version=a['expected_version'],actor='hermes',key=a['idempotency_key']),COMPANY_FIELDS))
    for action in ('archive','restore'):
        tool('crm_company_'+action, action.title()+' the exact Company at its expected version. Existing links remain visible.', Version, 'crm_company_write', lambda crm,a,action=action: project(getattr(CompanyStore(crm),action)(a['record_id'],expected_version=a['expected_version'],actor='hermes',key=a['idempotency_key']),COMPANY_FIELDS))
    tool('crm_contact_company_set', 'Set or clear a reviewed exact primary Company ID using the contact version. Never overwrites legacy company text.', Link, 'crm_company_write', lambda crm,a: project(CompanyStore(crm).set_contact_company(a['record_id'],a['company_id'],expected_contact_version=a['expected_contact_version'],actor='hermes',key=a['idempotency_key']),LINK_FIELDS))
    tool('crm_event_list', 'List local scheduled/completed/cancelled Events. No invitations, provider calls, or reminders.', Events, 'crm_event_read', lambda crm,a: page(EventStore(crm).list(**a),EVENT_FIELDS))
    tool('crm_event_get', 'Read an exact local Event, omitting ordinary notes and outcome text.', Get, 'crm_event_read', lambda crm,a: project(EventStore(crm).get(a['record_id']),EVENT_FIELDS))
    tool('crm_event_create', 'Create a local scheduled appointment/call with explicit-offset times and IANA display timezone. Does not invite, call, or schedule automation.', Create, 'crm_event_write', lambda crm,a: project(EventStore(crm).create(a['data'],actor='hermes',key=a['idempotency_key']),EVENT_FIELDS))
    tool('crm_event_update', 'Edit an explicitly requested scheduled local Event at its current version.', Update, 'crm_event_write', lambda crm,a: project(EventStore(crm).update(a['record_id'],a['data'],expected_version=a['expected_version'],actor='hermes',key=a['idempotency_key']),EVENT_FIELDS))
    tool('crm_event_complete', 'Record an explicitly supplied nonfuture occurrence and self-reported outcome. No task completion or verified communication claim.', Complete, 'crm_event_write', lambda crm,a: project(EventStore(crm).complete(a['record_id'],a['data'],expected_version=a['expected_version'],actor='hermes',key=a['idempotency_key']),EVENT_FIELDS))
    for action in ('cancel','reopen','needs_rescheduling'):
        tool('crm_event_'+action, action.title()+' an exact local Event with a reason and expected version. Prior revisions remain.', Reason, 'crm_event_write', lambda crm,a,action=action: project(getattr(EventStore(crm),action)(a['record_id'],a['reason'],expected_version=a['expected_version'],actor='hermes',key=a['idempotency_key']),EVENT_FIELDS))
    tool('crm_relationship_activities', 'Read completed local Events and self-reported contact logs, with provenance and time basis. Not verified provider communication.', Activities, 'crm_event_read', lambda crm,a: page(RelationshipQueries(crm).relationship_activities(**a),ACTIVITY_FIELDS))

    tool('crm_event_reschedule', 'Reschedule a local Event with explicit starts_at, ends_at and timezone. No invitation or scheduler effects.', Update, 'crm_event_write', lambda crm,a: project(EventStore(crm).reschedule(a['record_id'],a['data'],expected_version=a['expected_version'],actor='hermes',key=a['idempotency_key']),EVENT_FIELDS))
    tool('crm_event_tasks', 'Page tasks explicitly linked to an Event. No scheduling or task execution.', RecordPage, 'crm_event_read', lambda crm,a: page(RelationshipQueries(crm).event_tasks(a['record_id'],limit=a.get('limit',50),offset=a.get('offset',0)),CORE_FIELDS))
    tool('crm_event_task_create', 'Create a local task explicitly linked to an Event, without assigning or dispatching an agent.', Update, 'crm_event_write', lambda crm,a: task_receipt(EventStore(crm).create_task(a['record_id'],a['data'],expected_version=a['expected_version'],actor='hermes',key=a['idempotency_key'])))
    tool('crm_event_task_link', 'Link a reviewed existing task to an exact Event with both current versions. No execution or completion.', TaskLink, 'crm_event_write', lambda crm,a: task_receipt(EventStore(crm).link_task(a['record_id'],a['task_id'],expected_version=a['expected_version'],expected_task_version=a['expected_task_version'],actor='hermes',key=a['idempotency_key'])))
    tool('crm_event_task_unlink', 'Remove an explicit Event-task relationship at the current task version; retain both records.', TaskUnlink, 'crm_event_write', lambda crm,a: task_receipt(EventStore(crm).unlink_task(a['record_id'],event_id=a['event_id'],expected_version=a['expected_version'],expected_task_version=a['expected_task_version'],actor='hermes',key=a['idempotency_key'])))
    tool('crm_event_revisions', 'Read immutable Event revision metadata and minimized snapshots, without notes, reasons, or outcome text.', RecordPage, 'crm_event_read', revisions)
