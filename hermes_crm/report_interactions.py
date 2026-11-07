"""Explicitly authored interaction claims. Never proof of sending or delivery."""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Literal
from pydantic import Field, field_validator
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, func, literal, select, update
from .domain import CRMError, StrictModel, contacts, now, settings
from .report_store import ScopedStore, canonical, check_tables, scope_for

metadata = MetaData()
interactions = Table('crm_report_interactions', metadata,
    Column('scope', String(64), primary_key=True), Column('id', String(36), primary_key=True),
    Column('contact_id', String(36), nullable=False), Column('version', Integer, nullable=False),
    Column('happened_at', String(40), nullable=False), Column('kind', String(20), nullable=False),
    Column('direction', String(20), nullable=False), Column('summary', Text, nullable=False),
    Column('actor', String(160), nullable=False), Column('provenance', String(20), nullable=False),
    Column('created_at', String(40), nullable=False), Column('voided_at', String(40)),
    Column('void_reason', Text), Column('void_actor', String(160)))
operations = Table('crm_interaction_operations', metadata,
    Column('scope', String(64), primary_key=True), Column('key', String(160), primary_key=True),
    Column('digest', String(64), nullable=False), Column('response', Text, nullable=False))

def interaction_scope(crm, connection=None):
    return scope_for(crm, connection=connection) if check_tables(crm, [interactions, operations], connection=connection) else None

def last_contact_expression(crm, conn):
    scope = interaction_scope(crm, connection=conn)
    if scope is None: return literal(None)
    return select(func.max(interactions.c.happened_at)).where(
        interactions.c.scope == scope, interactions.c.contact_id == contacts.c.id,
        interactions.c.voided_at.is_(None)).correlate(contacts).scalar_subquery()

class InteractionInput(StrictModel):
    contact_id: str
    happened_at: str
    kind: Literal['meeting','call','email','chat','other']
    direction: Literal['inbound','outbound','other'] = 'other'
    summary: str = Field(min_length=1,max_length=2000)
    @field_validator('contact_id')
    @classmethod
    def identifier(cls,value):
        if str(uuid.UUID(value)) != value: raise ValueError('Use canonical contact UUID')
        return value
    @field_validator('happened_at')
    @classmethod
    def timestamp(cls,value):
        parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None: raise ValueError('happened_at must include a timezone')
        parsed = parsed.astimezone(timezone.utc)
        if parsed > datetime.now(timezone.utc): raise ValueError('Future interactions cannot be recorded')
        return parsed.isoformat(timespec='microseconds')

class InteractionStore(ScopedStore):
    tables = [interactions,operations]
    operation_table = operations
    @staticmethod
    def _actor(actor):
        if not isinstance(actor,str) or not actor.strip() or len(actor)>160: raise CRMError('A trusted actor is required')
        return actor.strip()
    @staticmethod
    def _decode(row):
        result = dict(row); result.pop('scope',None)
        return result
    def create(self,data,expected_contact_version,actor,key):
        values = InteractionInput.model_validate(data).model_dump(mode='json')
        self._version(expected_contact_version)
        actor = self._actor(actor)
        def action(conn,scope):
            # PostgreSQL row lock serializes contact edits; SQLite BEGIN IMMEDIATE does likewise.
            contact = conn.execute(select(contacts.c.version).where(contacts.c.id==values['contact_id']).with_for_update()).scalar()
            if contact is None: raise CRMError('Contact not found',404)
            if contact != expected_contact_version: raise CRMError('Contact changed; refresh before recording interaction',409)
            result = dict(id=str(uuid.uuid4()),version=1,**values,actor=actor,provenance='self_reported',created_at=now(),voided_at=None,void_reason=None,void_actor=None)
            conn.execute(interactions.insert().values(scope=scope,**result))
            return result
        return self._write(key,['create',values,expected_contact_version,actor],action)
    def void(self,record_id,expected_version,reason,actor,key):
        self._version(expected_version)
        if not isinstance(reason,str) or not reason.strip() or len(reason)>2000: raise CRMError('A correction reason of at most 2000 characters is required')
        actor = self._actor(actor); reason = reason.strip()
        def action(conn,scope):
            row = conn.execute(select(interactions).where(interactions.c.scope==scope,interactions.c.id==record_id)).mappings().first()
            if row is None: raise CRMError('Interaction not found',404)
            if row['version'] != expected_version or row['voided_at']: raise CRMError('Interaction changed or was already voided',409)
            values = dict(version=expected_version+1,voided_at=now(),void_reason=reason,void_actor=actor)
            changed = conn.execute(update(interactions).where(interactions.c.scope==scope,interactions.c.id==record_id,interactions.c.version==expected_version).values(**values))
            if changed.rowcount != 1: raise CRMError('Interaction changed; refresh before voiding',409)
            return dict(self._decode(row),**values)
        return self._write(key,['void',record_id,expected_version,reason,actor],action)
    def list(self,contact_id,limit=50,offset=0,include_voided=False):
        self.crm._integer(limit,'limit',1,100); self.crm._integer(offset,'offset')
        if type(include_voided) is not bool: raise CRMError('include_voided must be boolean')
        self.crm.get('contacts',contact_id)
        if not self.exists(): return dict(items=[],total=0,limit=limit,offset=offset)
        stmt = select(interactions).where(interactions.c.scope==scope_for(self.crm),interactions.c.contact_id==contact_id)
        if not include_voided: stmt = stmt.where(interactions.c.voided_at.is_(None))
        with self.crm.engine.connect() as conn:
            total = conn.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            items = [self._decode(r) for r in conn.execute(stmt.order_by(interactions.c.happened_at.desc(),interactions.c.id).limit(limit).offset(offset)).mappings()]
        return dict(items=items,total=total,limit=limit,offset=offset)
