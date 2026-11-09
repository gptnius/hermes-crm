import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from hermes_crm.gmail_incremental import IncrementalGmailReader
from hermes_crm.gmail_reader import DAY_MS, GmailReadError

MAIL = 'owner@example.com'
START = 1700000000000


def response(data, status=200):
    return SimpleNamespace(status=status, headers={'content-type': 'application/json'},
                           body=json.dumps(data).encode())


def profile(cursor='9001', mail=MAIL):
    return response({'emailAddress': mail, 'historyId': cursor})


def metadata(mid='m1', labels=None, headers=None):
    return response({'id': mid, 'threadId': 't1', 'historyId': '8003',
                     'internalDate': str(START + 1), 'labelIds': labels or ['INBOX'],
                     'payload': {'headers': headers or []}})


class Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, *, timeout):
        assert method == 'GET'
        assert 0 < timeout <= 30
        assert '/users/owner%40example.com/' in url
        self.calls.append((urlsplit(url).path, parse_qs(urlsplit(url).query)))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_bootstrap_captures_start_cursor_and_preserves_address_syntax():
    raw = '=?utf-8?q?X_=3Ca=40evil.test=3E?= <real@example.com>'
    t = Transport(profile('1001'), response({'messages': [{'id': 'm1'}]}),
                  metadata(headers=[{'name': 'From', 'value': raw}, {'name': 'Bcc', 'value': 'secret'}]),
                  profile('9999'))
    result = IncrementalGmailReader(t).bootstrap(MAIL, START, START + 7 * DAY_MS)
    assert result.status == 'complete' and result.checkpoint == '1001'
    assert result.observations[0].raw_headers == (('from', raw),)
    query = t.calls[1][1]
    assert query['includeSpamTrash'] == ['false']
    assert '-in:drafts' in query['q'][0]
    assert t.calls[2][1]['format'] == ['metadata']
    assert set(t.calls[2][1]['metadataHeaders']) == {'Subject', 'From', 'To', 'Cc', 'Date'}


def test_sparse_history_all_pages_deduplicates_and_observes_sent():
    event = {'id': '3007', 'messagesAdded': [{'message': {'id': 'm1'}}]}
    t = Transport(profile(), response({'history': [event], 'historyId': '70001', 'nextPageToken': 'p'}),
                  response({'history': [{'id': '70203', 'labelsAdded': [{'message': {'id': 'm1'}, 'labelIds': ['SENT']}]}], 'historyId': '90007'}),
                  metadata(labels=['SENT']), profile('90009'))
    r = IncrementalGmailReader(t).incremental(MAIL, '1001')
    assert r.status == 'complete' and r.checkpoint == '90007'
    assert len(r.observations) == 1 and r.observations[0].observed_in_sent
    assert [c[1]['startHistoryId'] for c in t.calls if c[0].endswith('/history')] == [['1001'], ['1001']]


@pytest.mark.parametrize('first,last,expected', [('messagesDeleted', 'messagesAdded', 'eligible'), ('messagesAdded', 'messagesDeleted', 'deleted')])
def test_latest_specific_event_controls_tombstone(first, last, expected):
    h = [{'id': '11', first: [{'message': {'id': 'm1'}}]},
         {'id': '29', last: [{'message': {'id': 'm1'}}]}]
    responses = [profile(), response({'history': h, 'historyId': '99'})]
    if expected == 'eligible':
        responses.append(metadata())
    responses.append(profile())
    r = IncrementalGmailReader(Transport(*responses)).incremental(MAIL, '1')
    assert r.status == 'complete' and r.observations[0].status == expected


def test_message_404_is_not_deletion_or_stale_cursor():
    t = Transport(profile(), response({'history': [{'id': '22', 'messages': [{'id': 'm1'}]}], 'historyId': '30'}),
                  response({}, 404), profile())
    r = IncrementalGmailReader(t).incremental(MAIL, '1')
    assert r.status == 'partial' and r.checkpoint is None
    assert r.observations[0].status == 'unavailable'
    assert r.reasons == ('message_unavailable',)


def test_history_404_requires_resync():
    r = IncrementalGmailReader(Transport(profile(), response({}, 404))).incremental(MAIL, '1')
    assert r.status == 'requires_resync' and r.checkpoint is None


@pytest.mark.parametrize('labels', [['DRAFT'], ['SPAM'], ['TRASH']])
def test_excluded_state_is_marked_not_eligible(labels):
    r = IncrementalGmailReader(Transport(profile(), response({'messages': [{'id': 'm1'}]}), metadata(labels=labels), profile())).bootstrap(MAIL, START, START + 30 * DAY_MS)
    assert r.observations[0].status == 'not_eligible'


def test_cycle_and_page_limit_fail_without_cursor():
    page = response({'historyId': '99', 'nextPageToken': 'p'})
    r = IncrementalGmailReader(Transport(profile(), page, page)).incremental(MAIL, '1')
    assert r.reasons == ('page_token_cycle',) and r.checkpoint is None
    r = IncrementalGmailReader(Transport(profile(), page), max_pages=1).incremental(MAIL, '1')
    assert r.reasons == ('page_limit',)


def test_message_limit_and_untrusted_body_fail_closed():
    r = IncrementalGmailReader(Transport(profile(), response({'messages': [{'id': 'a'}, {'id': 'b'}]})), max_messages=1).bootstrap(MAIL, START, START + 7 * DAY_MS)
    assert r.reasons == ('message_limit',)
    bad = metadata()
    data = json.loads(bad.body)
    data['snippet'] = 'PRIVATE TEXT'
    r = IncrementalGmailReader(Transport(profile(), response({'messages': [{'id': 'm1'}]}), response(data))).bootstrap(MAIL, START, START + 7 * DAY_MS)
    assert r.status == 'partial' and r.observations == () and 'PRIVATE' not in repr(r)


def test_identity_change_drops_all_observations():
    r = IncrementalGmailReader(Transport(profile(), response({'messages': [{'id': 'm1'}]}), metadata(), profile(mail='other@example.com'))).bootstrap(MAIL, START, START + 7 * DAY_MS)
    assert r.reasons == ('mailbox_mismatch',) and not r.observations and r.checkpoint is None


def test_provider_failure_is_sanitized():
    r = IncrementalGmailReader(Transport(RuntimeError('SECRET'))).incremental(MAIL, '1')
    assert r.reasons == ('provider_unavailable',) and 'SECRET' not in repr(r)


def test_cancellation_and_deadline():
    t = Transport()
    r = IncrementalGmailReader(t, cancelled=lambda: True).incremental(MAIL, '1')
    assert r.reasons == ('cancelled_or_profile_changed',) and t.calls == []
    times = iter([0, 200])
    r = IncrementalGmailReader(t, clock=lambda: next(times)).incremental(MAIL, '1')
    assert r.reasons == ('deadline_exceeded',)


def test_guard_after_dispatch_prevents_publication():
    calls = iter([True, False])
    t = Transport(profile())
    r = IncrementalGmailReader(t).incremental(MAIL, '1', guard=lambda: next(calls))
    assert r.reasons == ('cancelled_or_profile_changed',) and len(t.calls) == 1


def test_empty_incremental_commits_history_response_not_final_profile():
    r = IncrementalGmailReader(Transport(profile('80'), response({'historyId': '1007'}), profile('9999'))).incremental(MAIL, '23')
    assert r.status == 'complete' and r.checkpoint == '1007'


def test_no_default_transport_and_invalid_limits():
    with pytest.raises(TypeError):
        IncrementalGmailReader()
    with pytest.raises(GmailReadError):
        IncrementalGmailReader(None)
    with pytest.raises(GmailReadError):
        IncrementalGmailReader(Transport(), timeout_seconds=float('nan'))


def test_unsafe_duplicate_headers_are_signalled_without_decoding():
    headers = [{'name': 'To', 'value': 'a@example.com'}, {'name': 'To', 'value': 'b@example.com'},
               {'name': 'From', 'value': 'bad\nheader'}]
    r = IncrementalGmailReader(Transport(profile(), response({'messages': [{'id': 'm1'}]}), metadata(headers=headers), profile())).bootstrap(MAIL, START, START + 7 * DAY_MS)
    assert r.observations[0].header_issues == ('duplicate_to', 'unsafe_from')
    assert all(name != 'from' for name, value in r.observations[0].raw_headers)


def test_same_record_add_delete_is_ambiguous_and_fetches_current_state():
    item = {'id': '20', 'messagesAdded': [{'message': {'id': 'm1'}}],
            'messagesDeleted': [{'message': {'id': 'm1'}}]}
    r = IncrementalGmailReader(Transport(profile(), response({'history': [item], 'historyId': '30'}), response({}, 404), profile())).incremental(MAIL, '1')
    assert r.status == 'partial' and r.observations[0].status == 'unavailable'


def test_repeated_identical_history_record_is_safe():
    item = {'id': '20', 'messagesDeleted': [{'message': {'id': 'm1'}}]}
    r = IncrementalGmailReader(Transport(profile(), response({'history': [item], 'historyId': '30', 'nextPageToken': 'p'}), response({'history': [item], 'historyId': '30'}), profile())).incremental(MAIL, '1')
    assert r.status == 'complete' and len(r.observations) == 1


@pytest.mark.parametrize('history,cursor', [([{'id': '30'}, {'id': '20'}], '40'),
                                         ([{'id': '70'}], '40'), ([], '1')])
def test_invalid_history_order_never_commits(history, cursor):
    r = IncrementalGmailReader(Transport(profile(), response({'history': history, 'historyId': cursor}))).incremental(MAIL, '10')
    assert r.status == 'partial' and r.checkpoint is None


@pytest.mark.parametrize('bad', [{'historyId': '3', 'history': {}},
                                 {'historyId': '3', 'nextPageToken': ''},
                                 {'historyId': '3', 'history': [{'id': '2', 'messagesAdded': [{}]}]},
                                 {'historyId': '3', 'snippet': 'PRIVATE'}])
def test_malformed_history_is_safely_partial(bad):
    r = IncrementalGmailReader(Transport(profile(), response(bad))).incremental(MAIL, '1')
    assert r.status == 'partial' and r.checkpoint is None and not r.observations
    assert 'PRIVATE' not in repr(r)


@pytest.mark.parametrize('role', ['From', 'To'])
@pytest.mark.parametrize('second', ['bad\nheader', 'victim@example.com', 'bad\r\nnot-a-fold'])
@pytest.mark.parametrize('reverse', [False, True])
def test_reader_to_matcher_omits_entire_unsafe_or_duplicate_role(role, second, reverse):
    from hermes_crm.gmail_matching import ContactIdentity, match_headers
    values = ['victim@example.com', second]
    if reverse:
        values.reverse()
    headers = [{'name': role, 'value': value} for value in values]
    r = IncrementalGmailReader(Transport(profile(), response({'messages': [{'id': 'm1'}]}), metadata(headers=headers), profile())).bootstrap(MAIL, START, START + 7 * DAY_MS)
    observed = r.observations[0]
    assert observed.raw_headers == ()
    assert 'duplicate_' + role.lower() in observed.header_issues
    matched = match_headers(observed.raw_headers, [ContactIdentity('victim', 'victim@example.com', 1)], [MAIL])
    assert matched.matches == ()


def test_reader_to_matcher_unfolds_only_ordinary_header_whitespace():
    from hermes_crm.gmail_matching import ContactIdentity, match_headers
    headers = [{'name': 'From', 'value': 'owner@example.com'},
               {'name': 'To', 'value': 'Victim\r\n \t<victim@example.com>,\r\n\t Other <other@example.com>'}]
    r = IncrementalGmailReader(Transport(profile(), response({'messages': [{'id': 'm1'}]}), metadata(headers=headers), profile())).bootstrap(MAIL, START, START + 7 * DAY_MS)
    observed = r.observations[0]
    assert observed.header_issues == ()
    assert observed.raw_headers[1] == ('to', 'Victim <victim@example.com>, Other <other@example.com>')
    matched = match_headers(observed.raw_headers, [ContactIdentity('victim', 'victim@example.com', 1)], [MAIL])
    assert matched.contact_ids == ('victim',)


def test_empty_final_history_page_cannot_regress_terminal_cursor():
    t = Transport(profile(), response({'history': [{'id': '90', 'messagesDeleted': [{'message': {'id': 'm1'}}]}], 'historyId': '100', 'nextPageToken': 'p'}),
                  response({'historyId': '20'}))
    r = IncrementalGmailReader(t).incremental(MAIL, '10')
    assert r.status == 'partial' and r.checkpoint is None and r.observations == ()
    assert r.reasons == ('invalid_history_order',)


def test_verify_mailbox_only_reads_profiles_and_returns_frozen_observations():
    from dataclasses import FrozenInstanceError
    t = Transport(profile('20'), profile('99'))
    verified = IncrementalGmailReader(t).verify_mailbox(MAIL)
    assert verified.mailbox == MAIL and verified.checkpoint == '99'
    assert len(t.calls) == 2
    assert all(path.endswith('/profile') and params == {'fields': ['emailAddress,historyId']}
               for path, params in t.calls)
    assert not hasattr(verified, 'subject')
    with pytest.raises(FrozenInstanceError):
        verified.mailbox = 'other@example.com'


@pytest.mark.parametrize('responses,code', [([profile(mail='other@example.com')], 'mailbox_mismatch'),
                                            ([profile(), profile(mail='other@example.com')], 'mailbox_mismatch'),
                                            ([profile('30'), profile('20')], 'invalid_history_order'),
                                            ([RuntimeError('SECRET')], 'provider_unavailable')])
def test_verify_mailbox_fixed_failures(responses, code):
    with pytest.raises(GmailReadError, match='^' + code + '$'):
        IncrementalGmailReader(Transport(*responses)).verify_mailbox(MAIL)


def test_verify_mailbox_cancelled_and_version_guard_change():
    t = Transport()
    with pytest.raises(GmailReadError, match='^cancelled_or_profile_changed$'):
        IncrementalGmailReader(t, cancelled=lambda: True).verify_mailbox(MAIL)
    assert t.calls == []
    t = Transport(profile())
    versions = iter([True, False])
    with pytest.raises(GmailReadError, match='^cancelled_or_profile_changed$'):
        IncrementalGmailReader(t).verify_mailbox(MAIL, guard=lambda: next(versions))
    assert len(t.calls) == 1


def test_verify_mailbox_deadline_and_validation_limits():
    t = Transport()
    ticks = iter([0, 301])
    with pytest.raises(GmailReadError, match='^deadline_exceeded$'):
        IncrementalGmailReader(t, clock=lambda: next(ticks)).verify_mailbox(MAIL)
    assert t.calls == []
    with pytest.raises(GmailReadError, match='^invalid_email$'):
        IncrementalGmailReader(t).verify_mailbox('me')
    with pytest.raises(GmailReadError, match='^invalid_limits$'):
        IncrementalGmailReader(t, deadline_seconds=301)
