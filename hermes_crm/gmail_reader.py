"""Bounded manual contact reads through Hermes's own optional OAuth entry.

No account discovery or OAuth setup happens on import. Callers own consent,
profile/activation guards and atomic publication. Endpoint identity observations
are not an atomic grant lease; trusted operators must not rebind during a scan.
Only a captured own-mailbox address is used, never ``me`` or a fallback grant.
The host helper buffers bytes before our 1 MiB check: this is not a transport
streaming memory limit. Deadlines do not instantly cancel an in-flight request.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from email.header import decode_header, make_header
from urllib.parse import quote, urlencode

PROVIDER_ID = 'gmail-history-readonly'
SCOPES = ('https://www.googleapis.com/auth/gmail.readonly', 'openid',
          'https://www.googleapis.com/auth/userinfo.email')
ISSUER = 'https://accounts.google.com'
USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'
MESSAGE_FIELDS = 'id,threadId,labelIds,historyId,internalDate,payload/headers'
HEADER_NAMES = ('Subject', 'From', 'To', 'Cc', 'Date')
DAY_MS = 86_400_000


class GmailReadError(RuntimeError):
    """Fixed safe code only. Never include a provider exception or response."""


@dataclass(frozen=True)
class IdentityBinding:
    subject: str
    mailbox: str
    issuer: str = ISSUER


@dataclass(frozen=True)
class MessageMetadata:
    message_id: str
    thread_id: str
    internal_date_ms: int
    labels: tuple[str, ...]
    display_headers: tuple[tuple[str, str], ...]
    header_issues: tuple[str, ...]
    description: str
    history_id: str = ''


@dataclass(frozen=True)
class ScanResult:
    messages: tuple[MessageMetadata, ...]
    coverage: str
    gaps: tuple[str, ...]
    pages_read: int


def validate_email(value):
    """Conservative ASCII bare mailbox, preserving exact case/dots/plus tags.

    Quoted local parts, address lists, IDNs and Gmail query grammar are rejected,
    not guessed or normalized. Ordinary dotted, hyphenated and plus accounts work.
    """
    if not isinstance(value, str) or len(value) > 254 or value.count('@') != 1:
        raise GmailReadError('invalid_email')
    local, domain = value.split('@')
    if (not 1 <= len(local) <= 64 or
            not re.fullmatch(r"[A-Za-z0-9_+%-]+(?:\.[A-Za-z0-9_+%-]+)*", local) or
            len(domain) > 253 or '.' not in domain or
            any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p)
                for p in domain.split('.'))):
        raise GmailReadError('invalid_email')
    return value


def contact_query(contact_email, start_ms, end_ms):
    email = validate_email(contact_email)
    if (type(start_ms) is not int or type(end_ms) is not int or start_ms < 1000 or
            end_ms > 253402300799000 or end_ms - start_ms not in (7 * DAY_MS, 30 * DAY_MS)):
        raise GmailReadError('invalid_window')
    # One-second superset; metadata is locally filtered to exact millisecond bounds.
    return (f'{{from:{email} to:{email} cc:{email}}} '
            f'after:{start_ms // 1000 - 1} before:{(end_ms + 999) // 1000 + 1} -in:drafts')


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise GmailReadError('invalid_message_id')
    return value


def _shape(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise GmailReadError('invalid_response_shape')


def _decode(response):
    if (not isinstance(response.headers, dict) or
            any(not isinstance(k, str) or not isinstance(v, str) for k, v in response.headers.items())):
        raise GmailReadError('invalid_response_headers')
    types = [v for k, v in response.headers.items() if k.lower() == 'content-type']
    if len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json':
        raise GmailReadError('invalid_content_type')
    if type(response.body) is not bytes or len(response.body) > 1_048_576:
        raise GmailReadError('invalid_response_size')
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise GmailReadError('duplicate_json_key')
            result[k] = v
        return result
    def invalid(_):
        raise GmailReadError('invalid_json')
    failed = False
    try:
        value = json.loads(response.body.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)
    except Exception:
        failed = True
    if failed:
        raise GmailReadError('invalid_json')
    if not isinstance(value, dict):
        raise GmailReadError('invalid_response_shape')
    return value


def _header(value):
    if not isinstance(value, str) or len(value) > 4096:
        return '(unsupported header)', True
    failed = False
    try:
        value = re.sub(r'\r\n[ \t]+', ' ', value)
        value = str(make_header(decode_header(value)))
        if len(value) > 4096 or any(unicodedata.category(c).startswith('C') for c in value):
            failed = True
    except Exception:
        failed = True
    return ('(unsupported header)', True) if failed else (value, False)


def _metadata(data, expected_id, start_ms, end_ms):
    _shape(data, ('id', 'threadId', 'labelIds', 'historyId', 'internalDate', 'payload'),
           ('id', 'threadId', 'internalDate', 'historyId'))
    if _identifier(data['id']) != expected_id:
        raise GmailReadError('message_id_mismatch')
    thread = _identifier(data['threadId'])
    date = data['internalDate']
    if not isinstance(date, str) or not re.fullmatch(r'[0-9]{1,15}', date):
        raise GmailReadError('invalid_message_date')
    if 'historyId' in data and (not isinstance(data['historyId'], str) or
                              not re.fullmatch(r'[1-9][0-9]{0,39}', data['historyId'])):
        raise GmailReadError('invalid_history_id')
    labels = data.get('labelIds', [])
    if not isinstance(labels, list) or len(labels) > 100:
        raise GmailReadError('invalid_labels')
    labels = tuple(_identifier(label) for label in labels)
    if len(set(labels)) != len(labels):
        raise GmailReadError('invalid_labels')
    payload = data.get('payload', {})
    _shape(payload, ('headers',))
    headers = payload.get('headers', [])
    if not isinstance(headers, list) or len(headers) > 100:
        raise GmailReadError('invalid_headers')
    display, issues, seen = {}, [], set()
    for header in headers:
        _shape(header, ('name', 'value'), ('name', 'value'))
        if not isinstance(header['name'], str) or not isinstance(header['value'], str):
            raise GmailReadError('invalid_headers')
        name = header['name'].lower()
        if name not in {n.lower() for n in HEADER_NAMES}:
            # In particular Bcc is never retained. Unexpected content headers fail closed.
            if name == 'bcc':
                continue
            raise GmailReadError('unexpected_header')
        if name in seen:
            display[name] = '(unsupported header)'
            issues.append('duplicate_' + name)
        else:
            display[name], unsafe = _header(header['value'])
            if unsafe:
                issues.append('unsafe_' + name)
        seen.add(name)
    if set(labels) & {'DRAFT', 'SPAM', 'TRASH'} or not start_ms <= int(date) < end_ms:
        return None
    return MessageMetadata(expected_id, thread, int(date), labels, tuple(display.items()),
                           tuple(sorted(set(issues))), 'observed_in_sent' if 'SENT' in labels else 'mailbox_item',
                           data['historyId'])


def _host_transport(provider, method, url, *, timeout):
    from hermes_cli.plugin_provider_requests import credentialed_provider_request
    return credentialed_provider_request(provider, method, url, timeout=timeout)


class GmailReader:
    def __init__(self, transport=None, *, cancelled=None, timeout_seconds=30,
                 max_pages=10, max_messages=1000, deadline_seconds=120, clock=time.monotonic):
        if (type(max_pages) is not int or not 1 <= max_pages <= 10 or
                type(max_messages) is not int or not 1 <= max_messages <= 1000 or
                not 0 < timeout_seconds <= 30 or not 0 < deadline_seconds <= 300):
            raise GmailReadError('invalid_limits')
        self.transport = transport or _host_transport
        self.cancelled = cancelled or (lambda: False)
        self.timeout_seconds = timeout_seconds
        self.max_pages, self.max_messages = max_pages, max_messages
        self.deadline_seconds, self.clock = deadline_seconds, clock

    def _check(self, guard, deadline):
        failed = False
        try:
            if self.cancelled() or guard() is False:
                failed = True
        except Exception:
            failed = True
        if failed:
            raise GmailReadError('cancelled_or_profile_changed')
        if self.clock() >= deadline:
            raise GmailReadError('deadline_exceeded')

    def _get(self, url, guard, deadline, *, missing_ok=False):
        self._check(guard, deadline)
        failed = False
        try:
            response = self.transport(PROVIDER_ID, 'GET', url,
                                      timeout=min(self.timeout_seconds, deadline - self.clock()))
        except Exception:
            failed = True
        self._check(guard, deadline)
        if failed:
            raise GmailReadError('provider_unavailable')
        if type(getattr(response, 'status', None)) is not int:
            raise GmailReadError('invalid_provider_response')
        if response.status == 404 and missing_ok:
            return None
        if response.status != 200:
            raise GmailReadError('provider_status')
        try:
            result = _decode(response)
        except Exception:
            failed = True
        if failed:
            raise GmailReadError('invalid_provider_response')
        return result

    def _identity(self, expected_mailbox, guard, deadline):
        info = self._get(USERINFO_URL, guard, deadline)
        subject = info.get('sub')
        if (not isinstance(subject, str) or not re.fullmatch(r'[!-~]{1,255}', subject) or
                info.get('email_verified') is not True or info.get('email') != expected_mailbox):
            raise GmailReadError('identity_mismatch')
        profile = self._get(self._base(expected_mailbox) + '/profile?' + urlencode({'fields': 'emailAddress'}),
                            guard, deadline)
        _shape(profile, ('emailAddress',), ('emailAddress',))
        if profile['emailAddress'] != expected_mailbox:
            raise GmailReadError('mailbox_mismatch')
        return IdentityBinding(subject, expected_mailbox)

    @staticmethod
    def _base(mailbox):
        return 'https://gmail.googleapis.com/gmail/v1/users/' + quote(mailbox, safe='')

    def verify_identity(self, expected_mailbox, guard):
        validate_email(expected_mailbox)
        deadline = self.clock() + self.deadline_seconds
        binding = self._identity(expected_mailbox, guard, deadline)
        if self._identity(expected_mailbox, guard, deadline) != binding:
            raise GmailReadError('identity_changed')
        return binding

    def scan_contact(self, binding, contact_email, start_ms, end_ms, guard):
        query = contact_query(contact_email, start_ms, end_ms)
        if not isinstance(binding, IdentityBinding) or binding.issuer != ISSUER:
            raise GmailReadError('invalid_binding')
        validate_email(binding.mailbox)
        deadline = self.clock() + self.deadline_seconds
        if self._identity(binding.mailbox, guard, deadline) != binding:
            raise GmailReadError('identity_changed')
        messages, gaps, ids, tokens = [], [], set(), set()
        token, pages = None, 0
        while pages < self.max_pages:
            params = {'q': query, 'includeSpamTrash': 'false', 'maxResults': '100',
                      'fields': 'messages(id,threadId),nextPageToken,resultSizeEstimate'}
            if token is not None:
                params['pageToken'] = token
            data = self._get(self._base(binding.mailbox) + '/messages?' + urlencode(params), guard, deadline)
            pages += 1
            _shape(data, ('messages', 'nextPageToken', 'resultSizeEstimate'))
            if 'resultSizeEstimate' in data and (type(data['resultSizeEstimate']) is not int or data['resultSizeEstimate'] < 0):
                raise GmailReadError('invalid_estimate')
            records = data.get('messages', [])
            if not isinstance(records, list) or len(records) > 100:
                raise GmailReadError('invalid_message_list')
            for item in records:
                _shape(item, ('id', 'threadId'), ('id',))
                mid = _identifier(item['id'])
                if 'threadId' in item:
                    _identifier(item['threadId'])
                if mid in ids:
                    gaps.append('duplicate_message_id')
                    continue
                if len(ids) >= self.max_messages:
                    gaps.append('message_limit')
                    break
                ids.add(mid)
                params_get = [('format', 'metadata'), ('fields', MESSAGE_FIELDS)]
                params_get.extend(('metadataHeaders', h) for h in HEADER_NAMES)
                raw = self._get(self._base(binding.mailbox) + '/messages/' + mid + '?' + urlencode(params_get),
                                guard, deadline, missing_ok=True)
                if raw is None:
                    gaps.append('message_unavailable')
                    continue
                projected = _metadata(raw, mid, start_ms, end_ms)
                if projected is not None:
                    messages.append(projected)
            token = data.get('nextPageToken')
            if token is not None:
                if (not isinstance(token, str) or not 1 <= len(token) <= 2048 or
                        any(unicodedata.category(c).startswith('C') for c in token)):
                    raise GmailReadError('invalid_page_token')
                if token in tokens:
                    gaps.append('page_token_cycle')
                    break
                tokens.add(token)
            if token is None or 'message_limit' in gaps:
                break
            if len(ids) >= self.max_messages:
                gaps.append('message_limit')
                break
        else:
            gaps.append('page_limit')
        if self._identity(binding.mailbox, guard, deadline) != binding:
            raise GmailReadError('identity_changed')
        self._check(guard, deadline)
        return ScanResult(tuple(messages), 'partial' if gaps else 'complete_query', tuple(sorted(set(gaps))), pages)
