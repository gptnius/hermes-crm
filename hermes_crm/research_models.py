"""Strict bounded caller-supplied source references, never fetched or verified."""
import unicodedata, uuid, ipaddress, re
from datetime import datetime, date
from typing import Annotated, Literal
from urllib.parse import urlsplit, unquote, parse_qsl
from pydantic import ConfigDict, Field, field_validator, model_validator
from .domain import StrictModel
from .report_store import canonical

def clean(value, multiline=False):
    if any(unicodedata.category(c) in ('Cc','Cf','Cs') and not (multiline and c in '\n\t') for c in value): raise ValueError('Control characters are not allowed')
    return value
class Target(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    target_kind: Literal['contacts','companies']
    target_id: str = Field(min_length=36,max_length=36)
    @field_validator('target_id')
    @classmethod
    def ident(cls,v):
        if str(uuid.UUID(v)) != v: raise ValueError('Canonical UUID required')
        return v
class EvidenceInput(Target):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    target_version: int = Field(strict=True,ge=1)
    question: str = Field(min_length=1,max_length=1000)
    source_url: str = Field(min_length=1,max_length=2048)
    source_title: str = Field(min_length=1,max_length=200)
    observed_at: str = Field(max_length=40)
    published_on: str | None = Field(default=None,max_length=10)
    claims: list[Annotated[str,Field(min_length=1,max_length=2000)]] = Field(min_length=1,max_length=10)
    hypotheses: list[Annotated[str,Field(min_length=1,max_length=2000)]] = Field(default_factory=list,max_length=10)
    @field_validator('question','source_title')
    @classmethod
    def text(cls,v):
        clean(v)
        if not v.strip(): raise ValueError('Nonblank text required')
        return v
    @field_validator('source_url')
    @classmethod
    def url(cls,v):
        clean(v); clean(unquote(v))
        if re.search(r'%(?![0-9a-fA-F]{2})',v): raise ValueError('Invalid URL escape')
        if any(c.isspace() for c in v) or '\\' in v: raise ValueError('Invalid HTTPS reference')
        try:
            u=urlsplit(v); port=u.port
            sensitive={"token","access_token","refresh_token","api_key","apikey","secret","password","signature","sig","x-amz-signature","x-amz-credential","x-goog-signature","key","client_secret","authorization","api-key","x-amz-security-token","credential","credentials","auth","access-token","refresh-token","client-secret"}
            if any(k.lower() in sensitive for k,_ in parse_qsl(u.query,keep_blank_values=True)+parse_qsl(u.fragment,keep_blank_values=True)): raise ValueError()
            if u.scheme!='https' or not u.hostname or u.username is not None or u.password is not None: raise ValueError()
            host=u.hostname
            if '%' in host: raise ValueError()
            try: ipaddress.ip_address(host)
            except ValueError:
                ascii_host=host.encode('idna').decode('ascii').rstrip('.')
                if len(ascii_host)>253 or not all(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?',label) for label in ascii_host.split('.')): raise ValueError()
        except (ValueError,UnicodeError): raise ValueError('HTTPS source without credentials or secret-bearing parameters required') from None
        return v
    @field_validator('observed_at')
    @classmethod
    def timestamp(cls,v):
        clean(v)
        # Match the native/standalone reviewable timestamp grammar without
        # normalizing caller-supplied offsets, precision or spelling.
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])',v):
            raise ValueError('ISO timestamp with T and Z or HH:MM offset required')
        d=datetime.fromisoformat(v.replace('Z','+00:00'))
        if d.tzinfo is None or d.utcoffset() is None: raise ValueError('Explicit offset required')
        return v
    @field_validator('published_on')
    @classmethod
    def day(cls,v):
        if v is not None and date.fromisoformat(v).isoformat()!=v: raise ValueError('ISO date required')
        return v
    @model_validator(mode='after')
    def bounds(self):
        for text in self.claims+self.hypotheses:
            clean(text,multiline=True)
            if not text.strip(): raise ValueError('Nonblank claims required')
        if len(canonical(self.model_dump()).encode())>32768: raise ValueError('Evidence packet exceeds 32 KiB')
        return self
class ProposalInput(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    evidence_id: str = Field(min_length=36,max_length=36)
    evidence_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    evidence_lifecycle_version: int = Field(strict=True,ge=1)
    target_version: int = Field(strict=True,ge=1)
    addition: str = Field(min_length=1,max_length=10000)
    @field_validator('addition')
    @classmethod
    def text(cls,v):
        clean(v,multiline=True)
        if not v.strip(): raise ValueError('Nonblank addition required')
        return v
class Review(StrictModel):
    proposal_version: int = Field(strict=True,ge=1)
    proposal_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
class Apply(Review):
    target_version: int = Field(strict=True,ge=1)
    before_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    after_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
class Lifecycle(StrictModel):
    lifecycle_version: int = Field(strict=True,ge=1)
