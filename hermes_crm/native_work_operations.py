"""Bounded explicit-command operations, never an agent-tool approval substitute.

REST only prepares, observes, or withdraws local intent. The synchronous native
command receives its real host context and owns the only dispatch path. The CRM
review Confirm click invokes that command. No native question or model approval
is claimed. Expiry/withdrawal fences future effects, never undoes earlier ones.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, Text, UniqueConstraint, func, inspect, select, update
from sqlalchemy.exc import IntegrityError

from .domain import CRMError, now, tasks
from .native_work import NativeWorkStore, assignments, _future, _identity, _json, _text

SCHEMA_VERSION = 1
APPROVAL_SECONDS = 300
TERMINAL = frozenset({'finished', 'stale', 'expired', 'unknown', 'withdrawn'})
metadata = MetaData()
tasks.to_metadata(metadata)
assignments.to_metadata(metadata)
operations = Table('crm_native_work_operations', metadata,
    Column('id', String(36), primary_key=True),
    Column('workspace', String(160), nullable=False), Column('profile', String(160), nullable=False),
    Column('assignment_id', String(36), ForeignKey('crm_native_assignments.id'), nullable=False),
    Column('idempotency_key', String(160), nullable=False), Column('request', Text, nullable=False),
    Column('snapshot', Text, nullable=False), Column('digest', String(64), nullable=False),
    Column('verb', String(16), nullable=False), Column('state', String(32), nullable=False),
    Column('version', Integer, nullable=False), Column('reason', String(160), nullable=False),
    Column('intended_session_id', String(160), nullable=False),
    Column('actual_session_id', String(160)), Column('actual_session_key', String(300)),
    # Prepared intent reserves the mutation slot even before command delivery.
    # A crashed dispatch holds it; a returned unknown releases only if the
    # assignment is non-pending. Observation remains possible in either case.
    Column('assignment_slot', String(36)), Column('source_digest', String(64)),
    Column('result', Text), Column('expires_at', String(40), nullable=False),
    Column('created_at', String(40), nullable=False), Column('updated_at', String(40), nullable=False),
    UniqueConstraint('workspace', 'profile', 'idempotency_key'),
    UniqueConstraint('workspace', 'profile', 'assignment_slot'))


def _uuid(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value: raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise CRMError('Expected one canonical operation UUID') from None
    return value


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def command_name(workspace, profile):
    """Stable collision-resistant routing label, not a credential or approval token."""
    return 'crm-assignment-' + _hash(_json({'namespace': 'hermes-crm-user-command-v1',
                                           'workspace': workspace, 'profile': profile}))[:32]


class OperationFence(CRMError):
    def __init__(self, state, message):
        super().__init__(message, 409)
        self.state = state


class WorkOperationStore:
    def __init__(self, crm, *, initialize=False):
        self.crm, self.profile = crm, crm.profile
        self.workspace = crm.workspace_token()
        self.work = NativeWorkStore(crm, initialize=False, workspace=self.workspace)
        schema = crm.engine.get_execution_options().get('schema_translate_map', {}).get(None)
        inspector = inspect(crm.engine)
        self.available = inspector.has_table(operations.name, schema=schema)
        if self.available:
            columns = {c['name']: c for c in inspector.get_columns(operations.name, schema=schema)}
            compatible = set(columns) == set(operations.c.keys())
            if compatible:
                compatible = all(columns[c.name]['nullable'] == c.nullable and
                    columns[c.name]['type']._type_affinity is c.type._type_affinity and
                    getattr(columns[c.name]['type'], 'length', None) == getattr(c.type, 'length', None)
                    for c in operations.c)
            unique = {tuple(c['column_names']) for c in inspector.get_unique_constraints(operations.name, schema=schema)}
            foreign = {(tuple(c['constrained_columns']), c['referred_table'], tuple(c['referred_columns']))
                       for c in inspector.get_foreign_keys(operations.name, schema=schema)}
            compatible = compatible and unique == {
                ('workspace', 'profile', 'idempotency_key'), ('workspace', 'profile', 'assignment_slot')}
            compatible = compatible and inspector.get_pk_constraint(operations.name, schema=schema).get('constrained_columns') == ['id']
            compatible = compatible and foreign == {(('assignment_id',), assignments.name, ('id',))}
            if not compatible:
                raise CRMError('Native operation schema is incompatible; explicit migration required', 503)
        if initialize and not self.available:
            if not self.work.available: raise CRMError('No native assignments exist', 404)
            metadata.create_all(crm.engine, tables=[operations])
            self.available = True

    def _row(self, conn, operation_id, *, lock=False):
        _uuid(operation_id)
        if not self.available: raise CRMError('Operation not found in current workspace/profile', 404)
        query = select(operations).where(operations.c.id == operation_id,
            operations.c.workspace == self.workspace, operations.c.profile == self.profile)
        if lock:
            # A no-op write obtains the same lock on SQLite and PostgreSQL, with
            # no pre-lock read/snapshot promotion race.
            conn.execute(update(operations).where(operations.c.id == operation_id,
                operations.c.workspace == self.workspace, operations.c.profile == self.profile)
                .values(version=operations.c.version))
        row = conn.execute(query).mappings().first()
        if row is None: raise CRMError('Operation not found in current workspace/profile', 404)
        row = dict(row)
        if _hash(row['snapshot']) != row['digest']:
            raise CRMError('Operation review integrity check failed', 503)
        return row

    def _change(self, conn, row, **values):
        stamp = now()
        count = conn.execute(update(operations).where(operations.c.id == row['id'],
            operations.c.version == row['version']).values(**values,
            version=row['version'] + 1, updated_at=stamp)).rowcount
        if count != 1: raise CRMError('Concurrent operation change; read status without redispatching', 409)
        row.update(values, version=row['version'] + 1, updated_at=stamp)

    def _snapshot(self, conn, assignment_id):
        assignment = self.work._row(conn, assignment_id)
        task = conn.execute(select(tasks.c.id, tasks.c.version, tasks.c.status, tasks.c.title, tasks.c.due_at)
                            .where(tasks.c.id == assignment['task_id'])).mappings().first()
        if task is None: raise CRMError('Source task not found', 404)
        frozen = {key: assignment[key] for key in ('id', 'version', 'generation', 'digest', 'state', 'job_id')}
        frozen['payload'] = json.loads(assignment['payload'])
        return {'assignment': frozen, 'task': dict(task)}

    @staticmethod
    def _expired(row):
        return datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc)

    def _view(self, row):
        # Never expose internal source identity/session key or a write capability.
        result = {key: row[key] for key in ('id', 'verb', 'state', 'version', 'reason', 'assignment_id',
            'intended_session_id', 'actual_session_id', 'expires_at', 'created_at', 'updated_at')}
        result.update(schema_version=SCHEMA_VERSION, profile=row['profile'], workspace_token=row['workspace'],
            command_name=command_name(row['workspace'], row['profile']),
            idempotency_key=row['idempotency_key'], task_id=json.loads(row['snapshot'])['task']['id'], snapshot=json.loads(row['snapshot']),
            result=json.loads(row['result']) if row['result'] else None,
            mutation_slot_held=row['assignment_slot'] is not None,
            provenance='authenticated_local_command' if row['actual_session_id'] else None,
            authorization_channel='crm_user_command' if row['actual_session_id'] else None,
            expected_assignment_version=json.loads(row['request'])['expected_assignment_version'])
        # A read does not change durable state, dispatch, or retry.
        result['deadline_elapsed'] = self._expired(row)
        return result

    def get(self, operation_id):
        with self.crm.engine.connect() as conn:
            return self._view(self._row(conn, operation_id))

    def prepare(self, *, verb, assignment_id, expected_assignment_version, intended_session_id, idempotency_key):
        if verb not in ('schedule', 'check', 'cancel'): raise CRMError('Invalid operation verb')
        _text(assignment_id, 'assignment_id', 36)
        _text(intended_session_id, 'intended_session_id')
        _text(idempotency_key, 'idempotency_key')
        if type(expected_assignment_version) is not int or expected_assignment_version < 1:
            raise CRMError('expected_assignment_version must be a positive integer')
        request = _json(dict(verb=verb, assignment_id=assignment_id,
            expected_assignment_version=expected_assignment_version, intended_session_id=intended_session_id))
        def existing(conn):
            row = conn.execute(select(operations).where(operations.c.workspace == self.workspace,
                operations.c.profile == self.profile, operations.c.idempotency_key == idempotency_key)).mappings().first()
            if row:
                if row['request'] != request: raise CRMError('Operation idempotency key payload conflict', 409)
                return self._view(self._row(conn, row['id']))
        if not self.available: raise CRMError('Native operation store has not been initialized', 503)
        try:
            with self.crm.engine.begin() as conn:
                replay = existing(conn)
                if replay is not None: return replay
                # Lock task then assignment in the same order as native-work
                # mutation paths. Both reads below now describe one reviewed
                # state on SQLite and PostgreSQL, not a mixed READ COMMITTED view.
                if verb != 'check':
                    blocked = conn.execute(select(operations.c.id).where(operations.c.workspace == self.workspace,
                        operations.c.profile == self.profile, operations.c.assignment_slot == assignment_id)).first()
                    if blocked:
                        replay = existing(conn)
                        if replay is not None: return replay
                        raise CRMError('This assignment has an unresolved operation. Read operation history before another mutation.', 409)
                initial = self.work._row(conn, assignment_id)
                conn.execute(update(tasks).where(tasks.c.id == initial['task_id']).values(version=tasks.c.version))
                # Recheck after waiting for the task lock. A command may have
                # claimed an operation meanwhile; do not hold the assignment
                # lock while waiting on its unique slot or settlement.
                if verb != 'check':
                    blocked = conn.execute(select(operations.c.id).where(operations.c.workspace == self.workspace,
                        operations.c.profile == self.profile, operations.c.assignment_slot == assignment_id)).first()
                    if blocked:
                        replay = existing(conn)
                        if replay is not None: return replay
                        raise CRMError('This assignment has an unresolved operation. Read operation history before another mutation.', 409)
                conn.execute(update(assignments).where(assignments.c.id == assignment_id,
                    assignments.c.workspace == self.workspace, assignments.c.profile == self.profile)
                    .values(version=assignments.c.version))
                snapshot = self._snapshot(conn, assignment_id)
                a, task = snapshot['assignment'], snapshot['task']
                if a['version'] != expected_assignment_version: raise CRMError('Stale assignment version', 409)
                if verb == 'schedule':
                    if a['state'] != 'pending': raise CRMError('Only a never-scheduled pending assignment can be scheduled', 409)
                    if task['status'] != 'open' or task['version'] != a['payload']['task_version']:
                        raise CRMError('Source task changed or is no longer open', 409)
                    _future(a['payload']['run_at'])
                frozen = _json(snapshot)
                row = dict(id=str(uuid.uuid4()), workspace=self.workspace, profile=self.profile,
                    assignment_id=assignment_id, idempotency_key=idempotency_key, request=request,
                    snapshot=frozen, digest=_hash(frozen), verb=verb, state='prepared', version=1,
                    reason='awaiting_explicit_command', intended_session_id=intended_session_id,
                    actual_session_id=None, actual_session_key=None, assignment_slot=assignment_id if verb != 'check' else None, source_digest=None,
                    result=None, expires_at=(datetime.now(timezone.utc) + timedelta(seconds=APPROVAL_SECONDS)).isoformat(timespec='microseconds'),
                    created_at=now(), updated_at=now())
                conn.execute(operations.insert().values(**row))
                return self._view(row)
        except IntegrityError:
            with self.crm.engine.connect() as conn:
                replay = existing(conn)
                if replay is not None: return replay
            raise CRMError('This assignment has an unresolved operation. Read its status or explicitly withdraw it before preparing another mutation.', 409) from None

    def withdraw(self, operation_id):
        with self.crm.engine.begin() as conn:
            row = self._row(conn, operation_id, lock=True)
            if row['state'] == 'prepared':
                self._change(conn, row, state='withdrawn', assignment_slot=None, reason='prepared_command_withdrawn_no_dispatch')
            elif row['state'] != 'withdrawn':
                raise CRMError('Operation already claimed or settled; withdrawal cannot undo or interrupt it. Read status and explicitly review any next action.', 409)
            return self._view(row)

    def _settle(self, operation_id, state, reason, result=None):
        with self.crm.engine.begin() as conn:
            row = self._row(conn, operation_id, lock=True)
            values = {}
            if row['state'] not in TERMINAL:
                values.update(state=state, reason=reason)
            if result is not None: values['result'] = _json(result)
            if state != 'unknown':
                values['assignment_slot'] = None
            elif result is not None and row['state'] == 'dispatching':
                # A returned unknown effect may permit a freshly reviewed Cancel,
                # never a replacement Schedule. Record evidence and release only
                # while the assignment is locked in a non-pending state. Crash or
                # unknown-before-claim leaves its reservation intact.
                safe = conn.execute(update(assignments).where(assignments.c.id == row['assignment_id'],
                    assignments.c.workspace == self.workspace, assignments.c.profile == self.profile,
                    assignments.c.state != 'pending').values(version=assignments.c.version)).rowcount
                if safe == 1: values['assignment_slot'] = None
            if values: self._change(conn, row, **values)
            return self._view(row)

    @staticmethod
    def _source_identity(ctx, source, session_id, session_key, platform):
        # These values are actual keyword arguments supplied by the host, not
        # command text or REST claims. Local source authority is enforced by RPC.
        def field(name):
            value = source.get(name) if isinstance(source, dict) else getattr(source, name, None)
            return getattr(value, 'value', value)
        if platform != 'local' or field('platform') != 'local':
            raise CRMError('Only a genuine local native session command is supported', 403)
        _text(session_id, 'actual session_id')
        _text(session_key, 'actual session_key', 300)
        if not field('chat_id'): raise CRMError('Missing native source', 403)
        if _identity(ctx) is not None: raise CRMError('Scheduled executions cannot dispatch user commands', 403)
        return _hash(_json(dict(profile=ctx.profile_name, session_id=session_id, session_key=session_key,
            platform=platform, source={key: field(key) for key in
                ('platform', 'chat_id', 'user_id', 'profile', 'chat_type', 'detached_route')})))

    def execute(self, ctx, operation_id, *, source, session_id, session_key, platform):
        """Authenticated local command is the confirmation action, not an approval flag.

        Only the UUID arrives as command text. The complete reviewed snapshot was
        prepared by the server and rendered by CRM before its explicit Confirm.
        The host authenticates the calling session, not who clicked the UI.
        """
        _uuid(operation_id)
        self.work._host(ctx, scheduling=True)
        fingerprint = self._source_identity(ctx, source, session_id, session_key, platform)
        with self.crm.engine.connect() as conn:
            row = self._row(conn, operation_id)
        if row['intended_session_id'] != session_id:
            raise CRMError('Command session does not match the reviewed operation', 403)
        if row['state'] != 'prepared': return self._view(row)
        guard = _CommandGuard(self, operation_id, ctx, source, session_id, session_key, platform, fingerprint)
        try:
            args = dict(assignment_id=row['assignment_id'], _operation_guard=guard,
                        session_id=session_id, session_key=session_key, platform=platform)
            if row['verb'] == 'schedule': result = self.work.schedule(ctx, **args)
            elif row['verb'] == 'cancel':
                result = self.work.cancel(ctx, version=json.loads(row['request'])['expected_assignment_version'], **args)
            else: result = self.work.reconcile(ctx, **args)
            if guard.failure is not None:
                failure = guard.failure
                return self._settle(operation_id, getattr(failure, 'state', 'stale'), 'command_fence_blocked_further_effects', result)
            uncertain = result['state'] in {'unknown', 'create_unknown', 'resume_unknown'} or 'unknown' in result['reason']
            return self._settle(operation_id, 'unknown' if uncertain else 'finished',
                'scheduler_outcome_unknown_no_redispatch' if uncertain else 'native_operation_returned', result)
        except _AlreadyConsumed:
            return self.get(operation_id)
        except OperationFence as exc:
            return self._settle(operation_id, exc.state, exc.message)
        except CRMError as exc:
            return self._settle(operation_id, 'stale' if exc.status in (403, 409) else 'unknown',
                'native_context_or_review_changed' if exc.status in (403, 409) else 'native_operation_failed_no_redispatch')
        except Exception:
            return self._settle(operation_id, 'unknown', 'native_operation_failed_no_redispatch')

    def page(self, *, task_id=None, limit=25, offset=0):
        self.crm._integer(limit, 'limit', 1, 100)
        self.crm._integer(offset, 'offset')
        if task_id is not None: _text(task_id, 'task_id', 36)
        result = dict(items=[], total=0, limit=limit, offset=offset, observed_at=now(),
                      profile=self.profile, workspace_token=self.workspace, task_id=task_id)
        if not self.available: return result
        predicates = [operations.c.workspace == self.workspace, operations.c.profile == self.profile]
        if task_id is not None:
            predicates.append(operations.c.assignment_id.in_(select(assignments.c.id).where(assignments.c.task_id == task_id)))
        from .native_work import read_snapshot
        with read_snapshot(self.crm) as conn:
            result['total'] = conn.execute(select(func.count()).select_from(operations).where(*predicates)).scalar_one()
            rows = conn.execute(select(operations).where(*predicates)
                .order_by(operations.c.created_at.desc(), operations.c.id).limit(limit).offset(offset)).mappings()
            result['items'] = [self._view(self._row(conn, r['id'])) for r in rows]
        return result


class _AlreadyConsumed(Exception):
    pass


class _CommandGuard:
    """Internal Python capability, never serialized or forwarded to host tools."""
    def __init__(self, store, operation_id, ctx, source, session_id, session_key, platform, fingerprint):
        self.store, self.operation_id, self.ctx = store, operation_id, ctx
        self.context = source, session_id, session_key, platform
        self.fingerprint = fingerprint
        self.failure = None

    def _operation(self, conn, *, claiming=False):
        row = self.store._row(conn, self.operation_id, lock=True)
        if claiming and row['state'] != 'prepared': raise _AlreadyConsumed()
        if row['state'] == 'withdrawn': raise OperationFence('withdrawn', 'operation_withdrawn_no_further_effects')
        if self.store._expired(row): raise OperationFence('expired', 'approval_deadline_elapsed_no_further_effects')
        expected = 'prepared' if claiming else 'dispatching'
        if row['state'] != expected:
            if claiming: raise _AlreadyConsumed()
            raise OperationFence('stale', 'operation_claim_no_longer_valid')
        if self.store._source_identity(self.ctx, *self.context) != self.fingerprint or (not claiming and row['source_digest'] != self.fingerprint):
            raise OperationFence('stale', 'native_source_changed')
        if row['intended_session_id'] != self.context[1]: raise OperationFence('stale', 'native_session_changed')
        self.store.work._host(self.ctx, scheduling=True)
        # Context facade calls and row-lock acquisition may have waited. The
        # deadline is checked again after that work, not just on entry.
        if self.store._expired(row): raise OperationFence('expired', 'approval_deadline_elapsed_no_further_effects')
        return row

    def _task(self, conn, snapshot):
        task = snapshot['task']
        changed = conn.execute(update(tasks).where(tasks.c.id == task['id'], tasks.c.version == task['version'],
            tasks.c.status == task['status']).values(version=tasks.c.version)).rowcount
        if changed != 1: raise OperationFence('stale', 'source_task_changed')

    def claim(self, conn, assignment):
        row = self._operation(conn, claiming=True)
        review = json.loads(row['snapshot'])
        self._task(conn, review)
        # Claim local effects only after obtaining every mutation lock. In
        # particular Cancel must not advance generation after a lock wait that
        # consumed its approval deadline.
        locked = conn.execute(update(assignments).where(assignments.c.id == assignment['id'],
            assignments.c.workspace == self.store.workspace, assignments.c.profile == self.store.profile,
            assignments.c.version == assignment['version']).values(version=assignments.c.version)).rowcount
        if locked != 1: raise OperationFence('stale', 'reviewed_assignment_changed')
        if self.store._snapshot(conn, assignment['id']) != review:
            raise OperationFence('stale', 'reviewed_assignment_changed')
        row = self._operation(conn, claiming=True)  # revalidate after every lock wait
        self.store._change(conn, row, state='dispatching', reason='authenticated_local_command_claimed',
            actual_session_id=self.context[1], actual_session_key=self.context[2], source_digest=self.fingerprint)

    def fence(self, conn, assignment):
        try:
            return self._fence(conn, assignment)
        except CRMError as exc:
            self.failure = exc
            raise

    def _fence(self, conn, assignment):
        row = self._operation(conn)
        review = json.loads(row['snapshot'])
        self._task(conn, review)
        expected = review['assignment']
        generation = expected['generation'] + (1 if row['verb'] == 'cancel' and expected['state'] not in {'cancelled', 'superseded'} else 0)
        if assignment['id'] != expected['id'] or assignment['digest'] != expected['digest'] or assignment['generation'] != generation:
            raise OperationFence('stale', 'reviewed_assignment_changed')
        if row['verb'] == 'schedule': _future(expected['payload']['run_at'])
        self._operation(conn)  # source/runtime/deadline after any task-lock wait
