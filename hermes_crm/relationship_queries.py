"""Coherent current-relationship rollups and explicitly sourced interaction history."""
from contextlib import nullcontext
from sqlalchemy import select, func, literal, String, Boolean, case, and_, or_, union_all
from .domain import CRMError, TABLES, contacts, deals, tasks, activity
from .relationship_schema import companies, contact_companies, events, event_tasks
from .relationship_store import check_schema
from .report_store import scope_for

RELATIONSHIP_SEMANTICS = 'current_contact_relationships'


def _contact_expression(kind, source=None):
    source = source if source is not None else TABLES.get(kind)
    if kind == 'contacts': return source.c.id
    if kind == 'deals': return source.c.contact_id
    if kind == 'tasks':
        related = deals.alias('relationship_task_deal')
        indirect = select(related.c.contact_id).where(related.c.id == source.c.deal_id).correlate(source).scalar_subquery()
        return case((source.c.contact_id.is_(None), indirect), else_=source.c.contact_id)
    raise CRMError('Unsupported relationship record kind')


def company_expressions(crm, kind, source=None, *, conn):
    source = source if source is not None else TABLES.get(kind)
    """Correlated scalar expressions: never multiply report rows or infer by text."""
    if kind not in ('contacts', 'deals', 'tasks'): raise CRMError('Unsupported relationship record kind')
    if not check_schema(crm, conn):
        return {name: literal(None, type_=Boolean() if name == 'company_archived' else String()) for name in ('company_id', 'company_name', 'company_archived', 'company_link_basis')}
    scope = scope_for(crm, connection=conn)
    contact_id = _contact_expression(kind, source)
    joined = contact_companies.join(companies, and_(companies.c.scope == contact_companies.c.scope, companies.c.id == contact_companies.c.company_id))
    predicates = (contact_companies.c.scope == scope, contact_companies.c.contact_id == contact_id)
    return {name: select(column).select_from(joined).where(*predicates).correlate(source).scalar_subquery()
            for name, column in (('company_id', companies.c.id), ('company_name', companies.c.name), ('company_archived', companies.c.archived_at.is_not(None)), ('company_link_basis', literal('current_contact_relationships')))}


def audit_scope_predicate(crm, conn):
    """Filter new audit kinds before pagination; legacy audit visibility is unchanged."""
    import uuid
    current_scope = scope_for(crm, connection=conn)
    policy_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'task-owner-policy:'+current_scope)) if current_scope else None
    ordinary = or_(activity.c.entity_type.not_in(('companies', 'events', 'task_owner_policy')),
                   and_(activity.c.entity_type == 'task_owner_policy', activity.c.entity_id == policy_id))
    if not check_schema(crm, conn):
        return ordinary
    scope = scope_for(crm, connection=conn)
    return or_(
        ordinary,
        and_(activity.c.entity_type == 'companies', activity.c.entity_id.in_(
            select(companies.c.id).where(companies.c.scope == scope))),
        and_(activity.c.entity_type == 'events', activity.c.entity_id.in_(
            select(events.c.id).where(events.c.scope == scope))),
    )


def project_records(crm, kind, records, conn=None):
    return RelationshipQueries(crm).project_records(kind, records, conn=conn)


class RelationshipQueries:
    def __init__(self, crm): self.crm = crm

    def _read(self, conn): return nullcontext(conn) if conn is not None else self.crm._read_connection()

    def _page(self, conn, stmt, order, limit, offset):
        self.crm._integer(limit, 'limit', 1, 100)
        self.crm._integer(offset, 'offset')
        total = conn.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        items = [dict(row) for row in conn.execute(stmt.order_by(*order).limit(limit).offset(offset)).mappings()]
        return dict(items=items, total=total, limit=limit, offset=offset)

    def _company(self, conn, company_id):
        if not check_schema(self.crm, conn): raise CRMError('Company not found', 404)
        scope = scope_for(self.crm, connection=conn)
        row = conn.execute(select(companies).where(companies.c.scope == scope, companies.c.id == company_id)).mappings().first()
        if row is None: raise CRMError('Company not found', 404)
        return {k: v for k, v in row.items() if k != 'scope'}

    def _records(self, conn, company_id, kind):
        if kind == 'opportunities': kind = 'deals'
        scope = scope_for(self.crm, connection=conn)
        if kind == 'events':
            table = events
            predicate = and_(events.c.scope == scope, events.c.company_id == company_id)
        elif kind in TABLES:
            table = TABLES[kind]
            linked = select(contact_companies.c.contact_id).where(contact_companies.c.scope == scope, contact_companies.c.company_id == company_id)
            predicate = _contact_expression(kind).in_(linked)
            if kind == 'tasks':
                event_members = select(event_tasks.c.task_id).select_from(event_tasks.join(events, and_(event_tasks.c.scope == events.c.scope, event_tasks.c.event_id == events.c.id))).where(event_tasks.c.scope == scope, events.c.company_id == company_id)
                predicate = or_(predicate, tasks.c.id.in_(event_members))
        else: raise CRMError('Unknown Company record kind')
        columns = [c for c in table.c if c.name not in ('scope', 'notes', 'outcome', 'outcome_summary')]
        return table, select(*columns).where(predicate), kind

    def company_detail(self, company_id, *, conn=None):
        with self._read(conn) as conn:
            company = self._company(conn, company_id)
            counts = {}
            for kind in ('contacts', 'deals', 'tasks', 'events'):
                _, stmt, _ = self._records(conn, company_id, kind)
                counts[kind] = conn.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            return dict(company=company, counts=counts, relationship_semantics=RELATIONSHIP_SEMANTICS)

    def company_records(self, company_id, kind, limit=50, offset=0, *, conn=None):
        with self._read(conn) as conn:
            self._company(conn, company_id)
            table, stmt, kind = self._records(conn, company_id, kind)
            order = (table.c.starts_at.desc(), table.c.id) if kind == 'events' else (table.c.created_at.desc(), table.c.id)
            page = self._page(conn, stmt, order, limit, offset)
            if kind in TABLES: page['items'] = self.project_records(kind, page['items'], conn=conn)
            return page

    def project_records(self, kind, records, *, conn=None):
        if kind not in TABLES: raise CRMError('Unsupported relationship record kind')
        result = [dict(record) for record in records]
        with self._read(conn) as conn:
            expressions = company_expressions(self.crm, kind, conn=conn)
            projected = {}
            # Bound SQL parameter counts without imposing a result-size cap.
            ids = list(dict.fromkeys(r['id'] for r in result))
            for start in range(0, len(ids), 400):
                stmt = select(TABLES[kind].c.id, *(value.label(name) for name, value in expressions.items())).where(TABLES[kind].c.id.in_(ids[start:start + 400]))
                projected.update((row['id'], dict(row)) for row in conn.execute(stmt).mappings())
            event_links = {}
            if kind == 'tasks' and check_schema(self.crm, conn):
                scope = scope_for(self.crm, connection=conn)
                joined = event_tasks.join(events, and_(events.c.scope == event_tasks.c.scope, events.c.id == event_tasks.c.event_id)).outerjoin(companies, and_(companies.c.scope == events.c.scope, companies.c.id == events.c.company_id))
                for start in range(0, len(ids), 400):
                    stmt = select(event_tasks.c.task_id, events.c.id.label('event_id'), events.c.title.label('event_title'), events.c.status.label('event_status'), events.c.contact_id.label('event_contact_id'), events.c.company_id.label('event_company_id'), companies.c.name.label('event_company_name')).select_from(joined).where(event_tasks.c.scope == scope, event_tasks.c.task_id.in_(ids[start:start + 400]))
                    event_links.update((row['task_id'], dict(row)) for row in conn.execute(stmt).mappings())
            for record in result:
                fields = projected.get(record['id'], {})
                record.update({name: fields.get(name) for name in expressions})
                record['company_link_basis'] = 'current_contact_relationships' if record['company_id'] is not None else None
                if kind == 'tasks':
                    link = event_links.get(record['id'], {})
                    record.update({name: link.get(name) for name in ('event_id', 'event_title', 'event_status', 'event_contact_id', 'event_company_id', 'event_company_name')})
                    record['event_link_basis'] = 'explicit_event_tasks' if link else None
        return result

    def selectors(self, kind, q='', limit=50, offset=0, *, conn=None):
        """Minimal, paged core-record choices; text search never chooses an identity."""
        if kind not in TABLES: raise CRMError('Unknown selector record kind')
        query = self.crm._text_filter(q, 'q')
        table = TABLES[kind]
        names = ('id', 'version', 'name', 'title', 'email', 'company', 'contact_id', 'deal_id', 'status')
        stmt = select(*(table.c[name] for name in names if name in table.c))
        if query:
            searchable = [table.c[name] for name in ('id', 'name', 'title', 'email', 'company') if name in table.c]
            stmt = stmt.where(or_(*(func.lower(column).like('%' + query + '%', escape='\\') for column in searchable)))
        title = table.c.name if kind == 'contacts' else table.c.title
        with self._read(conn) as conn:
            return self._page(conn, stmt, (func.lower(title), table.c.id), limit, offset)

    def company_expressions(self, kind, source, *, conn): return company_expressions(self.crm, kind, source, conn=conn)

    def _event(self, conn, event_id):
        if not check_schema(self.crm, conn): raise CRMError('Event not found', 404)
        scope = scope_for(self.crm, connection=conn)
        row = conn.execute(select(events).where(events.c.scope == scope, events.c.id == event_id)).mappings().first()
        if row is None: raise CRMError('Event not found', 404)
        return {key: value for key, value in row.items() if key != 'scope'}

    def event_detail(self, event_id, *, conn=None):
        with self._read(conn) as conn:
            from .events import Events
            event = Events(self.crm).get(event_id, include_text=True, conn=conn)
            scope = scope_for(self.crm, connection=conn)
            count = conn.execute(select(func.count()).select_from(event_tasks.join(tasks, tasks.c.id == event_tasks.c.task_id)).where(event_tasks.c.scope == scope, event_tasks.c.event_id == event_id)).scalar_one()
            return dict(event=event, counts=dict(tasks=count), relationship_semantics='explicit_event_tasks')

    def event_tasks(self, event_id, limit=50, offset=0, *, conn=None):
        with self._read(conn) as conn:
            self._event(conn, event_id)
            scope = scope_for(self.crm, connection=conn)
            linked = select(event_tasks.c.task_id).where(event_tasks.c.scope == scope, event_tasks.c.event_id == event_id)
            stmt = select(*(c for c in tasks.c if c.name != 'notes')).where(tasks.c.id.in_(linked))
            page = self._page(conn, stmt, (tasks.c.due_at, tasks.c.id), limit, offset)
            page['items'] = self.project_records('tasks', page['items'], conn=conn)
            return page

    def contact_tasks(self, contact_id, limit=50, offset=0, *, conn=None):
        with self._read(conn) as conn:
            self.crm._get(conn, 'contacts', contact_id)
            predicate = _contact_expression('tasks') == contact_id
            if check_schema(self.crm, conn):
                scope = scope_for(self.crm, connection=conn)
                linked = select(event_tasks.c.task_id).select_from(event_tasks.join(events, and_(events.c.scope == event_tasks.c.scope, events.c.id == event_tasks.c.event_id))).where(event_tasks.c.scope == scope, events.c.contact_id == contact_id)
                predicate = or_(predicate, tasks.c.id.in_(linked))
            stmt = select(*(c for c in tasks.c if c.name != 'notes')).where(predicate)
            page = self._page(conn, stmt, (tasks.c.due_at, tasks.c.id), limit, offset)
            page['items'] = self.project_records('tasks', page['items'], conn=conn)
            return page

    def relationship_activities(self, contact_id=None, company_id=None, limit=50, offset=0, *, conn=None):
        """Only completed local claims and nonvoid logs; no audit or planned Events."""
        from .report_interactions import interactions, interaction_scope
        self.crm._integer(limit, 'limit', 1, 100)
        self.crm._integer(offset, 'offset')
        with self._read(conn) as conn:
            available = check_schema(self.crm, conn)
            scope = scope_for(self.crm, connection=conn)
            if contact_id is not None: self.crm._get(conn, 'contacts', contact_id)
            if company_id is not None: self._company(conn, company_id)
            statements = []
            if available:
                stmt = select((literal('event:') + events.c.id).label('id'), events.c.id.label('record_id'), literal('event').label('record_type'), events.c.title.label('title'), events.c.kind.label('kind'), events.c.contact_id.label('contact_id'), events.c.company_id.label('company_id'), events.c.outcome_happened_at.label('happened_at'), events.c.recorded_at.label('recorded_at'), literal('local').label('source'), events.c.outcome_provenance.label('provenance'), literal('claimed_occurrence').label('timestamp_basis')).where(events.c.scope == scope, events.c.status == 'completed')
                if contact_id is not None: stmt = stmt.where(events.c.contact_id == contact_id)
                if company_id is not None: stmt = stmt.where(events.c.company_id == company_id)
                statements.append(stmt)
            log_scope = interaction_scope(self.crm, connection=conn)
            if log_scope is not None:
                stmt = select((literal('interaction:') + interactions.c.id).label('id'), interactions.c.id.label('record_id'), literal('interaction').label('record_type'), literal('Logged interaction').label('title'), interactions.c.kind.label('kind'), interactions.c.contact_id.label('contact_id'), literal(None, type_=String()).label('company_id'), interactions.c.happened_at.label('happened_at'), interactions.c.created_at.label('recorded_at'), literal('contact_log').label('source'), interactions.c.provenance.label('provenance'), literal('self_reported_happened_at').label('timestamp_basis')).where(interactions.c.scope == log_scope, interactions.c.voided_at.is_(None))
                if contact_id is not None: stmt = stmt.where(interactions.c.contact_id == contact_id)
                if company_id is not None:
                    stmt = stmt.where(interactions.c.contact_id.in_(select(contact_companies.c.contact_id).where(contact_companies.c.scope == scope, contact_companies.c.company_id == company_id)))
                statements.append(stmt)
            if not statements: page = dict(items=[], total=0, limit=limit, offset=offset)
            else:
                combined = union_all(*statements).subquery()
                page = self._page(conn, select(combined), (combined.c.happened_at.desc(), combined.c.id), limit, offset)
            contact_ids = {item['contact_id'] for item in page['items'] if item['contact_id']}
            contact_rows = [dict(row) for row in conn.execute(select(contacts.c.id, contacts.c.name).where(contacts.c.id.in_(contact_ids))).mappings()] if contact_ids else []
            targets = {row['id']: row for row in self.project_records('contacts', contact_rows, conn=conn)}
            company_ids = {item['company_id'] for item in page['items'] if item['company_id']}
            company_targets = {row['id']: dict(row) for row in conn.execute(select(companies.c.id, companies.c.name, companies.c.archived_at).where(companies.c.scope == scope, companies.c.id.in_(company_ids))).mappings()} if company_ids and available else {}
            for item in page['items']:
                target = targets.get(item['contact_id'], {})
                item['contact_name'] = target.get('name')
                if item['record_type'] == 'interaction':
                    item['company_id'] = target.get('company_id')
                    item['company_name'] = target.get('company_name')
                    item['company_archived'] = target.get('company_archived')
                else:
                    company = company_targets.get(item['company_id'], {})
                    item['company_name'] = company.get('name')
                    item['company_archived'] = company.get('archived_at') is not None if company else None
                item.update(source_type=item['record_type'], source_id=item['record_id'], display_timestamp=item['happened_at'], time_basis=item['timestamp_basis'])
                item['relationship_basis'] = 'explicit_company' if item['record_type'] == 'event' else 'current_contact_relationships'
            return page

    def record_history(self, kind=None, record_id=None, limit=50, offset=0, *, conn=None):
        entity_type, entity_id = kind, record_id
        if entity_type is not None and entity_type not in ('contacts', 'deals', 'tasks', 'companies', 'events', 'customization'): raise CRMError('Unknown record type')
        with self._read(conn) as conn:
            stmt = select(activity).where(audit_scope_predicate(self.crm, conn))
            if entity_type is not None: stmt = stmt.where(activity.c.entity_type == entity_type)
            if entity_id is not None: stmt = stmt.where(activity.c.entity_id == entity_id)
            return self._page(conn, stmt, (activity.c.created_at.desc(), activity.c.id), limit, offset)
