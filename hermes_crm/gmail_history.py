"""Optional, local-only Gmail metadata ledger. No provider work happens on reads.

Retention is explicit: metadata remains until Clear local history. Disconnect
fences work but neither deletes evidence nor revokes host-owned authorization.
Only one manual operation per workspace/profile can run; a crashed running
operation is reconciled locally and must be disconnected before another run.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import uuid

from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, Text, UniqueConstraint, delete, func, inspect, select, update
from sqlalchemy.exc import IntegrityError
from .domain import CRMError, contacts, now

metadata = MetaData()
connections = Table('crm_gmail_connections', metadata,
    Column('scope', String(64), primary_key=True), Column('revision', Integer, nullable=False),
    Column('connected', Integer, nullable=False), Column('subject', String(255)),
    Column('mailbox', String(254)), Column('issuer', String(255)), Column('active_operation', String(36)))
operations = Table('crm_gmail_operations', metadata,
    Column('id', String(36), primary_key=True), Column('scope', String(64), nullable=False),
    Column('digest', String(64), nullable=False), Column('kind', String(16), nullable=False),
    Column('state', String(16), nullable=False), Column('reason', String(160), nullable=False),
    Column('contact_id', String(36)), Column('created_at', String(40), nullable=False),
    Column('finished_at', String(40)), Column('days', Integer),
    Column('start_ms', BigInteger), Column('end_ms', BigInteger), Column('coverage', String(32)))
snapshots = Table('crm_gmail_snapshots', metadata,
    Column('key', String(64), primary_key=True), Column('scope', String(64), nullable=False),
    Column('subject', String(255), nullable=False), Column('message_id', String(255), nullable=False),
    Column('payload', Text, nullable=False), Column('observed_at', String(40), nullable=False))
observations = Table('crm_gmail_observations', metadata,
    Column('id', String(36), primary_key=True), Column('scope', String(64), nullable=False),
    Column('snapshot_key', String(64), nullable=False), Column('operation_id', String(36), nullable=False),
    Column('payload', Text, nullable=False), Column('provenance', Text, nullable=False),
    Column('observed_at', String(40), nullable=False),
    UniqueConstraint('operation_id', 'snapshot_key'))
links = Table('crm_gmail_contact_links', metadata,
    Column('scope', String(64), primary_key=True), Column('contact_id', String(36), primary_key=True),
    Column('snapshot_key', String(64), primary_key=True))


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


class GmailHistoryStore:
    def __init__(self, crm, *, initialize=False):
        self.crm = crm
        self.scope = _hash([crm.workspace_token(), crm.profile])
        schema = crm.engine.get_execution_options().get('schema_translate_map', {}).get(None)
        inspector = inspect(crm.engine)
        found = [inspector.has_table(t.name, schema=schema) for t in metadata.sorted_tables]
        if any(found) and not all(found):
            raise CRMError('Email storage requires an explicit schema repair', 503)
        self.available = all(found)
        if self.available:
            for table in metadata.sorted_tables:
                cols = inspector.get_columns(table.name, schema=schema)
                by_name = {c['name']: c for c in cols}
                compatible = set(by_name) == set(table.c.keys())
                if compatible:
                    compatible = all(by_name[c.name]['nullable'] == c.nullable and
                        by_name[c.name]['type']._type_affinity is c.type._type_affinity and
                        getattr(by_name[c.name]['type'], 'length', None) == getattr(c.type, 'length', None)
                        for c in table.c)
                primary = inspector.get_pk_constraint(table.name, schema=schema).get('constrained_columns')
                expected_unique = {tuple(c.name for c in constraint.columns)
                    for constraint in table.constraints if isinstance(constraint, UniqueConstraint)}
                actual_unique = {tuple(c['column_names']) for c in inspector.get_unique_constraints(table.name, schema=schema)}
                if (not compatible or primary != [c.name for c in table.primary_key.columns]
                        or expected_unique != actual_unique):
                    raise CRMError('Email storage requires an explicit migration', 503)
        if initialize and not self.available:
            metadata.create_all(crm.engine)
            self.available = True
        if initialize:
            try:
                with crm.engine.begin() as conn:
                    if not self._connection(conn):
                        conn.execute(connections.insert().values(scope=self.scope, revision=0, connected=0))
            except IntegrityError:
                pass  # A concurrent initializer owns the same scoped row.

    def _connection(self, conn):
        return conn.execute(select(connections).where(connections.c.scope == self.scope)).mappings().first()

    def _lock(self, conn):
        conn.execute(update(connections).where(connections.c.scope == self.scope).values(revision=connections.c.revision))
        return self._connection(conn)

    def _operation(self, row):
        return {k: row[k] for k in ('id', 'kind', 'state', 'reason', 'contact_id', 'created_at', 'finished_at', 'days', 'start_ms', 'end_ms', 'coverage')}

    def status(self, *, enabled=False):
        result = dict(enabled=enabled, connected=False, mailbox=None, revision=0, operation=None,
                      retention='Retained locally until Clear local history; disconnect does not delete metadata.',
                      semantics='Last observed metadata, not a current mailbox snapshot. Missing query results do not prove deletion.')
        if not self.available:
            return result
        with self.crm.engine.connect() as conn:
            row = self._connection(conn)
            if row:
                result.update(connected=bool(row['connected']), mailbox=row['mailbox'], revision=row['revision'])
            op = conn.execute(select(operations).where(operations.c.scope == self.scope)
                              .order_by(operations.c.created_at.desc(), operations.c.id.desc()).limit(1)).mappings().first()
            if op:
                result['operation'] = self._operation(op)
        return result

    def operation(self, operation_id):
        if not self.available:
            raise CRMError('Email operation not found', 404)
        with self.crm.engine.connect() as conn:
            row = conn.execute(select(operations).where(operations.c.id == operation_id,
                operations.c.scope == self.scope)).mappings().first()
            if row is None:
                raise CRMError('Email operation not found', 404)
            return self._operation(row)

    def page(self, contact_id, *, limit=25, offset=0):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 2_000_000_000:
            raise CRMError('Invalid email history page')
        with self.crm.engine.connect() as conn:
            self._contact(conn, contact_id)
            result = dict(items=[], total=0, revision=self.status()['revision'], last_operation=None)
            if not self.available:
                return result
            where = (links.c.scope == self.scope, links.c.contact_id == contact_id, snapshots.c.scope == self.scope)
            joined = snapshots.join(links, snapshots.c.key == links.c.snapshot_key)
            result['total'] = conn.execute(select(func.count()).select_from(joined).where(*where)).scalar_one()
            rows = conn.execute(select(snapshots).select_from(joined).where(*where)
                                .order_by(snapshots.c.observed_at.desc(), snapshots.c.key).limit(limit).offset(offset)).mappings()
            result['items'] = [dict(json.loads(r['payload']), observed_at=r['observed_at']) for r in rows]
            op = conn.execute(select(operations).where(operations.c.scope == self.scope, operations.c.contact_id == contact_id)
                              .order_by(operations.c.created_at.desc()).limit(1)).mappings().first()
            result['last_operation'] = self._operation(op) if op else None
            return result

    def _contact(self, conn, contact_id, version=None, lock=False):
        if lock:
            conn.execute(update(contacts).where(contacts.c.id == contact_id).values(version=contacts.c.version))
        row = conn.execute(select(contacts).where(contacts.c.id == contact_id)).mappings().first()
        if row is None:
            raise CRMError('Contact not found', 404)
        if version is not None and row['version'] != version:
            raise CRMError('Contact changed; review it before reading email', 409)
        return row

    def mutate_local(self, kind, expected_revision, operation_id=None):
        if kind not in ('clear', 'disconnect') or type(expected_revision) is not int or expected_revision < 0:
            raise CRMError('Invalid local email operation')
        operation_id = operation_id or str(uuid.uuid4())
        try:
            if str(uuid.UUID(operation_id)) != operation_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise CRMError('Expected a canonical operation UUID') from None
        digest = _hash([kind, expected_revision])
        with self.crm.engine.begin() as conn:
            row = self._lock(conn)
            previous = conn.execute(select(operations).where(operations.c.id == operation_id)).mappings().first()
            if previous:
                if previous['scope'] != self.scope or previous['digest'] != digest:
                    raise CRMError('Operation identifier already used', 409)
                return self._operation(previous)
            if row['revision'] != expected_revision:
                raise CRMError('Email connection changed; refresh status', 409)
            conn.execute(update(connections).where(connections.c.scope == self.scope).values(
                revision=row['revision'] + 1, connected=0, active_operation=None,
                **(dict(subject=None, mailbox=None, issuer=None) if kind == 'clear' else {})))
            conn.execute(update(operations).where(operations.c.scope == self.scope, operations.c.state == 'running')
                         .values(state='cancelled', reason='Cancelled locally; already dispatched reads cannot be recalled.', finished_at=now()))
            if kind == 'clear':
                for table in (links, observations, snapshots):
                    conn.execute(delete(table).where(table.c.scope == self.scope))
            stamp = now()
            conn.execute(operations.insert().values(id=operation_id, scope=self.scope, digest=digest, kind=kind,
                state='finished', reason='Local metadata cleared.' if kind == 'clear' else 'Disconnected locally; host authorization was not revoked.',
                created_at=stamp, finished_at=stamp))
            return self._operation(conn.execute(select(operations).where(operations.c.id == operation_id)).mappings().one())

    def run(self, *, kind, operation_id, expected_revision, reader, guard, mailbox=None,
            contact_id=None, expected_contact_version=None, days=None):
        try:
            if str(uuid.UUID(operation_id)) != operation_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise CRMError('Expected a canonical operation UUID') from None
        if (type(expected_revision) is not int or expected_revision < 0 or kind not in ('verify', 'sync')
                or (kind == 'sync' and (type(days) is not int or days not in (7, 30)
                    or type(expected_contact_version) is not int or expected_contact_version < 1))):
            raise CRMError('Invalid manual email operation')
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000) if kind == 'sync' else None
        start_ms = end_ms - days * 86400000 if kind == 'sync' else None
        digest = _hash([kind, expected_revision, mailbox, contact_id, expected_contact_version, days])
        with self.crm.engine.begin() as conn:
            row = self._lock(conn)
            previous = conn.execute(select(operations).where(operations.c.id == operation_id)).mappings().first()
            if previous:
                if previous['scope'] != self.scope or previous['digest'] != digest:
                    raise CRMError('Operation identifier already used', 409)
                return self._operation(previous)
            if row['revision'] != expected_revision or row['active_operation']:
                raise CRMError('Email state changed or an operation is running; refresh status', 409)
            if kind == 'verify':
                if row['subject']:
                    raise CRMError('Disconnect and clear local history before verifying an account', 409)
            else:
                if not row['connected']:
                    raise CRMError('Verify an email connection first', 409)
                contact = dict(self._contact(conn, contact_id, expected_contact_version, lock=True))
            revision = row['revision'] + 1
            binding = dict(row)
            conn.execute(update(connections).where(connections.c.scope == self.scope).values(revision=revision, active_operation=operation_id))
            conn.execute(operations.insert().values(id=operation_id, scope=self.scope, digest=digest, kind=kind,
                state='running', reason='', contact_id=contact_id, created_at=now(), days=days, start_ms=start_ms, end_ms=end_ms))
        def check_guard():
            if guard() is False:
                raise CRMError('Email context changed', 409)
        def read_guard():
            check_guard()
            with self.crm.engine.connect() as connection:
                current = self._connection(connection)
                if current['revision'] != revision or current['active_operation'] != operation_id:
                    raise CRMError('Email operation was cancelled', 409)
        try:
            read_guard()
            if kind == 'verify':
                identity = reader.verify_identity(mailbox, read_guard)
            else:
                from .gmail_reader import IdentityBinding
                identity = IdentityBinding(subject=binding['subject'], mailbox=binding['mailbox'], issuer=binding['issuer'])
                scan = reader.scan_contact(identity, contact['email'], start_ms, end_ms, read_guard)
            read_guard()
            with self.crm.engine.begin() as conn:
                current = self._lock(conn)
                if current['revision'] != revision or current['active_operation'] != operation_id:
                    raise CRMError('Email operation was cancelled', 409)
                check_guard()
                if kind == 'verify':
                    conn.execute(update(connections).where(connections.c.scope == self.scope).values(
                        connected=1, subject=identity.subject, mailbox=identity.mailbox, issuer=identity.issuer))
                    state = 'finished'
                else:
                    self._contact(conn, contact_id, expected_contact_version, lock=True)
                    stamp = now()
                    for message in scan.messages:
                        provenance = dict(adapter='gmail-readonly-v1', kind='manual_contact_query',
                            mailbox=identity.mailbox, issuer=identity.issuer, contact_id=contact_id,
                            contact_version=expected_contact_version, start_ms=start_ms, end_ms=end_ms,
                            operation_id=operation_id)
                        payload = _json(dict(asdict(message), provenance=provenance))
                        key = _hash([self.scope, identity.issuer, identity.subject, message.message_id])
                        values = dict(scope=self.scope, subject=identity.subject, message_id=message.message_id,
                                      payload=payload, observed_at=stamp)
                        if conn.execute(select(snapshots.c.key).where(snapshots.c.key == key)).first():
                            conn.execute(update(snapshots).where(snapshots.c.key == key).values(**values))
                        else:
                            conn.execute(snapshots.insert().values(key=key, **values))
                        conn.execute(observations.insert().values(id=str(uuid.uuid4()), scope=self.scope,
                            snapshot_key=key, operation_id=operation_id, payload=payload, observed_at=stamp,
                            provenance=_json(provenance)))
                        if not conn.execute(select(links).where(links.c.scope == self.scope,
                            links.c.contact_id == contact_id, links.c.snapshot_key == key)).first():
                            conn.execute(links.insert().values(scope=self.scope, contact_id=contact_id, snapshot_key=key))
                    state = 'finished' if scan.coverage == 'complete_query' else 'partial'
                conn.execute(update(connections).where(connections.c.scope == self.scope).values(active_operation=None))
                conn.execute(update(operations).where(operations.c.id == operation_id).values(state=state,
                    coverage=scan.coverage if kind == 'sync' else None,
                    reason='Window query finished; not a complete mailbox history.' if kind == 'sync' and state == 'finished' else
                    'Coverage is partial.' if state == 'partial' else '', finished_at=now()))
        except Exception:
            # No provider/DB exception, URL, token, body or header enters output.
            with self.crm.engine.begin() as conn:
                current = self._lock(conn)
                if current['revision'] == revision and current['active_operation'] == operation_id:
                    conn.execute(update(connections).where(connections.c.scope == self.scope).values(active_operation=None))
                    conn.execute(update(operations).where(operations.c.id == operation_id).values(state='failed',
                        reason='Email read failed or its context changed. No staged metadata was saved.', finished_at=now()))
        with self.crm.engine.connect() as conn:
            return self._operation(conn.execute(select(operations).where(operations.c.id == operation_id)).mappings().one())
