"""Cross-family review validation for encrypted exports and offline recovery."""
from .domain import CRMError
from .report_review_schema import TABLES, events, operations
from .report_reviews import validate_ledger, report_binding


def validate_snapshot(tables,*,workspace,profile,scope):
    names={t.name for t in TABLES}
    if not names.intersection(tables): return
    try:
        if not names <= tables.keys(): raise ValueError()
        groups=validate_ledger(tables[events.name],tables[operations.name],scope)
        native={r['id']:r for r in tables.get('crm_native_assignments',[])}
        native_reports={r['id']:r for r in tables.get('crm_native_work_reports',[])}
        scheduled={r['id']:r for r in tables.get('crm_scheduled_research_v1',[])}
        scheduled_reports={r['key']:r for r in tables.get('crm_scheduled_research_ops_v1',[])}
        for (family,assignment_id,report_id),history in groups.items():
            assignment=(native if family=='native' else scheduled)[assignment_id]
            report=(native_reports if family=='native' else scheduled_reports)[report_id]
            binding=report_binding(family,assignment,report,workspace=workspace,profile=profile)
            if any(e['context']['report'] != binding for e in history): raise ValueError()
    except (CRMError,KeyError,TypeError,ValueError):
        raise CRMError('Report review export is not a consistent supported snapshot',422) from None
