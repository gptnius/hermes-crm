"""Executable OFFLINE DESIGN EXAMPLES, not a Gmail adapter or auth boundary.

All helpers and fixtures are test-local. No runtime module imports this file;
there is no transport, account/config discovery, OAuth or persistence here.
These examples test proposed decisions, not installed-host/provider behavior.
See docs/GMAIL_READONLY_PLAN.md for assumptions and unverified requirements.
"""
from __future__ import annotations

import json
import re
import socket
import unicodedata
from dataclasses import dataclass, replace
from email.header import decode_header, make_header
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import pytest


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    """Defense against accidental network use, not a malicious-code sandbox."""
    def denied(*args, **kwargs):
        raise AssertionError("The Gmail design tests must stay offline")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class FixtureResponse:
    """Matches the public host result shape; it is NOT the real helper."""
    status: int
    headers: dict[str, str]
    body: bytes


def response_fixture(value, *, status=200):
    return FixtureResponse(status, {"content-type": "application/json"},
                           json.dumps(value).encode())


def decode_response(response):
    # Deliberately do not support status_code, arbitrary .json(), or tool-success flags.
    if type(response.status) is not int or response.status != 200:
        raise SpecError("provider_status")
    if not isinstance(response.headers, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in response.headers.items()
    ):
        raise SpecError("provider_headers")
    content_types = [v for k, v in response.headers.items() if k.lower() == "content-type"]
    if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip() != "application/json":
        raise SpecError("provider_content_type")
    if type(response.body) is not bytes or len(response.body) > 1_048_576:
        raise SpecError("provider_body_size")

    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise SpecError("duplicate_json_key")
            obj[key] = value
        return obj

    def invalid_constant(_):
        raise SpecError("invalid_json_number")

    try:
        value = json.loads(response.body.decode("utf-8"), object_pairs_hook=unique_object,
                           parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise SpecError("provider_json") from None
    if not isinstance(value, dict):
        raise SpecError("provider_object_required")
    return value


def opaque(value, *, limit=512):
    if (not isinstance(value, str) or not 1 <= len(value) <= limit or
            value != value.strip() or any(unicodedata.category(c).startswith("C") for c in value)):
        raise SpecError("invalid_identifier")
    return value


def decimal_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]{0,39}", value) is None:
        raise SpecError("invalid_history_id")
    return value


def provider_message_id(value):
    # Conservative accepted subset. Unsupported provider identifiers fail closed.
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is None:
        raise SpecError("invalid_message_id")
    return value


def mailbox(value):
    # Conservative prototype, not a complete RFC mailbox parser or alias resolver.
    opaque(value, limit=254)
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+=?^_`{|}~-]+@[A-Za-z0-9.-]+", value):
        raise SpecError("explicit_mailbox_required")
    return value


@dataclass(frozen=True)
class Route:
    workspace: str
    profile: str
    activation: int


@dataclass(frozen=True)
class Binding:
    route: Route
    sub: str
    email: str
    issuer: str = "https://accounts.google.com"

    def namespace(self):
        return (self.route.workspace, self.route.profile, self.issuer, self.sub)


HISTORY_FIELDS = (
    "nextPageToken,historyId,history(id,messages(id,threadId),"
    "messagesAdded(message(id,threadId)),messagesDeleted(message(id,threadId)),"
    "labelsAdded(message(id,threadId),labelIds),labelsRemoved(message(id,threadId),labelIds))"
)


def verify_identity(binding, userinfo, profile, current_route):
    """Shape/equality predicates only; their inputs are NOT self-authenticating."""
    if current_route != binding.route:
        raise SpecError("activation_changed")
    sub = opaque(userinfo.get("sub"), limit=255)
    if not sub.isascii() or sub != binding.sub:
        raise SpecError("subject_changed")
    if userinfo.get("email_verified") is not True:
        raise SpecError("unverified_email")
    expected = mailbox(binding.email)
    if userinfo.get("email") != expected or profile.get("emailAddress") != expected:
        raise SpecError("mailbox_changed")
    decimal_id(profile.get("historyId"))


def planned_get(binding, operation, *, start_ms=None, end_ms=None, message_id=None,
                history_id=None, page_token=None):
    """Return a request description only. No HTTP client or caller-provided URL."""
    address = mailbox(binding.email)
    base = "https://gmail.googleapis.com/gmail/v1/users/" + quote(address, safe="")
    query = {}
    if operation == "userinfo":
        return "GET", "https://openidconnect.googleapis.com/v1/userinfo"
    if operation == "profile":
        url = base + "/profile"
    elif operation == "list":
        if (type(start_ms) is not int or type(end_ms) is not int or
                not 0 < start_ms < end_ms or end_ms - start_ms > 90 * 86400_000):
            raise SpecError("invalid_window")
        # Widen by one second, then filter exact millisecond bounds locally.
        query = {"q": f"after:{start_ms // 1000 - 1} before:{(end_ms + 999) // 1000 + 1} -in:drafts",
                 "includeSpamTrash": "false", "maxResults": 100}
        url = base + "/messages"
    elif operation == "message":
        url = base + "/messages/" + quote(provider_message_id(message_id), safe="")
        query = {"format": "metadata", "metadataHeaders": ["From", "To", "Cc", "Subject", "Date"],
                 "fields": "id,threadId,labelIds,historyId,internalDate,payload/headers"}
    elif operation == "history":
        url = base + "/history"
        query = {"startHistoryId": decimal_id(history_id), "maxResults": 100, "fields": HISTORY_FIELDS}
    else:
        raise SpecError("operation_not_allowed")
    if page_token is not None:
        if operation not in {"list", "history"}:
            raise SpecError("pagination_not_allowed")
        query["pageToken"] = opaque(page_token, limit=2048)
    return "GET", url + ("?" + urlencode(query, doseq=True) if query else "")


def enumerate_fixture_pages(pages, *, max_pages=10, max_ids=1000):
    """Pages are already available in memory. Returns IDs and coverage, not reads."""
    ids, seen_tokens = set(), set()
    for index, response in enumerate(pages):
        if index >= max_pages:
            return tuple(sorted(ids)), "partial_budget"
        page = decode_response(response)
        messages = page.get("messages", [])
        if not isinstance(messages, list) or len(messages) > 100:
            raise SpecError("invalid_list_page")
        for message in messages:
            if not isinstance(message, dict):
                raise SpecError("invalid_list_item")
            message_id = provider_message_id(message.get("id"))
            if message_id not in ids and len(ids) >= max_ids:
                return tuple(sorted(ids)), "partial_budget"
            ids.add(message_id)
        token = page.get("nextPageToken")
        if token is None:
            return tuple(sorted(ids)), "window_enumerated"
        opaque(token, limit=2048)
        if token in seen_tokens:
            raise SpecError("page_token_cycle")
        seen_tokens.add(token)
    return tuple(sorted(ids)), "partial_pages_missing"


def summarize_fixture_history(pages, start_id, *, max_pages=10):
    """Summarize synthetic typed events; expose a cursor only after final page."""
    decimal_id(start_id)
    events, tokens, previous = set(), set(), int(start_id)
    kinds = {"messagesAdded", "messagesDeleted", "labelsAdded", "labelsRemoved"}

    def message_ref(value):
        if not isinstance(value, dict) or set(value) - {"id", "threadId"}:
            raise SpecError("invalid_history_message")
        if "threadId" in value:
            opaque(value["threadId"])
        return provider_message_id(value.get("id"))

    for index, response in enumerate(pages):
        if index >= max_pages:
            return tuple(sorted(events)), None, "partial_budget"
        page = decode_response(response)
        if set(page) - {"historyId", "history", "nextPageToken"}:
            raise SpecError("unexpected_history_fields")
        terminal = decimal_id(page.get("historyId"))
        records = page.get("history", [])
        if not isinstance(records, list) or len(records) > 100:
            raise SpecError("invalid_history_page")
        for record in records:
            if not isinstance(record, dict) or set(record) - {"id", "messages", *kinds}:
                raise SpecError("invalid_history_record")
            revision = decimal_id(record.get("id"))
            if int(revision) <= int(start_id) or int(revision) < previous:
                raise SpecError("history_order")
            previous = int(revision)
            generic = record.get("messages", [])
            if not isinstance(generic, list):
                raise SpecError("invalid_generic_messages")
            generic_ids = {message_ref(message) for message in generic}
            typed_ids = set()
            # Generic messages repeats typed events; it must not manufacture a fifth type.
            for kind in kinds:
                changes = record.get(kind, [])
                if not isinstance(changes, list):
                    raise SpecError("invalid_history_changes")
                for change in changes:
                    allowed = {"message", "labelIds"} if kind.startswith("labels") else {"message"}
                    if not isinstance(change, dict) or set(change) - allowed:
                        raise SpecError("invalid_history_change")
                    message_id = message_ref(change.get("message"))
                    typed_ids.add(message_id)
                    labels = change.get("labelIds", [])
                    if not isinstance(labels, list) or len(labels) > 100:
                        raise SpecError("invalid_history_labels")
                    labels = tuple(sorted({opaque(label) for label in labels}))
                    if kind.startswith("labels") and not labels:
                        raise SpecError("missing_changed_labels")
                    events.add((revision, kind, message_id, labels))
            if not typed_ids or generic_ids - typed_ids:
                raise SpecError("untyped_history_change")
        if int(terminal) < previous:
            raise SpecError("terminal_cursor_regressed")
        token = page.get("nextPageToken")
        if token is None:
            return tuple(sorted(events)), terminal, "history_pages_finished"
        opaque(token, limit=2048)
        if token in tokens:
            raise SpecError("page_token_cycle")
        tokens.add(token)
    return tuple(sorted(events)), None, "partial_pages_missing"


DISPLAY_HEADERS = frozenset({"from", "to", "cc", "subject", "date"})


def plaintext_header(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise SpecError("unsafe_header")
    unfolded = re.sub(r"\r\n[ \t]+", " ", value)
    try:
        decoded = str(make_header(decode_header(unfolded)))
    except (LookupError, UnicodeError, ValueError):
        raise SpecError("unsafe_header") from None
    if len(decoded) > 1024 or any(unicodedata.category(c).startswith("C") for c in decoded):
        raise SpecError("unsafe_header")
    return decoded


@dataclass(frozen=True)
class Metadata:
    entity_key: tuple[str, ...]
    thread_id: str | None
    history_id: str
    internal_date_ms: int
    labels: tuple[str, ...]
    display_headers: tuple[tuple[str, str], ...]
    header_issues: tuple[str, ...]
    included: bool = True

    @property
    def description(self):
        if not self.included:
            return "excluded_from_current_view"
        return "observed_in_sent" if "SENT" in self.labels else "mailbox_item_observed"


def project_metadata(binding, data, *, start_ms, end_ms, expected_id):
    """Project only allowlisted metadata; no ProviderObservation 'sent' conversion."""
    if not isinstance(data, dict) or set(data) - {
        "id", "threadId", "historyId", "internalDate", "labelIds", "payload"
    }:
        raise SpecError("unexpected_message_fields")
    message_id = provider_message_id(data.get("id"))
    if message_id != provider_message_id(expected_id):
        raise SpecError("wrong_message")
    thread_id = opaque(data["threadId"]) if "threadId" in data else None
    revision = decimal_id(data.get("historyId"))
    timestamp = data.get("internalDate")
    if not isinstance(timestamp, str) or re.fullmatch(r"[0-9]{1,16}", timestamp) is None:
        raise SpecError("invalid_internal_date")
    labels = data.get("labelIds")
    if not isinstance(labels, list) or len(labels) > 100:
        raise SpecError("invalid_labels")
    labels = tuple(sorted({opaque(label) for label in labels}))
    payload = data.get("payload", {})
    if not isinstance(payload, dict) or set(payload) - {"headers"}:
        raise SpecError("unexpected_payload_fields")
    headers = payload.get("headers", [])
    if not isinstance(headers, list) or len(headers) > 50:
        raise SpecError("invalid_headers")
    display, issues, seen = {}, set(), set()
    for header in headers:
        if not isinstance(header, dict) or set(header) != {"name", "value"}:
            raise SpecError("invalid_header_shape")
        name = opaque(header["name"], limit=128).lower()
        if name not in DISPLAY_HEADERS:
            continue
        if name in seen:
            display[name] = "(unsupported header)"
            issues.add("duplicate_" + name)
            continue
        seen.add(name)
        try:
            display[name] = plaintext_header(header["value"])
        except SpecError:
            display[name] = "(unsupported header)"
            issues.add("unsafe_" + name)
    if "DRAFT" in labels or not start_ms <= int(timestamp) < end_ms:
        return None
    included = not bool({"SPAM", "TRASH"}.intersection(labels))
    return Metadata((*binding.namespace(), message_id), thread_id, revision, int(timestamp),
                    labels, tuple(sorted(display.items())) if included else (),
                    tuple(sorted(issues)) if included else (), included)


@dataclass(frozen=True)
class ReadObservation:
    # The caller is test code, not a trusted source. No auth claim is made here.
    batch: str
    ordinal: int
    metadata: Metadata


@dataclass(frozen=True)
class LedgerState:
    namespace: tuple[str, ...]
    route: Route
    cursor: str
    observations: tuple[ReadObservation, ...] = ()
    snapshots: tuple[Metadata, ...] = ()
    coverage: str = "window_enumerated"


def publish_fixture_batch(state, observations, *, expected_cursor, terminal_cursor,
                          final_page, current_route, failed=False):
    """In-memory atomic replacement example, NOT a database transaction test."""
    if (failed or not final_page or expected_cursor != state.cursor or current_route != state.route):
        raise SpecError("batch_not_publishable")
    decimal_id(terminal_cursor)
    if int(terminal_cursor) < int(state.cursor):
        raise SpecError("cursor_regressed")
    immutable = {(o.batch, o.ordinal): o for o in state.observations}
    snapshots = {m.entity_key: m for m in state.snapshots}
    for observation in observations:
        item = observation.metadata
        if item.entity_key[:-1] != state.namespace:
            raise SpecError("wrong_account")
        identity = (observation.batch, observation.ordinal)
        if identity in immutable and immutable[identity] != observation:
            raise SpecError("conflicting_observation")
        immutable[identity] = observation
        prior = snapshots.get(item.entity_key)
        if prior is not None and prior.history_id == item.history_id and prior != item:
            raise SpecError("conflicting_snapshot")
        if prior is None or int(item.history_id) > int(prior.history_id):
            snapshots[item.entity_key] = item
    return replace(state, cursor=terminal_cursor, observations=tuple(immutable.values()),
                   snapshots=tuple(snapshots.values()))


def history_failure(state, status):
    if status == 404:
        return replace(state, coverage="history_gap_rescan_required")
    return replace(state, coverage="partial_provider_error")


ROUTE = Route("synthetic-workspace", "synthetic-profile", 8)
BINDING = Binding(ROUTE, "synthetic-sub-A", "owner@example.com")
USERINFO = {"sub": BINDING.sub, "email": BINDING.email, "email_verified": True}
PROFILE = {"emailAddress": BINDING.email, "historyId": "9007199254740993"}
START, END = 1700000000123, 1700086400123


def message_fixture(**overrides):
    return {"id": "fixture-message-1", "threadId": "fixture-thread-1", "historyId": "9007199254740995",
            "internalDate": str(START), "labelIds": ["SENT"],
            "payload": {"headers": [{"name": "Subject", "value": "Synthetic message"}]}, **overrides}


def metadata_fixture(**overrides):
    data = message_fixture(**overrides)
    return project_metadata(BINDING, data, start_ms=START, end_ms=END, expected_id=data["id"])


def test_provider_result_is_status_headers_bytes_not_a_success_flag():
    assert decode_response(response_fixture({"messages": []})) == {"messages": []}
    assert not hasattr(response_fixture({}), "status_code")
    for status in [True, 201, 204, 301, 302, 401, 403, 404, 429, 500]:
        with pytest.raises(SpecError, match="provider_status"):
            decode_response(response_fixture({"success": True, "private_error": "do not echo"}, status=status))


@pytest.mark.parametrize("body", [b'[]', b'null', b'{"sub":"A","sub":"B"}', b'{"x":NaN}',
                                  b'\xff', b'{not json}', b'x' * 1_048_577])
def test_malformed_provider_body_fails_closed_without_echo(body):
    with pytest.raises(SpecError) as error:
        decode_response(FixtureResponse(200, {"content-type": "application/json"}, body))
    assert "not json" not in str(error.value)


def test_identity_requires_stable_subject_verified_email_explicit_mailbox_and_route():
    verify_identity(BINDING, USERINFO, PROFILE, ROUTE)
    for changed in [{**USERINFO, "sub": "B"}, {**USERINFO, "sub": ""},
                    {**USERINFO, "email_verified": "true"}, {**USERINFO, "email_verified": 1},
                    {**USERINFO, "email": "other@example.com"}]:
        with pytest.raises(SpecError):
            verify_identity(BINDING, changed, PROFILE, ROUTE)
    with pytest.raises(SpecError, match="mailbox_changed"):
        verify_identity(BINDING, USERINFO, {**PROFILE, "emailAddress": "alias@example.com"}, ROUTE)
    # Workspace/profile names return to their old values, but activation has advanced.
    with pytest.raises(SpecError, match="activation_changed"):
        verify_identity(BINDING, USERINFO, PROFILE, replace(ROUTE, activation=10))


def test_before_after_identity_checks_do_not_attest_intervening_grant():
    # The middle entry is deliberately unobservable to the predicate. This is a
    # counterexample to continuity, NOT evidence Gmail permits B to read A mail.
    for grant_sequence in [("A", "A", "A"), ("A", "B", "A"), ("A-v1", "A-v2", "A-v1")]:
        assert grant_sequence[0] == grant_sequence[-1]
        verify_identity(BINDING, USERINFO, PROFILE, ROUTE)
        verify_identity(BINDING, USERINFO, PROFILE, ROUTE)


def test_ordinary_account_resource_enforcement_is_a_separate_assumption():
    # Model the expected own-mailbox enforcement explicitly. This is NOT a
    # provider test; no assumption about web delegates/API delegation is added.
    authorized_resources = {"A": {"owner@example.com"}, "B": {"other@example.com"}}
    assert BINDING.email in authorized_resources["A"]
    assert BINDING.email not in authorized_resources["B"]
    # A credential ABA with an intervening B read would fail under this model.
    assert not all(BINDING.email in authorized_resources[g] for g in ("A", "B", "A"))


def test_fixed_get_descriptions_encode_mailbox_ids_and_page_tokens_as_data():
    _, url = planned_get(BINDING, "message", message_id="fixture-message-1")
    parsed = urlsplit(url)
    assert parsed.scheme == "https" and parsed.netloc == "gmail.googleapis.com"
    assert "/users/owner%40example.com/messages/fixture-message-1" == parsed.path.removeprefix("/gmail/v1")
    for bad_id in ("id/../send?x=y", "..", ".", "%2f", "\r\n"):
        with pytest.raises(SpecError, match="invalid_message_id"):
            planned_get(BINDING, "message", message_id=bad_id)
    query = parse_qs(parsed.query)
    assert query["format"] == ["metadata"] and "snippet" not in query["fields"][0]
    assert query["metadataHeaders"] == ["From", "To", "Cc", "Subject", "Date"]
    method, url = planned_get(BINDING, "list", start_ms=START, end_ms=END,
                              page_token="https://untrusted.invalid/?x=1&y=2")
    assert method == "GET"
    query = parse_qs(urlsplit(url).query)
    assert query["pageToken"] == ["https://untrusted.invalid/?x=1&y=2"]
    assert query["q"] == [f"after:{START // 1000 - 1} before:{(END + 999) // 1000 + 1} -in:drafts"]
    assert query["includeSpamTrash"] == ["false"]
    for forbidden in ("send", "draft", "modify", "watch", "attachment", "https://bad.invalid"):
        with pytest.raises(SpecError, match="operation_not_allowed"):
            planned_get(BINDING, forbidden)
    with pytest.raises(SpecError):
        planned_get(replace(BINDING, email="me"), "profile")
    assert planned_get(BINDING, "userinfo") == ("GET", "https://openidconnect.googleapis.com/v1/userinfo")


def test_list_follows_empty_pages_deduplicates_and_does_not_trust_estimate():
    pages = [response_fixture({"messages": [{"id": "a"}], "nextPageToken": "one", "resultSizeEstimate": 1}),
             response_fixture({"nextPageToken": "two"}),
             response_fixture({"messages": [{"id": "a"}, {"id": "b"}], "resultSizeEstimate": 9999})]
    assert enumerate_fixture_pages(pages) == (("a", "b"), "window_enumerated")
    assert enumerate_fixture_pages(pages, max_pages=1) == (("a",), "partial_budget")
    assert enumerate_fixture_pages(pages, max_ids=1) == (("a",), "partial_budget")
    assert enumerate_fixture_pages(pages[:2]) == (("a",), "partial_pages_missing")
    with pytest.raises(SpecError, match="page_token_cycle"):
        enumerate_fixture_pages([pages[0], pages[0]])


@pytest.mark.parametrize("page", [{"messages": None}, {"messages": [None]},
                                  {"messages": [{"threadId": "not-a-message-id"}]},
                                  {"nextPageToken": ""}, {"messages": [{"id": "x"}] * 101}])
def test_bad_list_page_cannot_claim_complete(page):
    with pytest.raises(SpecError):
        enumerate_fixture_pages([response_fixture(page)])


def test_history_pagination_never_advances_from_an_intermediate_current_id():
    event = {"id": "17", "messages": [{"id": "a"}],
             "messagesAdded": [{"message": {"id": "a"}}],
             "labelsAdded": [{"message": {"id": "a"}, "labelIds": ["SENT"]}]}
    pages = [response_fixture({"history": [event], "historyId": "99", "nextPageToken": "one"}),
             response_fixture({"historyId": "101", "nextPageToken": "two"}),
             response_fixture({"history": [{"id": "41", "messagesDeleted": [{"message": {"id": "b"}}]}],
                               "historyId": "103"})]
    events, cursor, coverage = summarize_fixture_history(pages, "11")
    assert len(events) == 3  # Generic messages did not create duplicate facts.
    assert cursor == "103" and coverage == "history_pages_finished"
    assert summarize_fixture_history(pages[:2], "11")[1:] == (None, "partial_pages_missing")
    assert summarize_fixture_history(pages, "11", max_pages=1)[1:] == (None, "partial_budget")
    with pytest.raises(SpecError, match="page_token_cycle"):
        summarize_fixture_history([pages[0], pages[0]], "11")


def test_untyped_or_out_of_order_history_is_not_a_complete_sync():
    for record in [{"id": "10", "messagesAdded": [{"message": {"id": "a"}}]},
                   {"id": "17", "messages": [{"id": "a"}]},
                   {"id": "17", "messages": [{"id": "a"}, {"id": "b"}],
                    "messagesAdded": [{"message": {"id": "a"}}]},
                   {"id": "17", "newChangeType": [{"id": "a"}]},
                   {"id": "17", "labelsRemoved": [{"message": {"id": "a"}}]}]:
        with pytest.raises(SpecError):
            summarize_fixture_history([response_fixture({"history": [record], "historyId": "99"})], "11")


@pytest.mark.parametrize("content", [{"snippet": "body excerpt"}, {"payload": {"body": "private"}},
                                     {"raw": "MIME"}, {"labelIds": ["UNREAD"]}])
def test_history_rejects_nonallowlisted_nested_message_content(content):
    record = {"id": "17", "messagesAdded": [{"message": {"id": "a", **content}}]}
    with pytest.raises(SpecError, match="invalid_history_message"):
        summarize_fixture_history([response_fixture({"history": [record], "historyId": "99"})], "11")


def test_metadata_must_match_the_exact_requested_provider_id():
    with pytest.raises(SpecError, match="wrong_message"):
        project_metadata(BINDING, message_fixture(), start_ms=START, end_ms=END, expected_id="different")


def test_sent_and_import_dates_are_weak_observations_not_transport_receipts():
    sent = metadata_fixture()
    assert sent.description == "observed_in_sent"
    assert sent.internal_date_ms == START
    assert not hasattr(sent, "provider_occurred_at")
    assert not hasattr(sent, "provider_submission_id")
    assert metadata_fixture(labelIds=["INBOX"]).description == "mailbox_item_observed"
    assert metadata_fixture(labelIds=[]).description == "mailbox_item_observed"
    assert metadata_fixture(labelIds=["DRAFT"]) is None
    assert metadata_fixture(internalDate=str(START - 1)) is None
    assert metadata_fixture(internalDate=str(END)) is None
    assert metadata_fixture(internalDate=str(END - 1)) is not None


def test_headers_are_plain_text_untrusted_claims_with_bounded_failures():
    raw_headers = [{"name": "Subject", "value": "=?utf-8?q?Hello_=E2=9C=93?="},
                   {"name": "From", "value": "Synthetic\r\n sender <sender@example.com>"},
                   {"name": "To", "value": "<img src=https://untrusted.invalid/track>"},
                   {"name": "Bcc", "value": "not retained"}]
    projected = metadata_fixture(payload={"headers": raw_headers})
    headers = dict(projected.display_headers)
    assert headers["subject"] == "Hello ✓"
    assert headers["from"] == "Synthetic sender <sender@example.com>"
    assert headers["to"] == "<img src=https://untrusted.invalid/track>"  # text, never markup
    assert "bcc" not in headers
    for unsafe in ["injection\r\nBcc: attacker@example.com", "bidi\u202eexample", "nul\x00", "x" * 4097,
                   "=?unknown-charset?b?YWJj?="]:
        projected = metadata_fixture(payload={"headers": [{"name": "Subject", "value": unsafe}]})
        assert dict(projected.display_headers)["subject"] == "(unsupported header)"
        assert projected.header_issues == ("unsafe_subject",)
    projected = metadata_fixture(payload={"headers": [{"name": "Subject", "value": "a"},
                                                       {"name": "subject", "value": "b"}]})
    assert projected.header_issues == ("duplicate_subject",)


@pytest.mark.parametrize("extra", [{"snippet": "body excerpt"}, {"raw": "data"},
                                   {"payload": {"body": {"data": "body"}}},
                                   {"payload": {"parts": []}}, {"internalDate": "NaN"},
                                   {"historyId": 9007199254740993}])
def test_content_and_bad_metadata_are_not_silently_persisted(extra):
    with pytest.raises(SpecError):
        metadata_fixture(**extra)


def test_message_keys_use_account_and_message_not_thread_or_subject():
    first = metadata_fixture()
    second = metadata_fixture(id="different-message-same-thread-and-subject")
    other_account = project_metadata(replace(BINDING, sub="synthetic-sub-B"), message_fixture(),
                                     start_ms=START, end_ms=END, expected_id="fixture-message-1")
    assert len({first.entity_key, second.entity_key, other_account.entity_key}) == 3
    assert first.thread_id == second.thread_id
    assert first.display_headers == second.display_headers


def test_atomic_publication_retains_observations_while_labels_change():
    old = LedgerState(BINDING.namespace(), ROUTE, "9007199254740993")
    first = ReadObservation("batch-one", 0, metadata_fixture())
    state = publish_fixture_batch(old, [first], expected_cursor=old.cursor,
                                  terminal_cursor="9007199254740997", final_page=True, current_route=ROUTE)
    assert old.observations == () and old.cursor == "9007199254740993"
    # Replaying a batch adds no second observation, but a new read is a new fact.
    replay = publish_fixture_batch(state, [first], expected_cursor=state.cursor,
                                   terminal_cursor=state.cursor, final_page=True, current_route=ROUTE)
    assert replay == state
    later = ReadObservation("batch-two", 0, metadata_fixture(labelIds=[], historyId="9007199254741001"))
    updated = publish_fixture_batch(state, [later], expected_cursor=state.cursor,
                                    terminal_cursor="9007199254741003", final_page=True, current_route=ROUTE)
    assert updated.snapshots[0].labels == () and len(updated.observations) == 2
    assert updated.observations[0].metadata.labels == ("SENT",)
    # A replay with older metadata cannot roll the latest snapshot backwards.
    assert publish_fixture_batch(updated, [first], expected_cursor=updated.cursor,
                                 terminal_cursor=updated.cursor, final_page=True,
                                 current_route=ROUTE).snapshots == updated.snapshots


@pytest.mark.parametrize("excluded_label", ["SPAM", "TRASH"])
def test_excluded_label_transition_hides_current_metadata_without_erasing_observations(excluded_label):
    state = LedgerState(BINDING.namespace(), ROUTE, "9007199254740993")
    first = ReadObservation("batch-one", 0, metadata_fixture())
    state = publish_fixture_batch(state, [first], expected_cursor=state.cursor,
                                  terminal_cursor="9007199254740997", final_page=True, current_route=ROUTE)
    excluded = metadata_fixture(labelIds=[excluded_label], historyId="9007199254741001")
    assert excluded.description == "excluded_from_current_view"
    assert not excluded.display_headers and not excluded.included
    updated = publish_fixture_batch(state, [ReadObservation("batch-two", 0, excluded)],
                                    expected_cursor=state.cursor, terminal_cursor="9007199254741003",
                                    final_page=True, current_route=ROUTE)
    assert len(updated.observations) == 2
    assert updated.observations[0].metadata.display_headers == first.metadata.display_headers
    assert not updated.snapshots[0].included


@pytest.mark.parametrize("overrides", [{"final_page": False}, {"failed": True},
                                       {"expected_cursor": "1"}, {"terminal_cursor": "5"},
                                       {"current_route": replace(ROUTE, activation=10)}])
def test_failed_partial_stale_and_changed_route_batches_do_not_advance(overrides):
    state = LedgerState(BINDING.namespace(), ROUTE, "9007199254740993")
    kwargs = {"expected_cursor": state.cursor, "terminal_cursor": "9007199254741003",
              "final_page": True, "current_route": ROUTE, **overrides}
    with pytest.raises(SpecError):
        publish_fixture_batch(state, [ReadObservation("batch", 0, metadata_fixture())], **kwargs)
    assert state.observations == () and state.cursor == "9007199254740993"


def test_mid_batch_conflict_publishes_nothing_and_history_expiry_keeps_old_cursor():
    state = LedgerState(BINDING.namespace(), ROUTE, "9007199254740993")
    good = ReadObservation("batch", 0, metadata_fixture())
    conflict = replace(good, metadata=metadata_fixture(labelIds=[]))
    with pytest.raises(SpecError, match="conflicting_observation"):
        publish_fixture_batch(state, [good, conflict], expected_cursor=state.cursor,
                              terminal_cursor="9007199254741003", final_page=True, current_route=ROUTE)
    assert not state.observations and not state.snapshots
    gap = history_failure(state, 404)
    assert gap.coverage == "history_gap_rescan_required" and gap.cursor == state.cursor
    assert history_failure(state, 403).coverage == "partial_provider_error"
    # History IDs above JavaScript's safe integer range remain exact strings.
    _, url = planned_get(BINDING, "history", history_id=state.cursor)
    assert parse_qs(urlsplit(url).query)["startHistoryId"] == ["9007199254740993"]
    assert parse_qs(urlsplit(url).query)["fields"] == [HISTORY_FIELDS]
