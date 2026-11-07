"""Additive, versioned customization catalog. Values never alter legacy record columns."""
import hashlib
import json
import math
import re
from datetime import date
from sqlalchemy import Table, Column, String, Integer, Text, MetaData, select, update, inspect, text

metadata = MetaData()
state = Table('crm_custom_schema', metadata, Column('id', Integer, primary_key=True), Column('version', Integer, nullable=False), Column('revision', Integer, nullable=False))
definitions = Table('crm_custom_definitions', metadata, Column('kind', String(20), primary_key=True), Column('key', String(64), primary_key=True), Column('definition', Text, nullable=False))
values_table = Table('crm_custom_values', metadata, Column('kind', String(20), primary_key=True), Column('record_id', String(36), primary_key=True), Column('values_json', Text, nullable=False))

def error(message, status=400):
    from .domain import CRMError
    raise CRMError(message, status)

def initialize(engine, legacy_metadata):
    with engine.connect() as conn:
        if conn.dialect.name == 'sqlite': conn.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            scope = str(engine.get_execution_options().get('schema_translate_map', {}))
            conn.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': int(hashlib.sha256(scope.encode()).hexdigest()[:15], 16)})
        try:
            schema = engine.get_execution_options().get('schema_translate_map', {}).get(None)
            inspector = inspect(conn)
            if inspector.has_table(state.name, schema=schema):
                columns = {c['name'] for c in inspector.get_columns(state.name, schema=schema)}
                if columns != {'id','version','revision'}: error('Incompatible customization schema', 503)
                rows = conn.execute(select(state)).mappings().all()
                if len(rows) != 1 or rows[0]['id'] != 1 or rows[0]['version'] != 1: error('Unsupported customization schema version', 503)
                for table in (state, definitions, values_table):
                    if not inspector.has_table(table.name, schema=schema) or {c['name'] for c in inspector.get_columns(table.name, schema=schema)} != set(table.c.keys()):
                        error('Incomplete customization schema', 503)
                    actual={c['name']:c for c in inspector.get_columns(table.name,schema=schema)}
                    for column in table.c:
                        found=actual[column.name]
                        if (found['type']._type_affinity is not column.type._type_affinity
                                or getattr(found['type'],'length',None) != getattr(column.type,'length',None)
                                or found['nullable'] != column.nullable):
                            error('Incompatible customization column',503)
                    if set(inspector.get_pk_constraint(table.name,schema=schema)['constrained_columns']) != {c.name for c in table.primary_key}:
                        error('Incompatible customization primary key',503)
            else:
                if any(inspector.has_table(t.name, schema=schema) for t in (definitions, values_table)):
                    error('Unversioned customization schema', 503)
                metadata.create_all(conn)
                from .domain import STAGES, PROBABILITIES
                for order, key in enumerate(STAGES):
                    definition = dict(key=key,label=key.title(),description='',color=('#4779ce','#9b69c6','#c67e24','#338b95','#32825e','#b85f67')[order],order=order,probability=PROBABILITIES[key],outcome=key if key in ('won','lost') else 'open',archived=False,version=1)
                    conn.execute(definitions.insert().values(kind='stages',key=key,definition=json.dumps(definition)))
                conn.execute(state.insert().values(id=1,version=1,revision=0))
            legacy_metadata.create_all(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

class Customization:
    def _catalog_lock(self, conn):
        # Common lock orders catalog changes and record writes on both supported engines.
        result = conn.execute(update(state).where(state.c.id == 1, state.c.version == 1).values(revision=state.c.revision+1))
        if result.rowcount != 1: error('Unsupported customization schema version',503)

    def _definitions(self, conn, kind):
        rows = conn.execute(select(definitions.c.definition).where(definitions.c.kind == kind)).scalars()
        return sorted((json.loads(r) for r in rows), key=lambda r:(r['order'],r['key']))

    def catalog(self, conn=None):
        from contextlib import nullcontext
        with (nullcontext(conn) if conn is not None else self.engine.connect()) as conn:
            rows = conn.execute(select(definitions)).mappings().all()
            result = dict(schema_version=1, stages=[], fields={k:[] for k in ('contacts','deals','tasks')})
            for row in rows:
                target = result['stages'] if row['kind']=='stages' else result['fields'][row['kind']]
                target.append(json.loads(row['definition']))
            for group in [result['stages'], *result['fields'].values()]: group.sort(key=lambda r:(r['order'],r['key']))
            return result

    def _definition(self, conn, kind, key):
        row = conn.execute(select(definitions.c.definition).where(definitions.c.kind==kind,definitions.c.key==key)).scalar()
        if row is None: error('Unknown stage or custom field')
        return json.loads(row)

    def _definition_write(self, kind, data, actor, idem=None, existing_key=None):
        from .domain import idempotency, now, activity
        import uuid
        if kind not in ('stages','contacts','deals','tasks'): error('Invalid record kind')
        if not isinstance(data, dict): error('Definition must be an object')
        if idem is not None and (not isinstance(idem,str) or not 1 <= len(idem)<=160): error('Invalid idempotency key')
        digest = hashlib.sha256(json.dumps(['definition',kind,data],sort_keys=True).encode()).hexdigest()
        with self.engine.begin() as conn:
            self._catalog_lock(conn)
            if idem:
                old_retry = conn.execute(select(idempotency).where(idempotency.c.key==idem)).mappings().first()
                if old_retry:
                    if old_retry['digest'] != digest: error('Idempotency key already used for different data',409)
                    return json.loads(old_retry['response'])
            old = self._definition(conn,kind,existing_key) if existing_key else None
            allowed = {'label','description','order','archived','version'} | ({'probability','color'} if kind=='stages' else {'choices'})
            if not old: allowed |= {'key','outcome'} if kind=='stages' else {'key','type'}
            if set(data)-allowed: error('Unknown or immutable definition fields')
            if old:
                if type(data.get('version')) is not int or data['version'] != old['version']: error('Definition changed. Refresh before editing.',409)
                item = {**old, **data, 'version':old['version']+1}
            else:
                if 'version' in data: error('Version is assigned by the server')
                item = dict(label='',description='',order=0,archived=False,version=1) | data
                if kind=='stages': item = dict(probability=10,outcome='open',color='#64748b') | item
                else: item = dict(choices=[]) | item
                key = item.get('key')
                if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,'+('19' if kind=='stages' else '63')+'}',key): error('Invalid stable key')
                if kind=='stages' and key=='unassigned': error('Reserved stage key')
                if len(self._definitions(conn,kind)) >= 100: error('Maximum of 100 definitions per kind')
                if conn.execute(select(definitions.c.key).where(definitions.c.kind==kind,definitions.c.key==key)).first(): error('Stable key already exists',409)
                if kind!='stages':
                    from .domain import MODELS
                    if key in MODELS[kind].model_fields: error('Custom key conflicts with a built-in field')
            if not isinstance(item['label'],str) or not 1<=len(item['label'].strip())<=120: error('Label must be 1–120 characters')
            item['label']=item['label'].strip()
            if not isinstance(item['description'],str) or len(item['description'])>2000: error('Description must be text of at most 2000 characters')
            if type(item['order']) is not int or not 0<=item['order']<=10000: error('Order must be an integer from 0 to 10000')
            if type(item['archived']) is not bool: error('Archived must be boolean')
            if kind=='stages':
                if not isinstance(item['color'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',item['color']): error('Color must use #RRGGBB')
                if item['outcome'] not in ('open','won','lost'): error('Invalid stage outcome')
                if type(item['probability']) is not int or not 0<=item['probability']<=100: error('Probability must be an integer from 0 to 100')
                if item['outcome']!='open': item['probability']=100 if item['outcome']=='won' else 0
                if item['archived']:
                    from .domain import deals
                    if item['key']=='lead': error('The default lead stage cannot be archived')
                    if conn.execute(select(deals.c.id).where(deals.c.stage==item['key']).limit(1)).first(): error('Move existing deals before archiving this stage',409)
            else:
                if item.get('type') not in ('text','number','boolean','date','single-select'): error('Invalid field type')
                choices=item['choices']
                if not isinstance(choices,list) or len(choices)>100 or any(not isinstance(c,str) or not 1<=len(c)<=120 or c!=c.strip() for c in choices) or len(set(choices))!=len(choices): error('Invalid choices')
                if item['type']=='single-select' and not choices: error('Single-select requires choices')
                if item['type']!='single-select' and choices: error('Choices only apply to single-select fields')
                # Removing choices could invalidate retained values, so first increment only allows additions.
                if old and not set(old['choices']).issubset(choices): error('Existing choices cannot be removed')
            if old:
                conn.execute(update(definitions).where(definitions.c.kind==kind,definitions.c.key==existing_key).values(definition=json.dumps(item)))
            else: conn.execute(definitions.insert().values(kind=kind,key=item['key'],definition=json.dumps(item)))
            conn.execute(activity.insert().values(id=str(uuid.uuid4()),entity_type='customization',entity_id=str(uuid.uuid5(uuid.NAMESPACE_URL,f'hermes-crm:customization:{kind}:{item["key"]}')),action='definition_updated' if old else 'definition_created',actor=actor[:160],summary=f"{kind}.{item['key']}: {item['label']}"[:400],created_at=now()))
            if idem: conn.execute(idempotency.insert().values(key=idem,digest=digest,response=json.dumps(item)))
            return item

    def create_stage(self,data,actor='local',key=None): return self._definition_write('stages',data,actor,key)
    def update_stage(self,stage_key,data,actor='local'): return self._definition_write('stages',data,actor,existing_key=stage_key)
    def create_field(self,kind,data,actor='local',key=None):
        if kind not in ('contacts','deals','tasks'): error('Invalid record kind')
        return self._definition_write(kind,data,actor,key)

    def update_field(self,kind,field_key,data,actor='local'):
        if kind not in ('contacts','deals','tasks'): error('Invalid record kind')
        return self._definition_write(kind,data,actor,existing_key=field_key)

    def _custom_values(self,conn,kind,record_id):
        raw=conn.execute(select(values_table.c.values_json).where(values_table.c.kind==kind,values_table.c.record_id==record_id)).scalar()
        return json.loads(raw) if raw else {}

    def _validate_custom(self,conn,kind,patch,current=None):
        if not isinstance(patch,dict) or len(patch)>100: error('custom_fields must be an object with at most 100 fields')
        result=dict(current or {})
        for key,value in patch.items():
            if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',key): error('Invalid custom field key')
            field=self._definition(conn,kind,key)
            if field['archived']: error('Archived fields cannot be edited')
            if value is None:
                result.pop(key,None)
                continue
            typ=field['type']
            valid=False
            if typ=='text': valid=isinstance(value,str) and len(value)<=10000
            elif typ=='number': valid=type(value) in (int,float) and abs(value)<=1e15 and math.isfinite(value)
            elif typ=='boolean': valid=type(value) is bool
            elif typ=='single-select': valid=isinstance(value,str) and value in field['choices']
            elif typ=='date':
                try: valid=isinstance(value,str) and date.fromisoformat(value).isoformat()==value
                except (ValueError,TypeError): pass
            if not valid: error(f'Invalid value for custom field: {key}')
            result[key]=value
        return result

    def _save_custom(self,conn,kind,record_id,values):
        clause=(values_table.c.kind==kind,values_table.c.record_id==record_id)
        if conn.execute(select(values_table.c.record_id).where(*clause)).first():
            conn.execute(update(values_table).where(*clause).values(values_json=json.dumps(values)))
        elif values: conn.execute(values_table.insert().values(kind=kind,record_id=record_id,values_json=json.dumps(values)))

    def _deal_stage(self,conn,values,default_probability=False):
        stage=self._definition(conn,'stages',values['stage'])
        if stage['archived']: error('Archived stages cannot receive deals')
        if stage['outcome']!='open' or default_probability: values['probability']=stage['probability']
