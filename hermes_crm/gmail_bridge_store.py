"""Optional local metadata bridge. Never authenticates or invokes a provider.

bind_verified is a trusted-runtime boundary: invoke only after verifying the
selected existing grant's mailbox. A fingerprint is SHA256 of a NONSECRET
connection selector, never a token. Account UUIDs are local namespaces, not
Google identities. Contact versions fence explicit alias edits; those deliberate
assignments survive unrelated contact edits. Reads recompute current associations.
Only complete SyncResult values publish metadata/checkpoints. Failed/partial
observations are discarded; old evidence survives. No delivery assertions.
"""
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import re
import time
import uuid
import unicodedata
from sqlalchemy import select, update, func, delete
from .domain import CRMError, contacts, settings
from .gmail_incremental import Observation, SyncResult
from .gmail_matching import ContactIdentity, CompiledMatcher, normalize_mailbox
from .gmail_bridge_schema import check_schema, state, receipts, messages, aliases as aliases_table, control_receipts
from .report_store import transaction

MAX_MESSAGES = 10000
MAX_RECEIPTS = 10000
MAX_CONTROL_RECEIPTS = 128

def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)

def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()

def _match(item, matcher):
    result = matcher.match(item['raw_headers'])
    issues = tuple(item.get('header_issues', ()))
    if issues:
        result = replace(result, issues=tuple(sorted(set(result.issues) | set(issues))), direction='unknown')
    return result


def _semantics(value):
    # Versions record provenance, not address identity or participant meaning.
    if isinstance(value, dict):
        return {k: _semantics(v) for k, v in value.items() if k != 'version'}
    if isinstance(value, (list, tuple)):
        return [_semantics(v) for v in value]
    return value


def _protected(response):
    if response.get('verification'):
        return response.get('status') in ('running', 'unknown')
    if response.get('lease'):
        return not response.get('outcome') or response['outcome'].get('status') == 'unknown'
    return response.get('status') == 'unknown'


def _request_revision(payload):
    kind = payload[0]
    if kind == 'bind':
        return payload[4]
    if kind == 'begin':
        return payload[1]
    if kind == 'finish':
        return payload[1]['revision']
    return payload[-1]


def _empty():
    return dict(revision=0, selected=None, enabled=False, accounts={}, lease=None, generation=0, polling_enabled=False, receipt_revision_floor=0)

def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,255}', value):
        raise CRMError('Invalid metadata identifier')
    return value

@dataclass(frozen=True)
class SyncLease:
    scope: str
    operation_id: str
    account_namespace: str
    generation: int
    token: str
    selector_fingerprint: str
    mailbox: str
    checkpoint: str | None
    revision: int
    expires_at: float
    mode: str = 'incremental'
    trigger: str = 'manual'

class GmailBridgeStore:
    def __init__(self, crm, *, clock=time.time):
        self.crm, self.clock = crm, clock
        self.profile = crm.profile
        self.workspace = crm.existing_workspace_token()
        self._schema_validated = False

    def _scope(self, conn, write=False):
        if self.crm.profile != self.profile:
            raise CRMError('Profile changed', 409)
        token = conn.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar()
        if self.workspace is not None and token != self.workspace:
            raise CRMError('Workspace changed', 409)
        if token is None and write:
            token = str(uuid.uuid4())
            conn.execute(settings.insert().values(key='workspace_id', value=token))
        if token is not None and not write:
            self.workspace = token
        return _hash([token, self.profile]) if token else None

    def _load(self, conn, scope):
        row = conn.execute(select(state.c.payload).where(state.c.scope == scope)).scalar()
        return json.loads(row) if row else _empty()

    def _write(self, key, payload, action, check_guard=None, *, control=False, pending=None):
        if not isinstance(key, str) or not key.strip() or len(key) > 160:
            raise CRMError('Invalid operation key')
        digest = _hash(payload)
        with transaction(self.crm) as conn:
            self.crm._catalog_lock(conn)
            scope = self._scope(conn, True)
            check_schema(self.crm, conn, True)
            old = None
            for table in (receipts, control_receipts):
                old = conn.execute(select(table).where(table.c.scope == scope, table.c.key == key)).mappings().first()
                if old:
                    break
            if old:
                if old['digest'] != digest:
                    raise CRMError('Operation key conflicts', 409)
                prior = json.loads(old['response'])
                if not pending or not prior.get('verification') or prior.get('status') != 'running':
                    return prior
                if pending == 'complete' and prior['expires_at'] <= self.clock():
                    raise CRMError('Verification outcome is unknown; use a new operation key', 409)
            elif pending:
                raise CRMError('Verification reservation is required', 409)
            data = self._load(conn, scope)
            if not old and type(_request_revision(payload)) is int and _request_revision(payload) < data['receipt_revision_floor']:
                raise CRMError('Operation receipt expired; request revision is stale', 409)
            if not control and not old:
                count = conn.execute(select(func.count()).select_from(receipts).where(receipts.c.scope == scope)).scalar_one()
                # An admitted sync always retains its terminal-receipt slot.
                reserve = 1 if payload[0] == 'begin' or (data['lease'] and payload[0] != 'finish') else 0
                if count >= MAX_RECEIPTS - reserve:
                    target = max(1, MAX_RECEIPTS // 2)
                    candidates = conn.execute(select(receipts.c.key, receipts.c.revision).where(
                        receipts.c.scope == scope, receipts.c.protected == 0).order_by(receipts.c.revision, receipts.c.key)
                        .limit(max(target, count - MAX_RECEIPTS + reserve + 1))).mappings().all()
                    if candidates:
                        conn.execute(delete(receipts).where(receipts.c.scope == scope, receipts.c.key.in_([r['key'] for r in candidates])))
                        data['receipt_revision_floor'] = max(data['receipt_revision_floor'], max(r['revision'] for r in candidates))
                        count -= len(candidates)
                    if count >= MAX_RECEIPTS - reserve:
                        raise CRMError('Protected operation capacity reached; local fencing controls remain available', 409)
            response = action(conn, scope, data)
            exists = conn.execute(select(state.c.scope).where(state.c.scope == scope)).scalar()
            if exists:
                conn.execute(update(state).where(state.c.scope == scope).values(payload=_json(data)))
            else:
                conn.execute(state.insert().values(scope=scope, payload=_json(data)))
            table = control_receipts if control else receipts
            values = dict(scope=scope, key=key, digest=digest, response=_json(response), revision=data['revision'])
            if not control:
                values['protected'] = int(_protected(response))
            if old:
                conn.execute(update(table).where(table.c.scope == scope, table.c.key == key).values(response=_json(response), revision=data['revision'], protected=int(_protected(response))))
            else:
                conn.execute(table.insert().values(**values))
            if control:
                expired = conn.execute(select(control_receipts.c.key).where(control_receipts.c.scope == scope)
                                       .order_by(control_receipts.c.revision.desc()).offset(MAX_CONTROL_RECEIPTS)).scalars().all()
                if expired:
                    conn.execute(delete(control_receipts).where(control_receipts.c.scope == scope, control_receipts.c.key.in_(expired)))
            if check_guard is not None:
                try:
                    valid = check_guard() is True
                except Exception:
                    valid = False
                if not valid:
                    raise CRMError('Sync cancelled or connection changed', 409)
            if self._scope(conn, True) != scope:
                raise CRMError('Workspace changed', 409)
            if pending == 'complete' and old and prior['expires_at'] <= self.clock():
                raise CRMError('Verification outcome is unknown; use a new operation key', 409)
        self.workspace = self.crm.existing_workspace_token()
        self._schema_validated = True
        return response

    @staticmethod
    def _revision(data, expected):
        if type(expected) is not int or expected != data['revision']:
            raise CRMError('Stale bridge revision', 409)

    def status(self):
        with self.crm._read_connection() as conn:
            scope = self._scope(conn)
            available = check_schema(self.crm, conn)
            data = self._load(conn, scope) if available else _empty()
            selected = data['accounts'].get(data['selected'])
            lease = data['lease']
            used_receipts = (conn.execute(select(func.count()).select_from(receipts).where(receipts.c.scope == scope)).scalar_one() if available else 0)
            protected_receipts = (conn.execute(select(func.count()).select_from(receipts).where(receipts.c.scope == scope, receipts.c.protected == 1)).scalar_one() if available else 0)
            return dict(revision=data['revision'], enabled=data['enabled'], polling_enabled=data['polling_enabled'],
                        control_receipt_retention=f'Latest {MAX_CONTROL_RECEIPTS} local controls; older retries return a stale-revision conflict.',
                        sync_capacity_reached=protected_receipts >= MAX_RECEIPTS - 1,
                        receipt_revision_floor=data['receipt_revision_floor'],
                        operation_receipt_retention=f'At most {MAX_RECEIPTS} ordinary receipts; oldest terminal receipts expire automatically. Unknown and active operations remain protected.',
                        polling_blocked_reason=('resync_required' if selected and selected.get('requires_resync') else
                                               'protected_operation_capacity' if protected_receipts >= MAX_RECEIPTS - 1 else None),
                        requires_resync=bool(selected and selected.get('requires_resync')),
                        own_aliases=selected['own_aliases'] if selected else [],
                        operation_receipts_remaining=max(0, MAX_RECEIPTS - used_receipts),
                        oldest_control_revision=(conn.execute(select(func.min(control_receipts.c.revision)).where(control_receipts.c.scope == scope)).scalar() if available else None),
                        account_namespace=data['selected'], mailbox=selected['mailbox'] if selected else None,
                        checkpoint=selected['checkpoint'] if selected else None,
                        lease_state=('expired_unknown' if lease['expires_at'] <= self.clock() else 'running') if lease else None,
                        retained_messages=(conn.execute(select(func.count()).select_from(messages).where(messages.c.scope == scope)).scalar_one() if selected or data['accounts'] else 0))

    def bind_verified(self, key, *, selector_fingerprint, mailbox, own_aliases=(), expected_revision, initial_checkpoint=None, check_guard=None, _reserved=False):
        if not isinstance(selector_fingerprint, str) or not re.fullmatch('[0-9a-f]{64}', selector_fingerprint):
            raise CRMError('A nonsecret selector fingerprint is required')
        if initial_checkpoint is not None and (not isinstance(initial_checkpoint, str) or not re.fullmatch(r'[1-9][0-9]{0,39}', initial_checkpoint)):
            raise CRMError('Invalid initial checkpoint')
        mailbox = normalize_mailbox(mailbox)
        own_aliases = self._aliases(own_aliases)
        def action(conn, scope, data):
            self._revision(data, expected_revision)
            current = data['accounts'].get(data['selected'])
            identity = dict(selector_fingerprint=selector_fingerprint, mailbox=mailbox, own_aliases=own_aliases)
            if current and any(current[k] != v for k, v in identity.items()):
                raise CRMError('Disconnect before selecting a different account identity', 409)
            if current is not None and initial_checkpoint is not None:
                raise CRMError('Initial checkpoint is only allowed for a new verified binding', 409)
            if current is None:
                if len(data['accounts']) >= 20:
                    raise CRMError('Local account capacity reached', 409)
                namespace = str(uuid.uuid4())
                data['accounts'][namespace] = dict(identity, checkpoint=initial_checkpoint, requires_resync=False)
                data['selected'] = namespace
            data['enabled'] = True
            data['polling_enabled'] = False
            data['revision'] += 1
            return dict(revision=data['revision'], account_namespace=data['selected'])
        return self._write(key, ['bind', selector_fingerprint, mailbox, own_aliases, expected_revision], action, check_guard, pending='complete' if _reserved else None)

    def reserve_verify(self, key, *, selector_fingerprint, mailbox, own_aliases=(), expected_revision):
        """Durably claim one verification dispatch. Replays never claim it again."""
        if not isinstance(selector_fingerprint, str) or not re.fullmatch('[0-9a-f]{64}', selector_fingerprint):
            raise CRMError('A nonsecret selector fingerprint is required')
        mailbox, own_aliases = normalize_mailbox(mailbox), self._aliases(own_aliases)
        newly_reserved = False
        def action(conn, scope, data):
            nonlocal newly_reserved
            self._revision(data, expected_revision)
            account = data['accounts'].get(data['selected'])
            if account and (account['selector_fingerprint'] != selector_fingerprint or
                            account['mailbox'] != mailbox or account['own_aliases'] != own_aliases):
                raise CRMError('Disconnect before selecting a different account identity', 409)
            newly_reserved = True
            return dict(status='running', verification=True, expires_at=self.clock() + 120)
        self._write(key, ['bind', selector_fingerprint, mailbox, own_aliases, expected_revision], action)
        return newly_reserved

    def complete_verify(self, key, *, selector_fingerprint, mailbox, own_aliases=(), expected_revision,
                        initial_checkpoint=None, check_guard=None):
        return self.bind_verified(key, selector_fingerprint=selector_fingerprint, mailbox=mailbox,
                                  own_aliases=own_aliases, expected_revision=expected_revision,
                                  initial_checkpoint=initial_checkpoint, check_guard=check_guard, _reserved=True)

    def fail_verify(self, key, *, selector_fingerprint, mailbox, own_aliases=(), expected_revision):
        payload = ['bind', selector_fingerprint, normalize_mailbox(mailbox), self._aliases(own_aliases), expected_revision]
        return self._write(key, payload, lambda conn, scope, data: dict(status='unknown', verification=True), pending='failure')

    def bind_receipt(self, key, *, selector_fingerprint, mailbox, own_aliases=(), expected_revision):
        """Preflight normalized bind intent before redispatching mailbox verification.

        The fresh trusted getProfile cursor is an outcome of verification, not a
        user request field, so it deliberately does not change the request digest.
        """
        digest = _hash(['bind', selector_fingerprint, normalize_mailbox(mailbox),
                        self._aliases(own_aliases), expected_revision])
        with self.crm._read_connection() as conn:
            scope = self._scope(conn)
            if not check_schema(self.crm, conn):
                return None
            row = conn.execute(select(receipts).where(receipts.c.scope == scope, receipts.c.key == key)).mappings().first()
            if row is None:
                return None
            if row['digest'] != digest:
                raise CRMError('Operation key conflicts', 409)
            result = json.loads(row['response'])
            if result.get('verification') and result.get('status') == 'running' and result['expires_at'] <= self.clock():
                result['status'] = 'unknown'
            return result

    @staticmethod
    def _aliases(values):
        if not isinstance(values, (tuple, list)) or len(values) > 20:
            raise CRMError('At most twenty explicit aliases are allowed')
        return sorted(set(normalize_mailbox(v) for v in values))

    def set_contact_aliases(self, key, *, contact_id, contact_version, aliases, expected_revision):
        aliases = self._aliases(aliases)
        def action(conn, scope, data):
            self._revision(data, expected_revision)
            row = conn.execute(select(contacts).where(contacts.c.id == contact_id)).mappings().first()
            if row is None or type(contact_version) is not int or row['version'] != contact_version:
                raise CRMError('Contact missing or changed', 409)
            existing = conn.execute(select(aliases_table.c.contact_id).where(aliases_table.c.scope == scope, aliases_table.c.contact_id == contact_id)).scalar()
            if not existing and conn.execute(select(func.count()).select_from(aliases_table).where(aliases_table.c.scope == scope)).scalar_one() >= 10000:
                raise CRMError('Alias catalog capacity reached', 409)
            values = dict(contact_version=contact_version, addresses=_json(aliases))
            if existing:
                conn.execute(update(aliases_table).where(aliases_table.c.scope == scope, aliases_table.c.contact_id == contact_id).values(**values))
            else:
                conn.execute(aliases_table.insert().values(scope=scope, contact_id=contact_id, **values))
            data['revision'] += 1
            return dict(revision=data['revision'])
        return self._write(key, ['aliases', contact_id, contact_version, aliases, expected_revision], action)

    def control(self, key, *, action, expected_revision):
        """pause/resume preserve namespace; disconnect fences; clear erases metadata.

        Clear keeps the selected identity and retained receipts, resets evidence/cursors,
        and removes unselected namespaces. Older terminal receipts expire visibly.
        Disconnect never revokes the host's grant. New bind gets a new namespace.
        """
        if action not in ('pause', 'resume', 'disconnect', 'clear', 'start_polling', 'stop_polling'):
            raise CRMError('Invalid bridge control')
        def apply(conn, scope, data):
            self._revision(data, expected_revision)
            if data['lease']:
                self._outcome(conn, scope, data['lease']['operation_id'], dict(status='cancelled', reason='local_control'))
                data['lease'] = None
            if action in ('pause', 'disconnect', 'clear'):
                # Explicit local fencing reconciles uncertain read-only work.
                # No provider action is retried, revoked or undone.
                for row in conn.execute(select(receipts).where(receipts.c.scope == scope, receipts.c.protected == 1)).mappings():
                    response = json.loads(row['response'])
                    if response.get('lease'):
                        response['outcome'] = dict(status='cancelled', reason='local_control')
                    else:
                        response['status'] = 'cancelled'
                        response['reason'] = 'local_control'
                    conn.execute(update(receipts).where(receipts.c.scope == scope, receipts.c.key == row['key'])
                                 .values(response=_json(response), protected=0, revision=data['revision'] + 1))
            if action == 'resume' and not data['selected']:
                raise CRMError('No selected connection', 409)
            if action == 'resume':
                data['enabled'] = True
            elif action in ('pause', 'disconnect'):
                data['enabled'] = False
                data['polling_enabled'] = False
            elif action == 'start_polling':
                if not data['enabled'] or not data['selected']:
                    raise CRMError('Gmail bridge is disabled', 409)
                data['polling_enabled'] = True
            elif action == 'stop_polling':
                data['polling_enabled'] = False
            if action == 'disconnect':
                data['selected'] = None
            if action == 'clear':
                conn.execute(delete(messages).where(messages.c.scope == scope))
                data['accounts'] = {data['selected']: data['accounts'][data['selected']]} if data['selected'] else {}
                for account in data['accounts'].values():
                    account['checkpoint'] = None
                    account['requires_resync'] = False
            data['revision'] += 1
            return dict(revision=data['revision'], enabled=data['enabled'])
        return self._write(key, ['control', action, expected_revision], apply, control=True)

    def _outcome(self, conn, scope, key, outcome):
        row = conn.execute(select(receipts.c.response).where(receipts.c.scope == scope, receipts.c.key == key)).scalar()
        if row:
            value = json.loads(row)
            value['outcome'] = outcome
            conn.execute(update(receipts).where(receipts.c.scope == scope, receipts.c.key == key).values(response=_json(value), protected=int(_protected(value))))

    def begin_sync_once(self, key, *, expected_revision, lease_seconds=120, mode='incremental', trigger='manual'):
        return self.begin_sync(key, expected_revision=expected_revision, lease_seconds=lease_seconds,
                               mode=mode, trigger=trigger, _new_only=True)

    def begin_sync(self, key, *, expected_revision, lease_seconds=120, mode='incremental', trigger='manual', _new_only=False):
        if trigger not in ('manual', 'poll'):
            raise CRMError('Invalid sync trigger')
        if mode not in ('incremental', '7days', '30days'):
            raise CRMError('Invalid sync mode')
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 300:
            raise CRMError('Invalid lease duration')
        newly_created = False
        def action(conn, scope, data):
            nonlocal newly_created
            newly_created = True
            self._revision(data, expected_revision)
            if not data['enabled'] or not data['selected']:
                raise CRMError('Gmail bridge is disabled', 409)
            if trigger == 'poll' and not data['polling_enabled']:
                raise CRMError('Gmail polling is disabled', 409)
            if data['lease']:
                if data['lease']['expires_at'] > self.clock():
                    raise CRMError('Sync already running', 409)
                self._outcome(conn, scope, data['lease']['operation_id'], dict(status='unknown', reason='lease_expired'))
            data['generation'] += 1
            data['revision'] += 1
            account = data['accounts'][data['selected']]
            if account.get('requires_resync') and mode == 'incremental':
                raise CRMError('Resync required; select an explicit bounded bootstrap', 409)
            lease = SyncLease(scope, key, data['selected'], data['generation'], str(uuid.uuid4()),
                              account['selector_fingerprint'], account['mailbox'], account['checkpoint'],
                              data['revision'], self.clock() + lease_seconds, mode, trigger)
            data['lease'] = asdict(lease)
            return dict(lease=asdict(lease), outcome=None)
        value = self._write(key, ['begin', expected_revision, lease_seconds, mode, trigger], action)
        return SyncLease(**value['lease']) if newly_created or not _new_only else None

    def validate_lease(self, lease):
        """Cheap read-only dispatch fence; not authentication or a grant refresh.

        Use before dispatch/polling. finish_sync already validates the lease under
        its transaction lock; its check_guard should check external configuration,
        not open another database transaction against this same store.
        """
        if not isinstance(lease, SyncLease):
            return False
        try:
            with self.crm._read_connection() as conn:
                scope = self._scope(conn)
                if not self._schema_validated:
                    if not check_schema(self.crm, conn):
                        return False
                    self._schema_validated = True
                data = self._load(conn, scope)
                account = data['accounts'].get(data['selected'])
                return bool(scope == lease.scope and data['enabled'] and
                            data['selected'] == lease.account_namespace and
                            data['revision'] == lease.revision and data['lease'] == asdict(lease) and
                            data['generation'] == lease.generation and self.clock() < lease.expires_at and
                            (lease.trigger != 'poll' or data['polling_enabled']) and
                            account and account['mailbox'] == lease.mailbox and
                            account['selector_fingerprint'] == lease.selector_fingerprint and
                            account['checkpoint'] == lease.checkpoint)
        except Exception:
            return False

    def _contacts(self, conn, scope):
        rows = conn.execute(select(contacts).order_by(contacts.c.id).limit(10001)).mappings().all()
        if len(rows) > 10000:
            raise CRMError('Contact matching capacity exceeded', 409)
        catalog = {r['contact_id']: r for r in conn.execute(select(aliases_table).where(aliases_table.c.scope == scope)).mappings()}
        result = []
        for row in rows:
            alias = catalog.get(row['id'], {})
            values = json.loads(alias['addresses']) if alias else []
            result.append(ContactIdentity(row['id'], row['email'], row['version'], tuple(values)))
        return result

    def finish_sync(self, lease, result, *, check_guard=lambda: True):
        return self._finish_sync(lease, result, check_guard=check_guard)

    def fail_sync(self, lease, *, unknown=False, check_guard=lambda: True):
        """Record sanitized terminal failure without provider errors or metadata."""
        if type(unknown) is not bool:
            raise CRMError('Invalid failure state')
        if not isinstance(lease, SyncLease):
            raise CRMError('Trusted sync lease required')
        coverage = 'bounded_bootstrap' if lease.mode in ('7days', '30days') else 'incremental_history'
        result = SyncResult('partial', None, (), coverage)
        return self._finish_sync(lease, result, check_guard=check_guard,
                                 failure_state='unknown' if unknown else 'failed')

    def _finish_sync(self, lease, result, *, check_guard, failure_state=None):
        """Trusted reader result only. The guard must verify current runtime binding."""
        if not isinstance(lease, SyncLease) or not isinstance(result, SyncResult):
            raise CRMError('Trusted sync result required')
        if (result.status not in ('complete', 'partial', 'requires_resync') or len(result.observations) > 10000 or
                result.coverage not in ('bounded_bootstrap', 'incremental_history')):
            raise CRMError('Invalid sync result')
        # Reasons and noncomplete metadata are deliberately not persisted or echoed.
        serialized = self._observations(result.observations) if result.status == 'complete' else []
        if result.status == 'complete' and (not isinstance(result.checkpoint, str) or not re.fullmatch(r'[1-9][0-9]{0,39}', result.checkpoint)):
            raise CRMError('Invalid checkpoint')
        payload = ['finish', asdict(lease), result.status, result.checkpoint, result.coverage, serialized, failure_state]
        def action(conn, scope, data):
            if (scope != lease.scope or data['lease'] != asdict(lease) or not data['enabled'] or
                    data['selected'] != lease.account_namespace or data['revision'] != lease.revision or
                    (failure_state is None and self.clock() >= lease.expires_at)):
                raise CRMError('Stale or disabled sync lease', 409)
            account = data['accounts'][lease.account_namespace]
            retained, unmatched = 0, 0
            if result.status == 'complete':
                if account['checkpoint'] and int(result.checkpoint) < int(account['checkpoint']):
                    raise CRMError('Checkpoint moved backwards', 409)
                identities = self._contacts(conn, scope)
                matcher = CompiledMatcher(identities, [account['mailbox'], *account['own_aliases']])
                for item in serialized:
                    where = (messages.c.scope == scope, messages.c.account_namespace == lease.account_namespace, messages.c.message_id == item['message_id'])
                    previous = conn.execute(select(messages.c.payload).where(*where)).scalar()
                    old = json.loads(previous) if previous else None
                    saved = None
                    if item['status'] == 'eligible':
                        matched = _match(item, matcher)
                        if any(p.matches for p in matched.participants):
                            item['historical_match'] = asdict(matched)
                            item['coverage'] = result.coverage
                            item['operation_id'] = lease.operation_id
                            item['observed_at'] = self.clock()
                            item['last_observation'] = dict(status='eligible', observed_at=self.clock(), operation_id=lease.operation_id)
                            saved = item
                            retained += 1
                        elif old:
                            old['last_observation'] = dict(status='eligible_unmatched', observed_at=self.clock(), operation_id=lease.operation_id)
                            saved = old
                        else:
                            unmatched += 1
                    elif old:
                        old['last_observation'] = dict(status=item['status'], observed_at=self.clock(), operation_id=lease.operation_id)
                        saved = old
                    if saved is not None:
                        if old:
                            conn.execute(update(messages).where(*where).values(payload=_json(saved)))
                        else:
                            conn.execute(messages.insert().values(scope=scope, account_namespace=lease.account_namespace, message_id=item['message_id'], payload=_json(saved)))
                if conn.execute(select(func.count()).select_from(messages).where(messages.c.scope == scope)).scalar_one() > MAX_MESSAGES:
                    raise CRMError('Local metadata capacity reached; clear explicitly', 409)
                account['checkpoint'] = result.checkpoint
                account['requires_resync'] = False
            elif result.status == 'requires_resync':
                account['requires_resync'] = True
            data['lease'] = None
            data['revision'] += 1
            outcome = dict(status=failure_state or result.status, coverage=result.coverage, retained=retained, unmatched=unmatched, revision=data['revision'])
            self._outcome(conn, scope, lease.operation_id, outcome)
            return outcome
        # Fixed-length key leaves user operation keys their full 160-char budget.
        def final_guard():
            return ((failure_state is not None or self.clock() < lease.expires_at) and
                    check_guard() is True and
                    (failure_state is not None or self.clock() < lease.expires_at))
        return self._write('finish:' + _hash(lease.operation_id), payload, action, final_guard)

    @staticmethod
    def _observations(observations):
        result, seen = [], set()
        for observation in observations:
            if not isinstance(observation, Observation):
                raise CRMError('Invalid observation')
            mid = _id(observation.message_id)
            if mid in seen:
                raise CRMError('Duplicate observation')
            seen.add(mid)
            if observation.status not in ('eligible', 'not_eligible', 'deleted', 'unavailable'):
                raise CRMError('Invalid observation state')
            allowed_issues = {prefix + role for prefix in ('unsafe_', 'duplicate_')
                              for role in ('from', 'to', 'cc', 'subject', 'date', 'message-id')}
            if (len(observation.header_issues) > 100 or
                    any(not isinstance(issue, str) or issue not in allowed_issues for issue in observation.header_issues)):
                raise CRMError('Invalid header issue')
            issues = sorted(set(observation.header_issues))
            suppressed = {role for role in ('from', 'to', 'cc', 'subject', 'date')
                          if any(prefix + role in issues for prefix in ('unsafe_', 'duplicate_'))}
            headers = []
            if len(observation.raw_headers) > 100:
                raise CRMError('Header capacity exceeded')
            for name, value in observation.raw_headers:
                if not isinstance(name, str):
                    raise CRMError('Invalid header')
                if name.lower() in ('from', 'to', 'cc', 'subject', 'date') and name.lower() not in suppressed:
                    if not isinstance(value, str) or len(value) > 4096 or any(unicodedata.category(c).startswith('C') for c in value):
                        raise CRMError('Unsafe metadata header')
                    headers.append((name.lower(), value))
            if len(observation.labels) > 100:
                raise CRMError('Invalid metadata labels')
            labels = sorted(set(_id(label) for label in observation.labels))
            history = observation.history_id
            if history and (not isinstance(history, str) or not re.fullmatch(r'[1-9][0-9]{0,39}', history)):
                raise CRMError('Invalid message history identifier')
            date = observation.internal_date_ms
            if date is not None and (type(date) is not int or not 0 <= date <= 253402300799000):
                raise CRMError('Invalid metadata date')
            result.append(dict(message_id=mid, thread_id=_id(observation.thread_id) if observation.thread_id else '',
                               internal_date_ms=date, history_id=history, labels=labels, raw_headers=headers, header_issues=issues, status=observation.status,
                               observed_in_sent=observation.observed_in_sent is True))
        return result

    def operation_receipt(self, key):
        with self.crm._read_connection() as conn:
            scope = self._scope(conn)
            if not check_schema(self.crm, conn):
                return None
            for table in (receipts, control_receipts):
                value = conn.execute(select(table.c.response).where(table.c.scope == scope, table.c.key == key)).scalar()
                if value:
                    result = json.loads(value)
                    if result.get('verification') and result.get('status') == 'running' and result['expires_at'] <= self.clock():
                        result['status'] = 'unknown'
                    if result.get('lease') and result.get('outcome') is None and result['lease']['expires_at'] <= self.clock():
                        result['outcome'] = dict(status='unknown', reason='lease_expired')
                    return result
            data = self._load(conn, scope)
            if data['receipt_revision_floor']:
                return dict(status='expired_or_unknown', receipt_revision_floor=data['receipt_revision_floor'])
            return None

    def page(self, *, contact_id=None, company_id=None, unresolved=False, limit=25, offset=0):
        if contact_id is not None and company_id is not None:
            raise CRMError('Choose either Contact or Company history')
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= MAX_MESSAGES:
            raise CRMError('Invalid page bounds')
        with self.crm._read_connection() as conn:
            scope = self._scope(conn)
            company_contacts = None
            if company_id is not None:
                from .relationship_schema import companies, contact_companies, check_schema as relationship_schema
                from .report_store import scope_for
                if not relationship_schema(self.crm, conn):
                    raise CRMError('Company not found', 404)
                relationship_scope = scope_for(self.crm, connection=conn)
                if not conn.execute(select(companies.c.id).where(companies.c.scope == relationship_scope,
                                                                companies.c.id == company_id)).scalar():
                    raise CRMError('Company not found', 404)
                company_contacts = set(conn.execute(select(contact_companies.c.contact_id)
                    .join(contacts, contacts.c.id == contact_companies.c.contact_id)
                    .where(contact_companies.c.scope == relationship_scope,
                           contact_companies.c.company_id == company_id)).scalars())
            available = check_schema(self.crm, conn)
            contact = (conn.execute(select(contacts.c.version).where(contacts.c.id == contact_id)).scalar()
                       if contact_id is not None else None)
            alias = (conn.execute(select(aliases_table).where(aliases_table.c.scope == scope,
                       aliases_table.c.contact_id == contact_id)).mappings().first()
                     if available and contact_id is not None else None)
            identity = dict(company_id=company_id,
                            association_basis='current_explicit_company_contacts' if company_id else 'exact_contact_address',
                            contact_version=contact,
                            explicit_aliases=json.loads(alias['addresses']) if alias and contact else [],
                            alias_record_version=alias['contact_version'] if alias else None)
            if not available:
                return dict(items=[], total=0, **identity)
            data = self._load(conn, scope)
            identities = self._contacts(conn, scope)
            matchers = {namespace: CompiledMatcher(identities, [account['mailbox'], *account['own_aliases']])
                        for namespace, account in data['accounts'].items()}
            items = []
            for row in conn.execute(select(messages).where(messages.c.scope == scope)).mappings():
                namespace = row['account_namespace']
                item = json.loads(row['payload'])
                current = asdict(_match(item, matchers[namespace]))
                historical = item['historical_match']
                # Compare canonical JSON because stored tuples round-trip as lists.
                review = _json(_semantics(current)) != _json(_semantics(historical)) or bool(item.get('header_issues'))
                linked = {m['contact_id'] for m in current['matches']}
                previous = {m['contact_id'] for m in historical['matches']}
                ambiguous = any(p['status'] in ('ambiguous', 'case_mismatch') for p in current['participants'])
                if contact_id is not None and contact_id not in linked | previous:
                    continue
                if company_contacts is not None and not (linked | previous) & company_contacts:
                    continue
                if unresolved and not (review or ambiguous):
                    continue
                items.append(dict(item, account_namespace=namespace, current_match=current,
                                  needs_review=review, source='gmail_metadata', match_basis='exact_visible_address',
                                  currently_linked=(contact_id in linked if contact_id else bool(linked & company_contacts)
                                                    if company_contacts is not None else bool(linked))))
            items.sort(key=lambda i: (-(i['internal_date_ms'] or 0), i['account_namespace'], i['message_id']))
            return dict(items=items[offset:offset + limit], total=len(items), **identity)
