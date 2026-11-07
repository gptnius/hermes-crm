"""Synthetic, offline contracts only: no real email or provider evidence."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes_crm.email_contracts import (
    AccountScope, ApprovedEmailSnapshot, DisabledEmailAdapter, EmailIntegrationDisabled,
    ProviderObservation, UnknownSendOutcome, merge_observations,
)

TIME = '2026-11-06T12:00:00+00:00'


def scope(**changes):
    return AccountScope(**(dict(workspace_id='synthetic-workspace', profile_id='synthetic-profile',
                               provider='synthetic-provider', account_id='synthetic-account') | changes))


def approved(**changes):
    return ApprovedEmailSnapshot(**(dict(scope=scope(), approval_reference='synthetic-review',
        approved_at=TIME, sender='sender@example.test', to=('buyer@example.test',), cc=(), bcc=(),
        subject=' Introduction ', text_body='Hello.\n\nSynthetic draft.\n') | changes))


def observation(event_kind='sent', **changes):
    data = dict(scope=scope(), adapter_id='synthetic-adapter', kind=event_kind,
                basis={'submitted': 'submission_response', 'sent': 'sent_item_read',
                       'received': 'received_item_read'}[event_kind],
                provider_message_id='message-1', provider_thread_id='thread-1', observed_at=TIME)
    if event_kind == 'submitted':
        data.update(provider_submission_id='submission-1', send_request_id='request-1')
    return ProviderObservation(**(data | changes))


def unknown(**changes):
    return UnknownSendOutcome(**(dict(scope=scope(), send_request_id='request-1',
        approved_snapshot_digest=approved().digest(), detected_at=TIME, reason='timeout') | changes))


def test_exact_frozen_review_snapshot_and_input_aliasing():
    recipients = ['buyer@example.test']
    item = approved(to=recipients)
    recipients.append('other@example.test')
    assert item.to == ('buyer@example.test',)
    assert item.subject == ' Introduction '
    assert item.text_body.endswith('\n')
    with pytest.raises(ValidationError):
        item.text_body = 'Changed after review'
    with pytest.raises(ValidationError):
        item.scope.account_id = 'another-account'
    assert 'Synthetic draft' not in repr(item)
    assert 'buyer@example.test' not in repr(item)


@pytest.mark.parametrize('change', [
    {'sender': 'other@example.test'}, {'to': ('other@example.test',)},
    {'cc': ('copy@example.test',)}, {'bcc': ('blind@example.test',)},
    {'subject': 'Introduction'}, {'text_body': 'Hello.\n\nSynthetic draft.'},
    {'in_reply_to_message_id': 'other-message'}, {'scope': scope(account_id='another-account')},
    {'scope': scope(workspace_id='another-workspace')}, {'approval_reference': 'other-review'},
])
def test_review_digest_binds_exact_payload_and_scope(change):
    assert approved().digest() != approved(**change).digest()


def test_recipient_order_and_case_are_not_rewritten():
    a = approved(to=('Case@example.test', 'second@example.test'))
    b = approved(to=('second@example.test', 'Case@example.test'))
    assert a.to[0] == 'Case@example.test'
    assert a.digest() != b.digest()


@pytest.mark.parametrize('change', [
    {'to': ()}, {'to': ('Name <buyer@example.test>',)}, {'to': ('bad@@example.test',)},
    {'sender': 'sender@example.test\r\nBcc: hidden@example.test'},
    {'to': ('buyer@example.test\x7f',)}, {'cc': ('buyer@example.test',)},
    {'subject': 'Subject\nBcc: hidden@example.test'}, {'approved_at': '2026-11-06T12:00:00'},
    {'html_body': '<b>not supported</b>'}, {'attachments': []},
    {'to': tuple(f'{n}@example.test' for n in range(100)), 'cc': ('extra@example.test',)},
])
def test_review_rejects_unreviewed_fields_and_unsafe_headers(change):
    with pytest.raises(ValidationError):
        approved(**change)


def test_utc_timestamps_without_losing_subseconds():
    a = approved(approved_at='2026-11-06T15:00:00.123456+03:00')
    assert a.approved_at == datetime(2026, 11, 6, 12, 0, 0, 123456, tzinfo=timezone.utc)
    assert a.digest() == approved(approved_at='2026-11-06T12:00:00.123456Z').digest()


@pytest.mark.parametrize('kind,change', [
    ('sent', {'basis': 'submission_response'}),
    ('submitted', {'basis': 'sent_item_read'}),
    ('submitted', {'provider_submission_id': None}),
    ('submitted', {'send_request_id': None}),
    ('sent', {'provider_message_id': None}),
    ('received', {'provider_message_id': None}),
    ('received', {'send_request_id': 'request-1'}),
    ('received', {'provider_submission_id': 'submission-1'}),
    ('sent', {'kind': 'delivered'}), ('sent', {'kind': 'unknown'}),
    ('sent', {'source': 'agent_note'}), ('sent', {'body': 'External mail content'}),
    ('sent', {'observed_at': '2026-11-06T12:00:00'}),
    ('sent', {'provider_occurred_at': '2026-11-06T12:00:00'}),
])
def test_observation_shape_does_not_conflate_evidence(kind, change):
    with pytest.raises(ValidationError):
        observation(kind, **change)


def test_submission_need_not_have_a_mailbox_message_or_thread_id():
    submitted = observation('submitted', provider_message_id=None, provider_thread_id=None)
    assert submitted.kind == 'submitted'
    assert submitted.provider_message_id is None


def test_mailbox_thread_is_optional_and_never_fabricated():
    assert observation(provider_thread_id=None).provider_thread_id is None


def test_observation_replay_is_idempotent_and_order_independent():
    first = observation()
    later = observation(observed_at='2026-11-06T12:01:00Z')
    assert merge_observations(first, first, later) == (first,)
    assert merge_observations(later, first) == (first,)


def test_submitted_sent_received_are_separate_monotonic_facts():
    submitted, sent, received = observation('submitted'), observation(), observation('received')
    expected = merge_observations(submitted, sent, received)
    assert len(expected) == 3
    assert merge_observations(received, sent, submitted, sent) == expected
    assert {item.kind for item in expected} == {'submitted', 'sent', 'received'}


@pytest.mark.parametrize('field', ['workspace_id', 'profile_id', 'provider', 'account_id'])
def test_ids_are_scoped_to_workspace_profile_provider_account(field):
    other = observation(scope=scope(**{field: 'another-scope'}))
    assert len(merge_observations(observation(), other)) == 2


def test_message_identity_not_thread_or_subject_controls_dedup():
    a = observation()
    b = observation(provider_message_id='message-2')
    assert a.provider_thread_id == b.provider_thread_id
    assert len(merge_observations(a, b)) == 2
    assert a.deduplication_key() != observation(provider_message_id='MESSAGE-1').deduplication_key()


@pytest.mark.parametrize('change', [
    {'provider_thread_id': 'different-thread'}, {'send_request_id': 'different-request'},
    {'adapter_id': 'unreviewed-adapter'}, {'provider_occurred_at': TIME},
])
def test_conflicting_same_identity_evidence_is_not_overwritten(change):
    with pytest.raises(ValueError, match='requires reconciliation'):
        merge_observations(observation(), observation(**change))


def test_unknown_is_local_not_provider_failure_and_never_retryable():
    uncertainty = unknown()
    sent = observation(send_request_id=uncertainty.send_request_id)
    assert merge_observations(sent) == (sent,)
    assert uncertainty.reason == 'timeout'  # A sent observation cannot silently erase uncertainty.
    assert uncertainty.source == 'local_transport'
    assert uncertainty.retry_allowed is False
    with pytest.raises(ValidationError):
        unknown(retry_allowed=True)
    with pytest.raises(ValidationError):
        unknown(source='provider_observation')
    with pytest.raises(ValidationError):
        unknown(approved_snapshot_digest='not-a-digest')
    with pytest.raises(ValidationError):
        unknown(detected_at='2026-11-06T12:00:00')


def test_untrusted_model_copy_is_revalidated_on_merge():
    # Pydantic model_copy(update=...) intentionally skips validation; an ingestion
    # boundary must not accept such an object without validating it again.
    forged = observation().model_copy(update={'basis': 'submission_response'})
    with pytest.raises(ValidationError):
        merge_observations(forged)


def test_only_adapter_is_disabled_for_any_claimed_approval_or_provider_payload():
    adapter = DisabledEmailAdapter()
    for method in (adapter.read_history, adapter.submit, adapter.reconcile):
        with pytest.raises(EmailIntegrationDisabled, match='not connected'):
            method(approved(), observation(), unknown(), enabled=True, approved=True)


def test_contract_is_not_imported_by_any_runtime_surface():
    root = Path(__file__).resolve().parents[1]
    surfaces = [root / 'hermes_crm' / name for name in
                ('domain.py', 'plugin.py', 'native_api.py', 'web.py', 'runtime.py', '__init__.py')]
    surfaces += [root / 'dashboard/plugin_api.py', root / 'desktop/plugin.js', root / 'plugin.yaml']
    assert all('email_contracts' not in path.read_text() for path in surfaces)


@pytest.mark.parametrize('code', [*range(32), 127])
def test_identifiers_and_headers_reject_all_c0_and_del_controls(code):
    unsafe = f'prefix{chr(code)}suffix'
    with pytest.raises(ValidationError):
        scope(account_id=unsafe)
    with pytest.raises(ValidationError):
        approved(subject=unsafe)
    with pytest.raises(ValidationError):
        approved(in_reply_to_message_id=unsafe)
    with pytest.raises(ValidationError):
        approved(approval_reference=unsafe)
    with pytest.raises(ValidationError):
        observation(provider_message_id=unsafe)


def test_snapshot_digest_revalidates_bypass_constructed_objects():
    invalid = approved().model_copy(update={'to': ('bad@@example.test',)})
    with pytest.raises(ValidationError):
        invalid.digest()
    forged_scope = scope().model_copy(update={'account_id': 'bad\x00account'})
    invalid = approved().model_copy(update={'scope': forged_scope})
    with pytest.raises(ValidationError):
        invalid.digest()


@pytest.mark.parametrize('code', [code for code in [*range(32), 127] if code not in (9, 10, 13)])
def test_body_rejects_controls_that_could_truncate_or_change_content(code):
    with pytest.raises(ValidationError):
        approved(text_body=f'before{chr(code)}after')


def test_body_preserves_permitted_tab_and_line_endings_exactly():
    body = 'Hello\tthere.\r\nSecond line.\nThird line.\r'
    assert approved(text_body=body).text_body == body
    assert approved(text_body=body).digest() != approved(text_body=body.replace('\r', '')).digest()


@pytest.mark.parametrize('address', [
    'buyer:other@example.test', 'buyer@example.test(comment)',
    '(comment)buyer@example.test', 'buyer@[127.0.0.1]',
    'buyer[other]@example.test', 'buyer]@example.test', 'buyer[@example.test',
])
@pytest.mark.parametrize('field', ['sender', 'to', 'cc', 'bcc'])
def test_bare_address_rejects_header_syntax_that_parsers_can_reinterpret(field, address):
    value = address if field == 'sender' else (address,)
    with pytest.raises(ValidationError):
        approved(**{field: value})


@pytest.mark.parametrize('field', ['sender', 'to', 'cc', 'bcc', 'subject', 'text_body',
                                    'approval_reference', 'in_reply_to_message_id'])
def test_snapshot_fields_reject_invalid_unicode_before_digest(field):
    value = 'a\ud800@example.test'
    if field in ('to', 'cc', 'bcc'):
        value = (value,)
    with pytest.raises(ValidationError):
        approved(**{field: value})


def test_digest_preserves_supported_valid_unicode():
    snapshot = approved(to=('buyer@example.test',), subject='Café ☕', text_body='Hello, 世界.\n')
    assert len(snapshot.digest()) == 64
    assert snapshot.text_body == 'Hello, 世界.\n'


@pytest.mark.parametrize('timestamp', ['0001-01-01T00:00:00+14:00', '9999-12-31T23:59:59-14:00'])
def test_utc_range_errors_are_contract_validation_errors(timestamp):
    for factory, field in ((approved, 'approved_at'), (observation, 'observed_at'),
                           (observation, 'provider_occurred_at'), (unknown, 'detected_at')):
        with pytest.raises(ValidationError):
            factory(**{field: timestamp})


@pytest.mark.parametrize('field', ['workspace_id', 'profile_id', 'provider', 'account_id'])
def test_scope_ids_reject_invalid_unicode(field):
    with pytest.raises(ValidationError):
        scope(**{field: 'prefix\ud800suffix'})


@pytest.mark.parametrize('field', ['adapter_id', 'provider_message_id', 'provider_thread_id',
                                    'provider_submission_id', 'send_request_id'])
def test_provider_ids_reject_invalid_unicode(field):
    with pytest.raises(ValidationError):
        observation('submitted', **{field: 'prefix\ud800suffix'})


@pytest.mark.parametrize('field', ['send_request_id', 'approved_snapshot_digest', 'reason', 'source'])
def test_unknown_outcome_text_rejects_invalid_unicode(field):
    with pytest.raises(ValidationError):
        unknown(**{field: 'prefix\ud800suffix'})
