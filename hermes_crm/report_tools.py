"""Dedicated report/contact-log toolsets, never added to saved crm_read jobs."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from .domain import CRMError
from .reports import ReportEngine
from .report_store import ReportStore
from .report_interactions import InteractionStore


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Empty(Strict):
    pass


class Run(Strict):
    definition: dict[str, Any] = Field(description='Typed catalog-validated report definition. No SQL or formulas.')
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=2_000_000_000)
    evaluated_at: str | None = Field(default=None, max_length=80,
        description='Optional frozen evaluation instant from a prior chart; data still reruns live.')


class Listing(Strict):
    include_archived: bool = False
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=2_000_000_000)


class Get(Strict):
    report_id: str = Field(min_length=1, max_length=36)
    version: int | None = Field(default=None, ge=1)


class SavedRun(Strict):
    report_id: str = Field(min_length=1, max_length=36)
    expected_version: int = Field(ge=1)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=2_000_000_000)
    evaluated_at: str | None = Field(default=None, max_length=80)


class Create(Strict):
    title: str = Field(min_length=1, max_length=160)
    definition: dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=160)


class Update(Create):
    report_id: str = Field(min_length=1, max_length=36)
    expected_version: int = Field(ge=1)


class Version(Strict):
    report_id: str = Field(min_length=1, max_length=36)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=160)


class Dashboard(Strict):
    cards: list[dict[str, Any]] = Field(max_length=12,
        description='Ordered cards referencing exact saved report IDs and versions. No arbitrary queries or HTML.')
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=160)


class ContactLog(Strict):
    contact_id: str = Field(min_length=1, max_length=36)
    happened_at: str = Field(max_length=80, description='Past actual-contact claim with explicit timezone. Self-reported, not delivery proof.')
    kind: Literal['meeting', 'call', 'email', 'chat', 'other']
    direction: Literal['inbound', 'outbound', 'other'] = 'other'
    summary: str = Field(min_length=1, max_length=2000)
    expected_contact_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=160)


class LogList(Strict):
    contact_id: str = Field(min_length=1, max_length=36)
    include_voided: bool = False
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=2_000_000_000)


class LogVoid(Strict):
    interaction_id: str = Field(min_length=1, max_length=36)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=160)


def current_report(crm, report_id, version=None):
    row = ReportStore(crm).get(report_id)
    if version is not None and row['version'] != version:
        raise CRMError('This report changed. Review its current version before running or adopting it.', 409)
    return row


def _saved_run(crm, args):
    row = current_report(crm, args['report_id'], args['expected_version'])
    if row['archived_at'] is not None:
        raise CRMError('This report is archived. Restore it before running.', 409)
    return ReportEngine(crm).run(row['definition'], **{k: v for k, v in args.items() if k not in {'report_id', 'expected_version'}})


def register_report_tools(register):
    def tool(name, description, model, toolset, operation):
        schema = model.model_json_schema()
        register(name, description, schema['properties'], schema.get('required', []),
                 lambda crm, args, context: operation(crm, args), toolset=toolset, argument_model=model)

    tool('crm_report_catalog', 'Describe supported report fields, types, units and semantics. No SQL, Gmail data or historical conversion claims.',
         Empty, 'crm_reports', lambda crm, a: ReportEngine(crm).catalog())
    tool('crm_report_run', 'Preview a typed report over live contacts/deals/tasks/Companies/local Events. UTC dates; distinct records. Last logged contact is self-reported; next task can be overdue and is not execution proof. Chart drilldown definitions rerun live, not historical snapshots.',
         Run, 'crm_reports', lambda crm, a: ReportEngine(crm).run(**a))
    tool('crm_report_list', 'List saved current-profile report definitions and versions, not email or external data.',
         Listing, 'crm_reports', lambda crm, a: ReportStore(crm).list(**a))
    tool('crm_report_get', 'Read one saved report definition. Optional exact version prevents silently changing a pinned chart.',
         Get, 'crm_reports', lambda crm, a: current_report(crm, a['report_id'], a.get('version')))
    tool('crm_saved_report_run', 'Run an active saved report at its exact current version. Results reflect live data and disclose evaluation/observation times.',
         SavedRun, 'crm_reports', _saved_run)
    tool('crm_dashboard_get', 'Read current profile custom dashboard cards, versions and unresolved report references. No provider calls.',
         Empty, 'crm_reports', lambda crm, a: ReportStore(crm).get_dashboard())
    tool('crm_report_create', 'Save a new typed report requested by the user. Preview with crm_report_run first. Stable idempotency key prevents duplicate creates; no dashboard is changed.',
         Create, 'crm_report_write', lambda crm, a: ReportStore(crm).create(a['title'], a['definition'], a['idempotency_key']))
    tool('crm_report_update', 'Update a saved report with its expected version and stable key. Dashboard references remain pinned until explicitly adopted; does not contact anyone.',
         Update, 'crm_report_write', lambda crm, a: ReportStore(crm).update(a['report_id'], a['title'], a['definition'], a['expected_version'], a['idempotency_key']))
    for action in ('archive', 'restore'):
        tool('crm_report_' + action, f'{action.title()} a saved report at its expected version. Archive is recoverable; affected dashboard references remain visible, not deleted.',
             Version, 'crm_report_write', lambda crm, a, action=action: getattr(ReportStore(crm), action)(a['report_id'], a['expected_version'], a['idempotency_key']))
    tool('crm_dashboard_save', 'Save the explicitly requested ordered dashboard cards against the current dashboard version. References pin exact report versions; no global filter is silently applied.',
         Dashboard, 'crm_report_write', lambda crm, a: ReportStore(crm).save_dashboard(a['cards'], a['expected_version'], a['idempotency_key']))
    tool('crm_contact_log', 'Record an explicitly provided past contact event as a self-reported claim. This does not send email/call, verify delivery, read Gmail or infer contact from an edit. The trusted adapter records the agent as author.',
         ContactLog, 'crm_interaction_write', lambda crm, a: InteractionStore(crm).create(
             {k: v for k, v in a.items() if k not in {'expected_contact_version', 'idempotency_key'}},
             a['expected_contact_version'], 'hermes', a['idempotency_key']))
    tool('crm_contact_log_list', 'Read explicitly logged contact claims and their self-reported provenance. These are not provider-verified communications.',
         LogList, 'crm_interaction_read', lambda crm, a: InteractionStore(crm).list(**a))
    tool('crm_contact_log_void', 'Invalidate an erroneous authored contact claim with a reason and expected version. Original evidence remains; no external message is changed.',
         LogVoid, 'crm_interaction_write', lambda crm, a: InteractionStore(crm).void(a['interaction_id'], a['expected_version'], a['reason'], 'hermes', a['idempotency_key']))
