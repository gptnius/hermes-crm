"""Synthetic-only deterministic matching; no provider or database required."""
from dataclasses import replace
import socket

import pytest

from hermes_crm.gmail_matching import (
    ContactIdentity, ContactMatch, match_headers, normalize_mailbox,
    MAX_CONTACTS, MAX_HEADERS, MAX_PARTICIPANTS,
)

OWNER = 'owner@example.com'
ALICE = ContactIdentity('alice', 'Alice@example.com', 3, ('alias@example.com',))
BOB = ContactIdentity('bob', 'bob@example.org', 2)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('Real network forbidden')
    monkeypatch.setattr(socket, 'create_connection', deny)
    monkeypatch.setattr(socket.socket, 'connect', deny)


def match(headers, contacts=(ALICE, BOB), own=(OWNER,)):
    return match_headers(headers, contacts, own)


def test_exact_conservative_normalization():
    assert normalize_mailbox(' Alice.Name+tag@EXAMPLE.COM ') == 'Alice.Name+tag@example.com'
    for value in ('"Alice"@example.com', 'a@例.com', 'a..b@example.com', 'a@example.com\n',
                  'a@example.com,b@example.com', 'a@localhost', None):
        with pytest.raises(ValueError, match='unsupported_mailbox'):
            normalize_mailbox(value)


def test_multiple_roles_aliases_duplicates_and_versions():
    result = match([('From', OWNER), ('To', '"Alice, A" <Alice@EXAMPLE.COM>, bob@example.org'),
                    ('Cc', 'alias@example.com, Alice@example.com')])
    assert result.matches == (ContactMatch('alice', 3), ContactMatch('bob', 2))
    assert result.contact_ids == ('alice', 'bob')
    assert result.direction == 'outbound_observed'
    assert result.participants[0].roles == ('to', 'cc')
    assert not result.issues


def test_ambiguity_is_visible_without_linking():
    duplicate = ContactIdentity('other', ALICE.email, 4)
    result = match([('From', ALICE.email), ('To', OWNER)], (ALICE, duplicate))
    assert not result.matches
    p = next(p for p in result.participants if p.address == ALICE.email)
    assert p.status == 'ambiguous'
    assert p.matches == (ContactMatch('alice', 3), ContactMatch('other', 4))


def test_own_alias_collision_excluded():
    result = match([('From', ALICE.email), ('To', OWNER)], own=(OWNER, ALICE.email))
    assert not result.matches
    assert all(p.status == 'own' for p in result.participants)
    assert result.direction == 'self_observed'


def test_case_dots_plus_not_guessed():
    result = match([('From', OWNER), ('To', 'alice@example.com, A.lice@example.com, Alice+tag@example.com')])
    assert not result.matches
    assert {p.address: p.status for p in result.participants} == {
        'alice@example.com': 'case_mismatch', 'A.lice@example.com': 'unmatched',
        'Alice+tag@example.com': 'unmatched', OWNER: 'own'}


def test_case_only_own_is_neither_link_nor_direction():
    result = match([('From', 'Owner@example.com'), ('To', BOB.email)],
                   (BOB, ContactIdentity('self', 'Owner@example.com', 1)))
    assert result.contact_ids == ('bob',)
    assert result.direction == 'unknown'
    assert result.participants[0].status == 'own_case_mismatch'


@pytest.mark.parametrize('value', ['bad', 'Alice@example.com garbage', 'Alice@example.com,,bob@example.org',
    '"Alice"@example.com', 'Group: Alice@example.com;', 'Alice@example.com (comment)',
    'Alice@example.com\nBcc: hidden@example.com', 'a@例.com', '<a..b@example.com>', 'x' * 4097])
def test_unsupported_header_not_salvaged(value):
    result = match([('From', OWNER), ('To', value)])
    assert not result.matches
    assert result.issues and result.direction == 'unknown'


def test_duplicate_header_omits_entire_role():
    result = match([('From', OWNER), ('To', ALICE.email), ('to', BOB.email)])
    assert not result.matches
    assert result.issues == ('duplicate_to',)


def test_bcc_ignored_and_cannot_set_direction():
    result = match([('From', ALICE.email), ('Bcc', OWNER), ('BCC', object())])
    assert result.contact_ids == ('alice',)
    assert result.direction == 'unknown'
    assert all(p.address != OWNER for p in result.participants)
    assert not result.issues


@pytest.mark.parametrize(('headers', 'direction'), [
    ([('From', ALICE.email), ('To', OWNER)], 'inbound_observed'),
    ([('From', OWNER), ('To', ALICE.email)], 'outbound_observed'),
    ([('From', OWNER), ('To', OWNER)], 'self_observed'),
    ([('To', OWNER)], 'unknown'),
    ([('From', ALICE.email + ', ' + OWNER), ('To', OWNER)], 'unknown'),
    ([('From', 'bad'), ('To', OWNER)], 'unknown'),
    ([('From', ALICE.email), ('To', BOB.email)], 'unknown'),
])
def test_header_direction_only(headers, direction):
    assert match(headers).direction == direction
    assert match(headers + [('Label', 'SENT'), ('Delivered-To', OWNER)]).direction == direction


def test_withdrawn_alias_or_changed_primary_not_rematched():
    headers = [('From', 'alias@example.com'), ('To', OWNER)]
    assert match(headers).contact_ids == ('alice',)
    updated = replace(ALICE, email='new@example.com', aliases=(), version=4)
    assert not match(headers, (updated,)).matches
    assert not match([('From', ALICE.email), ('To', OWNER)], (updated,)).matches


def test_duplicates_and_input_order_are_deterministic():
    a = replace(ALICE, aliases=('alias@example.com', 'alias@example.com', ALICE.email))
    headers = [('To', ALICE.email + ', ' + BOB.email + ', ' + ALICE.email), ('From', OWNER)]
    assert match(headers, (a, BOB)) == match(list(reversed(headers)), (BOB, a))


def test_encoded_unicode_display_and_folding():
    result = match([('From', OWNER), ('To', '=?utf-8?q?Alice?= <Alice@example.com>,\r\n bob@example.org')])
    assert result.contact_ids == ('alice', 'bob')
    assert match([('From', 'Ålice <Alice@example.com>'), ('To', OWNER)]).contact_ids == ('alice',)


def test_no_company_name_or_domain_guess():
    result = match([('From', 'Alice <stranger@example.com>'), ('To', OWNER)])
    assert not result.matches


@pytest.mark.parametrize(('headers', 'contacts', 'own', 'error'), [
    ([], (ALICE, ALICE), (OWNER,), 'duplicate_contact_id'),
    ([], (replace(ALICE, version=0),), (OWNER,), 'invalid_contact_identity'),
    ([], (), (), 'missing_own_mailbox'),
    ([], (), ('invalid',), 'unsupported_mailbox'),
    ([('Subject', '')] * (MAX_HEADERS + 1), (), (OWNER,), 'too_many_headers'),
    ([], [ContactIdentity(str(i), '', 1) for i in range(MAX_CONTACTS + 1)], (OWNER,), 'too_many_contacts'),
    ([], (replace(ALICE, aliases=('x@example.com',) * 21),), (OWNER,), 'too_many_aliases'),
    ([('To', ','.join(['a@x.co'] * (MAX_PARTICIPANTS + 1)))], (), (OWNER,), 'too_many_participants'),
])
def test_limits_and_invalid_inputs(headers, contacts, own, error):
    with pytest.raises(ValueError, match=error):
        match_headers(headers, contacts, own)


def test_invalid_contact_mailbox_reported_no_fallback():
    result = match([('From', OWNER), ('To', ALICE.email)], (replace(ALICE, email='Alice <Alice@example.com>', aliases=()),))
    assert not result.matches
    assert result.issues == ('unsupported_contact_mailbox',)


@pytest.mark.parametrize('headers', [
    [('From', OWNER), ('To', ALICE.email + ',' + BOB.email)],
    [('From', 'alice@example.com'), ('To', OWNER)],
    [('From', 'alias@example.com'), ('To', OWNER), ('Bcc', 'private@example.com')],
    [('From', ALICE.email), ('from', BOB.email), ('To', OWNER)],
    [('From', 'bad'), ('To', OWNER)],
    [('From', 'Owner@example.com'), ('To', BOB.email)],
    [],
])
def test_compiled_equivalence(headers):
    from hermes_crm.gmail_matching import CompiledMatcher
    contacts = (ALICE, BOB, ContactIdentity('duplicate', ALICE.email, 5),
                ContactIdentity('invalid', 'invalid', 1))
    compiled = CompiledMatcher(contacts, (OWNER,))
    assert compiled.match(headers) == match(headers, contacts)
    assert compiled.match(headers) == compiled.match(headers)


def test_compiled_snapshot_is_immutable_and_isolated():
    from dataclasses import FrozenInstanceError
    from hermes_crm.gmail_matching import CompiledMatcher
    aliases = ['alias@example.com']
    contacts = [ContactIdentity('alice', ALICE.email, 3, aliases)]
    own = [OWNER]
    first = CompiledMatcher(contacts, own)
    aliases.clear()
    contacts.clear()
    own.append('alias@example.com')
    headers = [('From', 'alias@example.com'), ('To', OWNER)]
    assert first.match(headers).contact_ids == ('alice',)
    second = CompiledMatcher(contacts, own)
    assert not second.match(headers).matches
    with pytest.raises(FrozenInstanceError):
        first.own = frozenset()
    with pytest.raises(TypeError):
        first.identities['alias@example.com'] = frozenset()
    with pytest.raises(AttributeError):
        first.identities['alias@example.com'].clear()
    assert first.match(headers).contact_ids == ('alice',)


def test_compiled_matches_do_not_leak_message_issues():
    from hermes_crm.gmail_matching import CompiledMatcher
    compiled = CompiledMatcher((ALICE,), (OWNER,))
    assert compiled.match([('From', 'bad')]).issues
    assert not compiled.match([('From', OWNER), ('To', ALICE.email)]).issues


def test_compiled_does_not_rebuild_contact_index(monkeypatch):
    import hermes_crm.gmail_matching as matching
    compiled = matching.CompiledMatcher((ALICE, BOB), (OWNER,))
    original = matching._bounded
    def guard(values, limit, code):
        assert code == 'too_many_headers'
        return original(values, limit, code)
    monkeypatch.setattr(matching, '_bounded', guard)
    for _ in range(5):
        assert compiled.match([('From', ALICE.email), ('To', OWNER)]).contact_ids == ('alice',)
