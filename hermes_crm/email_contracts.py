"""Unwired email data contracts. No authentication, approval, storage or transport.

Validation checks shape and consistency only. A future trusted, profile-bound
adapter must authenticate the source and check permission before constructing
provider observations. An agent, UI payload or provider ID cannot attest mail.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

OpaqueID = Annotated[str, StringConstraints(min_length=1, max_length=512, pattern=r'^[^\s\x00-\x1f\x7f](?:[^\x00-\x1f\x7f]*[^\s\x00-\x1f\x7f])?$')]
Digest = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]


class EmailContract(BaseModel):
    # No implicit trimming: exact approved content and provider identifiers matter.
    model_config = ConfigDict(extra='forbid', frozen=True, revalidate_instances='always')

    @field_validator('*')
    @classmethod
    def valid_unicode_text(cls, value):
        # Include tuple elements, which lack scalar Field string constraints.
        for item in value if isinstance(value, tuple) else (value,):
            if isinstance(item, str):
                try:
                    item.encode('utf-8')
                except UnicodeEncodeError as exc:
                    raise ValueError('Text must contain valid Unicode') from exc
        return value


class AccountScope(EmailContract):
    """Non-secret identity only; never credentials or transport/bearer tokens."""
    workspace_id: OpaqueID
    profile_id: OpaqueID
    provider: OpaqueID
    account_id: OpaqueID


class ApprovedEmailSnapshot(EmailContract):
    """Exact reviewed plain-text intent, NOT evidence that approval was granted.

    The future authorization boundary must resolve approval_reference itself,
    bind it to this digest, and recheck scope/revocation immediately before use.
    """
    scope: AccountScope
    approval_reference: OpaqueID
    approved_at: datetime
    sender: str = Field(min_length=3, max_length=254, repr=False)
    to: tuple[str, ...] = Field(min_length=1, max_length=100, repr=False)
    cc: tuple[str, ...] = Field(default=(), max_length=100, repr=False)
    bcc: tuple[str, ...] = Field(default=(), max_length=100, repr=False)
    subject: str = Field(max_length=998, repr=False)
    text_body: str = Field(max_length=100_000, repr=False)
    in_reply_to_message_id: OpaqueID | None = None

    @field_validator('approved_at')
    @classmethod
    def aware_approval_time(cls, value):
        return _utc(value)

    @model_validator(mode='after')
    def exact_envelope(self):
        addresses = (self.sender, *self.to, *self.cc, *self.bcc)
        # Conservative bare-address contract, not comprehensive RFC validation.
        # Never rewrite address case, plus-tags, recipient order or body bytes.
        for address in addresses:
            if (len(address) > 254 or address.count('@') != 1 or
                    not all(address.split('@')) or
                    any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c in '<>,;"\\:()[]' for c in address)):
                raise ValueError('Use a bare email address without whitespace or header syntax')
        if any(ord(c) < 32 or ord(c) == 127 for c in self.subject):
            raise ValueError('Subject cannot contain control characters')
        if any((ord(c) < 32 and c not in '\t\r\n') or ord(c) == 127 for c in self.text_body):
            raise ValueError('Body permits only tab, CR and LF control characters')
        if len(self.to) + len(self.cc) + len(self.bcc) > 100:
            raise ValueError('At most 100 recipients are supported')
        recipients = (*self.to, *self.cc, *self.bcc)
        if len(recipients) != len(set(recipients)):
            raise ValueError('Duplicate exact recipients require correction before review')
        return self

    def digest(self) -> str:
        """Detect changed intent, not identity, consent or secrecy."""
        snapshot = ApprovedEmailSnapshot.model_validate(self)
        return _digest(snapshot.model_dump(mode='json'))


class ProviderObservation(EmailContract):
    """Normalized evidence from a future trusted adapter, not self-authenticating.

    'sent' means independently observed provider sent state, not delivery or
    recipient identity verification. No message content is kept in this record.
    """
    scope: AccountScope
    adapter_id: OpaqueID
    source: Literal['provider_observation'] = 'provider_observation'
    kind: Literal['submitted', 'sent', 'received']
    basis: Literal['submission_response', 'sent_item_read', 'received_item_read']
    provider_message_id: OpaqueID | None = None
    provider_thread_id: OpaqueID | None = None
    provider_submission_id: OpaqueID | None = None
    send_request_id: OpaqueID | None = None
    observed_at: datetime
    provider_occurred_at: datetime | None = None

    @field_validator('observed_at', 'provider_occurred_at')
    @classmethod
    def aware_evidence_time(cls, value):
        return _utc(value) if value is not None else None

    @model_validator(mode='after')
    def consistent_evidence(self):
        expected = {'submitted': 'submission_response', 'sent': 'sent_item_read', 'received': 'received_item_read'}
        if self.basis != expected[self.kind]:
            raise ValueError('Observation kind must match its evidence basis')
        if self.kind == 'submitted':
            if self.provider_submission_id is None or self.send_request_id is None:
                raise ValueError('Submission requires a stable provider receipt and local request identity')
        elif self.provider_message_id is None:
            raise ValueError('Mailbox observation requires a provider message identity')
        if self.kind == 'received' and (self.send_request_id is not None or self.provider_submission_id is not None):
            raise ValueError('Received evidence cannot represent an outbound request')
        return self

    def deduplication_key(self) -> str:
        # Submitted and sent remain distinct facts even when message IDs match.
        identity = self.provider_submission_id if self.kind == 'submitted' else self.provider_message_id
        return _digest([self.scope.model_dump(), self.kind, identity])


class UnknownSendOutcome(EmailContract):
    """Local transport uncertainty, kept separately from provider observations.

    This is not proof of failure. Keep it until explicit, source-backed
    reconciliation; even observing a sent item does not silently remove it.
    """
    scope: AccountScope
    send_request_id: OpaqueID
    approved_snapshot_digest: Digest
    detected_at: datetime
    reason: Literal['timeout', 'connection_lost', 'interrupted', 'unusable_response']
    source: Literal['local_transport'] = 'local_transport'
    retry_allowed: Literal[False] = False

    @field_validator('detected_at')
    @classmethod
    def aware_failure_time(cls, value):
        return _utc(value)


def merge_observations(*observations: ProviderObservation) -> tuple[ProviderObservation, ...]:
    """Pure, order-independent union; conflicting same-identity facts fail closed.

    This is NOT a durable concurrent deduplication store. A future ledger needs a
    unique constraint and transaction. Observed-at differences alone are replay;
    keep the earliest observation time. Never collapse submitted into sent.
    """
    merged = {}
    for observation in observations:
        observation = ProviderObservation.model_validate(observation)
        key = observation.deduplication_key()
        previous = merged.get(key)
        if previous is not None:
            if previous.model_dump(exclude={'observed_at'}) != observation.model_dump(exclude={'observed_at'}):
                raise ValueError('Conflicting provider evidence requires reconciliation')
            if previous.observed_at <= observation.observed_at:
                continue
        merged[key] = observation
    return tuple(merged[key] for key in sorted(merged))


class EmailIntegrationDisabled(RuntimeError):
    pass


class DisabledEmailAdapter:
    """The only adapter supplied. No configuration switch enables it."""

    def read_history(self, *args, **kwargs):
        raise EmailIntegrationDisabled('Email history is not connected')

    def submit(self, *args, **kwargs):
        raise EmailIntegrationDisabled('Email sending is not connected')

    def reconcile(self, *args, **kwargs):
        raise EmailIntegrationDisabled('Email reconciliation is not connected')


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Email timestamps must include a timezone')
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError('Email timestamp is outside the supported UTC range') from exc


def _digest(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()
