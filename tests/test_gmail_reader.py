"""Synthetic-only production-reader tests; all real network entry points denied."""
import json
import socket
import sys
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlsplit

import pytest

from hermes_crm.gmail_reader import (
    DAY_MS, HEADER_NAMES, ISSUER, MESSAGE_FIELDS, PROVIDER_ID, SCOPES,
    GmailReader, GmailReadError, IdentityBinding, contact_query, validate_email,
)

START = 1_780_000_000_000
END = START + 7 * DAY_MS
BINDING = IdentityBinding('synthetic-subject', 'owner@example.com')


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('Real network forbidden')
    monkeypatch.setattr(socket, 'create_connection', deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket.socket, 'connect_ex', deny)


@dataclass
class Response:
    status: int = 200
    headers: dict = None
    body: bytes = b'{}'

    def __post_init__(self):
        if self.headers is None:
            self.headers = {'content-type': 'application/json; charset=utf-8'}


def response(data, status=200):
    return Response(status=status, body=json.dumps(data).encode())


def message(mid='m1', **extra):
    return {'id': mid, 'threadId': 'thread1', 'internalDate': str(START),
            'historyId': '9007199254740993', 'labelIds': ['SENT'],
            'payload': {'headers': [{'name': 'Subject', 'value': 'Hello'}]}, **extra}


class Transport:
    def __init__(self, pages=None, messages=None):
        self.pages = list(pages if pages is not None else [{'messages': [{'id': 'm1'}]}])
        self.messages = messages or {'m1': message()}
        self.calls = []
        self.identity_calls = 0
        self.subject = BINDING.subject
        self.mailbox = BINDING.mailbox
        self.verified = True
        self.after = None

    def __call__(self, provider, method, url, *, timeout):
        assert provider == PROVIDER_ID and method == 'GET' and 0 < timeout <= 30
        self.calls.append(url)
        parsed = urlsplit(url)
        assert parsed.scheme == 'https' and not parsed.fragment
        if parsed.hostname == 'openidconnect.googleapis.com':
            assert parsed.path == '/v1/userinfo'
            self.identity_calls += 1
            result = response({'sub': self.subject, 'email': self.mailbox, 'email_verified': self.verified})
        else:
            assert parsed.hostname == 'gmail.googleapis.com'
            assert '/users/owner%40example.com/' in parsed.path
            if parsed.path.endswith('/profile'):
                assert parse_qs(parsed.query) == {'fields': ['emailAddress']}
                result = response({'emailAddress': self.mailbox})
            elif parsed.path.endswith('/messages'):
                result = response(self.pages.pop(0))
            else:
                result = self.messages[parsed.path.rsplit('/', 1)[1]]
                if isinstance(result, dict):
                    result = response(result)
        if self.after:
            self.after(url)
        return result


def scan(transport=None, **kwargs):
    return GmailReader(transport or Transport(), **kwargs).scan_contact(
        BINDING, 'contact+tag@example.com', START, END, lambda: True)


def test_scopes_import_and_capture_are_lazy_and_minimal():
    assert SCOPES == ('https://www.googleapis.com/auth/gmail.readonly', 'openid',
                      'https://www.googleapis.com/auth/userinfo.email')
    assert 'hermes_cli.plugin_provider_requests' not in sys.modules
    transport = Transport()
    assert GmailReader(transport).verify_identity(BINDING.mailbox, lambda: True) == BINDING
    assert transport.identity_calls == 2
    assert len(transport.calls) == 4


def test_contact_query_preserves_exact_address_and_bounded_window():
    address = 'Some.Name+tag@sub.example.com'
    assert validate_email(address) == address
    q = contact_query(address, START, END)
    assert f'from:{address}' in q and f'to:{address}' in q and f'cc:{address}' in q
    assert 'bcc:' not in q and '-in:drafts' in q
    assert f'after:{START // 1000 - 1}' in q
    contact_query(address, START, START + 30 * DAY_MS)


@pytest.mark.parametrize('email', ['a@example.com OR in:anywhere', 'a@example.com\n',
    'Name <a@example.com>', 'a@b.com,b@b.com', 'a@b.com;to:evil@b.com', 'a"@b.com',
    'a{b}@example.com', 'a|b@example.com', 'a*b@example.com', '.a@example.com',
    'a..b@example.com', 'a@-bad.com', 'a@bad..com', 'a@bad.com.', 'é@example.com', 'a@localhost'])
def test_query_injection_and_ambiguous_addresses_rejected_before_transport(email):
    transport = Transport()
    with pytest.raises(GmailReadError, match='invalid_email'):
        GmailReader(transport).scan_contact(BINDING, email, START, END, lambda: True)
    assert not transport.calls


@pytest.mark.parametrize('start,end', [(START, START + DAY_MS), (True, END), (START, START),
                                      (START, END + 1), (0, 7 * DAY_MS)])
def test_invalid_windows(start, end):
    with pytest.raises(GmailReadError):
        contact_query('a@example.com', start, end)


def test_fixed_request_allowlists_metadata_and_weak_sent_semantics():
    transport = Transport()
    result = scan(transport)
    assert result.coverage == 'complete_query' and result.gaps == ()
    assert result.messages[0].description == 'observed_in_sent'
    assert result.messages[0].history_id == '9007199254740993'
    assert not hasattr(result.messages[0], 'provider_occurred_at')
    assert transport.identity_calls == 2
    query = parse_qs(urlsplit(transport.calls[2]).query)
    assert query['includeSpamTrash'] == ['false'] and query['maxResults'] == ['100']
    get = parse_qs(urlsplit(transport.calls[3]).query)
    assert get['format'] == ['metadata'] and get['fields'] == [MESSAGE_FIELDS]
    assert get['metadataHeaders'] == list(HEADER_NAMES)
    assert 'Bcc' not in get['metadataHeaders']
    assert scan(Transport(messages={'m1': message(labelIds=['INBOX'])})).messages[0].description == 'mailbox_item'


@pytest.mark.parametrize('changes', [{'sub': 'different'}, {'verified': False}, {'mailbox': 'other@example.com'}])
def test_bad_identity_never_reads_messages(changes):
    transport = Transport()
    for key, value in changes.items():
        setattr(transport, 'subject' if key == 'sub' else key, value)
    with pytest.raises(GmailReadError):
        scan(transport)
    assert len(transport.calls) == (2 if 'sub' in changes else 1)


def test_identity_replacement_at_end_discards_all_metadata():
    transport = Transport()
    def changed(url):
        if '/messages/' in url:
            transport.subject = 'other-subject'
    transport.after = changed
    with pytest.raises(GmailReadError, match='identity_changed'):
        scan(transport)


def test_profile_guard_before_after_each_request_and_cancel():
    transport = Transport()
    count = []
    result = GmailReader(transport).scan_contact(BINDING, 'a@example.com', START, END, lambda: count.append(1))
    assert len(count) == len(transport.calls) * 2 + 1
    assert result.messages
    transport = Transport()
    state = {'cancelled': False}
    transport.after = lambda _: state.update(cancelled=True)
    with pytest.raises(GmailReadError, match='cancelled_or_profile_changed'):
        scan(transport, cancelled=lambda: state['cancelled'])
    assert len(transport.calls) == 1
    with pytest.raises(GmailReadError, match='cancelled_or_profile_changed'):
        GmailReader(Transport()).verify_identity(BINDING.mailbox, lambda: False)


def test_guard_exception_is_redacted_without_chain():
    def guard():
        raise RuntimeError('secret-profile-data')
    with pytest.raises(GmailReadError) as exc:
        GmailReader(Transport()).verify_identity(BINDING.mailbox, guard)
    assert 'secret' not in str(exc.value) and exc.value.__context__ is None


def test_deadline_after_dispatched_request_rejects_response():
    transport = Transport()
    now = [0]
    transport.after = lambda _: now.__setitem__(0, 31)
    with pytest.raises(GmailReadError, match='deadline_exceeded'):
        scan(transport, deadline_seconds=30, clock=lambda: now[0])
    assert len(transport.calls) == 1


def test_empty_pages_continue_and_opaque_token_only_in_query():
    transport = Transport(pages=[{'nextPageToken': 'https://evil.invalid/?x=1'},
                                 {'messages': [{'id': 'm1'}]}])
    result = scan(transport)
    assert result.pages_read == 2 and result.coverage == 'complete_query'
    assert parse_qs(urlsplit(transport.calls[3]).query)['pageToken'] == ['https://evil.invalid/?x=1']


@pytest.mark.parametrize('pages,gap', [([{'nextPageToken': 'x'}, {'nextPageToken': 'x'}], 'page_token_cycle'),
    ([{'messages': [{'id': 'm1'}, {'id': 'm1'}]}], 'duplicate_message_id')])
def test_loops_and_duplicates_are_partial(pages, gap):
    result = scan(Transport(pages=pages))
    assert result.coverage == 'partial' and gap in result.gaps


def test_limits_and_missing_message_report_partial_not_absence():
    assert scan(Transport(pages=[{'nextPageToken': 'x'}]), max_pages=1).gaps == ('page_limit',)
    assert scan(Transport(pages=[{'messages': [{'id': 'm1'}, {'id': 'm2'}]}]), max_messages=1).gaps == ('message_limit',)
    result = scan(Transport(messages={'m1': response({}, 404)}))
    assert result.gaps == ('message_unavailable',) and not result.messages


@pytest.mark.parametrize('extra', [{'id': 'wrong'}, {'snippet': 'secret'}, {'raw': 'secret'},
    {'payload': {'body': {'data': 'secret'}}}, {'payload': {'parts': []}},
    {'historyId': 123}, {'internalDate': 'nan'}, {'labelIds': ['SENT', 'SENT']},
    {'payload': {'headers': [{'name': 'Content-Type', 'value': 'text/html'}]}}])
def test_malformed_or_content_response_fails_closed(extra):
    with pytest.raises(GmailReadError):
        scan(Transport(messages={'m1': message(**extra)}))


@pytest.mark.parametrize('extra', [{'labelIds': ['DRAFT']}, {'labelIds': ['SPAM']},
    {'labelIds': ['TRASH']}, {'internalDate': str(START - 1)}, {'internalDate': str(END)}])
def test_local_window_and_excluded_labels(extra):
    assert not scan(Transport(messages={'m1': message(**extra)})).messages


def test_missing_headers_safe_and_bcc_never_retained():
    assert scan(Transport(messages={'m1': message(payload={})})).messages[0].display_headers == ()
    headers = [{'name': 'Subject', 'value': '=?utf-8?q?Hi_=E2=9C=93?='},
               {'name': 'From', 'value': 'One\r\n sender <a@example.com>'},
               {'name': 'Bcc', 'value': 'private@example.com'}]
    data = scan(Transport(messages={'m1': message(payload={'headers': headers})})).messages[0]
    assert dict(data.display_headers) == {'subject': 'Hi ✓', 'from': 'One sender <a@example.com>'}


@pytest.mark.parametrize('value', ['bad\r\nBcc: x', 'bad\x00', 'bad\u202e', 'x' * 4097,
                                  '=?not-a-charset?b?YWJj?='])
def test_unsafe_headers_redacted(value):
    data = scan(Transport(messages={'m1': message(payload={'headers': [{'name': 'Subject', 'value': value}]})})).messages[0]
    assert data.display_headers == (('subject', '(unsupported header)'),)
    assert data.header_issues == ('unsafe_subject',)


@pytest.mark.parametrize('bad', [Response(302), Response(401), Response(403), Response(429), Response(500),
    Response(body=b'{"id":"m1","id":"m2"}'), Response(body=b'NaN'),
    Response(body=b'\xff'), Response(body=b'x' * 1_048_577),
    Response(headers={'content-type': 'text/html'}), Response(body=b'[]')])
def test_bad_provider_results_never_retry_or_fallback(bad):
    calls = []
    def transport(*args, **kwargs):
        calls.append(args)
        return bad
    with pytest.raises(GmailReadError):
        scan(transport)
    assert len(calls) == 1


def test_provider_exception_is_redacted_without_chaining():
    calls = []
    def transport(*args, **kwargs):
        calls.append(1)
        raise RuntimeError('secret bearer / private URL')
    with pytest.raises(GmailReadError) as exc:
        scan(transport)
    assert str(exc.value) == 'provider_unavailable'
    assert exc.value.__context__ is None and len(calls) == 1
