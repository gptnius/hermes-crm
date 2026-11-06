"""Durable internal-work intent and observed host evidence, never an agent runner.

No method calls Hermes or completes a CRM business task. Browser observations are
untrusted claims with explicit provenance, not backend verification. Callers must
inspect effective host tool scope before dispatch and reconcile unknown outcomes.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (Column, ForeignKey, Integer, MetaData, String, Table, Text,
                        UniqueConstraint, select, update)
from sqlalchemy.exc import IntegrityError

from .domain import CRMError, now, tasks

metadata = MetaData()
tasks.to_metadata(metadata)
assignments = Table('crm_agent_assignments', metadata,
    Column('id', String(36), primary_key=True),
    Column('task_id', String(36), ForeignKey('crm_tasks.id'), nullable=False),
    Column('workspace', String(160), nullable=False),
    Column('profile', String(160), nullable=False),
    Column('human_owner', String(160), nullable=False),
    Column('idempotency_key', String(160), nullable=False),
    Column('payload', Text, nullable=False), Column('digest', String(64), nullable=False),
    Column('generation', Integer, nullable=False), Column('created_at', String(40), nullable=False),
    UniqueConstraint('workspace', 'profile', 'idempotency_key'))
occurrences = Table('crm_agent_occurrences', metadata,
    Column('id', String(36), primary_key=True),
    Column('assignment_id', String(36), ForeignKey('crm_agent_assignments.id'), nullable=False),
    Column('generation', Integer, nullable=False), Column('version', Integer, nullable=False),
    Column('state', String(20), nullable=False), Column('reason', String(80), nullable=False),
    Column('session_request_id', String(36), nullable=False, unique=True),
    Column('submission_id', String(36), nullable=False, unique=True),
    Column('session_id', String(160), unique=True), Column('admission_id', String(160), unique=True),
    Column('dispatch_started', Integer, nullable=False),
    Column('cancel_requested', Integer, nullable=False),
    Column('safe_to_retry', Integer, nullable=False),
    Column('review_status', String(30), nullable=False),
    Column('retry_of', String(36), ForeignKey('crm_agent_occurrences.id')),
    Column('created_at', String(40), nullable=False), Column('updated_at', String(40), nullable=False),
    UniqueConstraint('assignment_id', 'generation'))
receipts = Table('crm_agent_receipts', metadata,
    Column('id', String(36), primary_key=True),
    Column('occurrence_id', String(36), ForeignKey('crm_agent_occurrences.id'), nullable=False),
    Column('kind', String(20), nullable=False), Column('reference', String(160), nullable=False),
    Column('provenance', String(30), nullable=False), Column('evidence', Text, nullable=False),
    Column('created_at', String(40), nullable=False),
    UniqueConstraint('occurrence_id', 'kind', 'reference'))

TERMINAL = {'succeeded', 'failed', 'cancelled'}
READ_TOOLS = frozenset({'crm_contact_get', 'crm_contact_list', 'crm_contact_report',
                        'crm_deal_get', 'crm_deal_list', 'crm_overview', 'crm_task_get', 'crm_task_list'})
DISCOVERY_TOOLS = frozenset({'tool_search', 'tool_describe', 'tool_call'})
SCOPE_MAX_AGE_SECONDS = 60


def _text(value, name, maximum=160):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise CRMError(f'Invalid {name}')
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _route(value):
    if not isinstance(value, dict) or set(value) != {'connectionId', 'profile', 'targetProfile', 'mode'}:
        raise CRMError('Invalid captured host route')
    for key in ('connectionId', 'profile', 'targetProfile'):
        _text(value[key], f'route {key}')
    if value['mode'] not in ('local', 'remote'):
        raise CRMError('Invalid host route mode')
    return dict(value)


def _names(value, name, allowed, required=()):
    if not isinstance(value, list) or not value or len(value) > 16 or any(
            not isinstance(item, str) for item in value):
        raise CRMError(f'Invalid {name}')
    if len(value) != len(set(value)) or not set(value) <= allowed or not set(required) <= set(value):
        raise CRMError(f'Unapproved or incomplete {name}')
    return sorted(value)


class ExecutionStore:
    def __init__(self, crm):
        self.crm = crm
        self.workspace = crm.workspace_token()
        self.profile = crm.profile
        metadata.create_all(crm.engine, tables=[assignments, occurrences, receipts])

    def _scope(self, profile):
        if profile != self.profile:
            raise CRMError('Cross-profile assignment is not supported', 403)

    def _assignment(self, conn, assignment_id):
        row = conn.execute(select(assignments).where(
            assignments.c.id == assignment_id, assignments.c.workspace == self.workspace,
            assignments.c.profile == self.profile)).mappings().first()
        if row is None:
            raise CRMError('Assignment not found in current workspace/profile', 404)
        return dict(row)

    def _occurrence(self, conn, occurrence_id):
        row = conn.execute(select(occurrences).where(occurrences.c.id == occurrence_id)).mappings().first()
        if row is None:
            raise CRMError('Occurrence not found', 404)
        result = dict(row)
        assignment = self._assignment(conn, result['assignment_id'])
        return assignment, result

    def _new_occurrence(self, conn, assignment_id, generation, run_at=None, retry_of=None):
        row = dict(id=str(uuid.uuid4()), assignment_id=assignment_id, generation=generation,
                   version=1, state='blocked' if run_at else 'pending',
                   reason='public_scheduler_api_unavailable' if run_at else '',
                   session_request_id=str(uuid.uuid4()), submission_id=str(uuid.uuid4()),
                   session_id=None, admission_id=None, dispatch_started=0, cancel_requested=0,
                   safe_to_retry=0, review_status='not_ready', retry_of=retry_of,
                   created_at=now(), updated_at=now())
        conn.execute(occurrences.insert().values(**row))
        return row

    def create(self, *, task_id, human_owner, prompt, success_criteria, idempotency_key,
               profile, run_at=None, host_connection_identity=None, host_profile_identity=None,
               host_route=None, required_tools=None):
        """Atomically persist exact immutable payload and stable external request IDs."""
        self._scope(profile)
        if host_connection_identity is not None:
            _text(host_connection_identity, 'host_connection_identity')
        if host_profile_identity is not None:
            _text(host_profile_identity, 'host_profile_identity')
        if host_route is not None: host_route = _route(host_route)
        required_tools = _names(required_tools if required_tools is not None else ['crm_task_get'],
                                'required tools', READ_TOOLS, ['crm_task_get'])
        for name, value, limit in [('task_id', task_id, 36), ('human_owner', human_owner, 160),
                                   ('prompt', prompt, 50000), ('success_criteria', success_criteria, 10000),
                                   ('idempotency_key', idempotency_key, 160)]:
            _text(value, name, limit)
        if run_at is not None:
            try:
                dt = datetime.fromisoformat(run_at.replace('Z', '+00:00'))
                if dt.tzinfo is None: raise ValueError()
                run_at = dt.astimezone(timezone.utc).isoformat(timespec='microseconds')
            except (ValueError, AttributeError):
                raise CRMError('run_at must be an ISO timestamp with timezone')
        request_payload = dict(task_id=task_id, human_owner=human_owner, prompt=prompt,
                               success_criteria=success_criteria, profile=profile,
                               workspace=self.workspace, run_at=run_at, action='internal',
                               authorization_scope='internal_crm_only',
                               host_connection_identity=host_connection_identity,
                               host_profile_identity=host_profile_identity,
                               host_route=host_route, required_tools=required_tools,
                               host_connection_provenance='caller_observed' if host_connection_identity else None)
        def existing(conn):
            row = conn.execute(select(assignments).where(
                assignments.c.workspace == self.workspace, assignments.c.profile == profile,
                assignments.c.idempotency_key == idempotency_key)).mappings().first()
            if row:
                saved_request = json.loads(row['payload'])
                saved_request.pop('task_version')
                saved_request.pop('task_status')
                if saved_request != request_payload:
                    raise CRMError('Idempotency key payload conflict', 409)
                return row['id']
        # Recover the original intent before resnapshotting mutable source data.
        with self.crm.engine.connect() as conn:
            assignment_id = existing(conn)
            if assignment_id is None:
                source_task = conn.execute(select(tasks).where(tasks.c.id == task_id)).mappings().first()
                if source_task is None: raise CRMError('Task not found', 404)
        if assignment_id is not None:
            return self.get(assignment_id)
        payload = _json(dict(request_payload, task_version=source_task['version'],
                             task_status=source_task['status']))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        try:
            with self.crm.engine.begin() as conn:
                assignment_id = existing(conn)
                if assignment_id is None:
                    task = conn.execute(select(tasks).where(tasks.c.id == task_id)).mappings().first()
                    if task is None: raise CRMError('Task not found', 404)
                    if task['version'] != source_task['version'] or task['status'] != 'open':
                        raise CRMError('Task changed or is not open', 409)
                    assignment_id = str(uuid.uuid4())
                    conn.execute(assignments.insert().values(id=assignment_id, task_id=task_id,
                        workspace=self.workspace, profile=profile, human_owner=human_owner,
                        idempotency_key=idempotency_key, payload=payload, digest=digest,
                        generation=1, created_at=now()))
                    self._new_occurrence(conn, assignment_id, 1, run_at)
        except IntegrityError:
            with self.crm.engine.connect() as conn:
                assignment_id = existing(conn)
                if assignment_id is None: raise
        return self.get(assignment_id)

    def get(self, assignment_id):
        with self.crm.engine.connect() as conn:
            row = self._assignment(conn, assignment_id)
            row['payload'] = json.loads(row['payload'])
            row['occurrences'] = [dict(r) for r in conn.execute(select(occurrences).where(
                occurrences.c.assignment_id == assignment_id).order_by(occurrences.c.generation)).mappings()]
            for occurrence in row['occurrences']:
                occurrence['receipts'] = [dict(r) for r in conn.execute(select(receipts).where(
                    receipts.c.occurrence_id == occurrence['id']).order_by(receipts.c.created_at, receipts.c.id)).mappings()]
                for kind, key in [('runtime', 'runtime'), ('scope', 'scope'), ('submit', 'submission')]:
                    evidence = [json.loads(r['evidence']) | {'reference': r['reference'], 'created_at': r['created_at']}
                                for r in occurrence['receipts'] if r['kind'] == kind]
                    occurrence[key] = max(evidence, key=lambda item: item['occurrence_version']) if evidence else None
                occurrence['scope_digest'] = occurrence['scope']['scope_digest'] if occurrence['scope'] else None
                occurrence['submit_started'] = occurrence['submission'] is not None
            return row

    def list(self, *, task_id=None, limit=100):
        if type(limit) is not int or not 1 <= limit <= 500: raise CRMError('Invalid limit')
        query = select(assignments.c.id).where(assignments.c.workspace == self.workspace,
                                             assignments.c.profile == self.profile)
        if task_id is not None: query = query.where(assignments.c.task_id == task_id)
        with self.crm.engine.connect() as conn:
            ids = conn.execute(query.order_by(assignments.c.created_at, assignments.c.id).limit(limit)).scalars().all()
        return [self.get(i) for i in ids]

    def _check_version(self, assignment, row, version, generation):
        if type(version) is not int or type(generation) is not int:
            raise CRMError('Version and generation must be integers', 409)
        if generation != row['generation'] or generation != assignment['generation']:
            raise CRMError('Stale execution generation', 409)
        if version != row['version']: raise CRMError('Stale occurrence version', 409)

    def _cas(self, conn, assignment, row, version, generation, values):
        self._check_version(assignment, row, version, generation)
        count = conn.execute(update(occurrences).where(occurrences.c.id == row['id'],
            occurrences.c.version == version).values(**values, version=version + 1, updated_at=now())).rowcount
        if count != 1: raise CRMError('Concurrent occurrence update', 409)

    def _change(self, occurrence_id, version, generation, operation):
        with self.crm.engine.begin() as conn:
            assignment, row = self._occurrence(conn, occurrence_id)
            values = operation(conn, assignment, row)
            self._cas(conn, assignment, row, version, generation, values)
        return self.get(assignment['id'])

    def _validate_task(self, conn, assignment):
        payload = json.loads(assignment['payload'])
        task = conn.execute(select(tasks).where(tasks.c.id == assignment['task_id'])).mappings().first()
        if task is None or task['status'] != 'open' or task['version'] != payload['task_version']:
            raise CRMError('Source task changed or is no longer open; create new intent', 409)

    def _guard_task(self, conn, assignment):
        # Conditional no-op write serializes with task edits on SQLite/PostgreSQL.
        # Hold the task row lock through occurrence CAS without changing data.
        payload = json.loads(assignment['payload'])
        guarded = conn.execute(update(tasks).where(
            tasks.c.id == assignment['task_id'], tasks.c.status == 'open',
            tasks.c.version == payload['task_version']).values(version=tasks.c.version)).rowcount
        if guarded != 1:
            raise CRMError('Source task changed or is no longer open; create new intent', 409)

    def _validate_connection(self, assignment, host_connection_identity):
        captured = json.loads(assignment['payload']).get('host_connection_identity')
        if not captured:
            raise CRMError('Local intent only: capture SDK host connection identity before dispatch', 409)
        if host_connection_identity != captured:
            raise CRMError('Host connection identity mismatch; do not resume on another connection', 409)

    def validate_dispatch(self, occurrence_id, *, host_connection_identity=None):
        """Read-only preflight; begin_dispatch repeats this check transactionally.

        The external host still needs scope inspection and generation reconciliation.
        A database transaction cannot atomically control a later host RPC.
        """
        with self.crm.engine.connect() as conn:
            assignment, row = self._occurrence(conn, occurrence_id)
            self._validate_connection(assignment, host_connection_identity)
            if row['generation'] != assignment['generation'] or row['state'] != 'pending' or row['cancel_requested']:
                raise CRMError('Occurrence cannot dispatch', 409)
            self._validate_task(conn, assignment)
            return dict(assignment_id=assignment['id'], occurrence_id=occurrence_id,
                        version=row['version'], generation=row['generation'], digest=assignment['digest'])

    def begin_dispatch(self, occurrence_id, *, version, generation, host_connection_identity=None):
        """Persist uncertainty BEFORE any external session-create or submission call."""
        def operation(conn, assignment, row):
            self._validate_connection(assignment, host_connection_identity)
            if row['state'] != 'pending' or row['cancel_requested']:
                raise CRMError('Occurrence cannot dispatch', 409)
            self._validate_task(conn, assignment)
            self._guard_task(conn, assignment)
            return dict(state='unknown', reason='dispatch_outcome_pending', dispatch_started=1)
        return self._change(occurrence_id, version, generation, operation)

    def mark(self, occurrence_id, *, version, generation, state, reason):
        if state not in {'blocked', 'unknown'}: raise CRMError('Use receipts for host execution state')
        _text(reason, 'reason', 80)
        def operation(conn, assignment, row):
            if row['state'] in TERMINAL: raise CRMError('Terminal occurrence', 409)
            return dict(state=state, reason=reason)
        return self._change(occurrence_id, version, generation, operation)

    def _latest_phase(self, conn, occurrence_id, kind):
        rows = conn.execute(select(receipts).where(receipts.c.occurrence_id == occurrence_id,
                                                   receipts.c.kind == kind)).mappings()
        values = [json.loads(row['evidence']) | {'reference': row['reference'], 'created_at': row['created_at']}
                  for row in rows]
        return max(values, key=lambda item: item['occurrence_version']) if values else None

    def _phase_binding(self, assignment, row, *, session_request_id, submission_id,
                       host_connection_identity, profile_id, route, session_id):
        self._validate_connection(assignment, host_connection_identity)
        payload = json.loads(assignment['payload'])
        if not payload.get('host_route') or _route(route) != payload['host_route']:
            raise CRMError('Captured host route mismatch or missing', 409)
        if not payload.get('host_profile_identity') or profile_id != payload['host_profile_identity']:
            raise CRMError('Host authority profile identity mismatch or uncaptured', 409)
        if session_request_id != row['session_request_id'] or submission_id != row['submission_id']:
            raise CRMError('Receipt operation identity mismatch', 409)
        if session_id != row['session_id']:
            raise CRMError('Phase session mismatch', 409)
        if not row['dispatch_started'] or row['state'] in TERMINAL:
            raise CRMError('Occurrence cannot record dispatch phase', 409)

    def _record_phase(self, occurrence_id, version, generation, kind, binding, operation):
        with self._receipt_transaction() as conn:
            assignment, row = self._occurrence(conn, occurrence_id)
            self._check_version(assignment, row, version, generation)
            self._phase_binding(assignment, row, **binding)
            evidence, values = operation(conn, assignment, row)
            evidence.update(binding, occurrence_version=version + 1, crm_generation=generation,
                            provenance='client_observed', reference_provenance='client_derived_sha256')
            reference = 'client-sha256:' + hashlib.sha256(_json(evidence).encode()).hexdigest()
            self._cas(conn, assignment, row, version, generation, values)
            conn.execute(receipts.insert().values(id=str(uuid.uuid4()), occurrence_id=occurrence_id,
                kind=kind, reference=reference, provenance='client_observed', evidence=_json(evidence), created_at=now()))
        return self.get(assignment['id'])

    def _runtime_epoch_high_water(self, conn, occurrence_id):
        # runtime.describe identifies the current authority incarnation. Admission
        # receipts instead retain their execution owner's epoch across restarts.
        history = conn.execute(select(receipts.c.evidence).where(
            receipts.c.occurrence_id == occurrence_id, receipts.c.kind == 'runtime')).scalars()
        return max((json.loads(raw)['authority_epoch'] for raw in history), default=-1)

    def record_runtime(self, occurrence_id, *, version, generation, session_request_id, submission_id,
                       host_connection_identity, profile_id, route, session_id, instance_id,
                       authority_epoch, desktop_protocol):
        """Record runtime.describe identity on the captured route, not attestation."""
        _text(instance_id, 'runtime instance_id')
        if type(authority_epoch) is not int or not 0 <= authority_epoch <= 9223372036854775807:
            raise CRMError('Invalid runtime authority_epoch')
        if desktop_protocol != 'hermes-gateway-v1': raise CRMError('Unsupported desktop protocol')
        binding = dict(session_request_id=session_request_id, submission_id=submission_id,
                       host_connection_identity=host_connection_identity, profile_id=profile_id,
                       route=route, session_id=session_id)
        def operation(conn, assignment, row):
            if authority_epoch < self._runtime_epoch_high_water(conn, occurrence_id):
                raise CRMError('Stale runtime authority epoch', 409)
            previous = self._latest_phase(conn, occurrence_id, 'runtime')
            changed = bool(previous and (previous['instance_id'] != instance_id or previous['authority_epoch'] != authority_epoch))
            return dict(source='runtime.describe', instance_id=instance_id, authority_epoch=authority_epoch,
                        desktop_protocol=desktop_protocol, resume_required=bool(row['session_id']) and
                        (changed or bool(previous and previous['resume_required']))), {}
        return self._record_phase(occurrence_id, version, generation, 'runtime', binding, operation)

    def record_scope(self, occurrence_id, *, version, generation, session_request_id, submission_id,
                     host_connection_identity, profile_id, route, session_id, runtime_reference,
                     enabled_toolsets, tools, visible_tools, total, resumed_session_id=None):
        """Freeze a bounded effective read inventory snapshot; never a strict host ceiling."""
        if enabled_toolsets != ['crm_read']: raise CRMError('Effective toolsets must be exactly crm_read')
        tools = _names(tools, 'effective tools', READ_TOOLS, ['crm_task_get'])
        visible_tools = _names(visible_tools, 'visible tools', READ_TOOLS | DISCOVERY_TOOLS)
        if type(total) is not int or total != len(tools): raise CRMError('Tool inventory total mismatch')
        if not (set(visible_tools) & READ_TOOLS) <= set(tools):
            raise CRMError('Visible tools contradict full inventory')
        binding = dict(session_request_id=session_request_id, submission_id=submission_id,
                       host_connection_identity=host_connection_identity, profile_id=profile_id,
                       route=route, session_id=session_id)
        def operation(conn, assignment, row):
            if not row['session_id']: raise CRMError('Scope requires a bound session', 409)
            runtime = self._latest_phase(conn, occurrence_id, 'runtime')
            if not runtime or runtime['reference'] != runtime_reference:
                raise CRMError('Runtime observation changed; revalidate scope', 409)
            if resumed_session_id is not None and resumed_session_id != row['session_id']:
                raise CRMError('Resume session mismatch', 409)
            if runtime['resume_required'] and resumed_session_id != row['session_id']:
                raise CRMError('Runtime changed; resume and revalidate the same session', 409)
            required = json.loads(assignment['payload'])['required_tools']
            if not set(required) <= set(tools): raise CRMError('Required task tools unavailable', 409)
            frozen = dict(source='tools.show+session.snapshot', runtime_reference=runtime_reference,
                          instance_id=runtime['instance_id'], authority_epoch=runtime['authority_epoch'],
                          enabled_toolsets=enabled_toolsets, tools=tools, visible_tools=visible_tools,
                          total=total, resumed_session_id=resumed_session_id, strict_host_ceiling=False)
            frozen['scope_digest'] = hashlib.sha256(_json(dict(frozen, **binding)).encode()).hexdigest()
            return frozen, {}
        return self._record_phase(occurrence_id, version, generation, 'scope', binding, operation)

    def prepare_submit(self, occurrence_id, *, version, generation, session_request_id, submission_id,
                       host_connection_identity, profile_id, route, session_id, scope_digest, replay=False):
        """Persist before prompt.submit; replay uses exactly the original immutable IDs.

        A scope snapshot is not an atomic host-enforced capability ceiling. Scope
        must be reobserved within 60 seconds. Replays additionally require an
        observed resume of this session and never generate a replacement prompt.
        """
        if type(replay) is not bool: raise CRMError('Invalid replay flag')
        binding = dict(session_request_id=session_request_id, submission_id=submission_id,
                       host_connection_identity=host_connection_identity, profile_id=profile_id,
                       route=route, session_id=session_id)
        def operation(conn, assignment, row):
            if row['cancel_requested']: raise CRMError('Cancellation requested; do not submit', 409)
            if row['state'] == 'blocked': raise CRMError('Occurrence is blocked; do not submit', 409)
            if not row['session_id']: raise CRMError('Submission requires a bound session', 409)
            if row['admission_id']: raise CRMError('Reconcile known admission instead of resubmitting', 409)
            previous = self._latest_phase(conn, occurrence_id, 'submit')
            if bool(previous) != replay:
                raise CRMError('Submission intent exists: replay same identity, or first submit required', 409)
            runtime = self._latest_phase(conn, occurrence_id, 'runtime')
            scope = self._latest_phase(conn, occurrence_id, 'scope')
            if not runtime or not scope or scope['scope_digest'] != scope_digest or scope['runtime_reference'] != runtime['reference']:
                raise CRMError('Scope/runtime evidence missing or changed; revalidate', 409)
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(scope['created_at'])).total_seconds()
            if not 0 <= age <= SCOPE_MAX_AGE_SECONDS:
                raise CRMError('Scope observation expired; revalidate', 409)
            if replay and scope['resumed_session_id'] != row['session_id']:
                raise CRMError('Resume the same session and revalidate before replay', 409)
            if replay and scope['occurrence_version'] <= previous['occurrence_version']:
                raise CRMError('Fresh recovery scope and resume required after each submit attempt', 409)
            self._validate_task(conn, assignment)
            self._guard_task(conn, assignment)
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(scope['created_at'])).total_seconds()
            if not 0 <= age <= SCOPE_MAX_AGE_SECONDS:
                raise CRMError('Scope observation expired while waiting; revalidate', 409)
            return dict(source='crm.prepare_submit', scope_digest=scope_digest,
                        runtime_reference=runtime['reference'], replay=replay, payload_digest=assignment['digest'],
                        submit_attempt=(previous['submit_attempt'] + 1) if previous else 1), dict(
                            state='unknown', reason='submission_outcome_pending', safe_to_retry=0)
        return self._record_phase(occurrence_id, version, generation, 'submit', binding, operation)

    def observe_host(self, occurrence_id, *, version, generation, session_request_id,
                     submission_id, session_id, admission_id, host_connection_identity,
                     profile_id, source, status, outcome, sequence, authority_epoch,
                     execution_generation, redacted_result=None, redacted_summary=''):
        """Normalize a client-observed public prompt receipt, never certify it.

        `redacted_result` accepts only final_response (already redacted), failed,
        error, interrupted and completed. Error is a boolean indicator, not raw
        error text. Only its digest and presence/boolean flags are persisted.
        Reference is a client-derived observation hash, not a host result ID.
        Initial terminal/unknown receipts bind their real admission atomically;
        no queued/admitted receipt is fabricated. Host and CRM generations differ.
        """
        observation = dict(profile_id=profile_id, source=source, status=status, outcome=outcome,
                           sequence=sequence, authority_epoch=authority_epoch,
                           execution_generation=execution_generation, redacted_result=redacted_result)
        return self.observe(occurrence_id, version=version, generation=generation, kind='host',
                            reference=None, session_request_id=session_request_id,
                            submission_id=submission_id, session_id=session_id, admission_id=admission_id,
                            host_connection_identity=host_connection_identity,
                            redacted_summary=redacted_summary, host_observation=observation)

    @staticmethod
    def _normalize_host(observation):
        fields = {'profile_id', 'source', 'status', 'outcome', 'sequence',
                  'authority_epoch', 'execution_generation', 'redacted_result'}
        if not isinstance(observation, dict) or set(observation) != fields:
            raise CRMError('Invalid host observation fields')
        _text(observation['profile_id'], 'host profile_id')
        if not isinstance(observation['source'], str) or observation['source'] not in {'prompt.submit', 'prompt.receipt', 'prompt.cancel'}:
            raise CRMError('Unsupported host observation source')
        if not isinstance(observation['status'], str) or observation['status'] not in {'queued', 'started', 'unknown', 'terminal'}:
            raise CRMError('Unsupported host status')
        outcome = observation['outcome']
        if outcome is not None: _text(outcome, 'host outcome', 80)
        for key in ('sequence', 'authority_epoch', 'execution_generation'):
            value = observation[key]
            if key == 'execution_generation' and value is None: continue
            minimum = 1 if key == 'sequence' else 0
            if type(value) is not int or not minimum <= value <= 9223372036854775807:
                raise CRMError(f'Invalid host {key}')
        normalized = {key: value for key, value in observation.items() if key != 'redacted_result'}
        result = observation['redacted_result']
        flags = None
        if result is not None:
            allowed = {'final_response', 'failed', 'error', 'interrupted', 'completed'}
            if not isinstance(result, dict) or not set(result) <= allowed:
                raise CRMError('Only allowlisted redacted result fields are accepted')
            for key, value in result.items():
                if key == 'final_response':
                    if not isinstance(value, str) or len(value) > 4000:
                        raise CRMError('Invalid redacted final_response')
                elif type(value) is not bool:
                    raise CRMError(f'Invalid redacted result {key} flag')
            flags = dict(final_response_present=bool(result.get('final_response', '').strip()),
                         failed=result.get('failed', False), error=result.get('error', False),
                         interrupted=result.get('interrupted', False), completed=result.get('completed'))
        normalized['redacted_result_digest'] = hashlib.sha256(_json(result).encode()).hexdigest() if result is not None else None
        normalized['result_flags'] = flags
        status = observation['status']
        state = 'unknown'
        if status in {'queued', 'started'} and outcome is None and result is None:
            state = 'admitted' if status == 'queued' else 'running'
        elif status == 'terminal':
            if outcome == 'completed' and flags and flags['final_response_present'] and not any(
                    flags[key] for key in ('failed', 'error', 'interrupted')) and flags['completed'] is not False:
                state = 'succeeded'
            elif outcome == 'failed' and not (flags and (flags['completed'] is True or flags['interrupted'])):
                state = 'failed'
            elif outcome == 'cancelled' and not (flags and (flags['completed'] is True or flags['failed'] or flags['error'])):
                state = 'cancelled'
        return normalized, state

    def _validate_host_history(self, conn, occurrence_id, row, observation):
        history = [json.loads(item) for item in conn.execute(select(receipts.c.evidence).where(
            receipts.c.occurrence_id == occurrence_id)).scalars()]
        prior_hosts = [item['host_observation'] for item in history if item.get('host_observation')]
        if any(item['authority_epoch'] > observation['authority_epoch'] for item in prior_hosts):
            raise CRMError('Stale host authority epoch', 409)
        if any(item['status'] == 'terminal' for item in prior_hosts) and observation['status'] != 'terminal':
            raise CRMError('Host terminal state regression', 409)
        if (row['state'] == 'running' or any(item.get('state') == 'running' for item in history)) and observation['status'] == 'queued':
            raise CRMError('State regression', 409)
        if any(item['sequence'] != observation['sequence'] for item in prior_hosts):
            raise CRMError('Host admission sequence identity conflict', 409)
        # Host sequence is immutable admission identity, not a status revision. Queued
        # -> started -> terminal may share it. Once terminal, its identity fields
        # cannot change at that tuple; only missing result evidence may hydrate.
        for item in prior_hosts:
            if item['status'] == 'terminal':
                if any(item[key] != observation[key] for key in ('status', 'outcome', 'authority_epoch', 'execution_generation')):
                    raise CRMError('Conflicting host terminal observation identity', 409)
                if item['redacted_result_digest'] is not None and item['redacted_result_digest'] != observation['redacted_result_digest']:
                    raise CRMError('Conflicting host terminal result evidence', 409)
        known_generations = [item['execution_generation'] for item in prior_hosts if item['execution_generation'] is not None]
        if known_generations and (observation['execution_generation'] is None or
                                  observation['execution_generation'] < max(known_generations)):
            raise CRMError('Missing or stale host execution generation', 409)

    @contextmanager
    def _receipt_transaction(self):
        try:
            with self.crm.engine.begin() as conn:
                yield conn
        except IntegrityError as exc:
            raise CRMError('Receipt identity already belongs to another occurrence or conflicts', 409) from exc

    def observe(self, occurrence_id, *, version, generation, kind, reference,
                session_request_id, submission_id, session_id=None, admission_id=None,
                state=None, redacted_summary='', provenance='client_observed',
                host_connection_identity=None, host_observation=None):
        """Append scoped host receipt claims, not a backend verification certificate.

        Summary must already be redacted; arbitrary host payloads/credentials are
        deliberately not accepted. reference is an opaque client observation reference, not a verified host ID.
        """
        if kind not in {'session', 'admission', 'result', 'not_admitted', 'host'}: raise CRMError('Invalid receipt kind')
        if provenance != 'client_observed': raise CRMError('Unsupported provenance')
        normalized_host = None
        if kind == 'host':
            if state is not None or reference is not None:
                raise CRMError('Host observation derives state and reference')
            normalized_host, state = self._normalize_host(host_observation)
            reference = 'client-sha256:' + hashlib.sha256(_json(dict(
                observation=normalized_host, session_id=session_id, admission_id=admission_id,
                session_request_id=session_request_id, submission_id=submission_id,
                host_connection_identity=host_connection_identity)).encode()).hexdigest()
        elif host_observation is not None:
            raise CRMError('Host fields require a structured host observation')
        _text(reference, 'reference')
        if not isinstance(redacted_summary, str) or len(redacted_summary) > 4000: raise CRMError('Invalid redacted summary')
        for name, value in [('session_id', session_id), ('admission_id', admission_id)]:
            if value is not None: _text(value, name)
        evidence = _json(dict(session_request_id=session_request_id, submission_id=submission_id,
                             session_id=session_id, admission_id=admission_id, state=state,
                             redacted_summary=redacted_summary, provenance=provenance,
                             host_connection_identity=host_connection_identity,
                             host_observation=normalized_host,
                             reference_provenance='client_derived_sha256' if normalized_host else 'caller_supplied'))
        with self._receipt_transaction() as conn:
            assignment, row = self._occurrence(conn, occurrence_id)
            self._check_version(assignment, row, version, generation)
            self._validate_connection(assignment, host_connection_identity)
            if session_request_id != row['session_request_id'] or submission_id != row['submission_id']:
                raise CRMError('Receipt operation identity mismatch', 409)
            if normalized_host:
                expected_profile = json.loads(assignment['payload']).get('host_profile_identity')
                if not expected_profile or normalized_host['profile_id'] != expected_profile:
                    raise CRMError('Host authority profile identity mismatch or uncaptured', 409)
                self._validate_host_history(conn, occurrence_id, row, normalized_host)
            previous = conn.execute(select(receipts).where(receipts.c.occurrence_id == occurrence_id,
                receipts.c.kind == kind, receipts.c.reference == reference)).mappings().first()
            if previous:
                if previous['evidence'] != evidence: raise CRMError('Receipt identity conflict', 409)
                return self.get(assignment['id'])
            if row['state'] in TERMINAL: raise CRMError('Terminal occurrence', 409)
            if not row['dispatch_started']: raise CRMError('Dispatch intent must precede host evidence', 409)
            if row['session_id'] and session_id != row['session_id']:
                raise CRMError('Receipt session mismatch', 409)
            if row['admission_id'] and admission_id != row['admission_id']:
                raise CRMError('Receipt admission mismatch', 409)
            values = {}
            if kind in {'admission', 'result'}:
                prior_structured = conn.execute(select(receipts.c.id).where(
                    receipts.c.occurrence_id == occurrence_id, receipts.c.kind == 'host').limit(1)).first()
                if prior_structured:
                    raise CRMError('Continue structured host observations for this admission', 409)
            if kind == 'host':
                if not row['session_id'] or not session_id or not admission_id:
                    raise CRMError('Session and admission association required', 409)
                values = dict(admission_id=admission_id, state=state, safe_to_retry=0,
                              reason='host_outcome_requires_review' if state == 'unknown' else '',
                              review_status='awaiting_human_review' if state == 'succeeded' else 'not_ready')
            elif kind == 'session':
                if not session_id or state is not None or admission_id is not None:
                    raise CRMError('Invalid session receipt')
                values = dict(session_id=session_id)
            elif kind == 'not_admitted':
                if row['admission_id'] or admission_id is not None or state != 'failed':
                    raise CRMError('Nonadmission evidence required', 409)
                if session_id != row['session_id']:
                    raise CRMError('Nonadmission session must match persisted session', 409)
                # A client assertion is not independently verified nonexecution.
                # Keep reconciliation possible and never authorize a fresh prompt.
                values = dict(state='unknown', reason='unverified_nonadmission', safe_to_retry=0)
            else:
                if not row['session_id'] or not session_id or not admission_id:
                    raise CRMError('Session and admission association required', 409)
                if kind == 'admission':
                    if state not in {'admitted', 'running'}: raise CRMError('Invalid admission state')
                    if state == 'admitted':
                        prior_admissions = conn.execute(select(receipts.c.evidence).where(
                            receipts.c.occurrence_id == occurrence_id,
                            receipts.c.kind.in_(['admission', 'host']))).scalars()
                        if row['state'] == 'running' or any(
                                json.loads(item)['state'] == 'running' for item in prior_admissions):
                            raise CRMError('State regression', 409)
                    values = dict(state=state, admission_id=admission_id, reason='')
                else:
                    if not row['admission_id'] or state not in TERMINAL:
                        raise CRMError('Admitted terminal result required', 409)
                    values = dict(state=state, reason='', review_status='awaiting_human_review' if state == 'succeeded' else 'not_ready')
            self._cas(conn, assignment, row, version, generation, values)
            conn.execute(receipts.insert().values(id=str(uuid.uuid4()), occurrence_id=occurrence_id,
                kind=kind, reference=reference, provenance=provenance, evidence=evidence, created_at=now()))
        return self.get(assignment['id'])

    def request_cancel(self, occurrence_id, *, version, generation):
        def operation(conn, assignment, row):
            if row['state'] in TERMINAL: raise CRMError('Terminal occurrence', 409)
            return dict(cancel_requested=1)
        return self._change(occurrence_id, version, generation, operation)

    def cancel_undispatched(self, occurrence_id, *, version, generation):
        """Local cancellation is conclusive only before any dispatch attempt."""
        def operation(conn, assignment, row):
            if row['dispatch_started'] or not row['cancel_requested'] or row['state'] in TERMINAL:
                raise CRMError('Host cancellation receipt required after dispatch', 409)
            return dict(state='cancelled', reason='cancelled_before_dispatch')
        return self._change(occurrence_id, version, generation, operation)

    def retry(self, occurrence_id, *, version, generation):
        """Reserved for independently verified nonadmission, not client claims.

        No current public observation method sets safe_to_retry. Until a verified
        backend reconciler exists, post-dispatch retries remain blocked.
        """
        with self.crm.engine.begin() as conn:
            assignment, row = self._occurrence(conn, occurrence_id)
            if row['state'] != 'failed' or not row['safe_to_retry'] or row['cancel_requested']:
                raise CRMError('Reconcile outcome before retry; automatic retry is forbidden', 409)
            self._cas(conn, assignment, row, version, generation, dict(safe_to_retry=0))
            count = conn.execute(update(assignments).where(assignments.c.id == assignment['id'],
                assignments.c.generation == generation).values(generation=generation + 1)).rowcount
            if count != 1: raise CRMError('Concurrent generation update', 409)
            self._new_occurrence(conn, assignment['id'], generation + 1, retry_of=occurrence_id)
        return self.get(assignment['id'])

    def coverage(self, assignment_id):
        row = self.get(assignment_id)
        current = row['occurrences'][-1]
        # Even an observed admission is not a guarantee of execution or delivery.
        return dict(assignment_id=assignment_id, state=current['state'],
                    covered=False, host_connection_bound=bool(row['payload'].get('host_connection_identity')),
                    reason='awaiting_human_review' if current['state'] == 'succeeded'
                    else current['reason'] or 'execution_not_guaranteed',
                    cancel_requested=bool(current['cancel_requested']))
