"""Local synthetic contract; no Gmail, account grants or credentials."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import pytest
from sqlalchemy import inspect, text, update, event, select
from hermes_crm.domain import CRM, CRMError, contacts
from hermes_crm.gmail_bridge_store import GmailBridgeStore
from hermes_crm.gmail_bridge_schema import state, version, messages
from hermes_crm.gmail_incremental import Observation, SyncResult

@pytest.fixture
def setup(tmp_path):
    crm = CRM('sqlite:///' + str(tmp_path / 'bridge.db'), profile='synthetic')
    contact = crm.create('contacts', {'name': 'Contact', 'email': 'contact@example.test'})
    store = GmailBridgeStore(crm)
    yield crm, store, contact
    crm.close()

def bind(store, key='bind', **kwargs):
    return store.bind_verified(key, selector_fingerprint=kwargs.pop('selector_fingerprint', 'a' * 64),
                               mailbox=kwargs.pop('mailbox', 'own@example.test'),
                               expected_revision=store.status()['revision'], **kwargs)

def begin(store, key='sync', **kwargs):
    return store.begin_sync(key, expected_revision=store.status()['revision'], **kwargs)

def result(checkpoint='100', mid='m1', target='contact@example.test', status='eligible'):
    return SyncResult('complete', checkpoint, (Observation(mid, 't1', 1000, '10', (),
                      (('From', 'own@example.test'), ('To', target), ('Bcc', 'secret@example.test'),
                       ('Subject', 'not retained')), status=status, observed_in_sent=True),), 'bounded_bootstrap')

def publish(store, key='sync', **kwargs):
    return store.finish_sync(begin(store, key), result(**kwargs))

def test_lazy_status(setup):
    crm, store, _ = setup
    before = inspect(crm.engine).get_table_names()
    assert not store.status()['enabled']
    assert store.page()['items'] == []
    assert inspect(crm.engine).get_table_names() == before
    assert not any(name.startswith('crm_gmail_bridge') for name in before)

def test_bind_resume_identity_and_no_silent_rebind(setup):
    _, store, _ = setup
    first = bind(store)
    with pytest.raises(CRMError, match='Disconnect'):
        bind(store, 'other', mailbox='different@example.test')
    store.control('pause', action='pause', expected_revision=1)
    assert not store.status()['enabled']
    store.control('resume', action='resume', expected_revision=2)
    assert store.status()['account_namespace'] == first['account_namespace']
    assert store.bind_verified('bind', selector_fingerprint='a' * 64, mailbox='own@example.test', expected_revision=0) == first  # immutable bind receipt, no second mutation
    with pytest.raises(CRMError, match='conflicts'):
        store.bind_verified('bind', selector_fingerprint='b' * 64, mailbox='own@example.test', expected_revision=0)

def test_metadata_dedupe_and_receipt(setup):
    crm, store, contact = setup
    bind(store)
    lease = begin(store)
    outcome = store.finish_sync(lease, result())
    assert store.finish_sync(lease, result()) == outcome
    publish(store, 'next', checkpoint='101')
    page = store.page(contact_id=contact['id'])
    assert page['total'] == 1
    assert page['items'][0]['currently_linked']
    assert page['items'][0]['current_match']['direction'] == 'outbound_observed'
    assert store.operation_receipt('sync')['outcome']['status'] == 'complete'
    with crm.engine.connect() as conn:
        payload = conn.execute(select(messages.c.payload)).scalar_one()
    assert 'secret@example.test' not in payload
    assert 'not retained' in payload  # Bounded subject is retained, unlike Bcc.
    assert 'delivery' not in payload

@pytest.mark.parametrize('status', ['partial', 'requires_resync'])
def test_noncomplete_never_advances_or_retains_errors(setup, status):
    _, store, _ = setup
    bind(store); publish(store)
    lease = begin(store, 'next')
    value = SyncResult(status, None, result(mid='m2').observations, 'incremental_history', ('PRIVATE RAW ERROR',))
    assert store.finish_sync(lease, value)['status'] == status
    assert store.status()['checkpoint'] == '100'
    assert store.page()['total'] == 1
    assert 'PRIVATE' not in json.dumps(store.operation_receipt('next'))

def test_profile_change_fences(setup):
    crm, store, _ = setup
    bind(store); lease = begin(store)
    crm.profile = 'other'
    with pytest.raises(CRMError, match='Profile'):
        store.finish_sync(lease, result())
    assert not GmailBridgeStore(crm).status()['enabled']
    crm.profile = 'synthetic'
    assert store.status()['checkpoint'] is None

def test_cross_profile_lease_rejected(setup):
    crm, store, _ = setup
    bind(store); lease = begin(store)
    crm.profile = 'other'
    other = GmailBridgeStore(crm)
    bind(other); begin(other, 'other-sync')
    with pytest.raises(CRMError, match='Stale'):
        other.finish_sync(lease, result())

def test_expired_lease_recovery_visible_unknown(setup):
    crm, _, _ = setup
    clock = [1000.0]
    store = GmailBridgeStore(crm, clock=lambda: clock[0])
    bind(store); lease = begin(store, lease_seconds=1)
    clock[0] += 2
    assert store.status()['lease_state'] == 'expired_unknown'
    replacement = begin(store, 'replacement')
    assert replacement.generation == lease.generation + 1
    assert store.operation_receipt('sync')['outcome']['status'] == 'unknown'
    with pytest.raises(CRMError, match='Stale'):
        store.finish_sync(lease, result())
    store.finish_sync(replacement, result())

def test_concurrent_begin_and_publish(setup):
    _, store, _ = setup
    bind(store)
    def attempt(key):
        try:
            return begin(store, key)
        except CRMError:
            return None
    with ThreadPoolExecutor(2) as pool:
        leases = list(pool.map(attempt, ['a', 'b']))
    assert sum(lease is not None for lease in leases) == 1
    lease = next(lease for lease in leases if lease)
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda _: store.finish_sync(lease, result()), range(2)))
    assert outcomes[0] == outcomes[1] and store.page()['total'] == 1

def test_cancel_guard_rolls_back(setup):
    _, store, _ = setup
    bind(store); lease = begin(store)
    with pytest.raises(CRMError, match='cancelled'):
        store.finish_sync(lease, result(), check_guard=lambda: False)
    assert store.status()['checkpoint'] is None and store.page()['total'] == 0
    store.finish_sync(lease, result())

def test_pause_disconnect_fence_and_account_namespace(setup):
    _, store, _ = setup
    first = bind(store); publish(store)
    lease = begin(store, 'late')
    store.control('disconnect', action='disconnect', expected_revision=store.status()['revision'])
    second = bind(store, 'bind2', mailbox='new@example.test', selector_fingerprint='b' * 64)
    with pytest.raises(CRMError, match='Stale'):
        store.finish_sync(lease, result())
    publish(store, 'new-sync')
    assert first['account_namespace'] != second['account_namespace']
    assert store.page()['total'] == 2

def test_multicontact_and_ambiguity(setup):
    crm, store, contact = setup
    second = crm.create('contacts', {'name': 'Second', 'email': 'second@example.test'})
    duplicate = crm.create('contacts', {'name': 'Duplicate', 'email': 'contact@example.test'})
    bind(store); publish(store, target='contact@example.test, second@example.test')
    row = store.page(unresolved=True)['items'][0]
    assert row['current_match']['matches'][0]['contact_id'] == second['id']
    ambiguous = next(p for p in row['current_match']['participants'] if p['status'] == 'ambiguous')
    assert {m['contact_id'] for m in ambiguous['matches']} == {contact['id'], duplicate['id']}
    assert store.page(contact_id=contact['id'])['total'] == 0
    assert store.page(contact_id=second['id'])['total'] == 1

def test_contact_change_and_alias_removal_recompute(setup):
    crm, store, contact = setup
    bind(store)
    store.set_contact_aliases('aliases', contact_id=contact['id'], contact_version=1,
                              aliases=['alias@example.test'], expected_revision=1)
    publish(store, target='alias@example.test')
    store.set_contact_aliases('remove', contact_id=contact['id'], contact_version=1,
                              aliases=[], expected_revision=store.status()['revision'])
    row = store.page(contact_id=contact['id'])['items'][0]
    assert row['needs_review'] and not row['currently_linked']
    assert store.page(unresolved=True)['total'] == 1
    with crm.engine.begin() as conn:
        conn.execute(update(contacts).where(contacts.c.id == contact['id']).values(email='new@example.test', version=2))
    with pytest.raises(CRMError, match='changed'):
        store.set_contact_aliases('stale', contact_id=contact['id'], contact_version=1,
                                  aliases=['alias@example.test'], expected_revision=store.status()['revision'])

def test_changed_contact_alias_version_and_missing_contact(setup):
    crm, store, contact = setup
    bind(store)
    store.set_contact_aliases('aliases', contact_id=contact['id'], contact_version=1,
                              aliases=['alias@example.test'], expected_revision=1)
    publish(store, target='alias@example.test')
    with crm.engine.begin() as conn:
        conn.execute(update(contacts).where(contacts.c.id == contact['id']).values(version=2))
    assert not store.page(contact_id=contact['id'])['items'][0]['needs_review']
    with crm.engine.begin() as conn:
        conn.execute(contacts.delete().where(contacts.c.id == contact['id']))
    assert not store.page(contact_id=contact['id'])['items'][0]['currently_linked']

@pytest.mark.parametrize('status', ['deleted', 'not_eligible', 'unavailable'])
def test_observed_absence_preserves_history(setup, status):
    _, store, contact = setup
    bind(store); publish(store)
    publish(store, 'changed', checkpoint='101', status=status)
    row = store.page(contact_id=contact['id'])['items'][0]
    assert row['last_observation']['status'] == status
    assert row['historical_match']['matches']

def test_unmatched_counts_only_and_clear(setup):
    _, store, _ = setup
    bind(store)
    assert publish(store, target='unmatched@example.test')['unmatched'] == 1
    assert store.page()['total'] == 0
    publish(store, 'matched')
    revision = store.status()['revision']
    cleared = store.control('clear', action='clear', expected_revision=revision)
    assert store.control('clear', action='clear', expected_revision=revision) == cleared
    assert store.page()['total'] == 0 and store.status()['checkpoint'] is None

def test_schema_rejects_newer_and_extra_columns(setup):
    crm, store, _ = setup
    bind(store)
    with crm.engine.begin() as conn:
        conn.execute(update(version).values(version=2))
    with pytest.raises(CRMError, match='Unsupported'):
        store.status()

def test_write_rollback(setup):
    crm, store, _ = setup
    bind(store); lease = begin(store)
    def fail(connection, cursor, statement, parameters, context, many):
        compiled = getattr(context, 'compiled', None)
        stmt = getattr(compiled, 'statement', None)
        if getattr(stmt, 'is_update', False) and getattr(stmt, 'table', None) is state:
            raise RuntimeError('synthetic write failure')
    event.listen(crm.engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError):
            store.finish_sync(lease, result())
    finally:
        event.remove(crm.engine, 'before_cursor_execute', fail)
    assert store.status()['checkpoint'] is None
    assert store.page()['total'] == 0
    store.finish_sync(lease, result())

def test_capacity_failure_and_stale_revision(setup, monkeypatch):
    import hermes_crm.gmail_bridge_store as module
    _, store, _ = setup
    bind(store)
    with pytest.raises(CRMError, match='Stale'):
        store.control('bad', action='pause', expected_revision=0)
    monkeypatch.setattr(module, 'MAX_MESSAGES', 0)
    lease = begin(store)
    with pytest.raises(CRMError, match='capacity'):
        store.finish_sync(lease, result())
    assert store.status()['checkpoint'] is None

def test_partial_schema_rejected(setup):
    crm, store, _ = setup
    with crm.engine.begin() as conn:
        state.create(conn)
    with pytest.raises(CRMError, match='Incomplete'):
        store.status()

@pytest.mark.parametrize('issue', ['unsafe_to', 'duplicate_to'])
def test_unsafe_role_never_automatches_even_if_reader_kept_value(setup, issue):
    crm, store, contact = setup
    second = crm.create('contacts', {'name': 'Second', 'email': 'second@example.test'})
    bind(store)
    observed = replace(result().observations[0], header_issues=(issue,),
                       raw_headers=(('From', 'own@example.test'), ('To', 'contact@example.test'), ('Cc', 'second@example.test')))
    store.finish_sync(begin(store), SyncResult('complete', '100', (observed,), 'bounded_bootstrap'))
    assert store.page(contact_id=contact['id'])['total'] == 0
    row = store.page(contact_id=second['id'])['items'][0]
    assert row['header_issues'] == [issue]
    assert row['current_match']['direction'] == 'unknown' and row['needs_review']

def test_filter_before_pagination_beyond_thousand(setup):
    crm, store, contact = setup
    other = crm.create('contacts', {'name': 'Other', 'email': 'other@example.test'})
    bind(store)
    observations = tuple(replace(result(mid='m' + str(i), target='other@example.test').observations[0],
                                 internal_date_ms=2000+i) for i in range(1005))
    observations += (result(mid='target').observations[0],)
    store.finish_sync(begin(store), SyncResult('complete', '100', observations, 'bounded_bootstrap'))
    page = store.page(contact_id=contact['id'], limit=1)
    assert page['total'] == 1 and page['items'][0]['message_id'] == 'target'
    with crm.engine.begin() as conn:
        conn.execute(update(contacts).where(contacts.c.id == contact['id']).values(email='changed@example.test', version=2))
    unresolved = store.page(unresolved=True, limit=1)
    assert unresolved['total'] == 1 and unresolved['items'][0]['message_id'] == 'target'

def test_own_alias_never_becomes_contact_link(setup):
    _, store, _ = setup
    bind(store, own_aliases=['contact@example.test'])
    assert publish(store)['unmatched'] == 1
    assert store.page()['total'] == 0

def test_normalized_incremental_does_not_rewrite_previous_messages(setup):
    from hermes_crm.gmail_bridge_schema import messages
    crm, store, _ = setup
    bind(store); publish(store)
    changes = []
    def observe(connection, cursor, statement, parameters, context, many):
        stmt = getattr(getattr(context, 'compiled', None), 'statement', None)
        if getattr(stmt, 'is_update', False) and getattr(stmt, 'table', None) is messages:
            changes.append(statement)
    event.listen(crm.engine, 'before_cursor_execute', observe)
    try:
        publish(store, 'second', mid='m2', checkpoint='101')
    finally:
        event.remove(crm.engine, 'before_cursor_execute', observe)
    assert changes == [] and store.page()['total'] == 2

def test_failed_initial_bind_does_not_poison_workspace_fence(setup):
    _, store, _ = setup
    with pytest.raises(CRMError, match='Stale'):
        store.bind_verified('bad', selector_fingerprint='a' * 64, mailbox='own@example.test', expected_revision=9)
    assert bind(store)['revision'] == 1

def test_guard_exception_never_exposes_private_error(setup):
    _, store, _ = setup
    bind(store); lease = begin(store)
    def fail():
        raise RuntimeError('PRIVATE PROVIDER RESPONSE')
    with pytest.raises(CRMError) as error:
        store.finish_sync(lease, result(), check_guard=fail)
    assert 'PRIVATE' not in str(error.value)
    assert store.status()['checkpoint'] is None

def test_subject_date_labels_and_history_preserved_safely(setup):
    _, store, _ = setup
    bind(store)
    observation = replace(result().observations[0], labels=('SENT', 'IMPORTANT'), history_id='123',
                          raw_headers=result().observations[0].raw_headers + (('Date', 'Fri, 01 Jan 2021 00:00:00 +0000'),))
    store.finish_sync(begin(store), SyncResult('complete', '123', (observation,), 'bounded_bootstrap'))
    row = store.page()['items'][0]
    assert row['labels'] == ['IMPORTANT', 'SENT'] and row['history_id'] == '123'
    assert ['subject', 'not retained'] in row['raw_headers']
    assert any(name == 'date' for name, value in row['raw_headers'])
    assert all(name != 'bcc' for name, value in row['raw_headers'])
    assert row['coverage'] == 'bounded_bootstrap'

def test_notes_edit_preserves_primary_matching_and_explicit_alias(setup):
    crm, store, contact = setup
    bind(store)
    store.set_contact_aliases('alias', contact_id=contact['id'], contact_version=1,
                              aliases=['alias@example.test'], expected_revision=1)
    publish(store)
    publish(store, 'alias-message', mid='m2', target='alias@example.test')
    with crm.engine.begin() as conn:
        conn.execute(update(contacts).where(contacts.c.id == contact['id']).values(notes='Notes edit', version=2))
    rows = store.page(contact_id=contact['id'])['items']
    assert len(rows) == 2 and all(row['currently_linked'] and not row['needs_review'] for row in rows)
    with crm.engine.begin() as conn:
        conn.execute(update(contacts).where(contacts.c.id == contact['id']).values(email='new@example.test', version=3))
    rows = {row['message_id']: row for row in store.page(contact_id=contact['id'])['items']}
    assert rows['m1']['needs_review'] and not rows['m1']['currently_linked']
    assert not rows['m2']['needs_review'] and rows['m2']['currently_linked']
    store.set_contact_aliases('remove-alias', contact_id=contact['id'], contact_version=3,
                              aliases=[], expected_revision=store.status()['revision'])
    assert all(not row['currently_linked'] for row in store.page(contact_id=contact['id'])['items'])

def test_validate_lease_is_cheap_and_fences_current_selection(setup, monkeypatch):
    import hermes_crm.gmail_bridge_store as module
    _, store, _ = setup
    bind(store); lease = begin(store)
    def should_not_reinspect(*args, **kwargs):
        raise AssertionError('Repeated schema inspection')
    with monkeypatch.context() as patch:
        patch.setattr(module, 'check_schema', should_not_reinspect)
        assert store.validate_lease(lease) and store.validate_lease(lease)
        assert not store.validate_lease(replace(lease, token='wrong'))
    store.control('pause', action='pause', expected_revision=store.status()['revision'])
    assert not store.validate_lease(lease)

def test_verified_initial_checkpoint_new_messages_only(setup):
    _, store, _ = setup
    bind(store, initial_checkpoint='987')
    lease = begin(store)
    assert lease.checkpoint == '987' and store.validate_lease(lease)
    with pytest.raises(CRMError, match='only allowed'):
        bind(store, 'rebind', initial_checkpoint='1000')

def test_bind_preflight_digest_and_guard_rollback(setup):
    _, store, _ = setup
    request = dict(selector_fingerprint='a' * 64, mailbox='own@example.test', expected_revision=0)
    assert store.bind_receipt('bind', **request) is None
    with pytest.raises(CRMError, match='cancelled'):
        store.bind_verified('bind', **request, check_guard=lambda: False)
    assert not store.status()['enabled']
    bound = store.bind_verified('bind', **request, initial_checkpoint='321')
    assert store.bind_receipt('bind', **request) == bound
    with pytest.raises(CRMError, match='conflicts'):
        store.bind_receipt('bind', **dict(request, mailbox='other@example.test'))

def test_failure_receipt_and_mode_digest(setup):
    _, store, _ = setup
    bind(store); lease = begin(store, mode='7days')
    with pytest.raises(CRMError, match='conflicts'):
        begin(store, mode='30days')
    assert store.fail_sync(lease, unknown=True)['status'] == 'unknown'
    assert store.operation_receipt('sync')['outcome']['status'] == 'unknown'
    assert store.status()['checkpoint'] is None
    assert store.fail_sync(lease, unknown=True)['status'] == 'unknown'
    another = begin(store, 'failed')
    assert store.fail_sync(another)['status'] == 'failed'

def test_receipt_capacity_reserves_finish_and_keeps_controls(setup, monkeypatch):
    import hermes_crm.gmail_bridge_store as module
    _, store, _ = setup
    monkeypatch.setattr(module, 'MAX_RECEIPTS', 3)
    bind(store)  # One receipt; begin plus terminal receipt can still be admitted.
    lease = begin(store)
    intent = dict(selector_fingerprint='a' * 64, mailbox='own@example.test', expected_revision=lease.revision)
    assert store.reserve_verify('pending', **intent)  # Recycles terminal bind receipt.
    with pytest.raises(CRMError, match='capacity'):
        store.reserve_verify('overflow', **intent)
    store.finish_sync(lease, result())
    assert store.operation_receipt('sync')['outcome']['status'] == 'complete'
    for action in ('pause', 'disconnect', 'clear'):
        revision = store.status()['revision']
        expected = store.control(action, action=action, expected_revision=revision)
        assert store.control(action, action=action, expected_revision=revision) == expected
    assert store.page()['total'] == 0
    assert store.operation_receipt('sync')['outcome']['status'] == 'complete'

def test_control_receipts_expire_visibly_without_reexecution(setup, monkeypatch):
    import hermes_crm.gmail_bridge_store as module
    from hermes_crm.gmail_bridge_schema import control_receipts
    from sqlalchemy import func
    crm, store, _ = setup
    monkeypatch.setattr(module, 'MAX_CONTROL_RECEIPTS', 2)
    bind(store)
    for i in range(3):
        store.control('pause' + str(i), action='pause', expected_revision=store.status()['revision'])
    with crm.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(control_receipts)).scalar_one() == 2
    assert store.status()['oldest_control_revision'] == 3
    with pytest.raises(CRMError, match='Stale'):
        store.control('pause0', action='pause', expected_revision=1)
    assert store.status()['revision'] == 4

def test_polling_is_separate_explicit_control(setup):
    _, store, _ = setup
    bind(store)
    assert not store.status()['polling_enabled']
    with pytest.raises(CRMError, match='polling'):
        begin(store, trigger='poll')
    store.control('start', action='start_polling', expected_revision=1)
    lease = begin(store, trigger='poll')
    assert lease.trigger == 'poll' and store.validate_lease(lease)
    store.control('stop', action='stop_polling', expected_revision=lease.revision)
    assert not store.validate_lease(lease)
    assert store.status()['enabled'] and not store.status()['polling_enabled']

def test_expiry_during_publication_rolls_back(setup, monkeypatch):
    crm, _, _ = setup
    clock = [100.0]
    store = GmailBridgeStore(crm, clock=lambda: clock[0])
    bind(store); lease = begin(store, lease_seconds=1)
    original = store._contacts
    def slow(conn, scope):
        clock[0] = 102
        return original(conn, scope)
    monkeypatch.setattr(store, '_contacts', slow)
    with pytest.raises(CRMError, match='cancelled'):
        store.finish_sync(lease, result())
    assert store.status()['checkpoint'] is None and store.page()['total'] == 0

def test_single_dispatch_sync_and_verification_claims(setup):
    _, store, _ = setup
    intent = dict(selector_fingerprint='a' * 64, mailbox='own@example.test', expected_revision=0)
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda _: store.reserve_verify('verify', **intent), range(2)))
    assert sorted(outcomes) == [False, True]
    assert store.bind_receipt('verify', **intent)['status'] == 'running'
    store.complete_verify('verify', **intent, initial_checkpoint='100')
    assert not store.reserve_verify('verify', **intent)
    with ThreadPoolExecutor(2) as pool:
        leases = list(pool.map(lambda _: store.begin_sync_once('sync', expected_revision=1), range(2)))
    assert sum(lease is not None for lease in leases) == 1
    assert store.validate_lease(next(lease for lease in leases if lease))

def test_unknown_verification_never_redispatches_same_key(setup):
    _, store, _ = setup
    intent = dict(selector_fingerprint='a' * 64, mailbox='own@example.test', expected_revision=0)
    assert store.reserve_verify('verify', **intent)
    assert store.fail_verify('verify', **intent)['status'] == 'unknown'
    assert not store.reserve_verify('verify', **intent)
    assert store.complete_verify('verify', **intent, initial_checkpoint='100')['status'] == 'unknown'
    assert not store.status()['enabled']
    assert store.reserve_verify('retry', **intent)
    store.complete_verify('retry', **intent, initial_checkpoint='100')
    assert store.status()['enabled']

def test_verification_expiry_during_final_guard_is_unknown(setup):
    crm, _, _ = setup
    clock = [100.0]
    store = GmailBridgeStore(crm, clock=lambda: clock[0])
    intent = dict(selector_fingerprint='a' * 64, mailbox='own@example.test', expected_revision=0)
    store.reserve_verify('verify', **intent)
    def guard():
        clock[0] = 221
        return True
    with pytest.raises(CRMError, match='unknown'):
        store.complete_verify('verify', **intent, initial_checkpoint='100', check_guard=guard)
    assert not store.status()['enabled']
    assert store.operation_receipt('verify')['status'] == 'unknown'

def test_clear_recovers_account_capacity(setup):
    _, store, _ = setup
    for index in range(20):
        bind(store, 'bind' + str(index))
        store.control('disconnect' + str(index), action='disconnect', expected_revision=store.status()['revision'])
    with pytest.raises(CRMError, match='account capacity'):
        bind(store, 'full')
    store.control('clear', action='clear', expected_revision=store.status()['revision'])
    assert bind(store, 'fresh')['account_namespace']

def test_resync_status_survives_reload_and_requires_explicit_bootstrap(setup):
    crm, store, _ = setup
    bind(store, initial_checkpoint='100')
    store.finish_sync(begin(store), SyncResult('requires_resync', None, (), 'incremental_history', ('stale_cursor',)))
    reloaded = GmailBridgeStore(crm)
    assert reloaded.status()['requires_resync']
    assert reloaded.status()['polling_blocked_reason'] == 'resync_required'
    with pytest.raises(CRMError, match='Resync'):
        begin(reloaded, 'automatic')
    lease = begin(reloaded, 'explicit', mode='7days')
    reloaded.finish_sync(lease, result(checkpoint='200'))
    assert not reloaded.status()['requires_resync']

def test_alias_read_contract(setup):
    _, store, contact = setup
    assert store.page(contact_id=contact['id'])['contact_version'] == 1
    bind(store, own_aliases=['own-alias@example.test'])
    store.set_contact_aliases('aliases', contact_id=contact['id'], contact_version=1,
                              aliases=['alias@example.test'], expected_revision=1)
    page = store.page(contact_id=contact['id'])
    assert page['explicit_aliases'] == ['alias@example.test'] and page['alias_record_version'] == 1
    assert store.status()['own_aliases'] == ['own-alias@example.test']

def test_terminal_receipts_compact_with_explicit_replay_floor(setup, monkeypatch):
    import hermes_crm.gmail_bridge_store as module
    from hermes_crm.gmail_bridge_schema import receipts
    from sqlalchemy import func
    crm, store, _ = setup
    monkeypatch.setattr(module, 'MAX_RECEIPTS', 6)
    bind(store)
    first_revision = store.status()['revision']
    first = store.begin_sync_once('first', expected_revision=first_revision)
    assert first.revision == first_revision + 1
    store.finish_sync(first, result())
    for i in range(10):
        publish(store, 'later' + str(i), mid='later' + str(i), checkpoint=str(101+i))
    assert store.status()['receipt_revision_floor'] > first.revision
    assert store.operation_receipt('first')['status'] == 'expired_or_unknown'
    with pytest.raises(CRMError, match='expired'):
        store.begin_sync_once('first', expected_revision=first_revision)
    with pytest.raises(CRMError):
        store.finish_sync(first, result())
    with crm.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(receipts)).scalar_one() <= 6
    assert not store.status()['sync_capacity_reached']

def test_unknown_receipts_protected_until_explicit_local_fence(setup, monkeypatch):
    import hermes_crm.gmail_bridge_store as module
    _, store, _ = setup
    monkeypatch.setattr(module, 'MAX_RECEIPTS', 6)
    bind(store)
    unknown = begin(store, 'unknown')
    store.fail_sync(unknown, unknown=True)
    for i in range(5):
        publish(store, 'later' + str(i), checkpoint=str(101+i))
    assert store.operation_receipt('unknown')['outcome']['status'] == 'unknown'
    store.control('pause', action='pause', expected_revision=store.status()['revision'])
    assert store.operation_receipt('unknown')['outcome']['status'] == 'cancelled'

def test_local_fence_reconciles_unknown_verification_without_replay(setup):
    _, store, _ = setup
    intent = dict(selector_fingerprint='a' * 64, mailbox='own@example.test', expected_revision=0)
    store.reserve_verify('verify', **intent)
    store.fail_verify('verify', **intent)
    store.control('disconnect', action='disconnect', expected_revision=0)
    assert store.bind_receipt('verify', **intent)['status'] == 'cancelled'
    assert not store.reserve_verify('verify', **intent)
    assert not store.status()['enabled']

def test_company_history_uses_only_current_explicit_contact_membership(setup):
    from hermes_crm.companies import CompanyStore
    crm, store, contact = setup
    companies = CompanyStore(crm)
    company = companies.create({'name': 'Explicit group', 'domain': 'example.test'}, actor='test', key='company')
    companies.set_contact_company(contact['id'], company['id'], expected_contact_version=1, actor='test', key='link')
    crm.create('contacts', {'name': 'Same domain', 'email': 'unlinked@example.test', 'company': 'Explicit group'})
    bind(store)
    publish(store)
    publish(store, 'unlinked', mid='m2', target='unlinked@example.test')
    page = store.page(company_id=company['id'], limit=1)
    assert page['total'] == 1 and page['items'][0]['message_id'] == 'm1'
    assert page['association_basis'] == 'current_explicit_company_contacts'
    companies.set_contact_company(contact['id'], None, expected_contact_version=2, actor='test', key='unlink')
    assert store.page(company_id=company['id'])['total'] == 0
    with pytest.raises(CRMError):
        store.page(contact_id=contact['id'], company_id=company['id'])
    crm.profile = 'different'
    with pytest.raises(CRMError, match='Company not found'):
        GmailBridgeStore(crm).page(company_id=company['id'])
