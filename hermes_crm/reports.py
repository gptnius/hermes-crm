"""Typed, read-only reports over the live CRM. No provider or mailbox access."""
from __future__ import annotations
import copy
import math
import hashlib
import json
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator, ValidationInfo
from sqlalchemy import select, func, and_, or_, literal, cast, String, Float, Boolean, JSON, case
from .domain import TABLES, contacts, deals, tasks, STAGES, CRMError, now
from .native_work import read_snapshot

TEXT_OPS = ['eq', 'ne', 'in', 'not_in', 'contains', 'is_null', 'is_not_null']
ORDER_OPS = ['eq', 'ne', 'in', 'not_in', 'gt', 'gte', 'lt', 'lte', 'between', 'is_null', 'is_not_null']

def field(kind='text', *, note='', unit=None, choices=None):
    return dict(type=kind, selectable=True, sortable=kind != 'set', groupable=kind != 'set',
                operators=(['has_any','has_all','has_none','is_empty'] if kind == 'set' else ORDER_OPS if kind in ('integer','number','datetime','date') else ['eq','ne','in','not_in','is_null','is_not_null'] if kind == 'boolean' else TEXT_OPS),
                unit=unit, semantic_notes=note, **({'choices': choices} if choices else {}))

FIELDS = {
 'contacts': {**{k:field() for k in ('id','name','email','company','title')},
    'contact_type':field(choices=['lead','customer','partner'], note='Current contact classification, not classification at creation.'),
    'created_at':field('datetime'), 'linked_stages':field('set', choices=list(STAGES), note='Distinct current stages of linked deals; no primary stage.'),
    **{k:field('integer',unit='records') for k in ('deal_count','open_followup_count','overdue_followup_count')},
    'next_followup_at':field('datetime',note='Earliest open task due time, including overdue; direct or deal-linked tasks counted once.'),
    'last_logged_contact_at':field('datetime',note='Latest non-voided self-reported interaction; null is not proof no contact occurred.')},
 'deals': {**{k:field() for k in ('id','title','contact_id','contact_name')},
    'value':field('integer',unit='USD cents'), 'currency':field(choices=['USD']),
    'stage':field(choices=list(STAGES),note='Current deal stage, not historical outcome date.'),
    'probability':field('integer',unit='percent'), 'created_at':field('datetime'),
    'expected_close_date':field('date',note='Expected close date, not actual won date.')},
 'tasks': {**{k:field() for k in ('id','title','contact_id','deal_id','contact_name')},
    'status':field(choices=['open','done']), 'priority':field(choices=['normal','high']),
    'due_at':field('datetime'), 'created_at':field('datetime')}
}
for fields in FIELDS.values():
    for name, info in fields.items(): info['label'] = name.replace('_',' ').capitalize()

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Sort(Strict):
    field: str
    direction: Literal['asc','desc'] = 'asc'
class Group(Strict):
    field: str
    interval: Literal['day'] | None = None
class Measure(Strict):
    op: Literal['count','sum','avg','min','max'] = 'count'
    field: str | None = None

class ReportDefinition(Strict):
    schema_version: Literal[1] = 1
    entity: Literal['contacts','deals','tasks']
    columns: list[str] = Field(default_factory=lambda:['id'], min_length=1, max_length=20)
    filter: dict[str, Any] | None = None
    sort: list[Sort] = Field(default_factory=list, max_length=3)
    group_by: Group | None = None
    measure: Measure | None = None
    timezone: Literal['UTC'] = 'UTC'

    @field_validator('schema_version', mode='before')
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int: raise ValueError('schema_version must be integer 1')
        return value

    @model_validator(mode='after')
    def validate_fields(self, validation: ValidationInfo):
        if type(self.schema_version) is not int: raise ValueError('schema_version must be integer 1')
        fields = (validation.context or {}).get('fields', FIELDS)[self.entity]
        def known(name):
            if name not in fields: raise ValueError(f'Unknown field: {name}')
            return fields[name]
        if len(set(self.columns)) != len(self.columns): raise ValueError('Duplicate columns')
        for name in self.columns: known(name)
        for item in self.sort:
            if not known(item.field)['sortable']: raise ValueError('Field cannot be sorted')
        if self.group_by:
            info = known(self.group_by.field)
            if not info['groupable']: raise ValueError('Field cannot be grouped')
            if self.group_by.interval and info['type'] not in ('date','datetime'): raise ValueError('Day grouping requires a date')
            if info['type'] == 'datetime' and not self.group_by.interval: raise ValueError('Timestamp grouping requires day interval')
        if self.measure:
            m = self.measure
            if m.op == 'count' and m.field is not None: raise ValueError('Count counts records; omit field')
            if m.op != 'count' and (m.field is None or known(m.field)['type'] not in ('integer','number')): raise ValueError('Measure requires numeric field')
        conditions = [0]
        def visit(node, depth=0):
            if type(node) is not dict: raise ValueError('Filter must be an object')
            if depth > (2 if self.group_by else 3): raise ValueError('Filter depth exceeds limit (grouped reports reserve one level for drilldown)')
            groups = set(node) & {'all','any'}
            if groups:
                if len(node) != 1: raise ValueError('Group must contain exactly all or any')
                values = node[next(iter(groups))]
                if type(values) is not list or not 1 <= len(values) <= 32: raise ValueError('Group requires 1 to 32 children')
                for child in values: visit(child,depth+1)
                return
            if set(node) != {'field','op','value'}: raise ValueError('Condition requires field, op, value only')
            name, op, value = node['field'],node['op'],node['value']
            if type(name) is not str: raise ValueError('Invalid field')
            info = known(name)
            if type(op) is not str or op not in info['operators']: raise ValueError(f'Invalid operator for {name}')
            conditions[0] += 1
            if conditions[0] > 32: raise ValueError('Too many conditions')
            if op in ('is_null','is_not_null'):
                if value is not None: raise ValueError('Null operators require null value')
                return
            if op == 'is_empty':
                if type(value) is not bool: raise ValueError('is_empty requires boolean')
                return
            islist = op in ('in','not_in','between','has_any','has_all','has_none')
            if islist and (type(value) is not list or not 1 <= len(value) <= 100): raise ValueError('List requires 1 to 100 values')
            if op == 'between' and len(value) != 2: raise ValueError('between requires two bounds')
            values = value if islist else [value]
            for index, val in enumerate(values):
                kind = info['type']
                if kind == 'integer':
                    if type(val) is not int or abs(val)>9_007_199_254_740_991: raise ValueError('Expected bounded integer')
                elif kind == 'number':
                    if type(val) not in (int,float) or abs(val)>1_000_000_000_000_000 or not math.isfinite(val): raise ValueError('Expected bounded finite number')
                elif kind == 'boolean':
                    if type(val) is not bool: raise ValueError('Expected boolean')
                else:
                    maximum = info.get('max_length', 500)
                    if type(val) is not str or len(val)>maximum: raise ValueError(f'Expected text of at most {maximum} characters')
                    if 'choices' in info and val not in info['choices']: raise ValueError('Unknown choice')
                    if kind == 'date':
                        if date.fromisoformat(val).isoformat()!=val: raise ValueError('Use YYYY-MM-DD')
                    if kind == 'datetime':
                        parsed=datetime.fromisoformat(val.replace('Z','+00:00'))
                        if parsed.tzinfo is None: raise ValueError('Timestamp requires timezone')
                        val=parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')
                        if islist: value[index]=val
                        else: node['value']=val
            if op == 'between' and value[0]>value[1]: raise ValueError('Reversed range')
        if self.filter is not None: visit(self.filter)
        if self.group_by and conditions[0] > 30: raise ValueError('Grouped reports reserve two of 32 conditions for drilldown')
        return self

class ReportEngine:
    def __init__(self, crm): self.crm=crm
    def _schema(self, conn):
        schema = self.crm.catalog(conn=conn)
        fields = copy.deepcopy(FIELDS)
        stages = schema['stages']
        choices = [s['key'] for s in stages]
        labels = {s['key']: s['label'] for s in stages}
        for entity, name in [('contacts','linked_stages'),('deals','stage')]:
            fields[entity][name].update(choices=choices, choice_labels=labels,
                archived_choices=[s['key'] for s in stages if s['archived']])
        fields['deals']['stage_outcome'] = dict(field(choices=['open','won','lost'],
            note='Current stage outcome, not historical outcome or actual close date.'), label='Stage outcome')
        for entity, definitions in schema['fields'].items():
            for definition in definitions:
                kind = definition['type']
                info = field('text' if kind == 'single-select' else kind,
                    note='Current stored value. Archived definitions and values remain readable; this is not value history.')
                info.update(label=definition['label'], custom=True, archived=definition['archived'],
                    definition_version=definition['version'])
                if kind == 'text': info['max_length'] = 10000
                if kind == 'single-select': info['choices'] = definition['choices']
                fields[entity]['custom.' + definition['key']] = info
        return fields, schema

    def validate_definition(self, definition, conn=None, fields=None):
        if conn is None:
            with read_snapshot(self.crm) as snapshot:
                return self.validate_definition(definition, conn=snapshot)
        if fields is None: fields, _ = self._schema(conn)
        raw = definition.model_dump() if isinstance(definition, ReportDefinition) else definition
        return ReportDefinition.model_validate(copy.deepcopy(raw), context={'fields': fields})

    def catalog(self, conn=None):
        if conn is None:
            with read_snapshot(self.crm) as snapshot: return self.catalog(conn=snapshot)
        fields, schema = self._schema(conn)
        return dict(schema_version=1, entities={k:dict(label=k.capitalize(), fields=v) for k,v in fields.items()},
                    stages=copy.deepcopy(schema['stages']),
                    timezones=['UTC'], intervals=['day'], measures=['count','sum','avg','min','max'],
                    limits=dict(columns=20,filter_depth=3,conditions=32,grouped_filter_depth=2,grouped_conditions=30,list_values=100,sorts=3,page_size=100,groups=100),
                    semantics='Live current-state reports, not historical snapshots. Archived fields and stages remain readable. Labels are current; identifiers are stable. Drilldowns rerun live; evaluation time freezes overdue predicates, not row membership.')

    def _expressions(self, entity, timestamp, conn, schema):
        table=TABLES[entity]
        expr={k:table.c[k] for k in FIELDS[entity] if k in table.c}
        if entity == 'contacts':
            expr['contact_type']=contacts.c.lifecycle
            linked=select(deals.c.id).where(deals.c.contact_id==contacts.c.id).correlate(contacts)
            open_tasks=self.crm._contact_tasks().where(tasks.c.status=='open')
            def agg(query, expression): return query.with_only_columns(expression).scalar_subquery()
            expr.update(deal_count=agg(linked,func.count()),open_followup_count=agg(open_tasks,func.count()),
                overdue_followup_count=agg(open_tasks.where(tasks.c.due_at<timestamp),func.count()),
                next_followup_at=agg(open_tasks,func.min(tasks.c.due_at)),last_logged_contact_at=literal(None))
            # Optional ledger is deliberately not initialized by a report read.
            try:
                from .report_interactions import last_contact_expression
            except ImportError:
                pass
            else:
                expr['last_logged_contact_at']=last_contact_expression(self.crm,conn)
            # PostgreSQL cannot infer an untyped NULL bind in IS NULL predicates.
            expr['last_logged_contact_at']=cast(expr['last_logged_contact_at'],String(40))
        if entity == 'deals':
            expr['expected_close_date']=deals.c.close_date
            expr['stage_outcome']=case({s['key']:s['outcome'] for s in schema['stages']}, value=deals.c.stage, else_=None)
        if entity in ('deals','tasks'):
            contact_id=table.c.contact_id
            if entity=='tasks':
                inherited=select(deals.c.contact_id).where(deals.c.id==tasks.c.deal_id).correlate(tasks).scalar_subquery()
                contact_id=func.coalesce(contact_id,inherited)
            expr['contact_name']=select(contacts.c.name).where(contacts.c.id==contact_id).correlate(table).scalar_subquery()
        if schema['fields'][entity]:
            from .customization import values_table
            for definition in schema['fields'][entity]:
                key, kind = definition['key'], definition['type']
                if conn.dialect.name == 'postgresql':
                    value = cast(values_table.c.values_json, JSON).op('->>')(key)
                else:
                    value = func.json_extract(values_table.c.values_json, '$.' + key)
                if kind == 'number': value = cast(value, Float)
                elif kind == 'boolean': value = cast(value, Boolean)
                else: value = cast(value, String)
                expr['custom.' + key] = select(value).where(
                    values_table.c.kind == entity, values_table.c.record_id == table.c.id).correlate(table).scalar_subquery()
        return expr

    def _predicate(self,node,expr):
        if 'all' in node: return and_(*(self._predicate(c,expr) for c in node['all']))
        if 'any' in node: return or_(*(self._predicate(c,expr) for c in node['any']))
        name,op,v=node['field'],node['op'],node['value']
        if name=='linked_stages':
            linked=select(deals.c.id).where(deals.c.contact_id==contacts.c.id).correlate(contacts)
            if op=='is_empty': return ~linked.exists() if v else linked.exists()
            if op=='has_all': return and_(*(linked.where(deals.c.stage==s).exists() for s in v))
            match=linked.where(deals.c.stage.in_(v)).exists()
            return ~match if op=='has_none' else match
        c=expr[name]
        if op=='is_null': return c.is_(None)
        if op=='is_not_null': return c.is_not(None)
        if op=='contains': return func.lower(c).like('%'+v.lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%',escape='\\')
        if op=='in': return c.in_(v)
        if op=='not_in': return c.not_in(v)
        if op=='between': return and_(c>=v[0],c<=v[1])
        return {'eq':lambda:c==v,'ne':lambda:c!=v,'gt':lambda:c>v,'gte':lambda:c>=v,'lt':lambda:c<v,'lte':lambda:c<=v}[op]()

    def run(self, definition, limit=50, offset=0, evaluated_at=None):
        self.crm._integer(limit,'limit',1,100); self.crm._integer(offset,'offset')
        if evaluated_at is None: evaluated_at=now()
        try:
            dt=datetime.fromisoformat(evaluated_at.replace('Z','+00:00'))
            if dt.tzinfo is None: raise ValueError()
            timestamp=dt.astimezone(timezone.utc).isoformat(timespec='microseconds')
        except (ValueError,AttributeError): raise CRMError('evaluated_at requires a timezone-aware timestamp')
        with read_snapshot(self.crm) as conn:
            fields, schema = self._schema(conn)
            definition=self.validate_definition(definition, conn=conn, fields=fields)
            d=definition.model_dump(exclude_none=True)
            result=dict(definition=d,definition_hash=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                observed_at=now(),evaluated_at=timestamp,timezone='UTC',units={k:fields[definition.entity][k]['unit'] for k in definition.columns},
                limit=limit,offset=offset,items=[],live=True,
                field_labels={k:v['label'] for k,v in fields[definition.entity].items()},
                choice_labels={k:v['choice_labels'] for k,v in fields[definition.entity].items() if 'choice_labels' in v})
            table=TABLES[definition.entity]
            expr=self._expressions(definition.entity,timestamp,conn, schema)
            predicate=self._predicate(definition.filter,expr) if definition.filter else literal(True)
            result['total']=conn.execute(select(func.count()).select_from(table).where(predicate)).scalar_one()
            # Aggregate a one-row-per-record relation, never a fanout join.
            # Public custom IDs can exceed PostgreSQL's 63-byte identifier limit.
            # Keep all SQL labels short and map back only at the API boundary.
            aliases={key:f'rf_{index}' for index,key in enumerate(sorted(expr))}
            relation=select(*(value.label(aliases[key]) for key,value in expr.items())).select_from(table).where(predicate).subquery()
            m=definition.measure or Measure()
            metric=func.count() if m.op=='count' else getattr(func,m.op)(relation.c[aliases[m.field]])
            if m.op=='sum': metric=func.coalesce(metric,0)
            if definition.group_by or definition.measure:
                result['metric']=self._json_number(conn.execute(select(metric).select_from(relation)).scalar_one())
                result['metric_unit']='records' if m.op=='count' else fields[definition.entity][m.field]['unit']
                detail=copy.deepcopy(d); detail.pop('group_by',None); detail.pop('measure',None)
                result['detail_definition']=detail
            if definition.group_by:
                g=definition.group_by
                key=relation.c[aliases[g.field]]
                if g.interval=='day': key=func.substr(key,1,10)
                grouped=select(key.label('key'),metric.label('value'),func.count().label('count')).select_from(relation).group_by(key)
                result['total_groups']=conn.execute(select(func.count()).select_from(grouped.subquery())).scalar_one()
                buckets=conn.execute(grouped.order_by(key.asc().nulls_last()).limit(100)).mappings()
                result['groups']=[]
                for bucket in buckets:
                    detail=copy.deepcopy(d); detail.pop('group_by',None); detail.pop('measure',None)
                    value=bucket['key']
                    if value is None: clause=dict(field=g.field,op='is_null',value=None)
                    elif g.interval=='day':
                        start=date.fromisoformat(value)
                        bounds=[start.isoformat()]
                        if start < date.max: bounds.append((start+timedelta(days=1)).isoformat())
                        if fields[definition.entity][g.field]['type']=='datetime': bounds=[b+'T00:00:00.000000+00:00' for b in bounds]
                        clauses=[dict(field=g.field,op='gte',value=bounds[0])]
                        if len(bounds)>1: clauses.append(dict(field=g.field,op='lt',value=bounds[1]))
                        clause={'all':clauses}
                    else: clause=dict(field=g.field,op='eq',value=value)
                    detail['filter']=self._combine_filter(detail.get('filter'),clause)
                    result['groups'].append(dict(bucket,value=self._json_number(bucket['value']),detail_definition=detail,evaluated_at=timestamp))
                result['truncated']=result['total_groups']>100
                return result
            columns=definition.columns
            selected=[expr[k].label(aliases[k]) for k in columns if k!='linked_stages']
            output_names={aliases[k]:k for k in columns if k!='linked_stages'}
            if 'id' not in columns: selected.append(table.c.id.label('_report_id'))
            # A stages-only report still needs identity for bounded page enrichment.
            order=[(expr[s.field].asc() if s.direction=='asc' else expr[s.field].desc()).nulls_last() for s in definition.sort]
            if not any(s.field=='id' for s in definition.sort): order.append(table.c.id.asc())
            rows=[{output_names.get(key,key):value for key,value in r.items()} for r in conn.execute(select(*selected).select_from(table).where(predicate).order_by(*order).limit(limit).offset(offset)).mappings()]
            if 'linked_stages' in columns:
                ids=[r.get('id',r.get('_report_id')) for r in rows]; stages={i:set() for i in ids}
                if ids:
                    for contact_id,stage in conn.execute(select(deals.c.contact_id,deals.c.stage).where(deals.c.contact_id.in_(ids)).distinct()): stages[contact_id].add(stage)
                for row in rows: row['linked_stages']=[s for s in fields['contacts']['linked_stages']['choices'] if s in stages[row.get('id',row.get('_report_id'))]]
            for row in rows:
                row.pop('_report_id',None)
                for key, value in row.items(): row[key]=self._json_number(value)
            result['items']=rows
        return result

    @staticmethod
    def _json_number(value):
        # PostgreSQL returns Decimal for AVG/SUM(bigint); JSON has no Decimal.
        if isinstance(value, Decimal): return int(value) if value == value.to_integral_value() else float(value)
        return value

    @staticmethod
    def _combine_filter(original, clause):
        # Flatten ANDs. Grouped-definition validation reserves enough public
        # filter budget for every generated drilldown to remain valid.
        if not original: return clause
        left=original['all'] if set(original)=={'all'} else [original]
        right=clause['all'] if set(clause)=={'all'} else [clause]
        return {'all':left+right}
