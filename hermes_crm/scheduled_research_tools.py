"""Additive registration seam; call explicitly from plugin.register.

No existing toolset gains a tool, and registration does not schedule a job.
"""
from typing import Literal
from pydantic import Field
from .relationship_tools import Strict
from .scheduled_research import ScheduledResearchStore, ResearchIntent, RUN_TOOLSET
from .research_models import EvidenceInput, ProposalInput

class Create(Strict):
    data: ResearchIntent
    idempotency_key: str = Field(min_length=1,max_length=120)
class Get(Strict):
    assignment_id: str = Field(min_length=36,max_length=36)
class List(Strict):
    task_id: str | None = Field(default=None,min_length=36,max_length=36)
    limit: int = Field(default=50,ge=1,le=100)
class Cancel(Get):
    expected_version: int = Field(ge=1)
class Run(Get):
    generation: int = Field(ge=1)
class Evidence(Run):
    operation_id: str = Field(min_length=1,max_length=80)
    data: EvidenceInput
class Proposal(Run):
    operation_id: str = Field(min_length=1,max_length=80)
    data: ProposalInput
class Report(Run):
    operation_id: Literal['result'] = 'result'
    summary: str = Field(min_length=1,max_length=10000)
    outcome: Literal['completed','blocked','failed'] = 'completed'

def register_scheduled_research_tools(register,ctx):
    def tool(name,description,model,toolset,action):
        schema=model.model_json_schema()
        def inline(v):
            if isinstance(v,dict):
                if '$ref' in v: return inline(schema['$defs'][v['$ref'].split('/')[-1]])
                return {k:inline(x) for k,x in v.items()}
            if isinstance(v,list): return [inline(x) for x in v]
            return v
        register(name,description,inline(schema['properties']),schema.get('required',[]),
            lambda crm,a,context:action(ScheduledResearchStore(crm, initialize=name == 'crm_scheduled_research_create'),a,context),
            toolset=toolset,argument_model=model)
    admin='crm_scheduled_research_schedule_v1'; read='crm_scheduled_research_read_v1'
    tool('crm_scheduled_research_create',
        'Save an explicitly requested future public research assignment for an existing open task and one exact current Company/Contact. Task version and explicit human owner are required; due time is separate from research run time. '
        'The public_question is approved input to external research tools and the configured model provider: exclude private notes and secrets. '
        'Choose search (search only) or web (search and extraction), a source limit and whether one note proposal is permitted. '
        'Intent only, not execution. No notes are applied, people contacted, grants changed or tasks completed.',Create,admin,
        lambda s,a,c:s.create(a['data'],idempotency_key=a['idempotency_key']))
    tool('crm_scheduled_research_get','Read saved scheduled research and authenticated operation receipts. A report is an agent claim awaiting review, not host completion.',Get,read,
        lambda s,a,c:s.get(a['assignment_id']))
    tool('crm_scheduled_research_list','List current profile research assignments; no host action.',List,read,
        lambda s,a,c:s.list(**a))
    tool('crm_scheduled_research_schedule',
        'On explicit scheduling intent, create paused, bind exact host job, then resume the future one-shot. '
        'Uses only reviewed research preset, assignment-bound writers and no_mcp. Retain host safeguards. '
        'Cron approval policy is unattended, not an interactive approval prompt. Availability is not guaranteed. '
        'Unknown outcomes must be checked, never automatically recreated.',Get,admin,
        lambda s,a,c:s.schedule(ctx,a['assignment_id'],**c))
    tool('crm_scheduled_research_reconcile','Observe the exact bound host job; never adopt, resume or retry an uncertain schedule.',Get,admin,
        lambda s,a,c:s.reconcile(ctx,a['assignment_id'],**c))
    tool('crm_scheduled_research_cancel','Invalidate reviewed assignment version and request pause of its exact future job. Does not stop a running agent.',Cancel,admin,
        lambda s,a,c:s.cancel(ctx,a['assignment_id'],expected_version=a['expected_version'],**c))
    tool('crm_scheduled_research_run_get','Read only this authenticated scheduled occurrence and approved public research input. No private notes or ordinary record text.',Run,RUN_TOOLSET,
        lambda s,a,c:s.run_get(ctx,a['assignment_id'],generation=a['generation']))
    tool('crm_scheduled_research_evidence','Save a cited source packet for the approved target/version from this authenticated occurrence. Sources remain unverified claims. Stable operation ID required for retries.',Evidence,RUN_TOOLSET,
        lambda s,a,c:s.evidence(ctx,a['assignment_id'],**{k:v for k,v in a.items() if k!='assignment_id'}))
    tool('crm_scheduled_research_propose','Prepare the one permitted cited note addition using evidence saved by this assignment. Never applies notes. Requires authenticated occurrence and stable retry ID.',Proposal,RUN_TOOLSET,
        lambda s,a,c:s.propose(ctx,a['assignment_id'],**{k:v for k,v in a.items() if k!='assignment_id'}))
    tool('crm_scheduled_research_report','Report this authenticated scheduled occurrence once. Outcome is an agent claim awaiting review, not task or host completion.',Report,RUN_TOOLSET,
        lambda s,a,c:s.report(ctx,a['assignment_id'],**{k:v for k,v in a.items() if k!='assignment_id'}))
