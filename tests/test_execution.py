"""Synthetic-only intent/evidence tests. No host, model, scheduling or outreach."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

from hermes_crm.domain import CRM, CRMError
from hermes_crm.execution import ExecutionStore, assignments, occurrences, receipts


@pytest.fixture
def setup(tmp_path):
    crm = CRM(f'sqlite:///{tmp_path}/execution.db', profile='synthetic')
    task = crm.create('tasks', {'title': 'Internal analysis', 'due_at': '2030-01-01T00:00:00Z'})
    store = ExecutionStore(crm)
    yield crm, store, task
    crm.close()


def create(setup, **extra):
    crm, store, task = setup
    args = dict(task_id=task['id'], human_owner='Synthetic owner', prompt='  Exact prompt\n',
                success_criteria='Internal summary saved for review', idempotency_key='one', profile=crm.profile,
                host_connection_identity='synthetic-sdk-connection',
                host_profile_identity='authority-profile-17',
                host_route={'connectionId': 'test-connection', 'profile': 'synthetic',
                            'targetProfile': 'synthetic', 'mode': 'local'})
    args.update(extra)
    return store.create(**args)


def current(assignment): return assignment['occurrences'][-1]
def cas(row): return dict(version=row['version'], generation=row['generation'])


def dispatch(store, assignment):
    row = current(assignment)
    return store.begin_dispatch(row['id'], **cas(row),
                                host_connection_identity=assignment['payload'].get('host_connection_identity'))


def observe(store, assignment, kind, **extra):
    row = current(assignment)
    args = dict(host_connection_identity=assignment['payload'].get('host_connection_identity'),
                kind=kind, reference=f'{kind}-receipt', session_request_id=row['session_request_id'],
                submission_id=row['submission_id'], session_id=row['session_id'], admission_id=row['admission_id'])
    args.update(extra)
    return store.observe(row['id'], **cas(row), **args)


def admitted(setup):
    store = setup[1]
    a = dispatch(store, create(setup))
    a = observe(store, a, 'session', session_id='session-1')
    return observe(store, a, 'admission', admission_id='admission-1', state='admitted')


def test_intent_exact_payload_persistence_idempotency(setup):
    crm, store, _ = setup
    a = create(setup)
    assert create(setup) == a
    assert a['payload']['prompt'] == '  Exact prompt\n'
    with crm.engine.connect() as conn:
        raw = conn.execute(select(assignments.c.payload)).scalar_one()
    assert a['digest'] == hashlib.sha256(raw.encode()).hexdigest()
    assert a['payload']['task_version'] == 1
    assert a['payload']['task_status'] == 'open'
    url = crm.url
    crm.close()
    reopened = CRM(url, profile='synthetic')
    try: assert ExecutionStore(reopened).get(a['id']) == a
    finally: reopened.close()


def test_conflicting_intent_missing_task_foreign_profile(setup):
    create(setup)
    with pytest.raises(CRMError, match='payload conflict'): create(setup, prompt='Different')
    with pytest.raises(CRMError, match='Cross-profile'): create(setup, profile='other')
    with pytest.raises(CRMError, match='Task not found'): create(setup, task_id='missing', idempotency_key='two')
    foreign = CRM(setup[0].url, profile='other')
    try:
        assert ExecutionStore(foreign).list() == []
        with pytest.raises(CRMError, match='current workspace/profile'):
            ExecutionStore(foreign).get(create(setup)['id'])
    finally: foreign.close()


def test_concurrent_intent_and_cas(setup):
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(lambda _: create(setup), range(4)))
    assert len({r['id'] for r in result}) == 1
    row = current(result[0])
    def run(_):
        try:
            setup[1].begin_dispatch(row['id'], **cas(row), host_connection_identity='synthetic-sdk-connection')
            return True
        except CRMError: return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(run, range(4))) == 1
    assert current(setup[1].get(result[0]['id']))['state'] == 'unknown'


def test_task_mutation_blocks_preflight_and_dispatch(setup):
    crm, store, task = setup
    a = create(setup)
    row = current(a)
    assert store.validate_dispatch(row['id'], host_connection_identity='synthetic-sdk-connection')['digest'] == a['digest']
    crm.update('tasks', task['id'], {'version': 1, 'status': 'done'})
    with pytest.raises(CRMError, match='Source task changed'): store.validate_dispatch(row['id'], host_connection_identity='synthetic-sdk-connection')
    with pytest.raises(CRMError, match='Source task changed'): dispatch(store, a)
    assert current(store.get(a['id']))['state'] == 'pending'


def test_scheduled_is_blocked_not_scheduled(setup):
    a = create(setup, run_at='2030-01-01T00:00:00Z')
    row = current(a)
    assert row['state'] == 'blocked'
    assert row['reason'] == 'public_scheduler_api_unavailable'
    with pytest.raises(CRMError): dispatch(setup[1], a)
    assert setup[1].coverage(a['id'])['covered'] is False
    with pytest.raises(CRMError): create(setup, run_at='2030-01-01')


def test_success_requires_admission_and_does_not_complete_task(setup):
    crm, store, task = setup
    a = admitted(setup)
    a = observe(store, a, 'admission', reference='running', state='running')
    with pytest.raises(CRMError, match='regression'):
        observe(store, a, 'admission', reference='stale', state='admitted')
    a = observe(store, a, 'result', state='succeeded', redacted_summary='Internal summary ready')
    row = current(a)
    assert row['review_status'] == 'awaiting_human_review'
    assert crm.get('tasks', task['id'])['status'] == 'open'
    assert store.coverage(a['id'])['reason'] == 'awaiting_human_review'
    assert all(r['provenance'] == 'client_observed' for r in row['receipts'])
    # Identical receipt can be reconciled after restart without another state transition.
    assert observe(store, a, 'result', state='succeeded', redacted_summary='Internal summary ready') == a
    with pytest.raises(CRMError, match='identity conflict'):
        observe(store, a, 'result', state='failed')


def test_invalid_evidence_is_atomic(setup):
    store = setup[1]
    a = create(setup)
    with pytest.raises(CRMError, match='Dispatch intent'): observe(store, a, 'session', session_id='session')
    a = dispatch(store, a)
    for change in [dict(submission_id='foreign'), dict(session_request_id='foreign'), dict(provenance='server_verified')]:
        with pytest.raises(CRMError): observe(store, a, 'session', session_id='session', **change)
    with pytest.raises(CRMError): observe(store, a, 'result', session_id='session', admission_id='admission', state='succeeded')
    a = observe(store, a, 'session', session_id='session')
    with pytest.raises(CRMError, match='session mismatch'):
        observe(store, a, 'admission', session_id='other', admission_id='admission', state='admitted')
    a = observe(store, a, 'admission', admission_id='admission', state='admitted')
    with pytest.raises(CRMError, match='admission mismatch'):
        observe(store, a, 'result', admission_id='other', state='succeeded')
    assert len(current(store.get(a['id']))['receipts']) == 2


def test_request_cancel_is_not_confirmed_cancellation(setup):
    store = setup[1]
    a = admitted(setup)
    row = current(a)
    a = store.request_cancel(row['id'], **cas(row))
    row = current(a)
    assert row['state'] == 'admitted' and row['cancel_requested'] == 1
    with pytest.raises(CRMError, match='Host cancellation receipt'): store.cancel_undispatched(row['id'], **cas(row))
    a = observe(store, a, 'result', state='cancelled')
    assert current(a)['state'] == 'cancelled'


def test_cancel_before_dispatch(setup):
    store = setup[1]
    a = create(setup)
    row = current(a)
    a = store.request_cancel(row['id'], **cas(row))
    with pytest.raises(CRMError): dispatch(store, a)
    row = current(a)
    assert current(store.cancel_undispatched(row['id'], **cas(row)))['state'] == 'cancelled'


def test_unknown_and_client_nonadmission_are_never_retryable(setup):
    store = setup[1]
    a = dispatch(store, create(setup))
    row = current(a)
    with pytest.raises(CRMError, match='Reconcile'): store.retry(row['id'], **cas(row))
    a = observe(store, a, 'not_admitted', state='failed', redacted_summary='Client says host rejected')
    row = current(a)
    assert row['state'] == 'unknown'
    assert row['reason'] == 'unverified_nonadmission'
    assert row['safe_to_retry'] == 0
    with pytest.raises(CRMError, match='Reconcile'): store.retry(row['id'], **cas(row))
    assert len(store.get(a['id'])['occurrences']) == 1


def test_execution_failure_is_not_safe_retry(setup):
    store = setup[1]
    a = observe(store, admitted(setup), 'result', state='failed')
    row = current(a)
    with pytest.raises(CRMError): store.retry(row['id'], **cas(row))


def test_fk_integrity_and_postgresql_ddl(setup):
    crm, store, _ = setup
    a = create(setup)
    with pytest.raises(IntegrityError):
        with crm.engine.begin() as conn:
            conn.execute(assignments.update().where(assignments.c.id == a['id']).values(task_id='nonexistent'))
    for table in (assignments, occurrences, receipts):
        assert 'CREATE TABLE crm_agent_' in str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert store.get(a['id'])['task_id'] == setup[2]['id']


def test_blocked_unknown_and_stale_versions(setup):
    store = setup[1]
    a = create(setup)
    row = current(a)
    a = store.mark(row['id'], **cas(row), state='blocked', reason='profile_offline')
    with pytest.raises(CRMError, match='Stale occurrence version'):
        store.mark(row['id'], **cas(row), state='unknown', reason='lost_response')
    row = current(a)
    a = store.mark(row['id'], **cas(row), state='unknown', reason='lost_response')
    assert store.coverage(a['id'])['reason'] == 'lost_response'


def test_reopen_after_admission_preserves_evidence_and_cancellation(setup):
    crm, store, _ = setup
    a = admitted(setup)
    row = current(a)
    a = store.request_cancel(row['id'], **cas(row))
    reopened = CRM(crm.url, profile=crm.profile)
    try:
        resumed = ExecutionStore(reopened)
        assert resumed.get(a['id']) == a
        # A cancellation request may lose the race to successful completion.
        result = observe(resumed, a, 'result', state='succeeded')
        assert current(result)['cancel_requested'] == 1
        assert current(result)['state'] == 'succeeded'
        assert current(result)['review_status'] == 'awaiting_human_review'
    finally: reopened.close()


def test_nonadmission_cannot_erase_admission(setup):
    store = setup[1]
    a = admitted(setup)
    with pytest.raises(CRMError, match='Nonadmission evidence'):
        observe(store, a, 'not_admitted', state='failed')
    assert current(store.get(a['id']))['state'] == 'admitted'


def test_session_identity_cannot_be_reused_by_other_occurrence(setup):
    store = setup[1]
    a = admitted(setup)
    b = dispatch(store, create(setup, idempotency_key='second'))
    with pytest.raises(CRMError, match='Receipt identity already belongs'):
        observe(store, b, 'session', session_id=current(a)['session_id'])
    assert current(store.get(b['id']))['session_id'] is None
    assert current(store.get(b['id']))['receipts'] == []


def test_nonadmission_rejects_embedded_admission_and_unbound_session(setup):
    store = setup[1]
    a = dispatch(store, create(setup))
    for extra in [dict(admission_id='present-admission'), dict(session_id='unbound-session'),
                  dict(admission_id='present-admission', session_id='unbound-session')]:
        with pytest.raises(CRMError):
            observe(store, a, 'not_admitted', state='failed', **extra)
    row = current(store.get(a['id']))
    assert row['safe_to_retry'] == 0 and row['state'] == 'unknown' and row['receipts'] == []
    with pytest.raises(CRMError): store.retry(row['id'], **cas(row))


def test_task_update_between_validation_and_dispatch_cas_is_rejected(setup, monkeypatch):
    crm, store, task = setup
    a = create(setup)
    validate = store._validate_task
    def interleave(conn, assignment):
        validate(conn, assignment)
        crm.update('tasks', task['id'], {'version': 1, 'status': 'done'})
    monkeypatch.setattr(store, '_validate_task', interleave)
    with pytest.raises(CRMError, match='Source task changed'): dispatch(store, a)
    assert crm.get('tasks', task['id'])['status'] == 'done'
    row = current(store.get(a['id']))
    assert row['dispatch_started'] == 0 and row['state'] == 'pending'


def test_duplicate_receipt_still_requires_current_version_and_generation(setup):
    crm, store, _ = setup
    a = admitted(setup)
    row = current(a)
    def duplicate(version, generation):
        return store.observe(row['id'], version=version, generation=generation, kind='admission',
                             host_connection_identity='synthetic-sdk-connection',
                             reference='admission-receipt', session_request_id=row['session_request_id'],
                             submission_id=row['submission_id'], session_id=row['session_id'],
                             admission_id=row['admission_id'], state='admitted')
    assert duplicate(row['version'], row['generation']) == a
    with pytest.raises(CRMError, match='Stale occurrence version'):
        duplicate(-999, row['generation'])
    with pytest.raises(CRMError, match='Stale execution generation'):
        duplicate(row['version'], -999)
    # Model a future verified reconciler advancing the assignment generation.
    # Client observations currently cannot create that retry generation.
    with crm.engine.begin() as conn:
        conn.execute(assignments.update().where(assignments.c.id == a['id']).values(generation=2))
    with pytest.raises(CRMError, match='Stale execution generation'):
        duplicate(row['version'], row['generation'])


def test_idempotent_create_recovers_snapshot_after_task_changes(setup):
    crm, store, task = setup
    a = create(setup)
    crm.update('tasks', task['id'], {'version': 1, 'notes': 'Changed after initial intent'})
    assert create(setup) == a
    assert create(setup)['payload']['task_version'] == 1
    with pytest.raises(CRMError, match='Source task changed'): dispatch(store, a)
    with pytest.raises(CRMError, match='payload conflict'): create(setup, prompt='Changed request')


def test_unknown_or_blocked_does_not_erase_observed_running_high_water(setup):
    store = setup[1]
    a = admitted(setup)
    a = observe(store, a, 'admission', reference='started', state='running')
    for state in ['unknown', 'blocked']:
        row = current(a)
        a = store.mark(row['id'], **cas(row), state=state, reason='lost_response')
        with pytest.raises(CRMError, match='State regression'):
            observe(store, a, 'admission', reference='stale-queued', state='admitted')
        assert current(store.get(a['id']))['state'] == state
    assert current(observe(store, a, 'result', state='succeeded'))['state'] == 'succeeded'


def test_connection_binding_is_immutable_caller_observed_and_not_profile_name(setup):
    crm, store, _ = setup
    a = create(setup)
    row = current(a)
    assert a['payload']['host_connection_identity'] == 'synthetic-sdk-connection'
    assert a['payload']['host_connection_provenance'] == 'caller_observed'
    for identity in [None, crm.profile, 'other-sdk-connection']:
        with pytest.raises(CRMError, match='Host connection identity mismatch'):
            store.validate_dispatch(row['id'], host_connection_identity=identity)
        with pytest.raises(CRMError, match='Host connection identity mismatch'):
            store.begin_dispatch(row['id'], **cas(row), host_connection_identity=identity)
    with pytest.raises(CRMError, match='payload conflict'):
        create(setup, host_connection_identity='other-sdk-connection')
    assert current(store.get(a['id']))['dispatch_started'] == 0


def test_absent_connection_identity_is_local_intent_only(setup):
    _, store, _ = setup
    a = create(setup, host_connection_identity=None)
    row = current(a)
    assert a['payload']['host_connection_provenance'] is None
    assert store.coverage(a['id'])['host_connection_bound'] is False
    for identity in [None, 'new-sdk-connection']:
        with pytest.raises(CRMError, match='Local intent only'):
            store.validate_dispatch(row['id'], host_connection_identity=identity)
        with pytest.raises(CRMError, match='Local intent only'):
            store.begin_dispatch(row['id'], **cas(row), host_connection_identity=identity)
    assert current(store.get(a['id']))['dispatch_started'] == 0


def test_cross_connection_new_and_duplicate_receipts_are_rejected(setup):
    store = setup[1]
    a = admitted(setup)
    for identity in [None, 'another-sdk-connection']:
        with pytest.raises(CRMError, match='Host connection identity mismatch'):
            observe(store, a, 'result', state='succeeded', host_connection_identity=identity)
        with pytest.raises(CRMError, match='Host connection identity mismatch'):
            observe(store, a, 'admission', state='admitted', host_connection_identity=identity)
    assert store.get(a['id']) == a


def host_session(setup, **extra):
    store = setup[1]
    a = dispatch(store, create(setup, **extra))
    return observe(store, a, 'session', session_id='structured-session')


def host_observe(store, a, **extra):
    row = current(a)
    args = dict(session_request_id=row['session_request_id'], submission_id=row['submission_id'],
                session_id=row['session_id'], admission_id='structured-admission',
                host_connection_identity=a['payload']['host_connection_identity'],
                profile_id='authority-profile-17', source='prompt.submit', status='queued',
                outcome=None, sequence=1, authority_epoch=100, execution_generation=None)
    args.update(extra)
    return store.observe_host(row['id'], **cas(row), **args)


def test_first_submit_terminal_binds_actual_admission_without_fabricated_queue(setup):
    store = setup[1]
    a = host_session(setup)
    a = host_observe(store, a, status='terminal', outcome='completed', sequence=7,
                     execution_generation=42, redacted_result={'final_response': 'Redacted summary', 'completed': True})
    row = current(a)
    assert row['state'] == 'succeeded' and row['admission_id'] == 'structured-admission'
    assert row['generation'] == 1 and row['review_status'] == 'awaiting_human_review'
    assert [r['kind'] for r in row['receipts']] == ['session', 'host']
    receipt = row['receipts'][-1]
    evidence = json.loads(receipt['evidence'])
    host = evidence['host_observation']
    assert host['status'] == 'terminal' and host['outcome'] == 'completed'
    assert host['source'] == 'prompt.submit' and host['sequence'] == 7
    assert host['authority_epoch'] == 100 and host['execution_generation'] == 42
    assert len(host['redacted_result_digest']) == 64
    assert 'Redacted summary' not in receipt['evidence']
    assert evidence['reference_provenance'] == 'client_derived_sha256'
    assert receipt['reference'].startswith('client-sha256:')
    assert receipt['provenance'] == 'client_observed'
    assert setup[0].get('tasks', setup[2]['id'])['status'] == 'open'
    assert host_observe(store, a, status='terminal', outcome='completed', sequence=7,
                        execution_generation=42, redacted_result={'final_response': 'Redacted summary', 'completed': True}) == a


@pytest.mark.parametrize('status,outcome', [('unknown', None), ('terminal', 'interrupted'),
                                           ('terminal', 'unknown'), ('terminal', 'unfamiliar')])
def test_initial_unknown_or_uncertain_terminal_has_real_identity_and_no_retry(setup, status, outcome):
    store = setup[1]
    a = host_observe(store, host_session(setup), status=status, outcome=outcome)
    row = current(a)
    assert row['state'] == 'unknown' and row['admission_id'] == 'structured-admission'
    assert row['safe_to_retry'] == 0
    assert json.loads(row['receipts'][-1]['evidence'])['host_observation']['status'] == status
    with pytest.raises(CRMError): store.retry(row['id'], **cas(row))


@pytest.mark.parametrize('result', [None, {}, {'final_response': ''}, {'final_response': '  '},
                                    {'final_response': 'Summary', 'completed': False},
                                    {'final_response': 'Summary', 'failed': True},
                                    {'final_response': 'Summary', 'error': True},
                                    {'final_response': 'Summary', 'interrupted': True}])
def test_completed_requires_consistent_nonempty_redacted_result(setup, result):
    store = setup[1]
    a = host_observe(store, host_session(setup), status='terminal', outcome='completed', redacted_result=result)
    assert current(a)['state'] == 'unknown'
    assert current(a)['review_status'] == 'not_ready'


def test_queued_cancel_without_result_is_observed_terminal_cancellation(setup):
    store = setup[1]
    a = host_observe(store, host_session(setup))
    row = current(a)
    a = store.request_cancel(row['id'], **cas(row))
    a = host_observe(store, a, source='prompt.cancel', status='terminal', outcome='cancelled', sequence=1)
    row = current(a)
    assert row['state'] == 'cancelled' and row['cancel_requested'] == 1
    host = json.loads(row['receipts'][-1]['evidence'])['host_observation']
    assert host['execution_generation'] is None and host['redacted_result_digest'] is None


def test_structured_observation_hash_changes_across_host_phases(setup):
    store = setup[1]
    a = host_observe(store, host_session(setup))
    first = current(a)['receipts'][-1]['reference']
    a = host_observe(store, a, source='prompt.receipt', status='started', sequence=1, execution_generation=7)
    assert current(a)['state'] == 'running'
    assert current(a)['receipts'][-1]['reference'] != first
    # Authority epochs may change; CRM generation is unrelated to host values.
    a = host_observe(store, a, source='prompt.receipt', status='started', sequence=1,
                     authority_epoch=101, execution_generation=8)
    assert current(a)['state'] == 'running'
    with pytest.raises(CRMError, match='State regression'):
        host_observe(store, a, source='prompt.receipt', status='queued', sequence=1, authority_epoch=101)


@pytest.mark.parametrize('sequence', [9, 11])
@pytest.mark.parametrize('epoch', [100, 101])
def test_structured_host_sequence_is_immutable_admission_identity(setup, sequence, epoch):
    store = setup[1]
    a = host_observe(store, host_session(setup), status='started', sequence=10, execution_generation=7)
    with pytest.raises(CRMError, match='Host admission sequence identity conflict'):
        host_observe(store, a, source='prompt.receipt', status='terminal', outcome='failed', sequence=sequence, execution_generation=7, authority_epoch=epoch)
    assert current(store.get(a['id']))['state'] == 'running'


def test_uncertain_terminal_allows_result_reconciliation_not_queued_regression(setup):
    store = setup[1]
    a = host_observe(store, host_session(setup), status='terminal', outcome='completed', sequence=2)
    with pytest.raises(CRMError, match='terminal state regression'):
        host_observe(store, a, source='prompt.receipt', sequence=2)
    with pytest.raises(CRMError, match='structured host observations'):
        observe(store, a, 'admission', admission_id='structured-admission', state='admitted')
    a = host_observe(store, a, source='prompt.receipt', status='terminal', outcome='completed', sequence=2,
                     redacted_result={'final_response': 'Safe redacted result'})
    assert current(a)['state'] == 'succeeded'
    with pytest.raises(CRMError, match='Conflicting host terminal observation identity'):
        host_observe(store, a, source='prompt.receipt', status='terminal', outcome='failed', sequence=2)


@pytest.mark.parametrize('extra', [dict(source='cron.submit'), dict(source=[]), dict(status=[]),
    dict(status='successful'), dict(sequence=True), dict(sequence=0), dict(sequence=1.5),
    dict(authority_epoch=-1), dict(authority_epoch='100'), dict(execution_generation=False),
    dict(execution_generation=-1), dict(execution_generation=2**63), dict(outcome='x'*81),
    dict(redacted_result={'messages': ['secret']}), dict(redacted_result={'error': 'raw secret'}),
    dict(redacted_result={'failed': 1}), dict(redacted_result={'completed': None}),
    dict(redacted_result={'final_response': 'x'*4001})])
def test_untrusted_host_metadata_is_bounded_and_allowlisted_atomically(setup, extra):
    store = setup[1]
    a = host_session(setup)
    with pytest.raises(CRMError): host_observe(store, a, **extra)
    assert store.get(a['id']) == a


def test_host_profile_session_admission_and_connection_association(setup):
    store = setup[1]
    a = host_session(setup)
    for extra in [dict(profile_id='synthetic'), dict(profile_id='foreign-authority'),
                  dict(session_id='another-session'), dict(host_connection_identity='another-connection')]:
        with pytest.raises(CRMError): host_observe(store, a, **extra)
    assert store.get(a['id']) == a
    a = host_observe(store, a)
    with pytest.raises(CRMError, match='admission mismatch'):
        host_observe(store, a, admission_id='other-admission')


def test_uncaptured_authority_profile_blocks_structured_observation(setup):
    store = setup[1]
    a = host_session(setup, host_profile_identity=None)
    with pytest.raises(CRMError, match='authority profile identity'):
        host_observe(store, a)
    assert current(store.get(a['id']))['admission_id'] is None


def phase_binding(a):
    row = current(a)
    return dict(**cas(row), session_request_id=row['session_request_id'], submission_id=row['submission_id'],
                session_id=row['session_id'], host_connection_identity=a['payload']['host_connection_identity'],
                profile_id=a['payload']['host_profile_identity'], route=a['payload']['host_route'])


def runtime(store, a, **extra):
    args = dict(**phase_binding(a), instance_id='instance-1', authority_epoch=100, desktop_protocol='hermes-gateway-v1')
    args.update(extra)
    return store.record_runtime(current(a)['id'], **args)


def scope(store, a, **extra):
    args = dict(**phase_binding(a), runtime_reference=current(a)['runtime']['reference'],
                enabled_toolsets=['crm_read'], tools=['crm_task_get'], visible_tools=['tool_search'], total=1)
    args.update(extra)
    return store.record_scope(current(a)['id'], **args)


def prepare(store, a, **extra):
    args = dict(**phase_binding(a), scope_digest=current(a)['scope_digest'])
    args.update(extra)
    return store.prepare_submit(current(a)['id'], **args)


def scoped_session(setup):
    store = setup[1]
    a = runtime(store, dispatch(store, create(setup)))
    a = observe(store, a, 'session', session_id='scoped-session')
    return scope(store, a)


def test_runtime_scope_and_submission_are_durable_bound_client_evidence(setup):
    crm, store, _ = setup
    a = scoped_session(setup)
    before = current(a)
    assert before['scope']['strict_host_ceiling'] is False
    assert before['runtime']['source'] == 'runtime.describe'
    assert before['runtime']['provenance'] == 'client_observed'
    a = prepare(store, a)
    row = current(a)
    assert row['submit_started'] is True and row['state'] == 'unknown'
    assert row['submission']['submit_attempt'] == 1 and row['submission']['replay'] is False
    assert row['submission']['payload_digest'] == a['digest']
    assert row['submission_id'] == before['submission_id']
    assert row['session_request_id'] == before['session_request_id']
    reopened = CRM(crm.url, profile=crm.profile)
    try: assert ExecutionStore(reopened).get(a['id']) == a
    finally: reopened.close()
    assert crm.get('tasks', setup[2]['id'])['version'] == 1


def test_submit_requires_scope_and_cannot_blindly_repeat_intent(setup):
    store = setup[1]
    a = runtime(store, dispatch(store, create(setup)))
    a = observe(store, a, 'session', session_id='scoped-session')
    with pytest.raises(CRMError, match='Scope/runtime'): prepare(store, a)
    a = scope(store, a)
    with pytest.raises(CRMError, match='first submit required'): prepare(store, a, replay=True)
    a = prepare(store, a)
    with pytest.raises(CRMError, match='Submission intent exists'): prepare(store, a)
    with pytest.raises(CRMError, match='Resume the same session'): prepare(store, a, replay=True)
    a = scope(store, a, resumed_session_id='scoped-session')
    a = prepare(store, a, replay=True)
    assert current(a)['submission']['submit_attempt'] == 2
    assert len(a['occurrences']) == 1
    assert current(a)['generation'] == 1


def test_runtime_change_invalidates_scope_and_requires_observed_resume(setup):
    store = setup[1]
    a = scoped_session(setup)
    previous_scope = current(a)['scope_digest']
    a = runtime(store, a, instance_id='instance-2', authority_epoch=101)
    assert current(a)['runtime']['resume_required'] is True
    with pytest.raises(CRMError, match='Scope/runtime'): prepare(store, a, scope_digest=previous_scope)
    with pytest.raises(CRMError, match='resume and revalidate'): scope(store, a)
    with pytest.raises(CRMError, match='Resume session mismatch'): scope(store, a, resumed_session_id='foreign')
    a = scope(store, a, resumed_session_id='scoped-session')
    assert current(a)['scope_digest'] != previous_scope
    assert current(prepare(store, a))['submit_started'] is True


@pytest.mark.parametrize('extra', [dict(enabled_toolsets=['crm_read', 'crm_write']),
    dict(tools=['crm_task_get', 'crm_task_create'], total=2), dict(tools=['crm_task_get', 'crm_task_get'], total=2),
    dict(tools=['crm_overview']), dict(visible_tools=['terminal']), dict(total=True), dict(total=2),
    dict(visible_tools=['crm_contact_list']), dict(runtime_reference='old-runtime'),
    dict(profile_id='foreign'), dict(session_id='foreign'), dict(submission_id='foreign')])
def test_scope_rejects_widened_malformed_or_foreign_evidence(setup, extra):
    store = setup[1]
    a = scoped_session(setup)
    with pytest.raises(CRMError): scope(store, a, **extra)
    assert store.get(a['id']) == a


def test_required_tools_and_route_are_immutable_and_strict(setup):
    store = setup[1]
    a = create(setup, required_tools=['crm_task_get', 'crm_contact_get'])
    with pytest.raises(CRMError, match='payload conflict'): create(setup)
    a = runtime(store, dispatch(store, a))
    a = observe(store, a, 'session', session_id='scoped-session')
    with pytest.raises(CRMError, match='Required task tools'): scope(store, a)
    altered = dict(a['payload']['host_route'], connectionId='foreign')
    with pytest.raises(CRMError, match='route mismatch'): runtime(store, a, route=altered)
    with pytest.raises(CRMError): runtime(store, a, route=dict(altered, token='secret'))
    with pytest.raises(CRMError): runtime(store, a, authority_epoch=True)
    with pytest.raises(CRMError): runtime(store, a, desktop_protocol='legacy')
    with pytest.raises(CRMError): runtime(store, a, instance_id='x'*161)
    a = scope(store, a, tools=['crm_task_get', 'crm_contact_get'], total=2)
    assert current(prepare(store, a))['submit_started'] is True


def test_prepare_rechecks_task_cancel_scope_expiry_and_cas(setup, monkeypatch):
    crm, store, task = setup
    a = scoped_session(setup)
    row = current(a)
    with pytest.raises(CRMError, match='Stale occurrence version'): prepare(store, a, version=row['version'] - 1)
    with pytest.raises(CRMError, match='Stale execution generation'): prepare(store, a, generation=2)
    # Expiration is tested with a synthetic, private evidence timestamp.
    with crm.engine.begin() as conn:
        conn.execute(receipts.update().where(receipts.c.reference == row['scope']['reference']).values(created_at='2000-01-01T00:00:00+00:00'))
    with pytest.raises(CRMError, match='expired'): prepare(store, a)
    a = scope(store, store.get(a['id']))
    validate = store._validate_task
    def interleave(conn, assignment):
        validate(conn, assignment)
        crm.update('tasks', task['id'], {'version': 1, 'status': 'done'})
    monkeypatch.setattr(store, '_validate_task', interleave)
    with pytest.raises(CRMError, match='Source task changed'): prepare(store, a)
    assert current(store.get(a['id']))['submit_started'] is False


def test_prepare_cancellation_blocks_first_submit_and_replay(setup):
    store = setup[1]
    a = scoped_session(setup)
    row = current(a)
    a = store.request_cancel(row['id'], **cas(row))
    with pytest.raises(CRMError, match='Cancellation requested'): prepare(store, a)
    assert current(store.get(a['id']))['submit_started'] is False


def test_prepare_known_admission_requires_receipt_reconciliation(setup):
    store = setup[1]
    a = prepare(store, scoped_session(setup))
    a = host_observe(store, a, session_id='scoped-session')
    with pytest.raises(CRMError, match='Reconcile known admission'): prepare(store, a, replay=True)


def test_concurrent_prepare_submit_is_single_durable_intent(setup):
    store = setup[1]
    a = scoped_session(setup)
    def run(_):
        try:
            prepare(store, a)
            return True
        except CRMError: return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(run, range(4))) == 1
    row = current(store.get(a['id']))
    assert row['submit_started'] is True
    assert len([r for r in row['receipts'] if r['kind'] == 'submit']) == 1


def test_retired_authority_cannot_overwrite_newer_running_observation(setup):
    store = setup[1]
    a = host_observe(store, host_session(setup), status='started', sequence=10,
                     authority_epoch=100, execution_generation=7)
    a = host_observe(store, a, source='prompt.receipt', status='started', sequence=10,
                     authority_epoch=101, execution_generation=8)
    for extra in [dict(status='terminal', outcome='failed', sequence=10),
                  dict(status='started', outcome=None, sequence=10)]:
        with pytest.raises(CRMError, match='Stale host authority epoch'):
            host_observe(store, a, source='prompt.receipt', authority_epoch=100,
                         execution_generation=7, **extra)
    assert store.get(a['id']) == a


@pytest.mark.parametrize('generation', [None, 6])
def test_known_execution_generation_cannot_regress(setup, generation):
    store = setup[1]
    a = host_observe(store, host_session(setup), status='started', execution_generation=7)
    with pytest.raises(CRMError, match='stale host execution generation'):
        host_observe(store, a, source='prompt.receipt', status='terminal', outcome='failed',
                     sequence=1, authority_epoch=101, execution_generation=generation)
    assert store.get(a['id']) == a


def test_terminal_identity_is_immutable_but_missing_result_can_hydrate(setup):
    store = setup[1]
    a = host_observe(store, host_session(setup), status='terminal', outcome='completed', sequence=2,
                     execution_generation=7)
    for extra in [dict(outcome='failed', execution_generation=7),
                  dict(outcome='completed', execution_generation=8)]:
        with pytest.raises(CRMError, match='Conflicting host terminal observation identity'):
            host_observe(store, a, source='prompt.receipt', status='terminal', sequence=2, **extra)
    assert store.get(a['id']) == a
    with pytest.raises(CRMError, match='Conflicting host terminal observation identity'):
        host_observe(store, a, source='prompt.receipt', status='terminal', outcome='failed',
                     sequence=2, execution_generation=7, authority_epoch=101)
    a = host_observe(store, a, source='prompt.receipt', status='terminal', outcome='completed',
                     sequence=2, execution_generation=7, redacted_result={'final_response': 'Summary'})
    assert current(a)['state'] == 'succeeded'


def test_terminal_contradictory_result_cannot_be_replaced_at_same_identity(setup):
    store = setup[1]
    a = host_observe(store, host_session(setup), status='terminal', outcome='completed', sequence=2,
                     redacted_result={'final_response': 'Summary', 'failed': True})
    with pytest.raises(CRMError, match='Conflicting host terminal result evidence'):
        host_observe(store, a, source='prompt.receipt', status='terminal', outcome='completed', sequence=2,
                     redacted_result={'final_response': 'Summary', 'failed': False})
    assert current(store.get(a['id']))['state'] == 'unknown'


def test_admission_sequence_can_stay_constant_across_legitimate_status_progress(setup):
    store = setup[1]
    a = host_observe(store, host_session(setup), sequence=1)
    a = host_observe(store, a, source='prompt.receipt', status='started', sequence=1, execution_generation=7)
    a = host_observe(store, a, source='prompt.receipt', status='terminal', outcome='failed',
                     sequence=1, execution_generation=7)
    assert current(a)['state'] == 'failed'


def test_each_same_id_replay_requires_scope_resume_after_previous_attempt(setup):
    store = setup[1]
    a = scope(store, scoped_session(setup), resumed_session_id='scoped-session')
    a = prepare(store, a)
    with pytest.raises(CRMError, match='Fresh recovery scope'): prepare(store, a, replay=True)
    a = scope(store, a, resumed_session_id='scoped-session')
    a = prepare(store, a, replay=True)
    with pytest.raises(CRMError, match='Fresh recovery scope'): prepare(store, a, replay=True)
    assert current(a)['submission']['submit_attempt'] == 2
    assert len(a['occurrences']) == 1


def test_scope_age_rechecked_after_task_lock_wait(setup, monkeypatch):
    from datetime import datetime as real_datetime, timedelta
    import hermes_crm.execution as execution
    store = setup[1]
    a = scoped_session(setup)
    created = real_datetime.fromisoformat(current(a)['scope']['created_at'])
    seconds = [59]
    class Clock(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return created + timedelta(seconds=seconds[0])
    monkeypatch.setattr(execution, 'datetime', Clock)
    guard = store._guard_task
    def delayed(conn, assignment):
        guard(conn, assignment)
        seconds[0] = 70
    monkeypatch.setattr(store, '_guard_task', delayed)
    with pytest.raises(CRMError, match='expired while waiting'): prepare(store, a)
    assert current(store.get(a['id']))['submit_started'] is False


@pytest.mark.parametrize('status,outcome,result,expected', [
    ('terminal', 'completed', {'final_response': 'Historical redacted result'}, 'succeeded'),
    ('terminal', 'failed', None, 'failed'),
    ('unknown', None, None, 'unknown'),
])
def test_runtime_restart_preserves_historical_admission_owner_evidence(setup, status, outcome, result, expected):
    store = setup[1]
    a = prepare(store, scoped_session(setup))
    a = host_observe(store, a, status='started', authority_epoch=100, execution_generation=7)
    a = runtime(store, a, instance_id='instance-2', authority_epoch=101)
    a = host_observe(store, a, source='prompt.receipt', status=status, outcome=outcome,
                     authority_epoch=100, execution_generation=7, redacted_result=result)
    assert current(a)['state'] == expected
    assert current(a)['runtime']['authority_epoch'] == 101
    receipt = json.loads(current(a)['receipts'][-1]['evidence'])['host_observation']
    assert receipt['authority_epoch'] == 100


def test_runtime_restart_can_report_historical_queued_admission(setup):
    store = setup[1]
    a = prepare(store, scoped_session(setup))
    a = host_observe(store, a, authority_epoch=100)
    a = runtime(store, a, instance_id='instance-2', authority_epoch=101)
    a = host_observe(store, a, source='prompt.receipt', authority_epoch=100)
    assert current(a)['state'] == 'admitted'
    assert current(a)['runtime']['authority_epoch'] == 101


def test_runtime_chronology_rejects_older_runtime_without_conflating_owner_epoch(setup):
    store = setup[1]
    a = scoped_session(setup)
    a = runtime(store, a, instance_id='instance-2', authority_epoch=101)
    with pytest.raises(CRMError, match='Stale runtime authority epoch'):
        runtime(store, a, instance_id='instance-1', authority_epoch=100)
    assert store.get(a['id']) == a
