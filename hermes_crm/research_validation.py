"""Stored-data shape/consistency checks, not authenticated tamper protection.

Receipts are historical snapshots: validation never compares them to current
record or evidence lifecycle state, so legitimate late retries still work.
"""
import hashlib
import json
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from .domain import CRMError
from .report_store import canonical
from .research_models import EvidenceInput, ProposalInput, Target, clean

Digest=Annotated[str,Field(pattern=r'^[a-f0-9]{64}$')]
Ident=Annotated[str,Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')]
Positive=Annotated[int,Field(strict=True,ge=1)]
Actor=Annotated[str,Field(min_length=1,max_length=160)]
Stamp=Annotated[str,Field(min_length=1,max_length=40)]
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,str_strip_whitespace=False)

class EvidenceMetadata(Strict,Target):
    id: Ident
    target_version: Positive
    digest: Digest
    lifecycle_version: Positive
    archived_at: Stamp | None
    recorded_at: Stamp
    recorded_actor: Actor
    source_url: str = Field(min_length=1,max_length=2048)
    source_title: str = Field(min_length=1,max_length=200)
    observed_at: Stamp
    published_on: str | None = Field(max_length=10)
    claims_count: int = Field(ge=1,le=10)
    hypotheses_count: int = Field(ge=0,le=10)
    @model_validator(mode='after')
    def source_metadata(self):
        EvidenceInput.model_validate(dict(target_kind=self.target_kind,target_id=self.target_id,target_version=self.target_version,question='Metadata validation',source_url=self.source_url,source_title=self.source_title,observed_at=self.observed_at,published_on=self.published_on,claims=['placeholder']))
        EvidenceInput.timestamp(self.recorded_at)
        if self.archived_at is not None: EvidenceInput.timestamp(self.archived_at)
        clean(self.recorded_actor)
        if not self.recorded_actor.strip(): raise ValueError('Empty actor')
        return self

class Disposition(Strict,Target):
    proposal_id: Ident
    proposal_digest: Digest
    proposal_version: Literal[2]
    evidence_id: Ident
    evidence_digest: Digest
    evidence_lifecycle_version: Positive
    target_version: Positive
    before_hash: Digest
    after_hash: Digest
    status: Literal['applied','dismissed']
    actor: Actor
    recorded_at: Stamp
    applied_target_version: Positive | None = None
    @model_validator(mode='after')
    def consistent(self):
        if type(self.proposal_version) is not int: raise ValueError('Invalid version type')
        EvidenceInput.timestamp(self.recorded_at);clean(self.actor)
        if not self.actor.strip():raise ValueError('Empty actor')
        if self.status=='applied' and self.applied_target_version!=self.target_version+1:raise ValueError('Invalid applied version')
        if self.status=='dismissed' and 'applied_target_version' in self.model_fields_set:raise ValueError('Dismissal has no applied version')
        return self

class ProposalSnapshot(Strict,ProposalInput,Target):
    id: Ident
    evidence_id: Ident
    proposal_version: Literal[1,2]
    status: Literal['pending','applied','dismissed']
    before_hash: Digest
    after_hash: Digest
    proposal_digest: Digest
    created_at: Stamp
    created_actor: Actor
    application_receipt: Disposition | None = None
    @model_validator(mode='after')
    def consistent(self):
        if type(self.proposal_version) is not int: raise ValueError('Invalid version type')
        EvidenceInput.timestamp(self.created_at);clean(self.created_actor)
        if not self.created_actor.strip():raise ValueError('Empty actor')
        raw=self.model_dump(exclude={'application_receipt','proposal_digest'})
        raw.update(proposal_version=1,status='pending')
        if hashlib.sha256(canonical(raw).encode()).hexdigest()!=self.proposal_digest:raise ValueError('Proposal digest mismatch')
        if self.status=='pending':
            if self.proposal_version!=1 or self.application_receipt is not None:raise ValueError('Invalid pending proposal')
        else:
            r=self.application_receipt
            if self.proposal_version!=2 or r is None:raise ValueError('Missing disposition')
            expected={k:getattr(self,k) for k in ('proposal_digest','proposal_version','evidence_id','evidence_digest','evidence_lifecycle_version','target_kind','target_id','target_version','before_hash','after_hash','status')}
            if r.proposal_id!=self.id or any(getattr(r,k)!=v for k,v in expected.items()):raise ValueError('Mismatched disposition')
        return self

def loads(raw):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('Duplicate stored key')
            out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs)

def failclosed(fn):
    def wrapped(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except (ValidationError,ValueError,TypeError,KeyError,AttributeError):
            raise CRMError('Stored research data is malformed or inconsistent',503) from None
    return wrapped

@failclosed
def evidence_row(row):
    row=dict(row);row.pop('scope',None)
    packet=loads(row.pop('packet'))
    validated=EvidenceInput.model_validate(packet).model_dump()
    if canonical(validated)!=canonical(packet):raise ValueError('Noncanonical packet')
    if hashlib.sha256(canonical(packet).encode()).hexdigest()!=row['digest']:raise ValueError('Evidence digest mismatch')
    if (packet['target_kind'],packet['target_id'])!=(row['target_kind'],row['target_id']):raise ValueError('Target mismatch')
    row.update(**{k:packet[k] for k in ('target_version','source_url','source_title','observed_at','published_on')},claims_count=len(packet['claims']),hypotheses_count=len(packet['hypotheses']))
    EvidenceMetadata.model_validate(row)
    return row,packet

@failclosed
def proposal_row(row):
    row=dict(row);row.pop('scope',None)
    receipt=row.pop('receipt')
    if receipt is not None:row['application_receipt']=loads(receipt)
    ProposalSnapshot.model_validate(row)
    return row

@failclosed
def response(raw):
    value=loads(raw)
    if not isinstance(value,dict):raise ValueError('Response must be object')
    if 'proposal_id' in value:Disposition.model_validate(value)
    elif 'proposal_digest' in value:ProposalSnapshot.model_validate(value)
    else:EvidenceMetadata.model_validate(value)
    return value

def export_row(name,row):
    if name=='crm_research_evidence':evidence_row(row)
    elif name=='crm_research_proposals':proposal_row(row)
    elif name=='crm_research_operations':response(row['response'])
