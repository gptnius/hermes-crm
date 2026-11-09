"""Pure, bounded Gmail metadata sync; no default transport or credential discovery.

Transport is a required callable ``transport('GET', url, timeout=seconds)`` returning
status, headers and body like gmail_reader. It must enforce the passed timeout and
bind the explicit mailbox to an already authorized own-account grant. Profile
checks detect mailbox changes, not an atomic grant lease. Cancellation/deadlines
are checked around each request and cannot interrupt a blocking transport.

History IDs are opaque decimal strings, never incremented. A bootstrap retains
its *starting* profile cursor so the next sync replays changes during the scan.
Consumers must atomically publish complete results and their checkpoint, and
must not publish partial results as a complete snapshot. SENT is observation,
not delivery confirmation. No sending, credentials or provider wiring exists.
API: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import time
import unicodedata
from urllib.parse import quote, urlencode

from .gmail_reader import (DAY_MS, HEADER_NAMES, MESSAGE_FIELDS, GmailReadError,
                           _decode, _identifier, _shape, validate_email)


@dataclass(frozen=True)
class MailboxVerification:
    """Observed mailbox and cursor, not an immutable subject or grant lease."""

    mailbox: str
    checkpoint: str


@dataclass(frozen=True)
class Observation:
    message_id: str
    thread_id: str = ''
    internal_date_ms: int | None = None
    history_id: str = ''
    labels: tuple[str, ...] = ()
    raw_headers: tuple[tuple[str, str], ...] = ()
    header_issues: tuple[str, ...] = ()
    status: str = 'eligible'
    observed_in_sent: bool = False


@dataclass(frozen=True)
class SyncResult:
    status: str
    checkpoint: str | None
    observations: tuple[Observation, ...]
    coverage: str
    reasons: tuple[str, ...] = ()
    pages_read: int = 0


def _history_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,39}', value):
        raise GmailReadError('invalid_history_id')
    return value


def _labels(value):
    if not isinstance(value, list) or len(value) > 100:
        raise GmailReadError('invalid_labels')
    result = tuple(_identifier(v) for v in value)
    if len(set(result)) != len(result):
        raise GmailReadError('invalid_labels')
    return result


def _observation(data, expected_id, window):
    _shape(data, ('id', 'threadId', 'internalDate', 'historyId', 'labelIds', 'payload'),
           ('id', 'threadId', 'internalDate', 'historyId'))
    if _identifier(data['id']) != expected_id:
        raise GmailReadError('message_id_mismatch')
    thread = _identifier(data['threadId'])
    history = _history_id(data['historyId'])
    date = data['internalDate']
    if not isinstance(date, str) or not re.fullmatch(r'[0-9]{1,15}', date):
        raise GmailReadError('invalid_message_date')
    labels = _labels(data.get('labelIds', []))
    payload = data.get('payload', {})
    _shape(payload, ('headers',))
    headers = payload.get('headers', [])
    if not isinstance(headers, list) or len(headers) > 100:
        raise GmailReadError('invalid_headers')
    raw, issues, seen, invalid_roles = [], [], set(), set()
    for header in headers:
        _shape(header, ('name', 'value'), ('name', 'value'))
        name, value = header['name'], header['value']
        if not isinstance(name, str) or not isinstance(value, str):
            raise GmailReadError('invalid_headers')
        name = name.lower()
        if name == 'bcc':
            continue
        if name not in {n.lower() for n in HEADER_NAMES}:
            raise GmailReadError('unexpected_header')
        if name in seen:
            issues.append('duplicate_' + name)
            invalid_roles.add(name)
        seen.add(name)
        # Only RFC5322 folding/linear whitespace is normalized. Never decode
        # RFC2047 words into address syntax. Any unsafe or duplicate instance
        # removes the whole role, including earlier otherwise safe instances.
        unfolded = re.sub(r'\r\n[ \t]+', ' ', value).replace('\t', ' ')
        if len(value) > 4096 or any(unicodedata.category(c).startswith('C') for c in unfolded):
            issues.append('unsafe_' + name)
            invalid_roles.add(name)
        else:
            raw.append((name, unfolded))
    raw = [(name, value) for name, value in raw if name not in invalid_roles]
    status = 'eligible'
    if set(labels) & {'DRAFT', 'SPAM', 'TRASH'} or (window and not window[0] <= int(date) < window[1]):
        status = 'not_eligible'
    return Observation(expected_id, thread, int(date), history, labels, tuple(raw),
                       tuple(sorted(set(issues))), status, 'SENT' in labels)


class IncrementalGmailReader:
    def __init__(self, transport, *, cancelled=lambda: False, clock=time.monotonic,
                 max_pages=10, max_messages=1000, timeout_seconds=30, deadline_seconds=120):
        if not callable(transport) or not callable(cancelled) or not callable(clock):
            raise GmailReadError('invalid_transport')
        if (type(max_pages) is not int or not 1 <= max_pages <= 100 or
                type(max_messages) is not int or not 1 <= max_messages <= 10000 or
                type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or
                not 0 < timeout_seconds <= 30 or
                type(deadline_seconds) not in (int, float) or not math.isfinite(deadline_seconds) or
                not 0 < deadline_seconds <= 300):
            raise GmailReadError('invalid_limits')
        self.transport, self.cancelled, self.clock = transport, cancelled, clock
        self.max_pages, self.max_messages = max_pages, max_messages
        self.timeout_seconds, self.deadline_seconds = timeout_seconds, deadline_seconds

    def _check(self, guard, deadline):
        failed = False
        try:
            failed = bool(self.cancelled()) or guard() is False
        except Exception:
            failed = True
        if failed:
            raise GmailReadError('cancelled_or_profile_changed')
        if self.clock() >= deadline:
            raise GmailReadError('deadline_exceeded')

    def _get(self, base, path, params, guard, deadline, missing=None):
        self._check(guard, deadline)
        failed = False
        try:
            response = self.transport('GET', base + path + '?' + urlencode(params, doseq=True),
                                      timeout=min(self.timeout_seconds, deadline - self.clock()))
        except Exception:
            failed = True
        self._check(guard, deadline)
        if failed:
            raise GmailReadError('provider_unavailable')
        if type(getattr(response, 'status', None)) is not int:
            raise GmailReadError('invalid_provider_response')
        if response.status == 404 and missing:
            raise GmailReadError(missing)
        if response.status != 200:
            raise GmailReadError('provider_status')
        failed = False
        try:
            data = _decode(response)
        except Exception:
            failed = True
        if failed:
            raise GmailReadError('invalid_provider_response')
        return data

    def _profile(self, mailbox, base, guard, deadline):
        data = self._get(base, '/profile', {'fields': 'emailAddress,historyId'}, guard, deadline)
        _shape(data, ('emailAddress', 'historyId'), ('emailAddress', 'historyId'))
        if data['emailAddress'] != mailbox:
            raise GmailReadError('mailbox_mismatch')
        return _history_id(data['historyId'])

    def verify_mailbox(self, mailbox, guard=lambda: True):
        """Read the explicit own-mailbox profile twice, without reading messages.

        Caller owns action-time approval and must fence connection/profile
        versions through ``guard``. Returns observations, not an atomic grant
        lease or immutable Google subject. Failures raise fixed GmailReadError
        codes; transport response/error details are never exposed.
        """
        validate_email(mailbox)
        base = 'https://gmail.googleapis.com/gmail/v1/users/' + quote(mailbox, safe='')
        deadline = self.clock() + self.deadline_seconds
        initial = self._profile(mailbox, base, guard, deadline)
        final = self._profile(mailbox, base, guard, deadline)
        if int(final) < int(initial):
            raise GmailReadError('invalid_history_order')
        self._check(guard, deadline)
        return MailboxVerification(mailbox, final)

    def bootstrap(self, mailbox, start_ms, end_ms, guard=lambda: True):
        if (type(start_ms) is not int or type(end_ms) is not int or start_ms < 1000 or
                end_ms > 253402300799000 or end_ms - start_ms not in (7 * DAY_MS, 30 * DAY_MS)):
            raise GmailReadError('invalid_window')
        return self._sync(mailbox, None, (start_ms, end_ms), guard)

    def incremental(self, mailbox, checkpoint, guard=lambda: True):
        return self._sync(mailbox, _history_id(checkpoint), None, guard)

    def _sync(self, mailbox, checkpoint, window, guard):
        validate_email(mailbox)
        base = 'https://gmail.googleapis.com/gmail/v1/users/' + quote(mailbox, safe='')
        deadline = self.clock() + self.deadline_seconds
        pages, observations, reasons = 0, [], []
        coverage = 'bounded_bootstrap' if window else 'incremental_history'
        try:
            anchor = self._profile(mailbox, base, guard, deadline)
            token, seen_tokens, changed = None, set(), {}
            terminal = None
            previous_history = None
            previous_record = None
            while True:
                if pages >= self.max_pages:
                    raise GmailReadError('page_limit')
                if window:
                    params = {'q': f'after:{window[0] // 1000 - 1} before:{(window[1] + 999) // 1000 + 1} -in:drafts',
                              'includeSpamTrash': 'false', 'maxResults': 100,
                              'fields': 'messages(id,threadId),nextPageToken,resultSizeEstimate'}
                    path = '/messages'
                else:
                    params = {'startHistoryId': checkpoint, 'maxResults': 100,
                              'fields': 'history(id,messages(id,threadId),messagesAdded(message(id,threadId)),messagesDeleted(message(id,threadId)),labelsAdded(message(id,threadId),labelIds),labelsRemoved(message(id,threadId),labelIds)),nextPageToken,historyId'}
                    path = '/history'
                if token is not None:
                    params['pageToken'] = token
                data = self._get(base, path, params, guard, deadline,
                                 missing='stale_cursor' if not window else None)
                pages += 1
                if window:
                    _shape(data, ('messages', 'nextPageToken', 'resultSizeEstimate'))
                    if 'resultSizeEstimate' in data and (type(data['resultSizeEstimate']) is not int or data['resultSizeEstimate'] < 0):
                        raise GmailReadError('invalid_estimate')
                    self._records(data.get('messages', []), changed, False)
                else:
                    _shape(data, ('history', 'nextPageToken', 'historyId'), ('historyId',))
                    prior_terminal = terminal
                    terminal = _history_id(data['historyId'])
                    if ((prior_terminal is not None and int(terminal) < int(prior_terminal)) or
                            (previous_history is not None and int(terminal) < int(previous_history)) or
                            int(terminal) < int(checkpoint)):
                        raise GmailReadError('invalid_history_order')
                    history = data.get('history', [])
                    if not isinstance(history, list) or len(history) > 100:
                        raise GmailReadError('invalid_history')
                    for item in history:
                        _shape(item, ('id', 'messages', 'messagesAdded', 'messagesDeleted', 'labelsAdded', 'labelsRemoved'), ('id',))
                        hid = _history_id(item['id'])
                        if int(hid) <= int(checkpoint) or int(hid) > int(terminal):
                            raise GmailReadError('invalid_history_order')
                        if previous_history is not None:
                            if int(hid) < int(previous_history):
                                raise GmailReadError('invalid_history_order')
                            if hid == previous_history:
                                if item != previous_record:
                                    raise GmailReadError('conflicting_history_record')
                                continue
                        previous_history, previous_record = hid, item
                        nondeleted = set()
                        # General messages may duplicate specific changes; specific deletes win.
                        self._records(item.get('messages', []), changed, False)
                        for kind in ('messagesAdded', 'labelsAdded', 'labelsRemoved', 'messagesDeleted'):
                            events = item.get(kind, [])
                            if not isinstance(events, list) or len(events) > 1000:
                                raise GmailReadError('invalid_history')
                            for event in events:
                                allowed = ('message', 'labelIds') if kind.startswith('labels') else ('message',)
                                _shape(event, allowed, ('message',))
                                if kind.startswith('labels'):
                                    _labels(event.get('labelIds', []))
                                self._records([event['message']], changed, kind == 'messagesDeleted')
                                mid = event['message']['id']
                                if kind != 'messagesDeleted':
                                    nondeleted.add(mid)
                                elif mid in nondeleted:
                                    # Events grouped within one history record have no
                                    # temporal ordering. Fetch current state instead.
                                    changed[mid] = (False, changed[mid][1])
                token = data.get('nextPageToken')
                if token is None:
                    break
                if (not isinstance(token, str) or not 1 <= len(token) <= 2048 or
                        any(unicodedata.category(c).startswith('C') for c in token)):
                    raise GmailReadError('invalid_page_token')
                if token in seen_tokens:
                    raise GmailReadError('page_token_cycle')
                seen_tokens.add(token)
            for mid, (deleted, thread) in changed.items():
                if deleted:
                    observations.append(Observation(mid, thread_id=thread, status='deleted'))
                    continue
                try:
                    data = self._get(base, '/messages/' + mid,
                                     {'format': 'metadata', 'fields': MESSAGE_FIELDS,
                                      'metadataHeaders': HEADER_NAMES}, guard, deadline,
                                     missing='message_unavailable')
                except GmailReadError as exc:
                    if str(exc) != 'message_unavailable':
                        raise
                    observations.append(Observation(mid, thread_id=thread, status='unavailable'))
                    reasons.append('message_unavailable')
                    continue
                observations.append(_observation(data, mid, window))
            self._profile(mailbox, base, guard, deadline)
            self._check(guard, deadline)
            if reasons:
                return SyncResult('partial', None, tuple(observations), coverage, tuple(sorted(set(reasons))), pages)
            return SyncResult('complete', anchor if window else terminal, tuple(observations), coverage, (), pages)
        except GmailReadError as exc:
            # Do not expose a possibly rebound account's observations on failure.
            code = str(exc)
            return SyncResult('requires_resync' if code == 'stale_cursor' else 'partial',
                              None, (), coverage, (code,), pages)

    def _records(self, records, changed, deleted):
        if not isinstance(records, list) or len(records) > 1000:
            raise GmailReadError('invalid_message_list')
        for record in records:
            _shape(record, ('id', 'threadId'), ('id',))
            mid = _identifier(record['id'])
            thread = _identifier(record['threadId']) if 'threadId' in record else ''
            if mid not in changed and len(changed) >= self.max_messages:
                raise GmailReadError('message_limit')
            changed[mid] = (deleted, thread)
