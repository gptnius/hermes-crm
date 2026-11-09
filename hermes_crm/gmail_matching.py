"""Pure, bounded matching of visible email participants to current CRM identities.

No provider access, persistence, company inference or delivery assertions. Callers
must supply current explicitly configured aliases, fence contact versions, and
replace old derived links when identities change. Use provider account identity
plus immutable message ID for deduplication, never these participant addresses.
"""
from __future__ import annotations

from dataclasses import dataclass
from email.policy import default
import re
import unicodedata
from types import MappingProxyType
from typing import Mapping

from .gmail_reader import GmailReadError, validate_email

MAX_CONTACTS = 10_000
MAX_HEADERS = 100
MAX_HEADER_LENGTH = 4096
MAX_PARTICIPANTS = 200
MAX_ALIASES = 20
ROLES = ('from', 'to', 'cc')
# Intentionally narrower than RFC5322: no comments, groups, quoted local parts,
# obsolete syntax or IDNs. Display names may be quoted and contain commas.
_MAILBOX = r'[A-Za-z0-9_+%.-]+@[A-Za-z0-9.-]+'
_DISPLAY = r'(?:"(?:[^"\\\r\n]|\\[^\r\n])*"|[^<>(),:;"\\@\r\n]+)'
_ADDRESS = rf'(?:{_MAILBOX}|(?:{_DISPLAY}\s*)?<\s*{_MAILBOX}\s*>)'
_LIST = re.compile(rf'\s*{_ADDRESS}(?:\s*,\s*{_ADDRESS})*\s*\Z')


@dataclass(frozen=True)
class ContactIdentity:
    contact_id: str
    email: str
    version: int
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, order=True)
class ContactMatch:
    contact_id: str
    version: int


@dataclass(frozen=True)
class Participant:
    address: str
    roles: tuple[str, ...]
    status: str
    matches: tuple[ContactMatch, ...]

    @property
    def contact_ids(self):
        return tuple(match.contact_id for match in self.matches)


@dataclass(frozen=True)
class MatchResult:
    matches: tuple[ContactMatch, ...]
    participants: tuple[Participant, ...]
    issues: tuple[str, ...]
    direction: str

    @property
    def contact_ids(self):
        return tuple(match.contact_id for match in self.matches)


def normalize_mailbox(value):
    """Trim outer ASCII space; lowercase domain only; reject unsupported syntax."""
    if not isinstance(value, str):
        raise ValueError('unsupported_mailbox')
    try:
        value = validate_email(value.strip(' \t'))
    except GmailReadError:
        raise ValueError('unsupported_mailbox') from None
    local, domain = value.split('@')
    return local + '@' + domain.lower()


def _bounded(values, limit, code):
    result = []
    for value in values:
        if len(result) >= limit:
            raise ValueError(code)
        result.append(value)
    return result


def _addresses(value):
    if not isinstance(value, str) or len(value) > MAX_HEADER_LENGTH:
        raise ValueError('unsupported_header')
    # Permit normal folding, but never arbitrary CR/LF or invisible controls.
    value = re.sub(r'\r\n[ \t]+', ' ', value)
    if any(unicodedata.category(char).startswith('C') and char != '\t' for char in value):
        raise ValueError('malformed_header')
    if not _LIST.fullmatch(value):
        raise ValueError('unsupported_header')
    try:
        header = default.header_factory('To', value)
    except (ValueError, IndexError, AttributeError):
        raise ValueError('malformed_header') from None
    if header.defects:
        raise ValueError('malformed_header')
    return tuple(normalize_mailbox(address.addr_spec) for address in header.addresses)


@dataclass(frozen=True, init=False)
class CompiledMatcher:
    """Immutable current-identity index, reusable within one scoped operation.

    Construct once per query/publication from freshly captured CRM identities.
    Never cache across requests, workspaces, profiles or identity changes. The
    index copies caller data; later mutations cannot change its snapshot.
    """
    own: frozenset[str]
    own_folded: frozenset[str]
    identities: Mapping[str, frozenset[ContactMatch]]
    folded: Mapping[str, frozenset[ContactMatch]]
    issues: frozenset[str]

    def __init__(self, contacts, own_mailboxes):
        own = {normalize_mailbox(value) for value in _bounded(own_mailboxes, MAX_ALIASES + 1, 'too_many_own_mailboxes')}
        if not own:
            raise ValueError('missing_own_mailbox')
        own_folded = {value.lower() for value in own}
        identities, seen_ids, issues = {}, set(), set()
        for contact in _bounded(contacts, MAX_CONTACTS, 'too_many_contacts'):
            if (not isinstance(contact, ContactIdentity) or not isinstance(contact.contact_id, str)
                    or not contact.contact_id or len(contact.contact_id) > 128
                    or type(contact.version) is not int or contact.version < 1):
                raise ValueError('invalid_contact_identity')
            if contact.contact_id in seen_ids:
                raise ValueError('duplicate_contact_id')
            seen_ids.add(contact.contact_id)
            match = ContactMatch(contact.contact_id, contact.version)
            aliases = _bounded(contact.aliases, MAX_ALIASES, 'too_many_aliases')
            for raw in (contact.email, *aliases):
                if raw == '':
                    continue
                try:
                    address = normalize_mailbox(raw)
                except ValueError:
                    issues.add('unsupported_contact_mailbox')
                    continue
                identities.setdefault(address, set()).add(match)
        folded = {}
        for address, matches in identities.items():
            folded.setdefault(address.lower(), set()).update(matches)

        object.__setattr__(self, 'own', frozenset(own))
        object.__setattr__(self, 'own_folded', frozenset(own_folded))
        object.__setattr__(self, 'identities', MappingProxyType({
            key: frozenset(value) for key, value in identities.items()}))
        object.__setattr__(self, 'folded', MappingProxyType({
            key: frozenset(value) for key, value in folded.items()}))
        object.__setattr__(self, 'issues', frozenset(issues))

    def match(self, headers):
        """Match visible participants without rebuilding or changing the index."""
        own, own_folded = self.own, self.own_folded
        identities, folded = self.identities, self.folded
        issues = set(self.issues)
        role_headers = {role: [] for role in ROLES}
        for pair in _bounded(headers, MAX_HEADERS, 'too_many_headers'):
            if not isinstance(pair, (tuple, list)) or len(pair) != 2 or not isinstance(pair[0], str):
                raise ValueError('invalid_header_pair')
            name, value = pair
            if name.lower() in role_headers:
                role_headers[name.lower()].append(value)
            # Bcc and all other values are ignored, including malformed Bcc values.
        participants, role_values = {}, {}
        participant_count = 0
        for role, values in role_headers.items():
            if not values:
                if role == 'from':
                    issues.add('missing_from')
                continue
            if len(values) != 1:
                issues.add('duplicate_' + role)
                continue
            try:
                addresses = _addresses(values[0])
            except ValueError as exc:
                issues.add(str(exc) + '_' + role)
                continue
            participant_count += len(addresses)
            if participant_count > MAX_PARTICIPANTS:
                raise ValueError('too_many_participants')
            role_values[role] = set(addresses)
            for address in addresses:
                participants.setdefault(address, set()).add(role)
        results, linked = [], set()
        for address, roles in sorted(participants.items()):
            matches = identities.get(address, set())
            if address in own:
                status, matches = 'own', set()
            elif address.lower() in own_folded:
                status, matches = 'own_case_mismatch', set()
            elif len(matches) > 1:
                status = 'ambiguous'
            elif matches:
                status = 'matched'
                linked.update(matches)
            elif address.lower() in folded:
                status, matches = 'case_mismatch', folded[address.lower()]
            else:
                status = 'unmatched'
            results.append(Participant(address, tuple(role for role in ROLES if role in roles),
                                       status, tuple(sorted(matches))))
        senders = role_values.get('from', set())
        recipients = role_values.get('to', set()) | role_values.get('cc', set())
        # Missing/malformed recipient roles or mixed/multiple senders do not support
        # a directional assertion. Bcc-only incoming mail remains unknown.
        direction = 'unknown'
        invalid_roles = any(code.endswith(('_from', '_to', '_cc')) for code in issues)
        own_case_uncertain = any(address not in own and address.lower() in own_folded
                                 for address in senders | recipients)
        if not invalid_roles and not own_case_uncertain and len(senders) == 1 and recipients:
            if senders <= own:
                direction = 'self_observed' if recipients <= own else 'outbound_observed'
            elif senders.isdisjoint(own) and recipients & own:
                direction = 'inbound_observed'
        return MatchResult(tuple(sorted(linked)), tuple(results), tuple(sorted(issues)), direction)


def match_headers(headers, contacts, own_mailboxes):
    """One-shot compatibility wrapper around a fresh immutable identity index.

    Duplicate/malformed roles are omitted and reported. Ambiguous/case-only
    candidates never auto-link. Direction is observation, not delivery proof.
    """
    return CompiledMatcher(contacts, own_mailboxes).match(headers)
