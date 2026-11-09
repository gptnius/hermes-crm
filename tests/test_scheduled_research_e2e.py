"""Opt-in real due-run, synthetic model and supplied (not fetched) source packet.

The native-work harness with a separately fingerprinted, narrowly approved
CalVer probe guard extension restricts networking to its model loopback
endpoint and denies real provider credentials. This test proves scheduling and
bound CRM writes, NOT functioning public search or real-model research quality.
"""
import hashlib
import os
from pathlib import Path
import sys
import pytest
import test_native_work_e2e as harness
from scheduled_research_guard import build_guard, EFFECTIVE_GUARD_SHA

HARNESS_SHA='4ff3de7608ecab41c6e9b147c2f6f908285aa808b59fa8539eb1fa596fb486c6'
GUARD_SHA='5f0c4fd97681dfafeb3cd487026279b685e260a6518d7ac72b56c4d4c9cca14b'

def test_scheduled_research_due_harness_seam():
    assert hashlib.sha256(Path(harness.__file__).read_bytes()).hexdigest()==HARNESS_SHA
    assert hashlib.sha256(harness.SAFETY_GUARD.encode()).hexdigest()==GUARD_SHA
    assert harness.PINNED_HOST_SHA=='2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19'
    assert hashlib.sha256(build_guard(harness.SAFETY_GUARD).encode()).hexdigest()==EFFECTIVE_GUARD_SHA
    compile(E2E_CHECK,'<scheduled-research-due-check>','exec')

@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'),reason='HERMES_SOURCE not set')
@pytest.mark.skipif(os.environ.get('HERMES_NATIVE_E2E')!='1',reason='Requires separate guarded due-run opt-in')
@pytest.mark.skipif(sys.version_info[:3]!=(3,14,9),reason='Safety guard requires pinned CPython 3.14.9')
@pytest.mark.parametrize('isolation',['in_process','host'])
def test_scheduled_research_real_due_run(tmp_path,isolation,monkeypatch):
    test_scheduled_research_due_harness_seam()
    monkeypatch.setattr(harness,'SAFETY_GUARD',build_guard(harness.SAFETY_GUARD))
    monkeypatch.setattr(harness,'E2E_CHECK',E2E_CHECK)
    harness.test_native_work_real_due_scheduler_loopback_model(tmp_path,isolation)

# Reuse only the reviewed loopback HTTP framing/stream transport verbatim. No
# environment or cleanup assertion changes. The sole subprocess extension is
# defined and fingerprinted separately in scheduled_research_guard.py.
_TRANSPORT_END='    def next_step(self, data):\n'
assert harness.E2E_CHECK.count(_TRANSPORT_END)==1
TRANSPORT=harness.E2E_CHECK.split(_TRANSPORT_END)[0]
_start=TRANSPORT.index('scheduled_catalog = ')
_end=TRANSPORT.index('\nclass LoopbackServer',_start)
TRANSPORT=TRANSPORT[:_start]+'''run_catalog = {'crm_scheduled_research_run_get', 'crm_scheduled_research_evidence',
    'crm_scheduled_research_propose', 'crm_scheduled_research_report'}
scheduled_catalog = run_catalog | {'web_search'}
forbidden_descriptions = {'crm_task_update', 'crm_work_schedule', 'crm_work_report',
    'crm_scheduled_research_schedule', 'crm_research_evidence_submit', 'cronjob_manage',
    'terminal', 'delegate_task', 'send_message', 'browser_exec'}
discovery_evidence = {}
'''+TRANSPORT[_end:]

NEXT_STEP=r'''
    def next_step(self,data):
        try:
            return self._next_step(data)
        except BaseException as exc:
            import traceback
            with (root / 'scheduled-model-errors.jsonl').open('a') as stream:
                stream.write(json.dumps({'error':repr(exc),'traceback':traceback.format_exc()})+'\n')
                stream.flush()
            raise

    def _next_step(self,data):
        global report_summary
        names={t['function']['name'] for t in data.get('tools',[])}
        assert names <= scheduled_catalog | {'tool_search','tool_describe','tool_call'},names
        assert 'Private fixture note' not in json.dumps(data), 'Private CRM text leaked into research run'
        messages=data['messages'];results=[];call_names={}
        for message in messages:
            for call in message.get('tool_calls') or []:call_names[call['id']]=call['function']['name']
            if message['role']=='tool':results.append((call_names[message['tool_call_id']],json.loads(message['content'])))
        def invoke(name,args):
            if name in names:return name,args,None
            assert 'tool_call' in names
            return 'tool_call',{'calls':[{'name':name,'arguments':args}]},None
        if 'tool_search' in names and not results:
            return 'tool_search',{'queries':['crm_scheduled_research','web_search'],'limit':25},None
        if results and results[-1][0]=='tool_search':
            found=results[-1][1]
            assert not found.get('error'),found
            # Search availability is provider-dependent. This fixture never
            # calls it or claims that supplied source data was fetched.
            assert run_catalog <= set(found['tools']) <= scheduled_catalog,found
            assert all(set(group['matches'])<=scheduled_catalog for group in found['results']),found
            discovery_evidence['tools']=sorted(found['tools'])
            return 'tool_describe',{'names':(sorted(run_catalog)+sorted(forbidden_descriptions))[:10]},None
        if results and results[-1][0]=='tool_describe':
            batches=[(sorted(run_catalog)+sorted(forbidden_descriptions))[i:i+10] for i in (0,10)]
            descriptions=[value for name,value in results if name=='tool_describe']
            assert len(descriptions)<=len(batches),descriptions
            all_missing=set();all_tools=set()
            for batch,described in zip(batches,descriptions):
                assert not described.get('error'),described
                assert set(described['tools'])==set(batch)&run_catalog,described
                missing=set(described.get('not_found',[]))|set(described.get('errors',{}))
                assert missing==set(batch)&forbidden_descriptions,described
                all_missing.update(missing);all_tools.update(described['tools'])
            if len(descriptions)<len(batches):
                return 'tool_describe',{'names':batches[len(descriptions)]},None
            assert all_tools==run_catalog and all_missing==forbidden_descriptions
            discovery_evidence['forbidden_unavailable']=sorted(all_missing)
        useful=[]
        for name,value in results:
            if name in ('tool_search','tool_describe'):continue
            assert value.get('ok') is True,value
            useful.append(value['data'])
        common={'assignment_id':expected['assignment_id'],'generation':1}
        if not useful:return invoke('crm_scheduled_research_run_get',common)
        work=useful[0]
        assert work['task_id']==expected['task_id'] and work['target_id']==expected['target_id']
        if len(useful)==1:
            packet={'target_kind':'contacts','target_id':work['target_id'],'target_version':work['target_version'],
                'question':'Synthetic supplied fixture only; no live research',
                'source_url':'https://synthetic.example.test/supplied-fixture',
                'source_title':'Synthetic supplied source, never fetched',
                'observed_at':datetime.now(timezone.utc).isoformat(),
                'claims':['Synthetic supplied claim for due-run persistence test.'],'hypotheses':[]}
            return invoke('crm_scheduled_research_evidence',dict(common,operation_id='source-1',data=packet))
        if len(useful)==2:
            e=useful[1]
            proposal={'evidence_id':e['id'],'evidence_digest':e['digest'],'evidence_lifecycle_version':e['lifecycle_version'],
                'target_version':work['target_version'],'addition':'Synthetic supplied claim (https://synthetic.example.test/supplied-fixture). Not live research.'}
            return invoke('crm_scheduled_research_propose',dict(common,operation_id='proposal-1',data=proposal))
        if len(useful)==3:
            assert useful[2]['status']=='pending'
            report_summary='SYNTHETIC supplied source and cited proposal saved for review. No public search was performed; task remains open.'
            return invoke('crm_scheduled_research_report',dict(common,operation_id='result',outcome='completed',summary=report_summary))
        assert len(useful)==4 and useful[3]['awaiting_human_review'] is True,useful
        return None,None,report_summary
'''

RUN=r'''
server=LoopbackServer(('127.0.0.1',port),Model)
server_thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True)
server_thread.start()
stop=threading.Event();ticker=None;manager=None;creator=None;owned_jobs=set()
evidence={'synthetic_model':True,'synthetic_supplied_source':True,'public_search_executed':False,
    'live_model_quality_verified':False,'desktop_notification_verified':False}
async def run():
    global ticker,manager,creator
    from hermes_cli.plugins import get_plugin_manager
    from tools.registry import registry
    from cron import jobs,executions
    from cron.scheduler_provider import InProcessCronScheduler
    from gateway.config import GatewayConfig,Platform
    from gateway.run import GatewayRunner
    from gateway.session_authority import initialize_session_authority
    from gateway.session_cron import unbind_owner
    from run_agent import AIAgent
    from gateway.session_context import scoped_current_session_id
    manager=get_plugin_manager();manager.discover_and_load()
    runner=GatewayRunner(GatewayConfig())
    authority=await initialize_session_authority(runner,profile_id='default',instance_id='synthetic-research-e2e')
    creator=AIAgent(model='synthetic-crm-fixture',provider='custom',api_key='no-key-required',
        base_url=f'http://127.0.0.1:{port}/v1',enabled_toolsets=['crm_read','crm_write',
            'crm_scheduled_research_schedule_v1','crm_scheduled_research_read_v1','cronjob','no_mcp'],
        quiet_mode=True,skip_context_files=True,skip_memory=True,skip_background_review=True)
    def raw(name,args,**context):
        if context.get('parent_agent') is creator:
            context.setdefault('session_id','synthetic-creator');context.setdefault('task_id','synthetic-scheduling-turn')
            with scoped_current_session_id('synthetic-creator'):
                value=registry.dispatch(name,args,scope=manager.scope_key,**context)
        else:value=registry.dispatch(name,args,scope=manager.scope_key,**context)
        return json.loads(value) if isinstance(value,str) else value
    def tool(name,args,**context):
        value=raw(name,args,**context)
        assert value.get('ok') is True,(name,value)
        return value['data']
    real_cron=registry.get_entry('cronjob_manage',scope=manager.scope_key).handler
    observed=[]
    def observe(args,**context):
        observed.append(args['action'])
        assert context['session_id']=='synthetic-creator' and context['task_id']=='synthetic-scheduling-turn'
        if args['action']=='create':
            assert args['paused'] is True and args['repeat']==1
            assert args['enabled_toolsets']==['search','crm_scheduled_research_run_v1','no_mcp']
            assert args['deliver']==args['failure_deliver']=='local'
        if args['action']=='resume':
            job=jobs.get_job(args['job_id']);assert job['enabled'] is False and job['state']=='paused'
            with sqlite3.connect(home/'plugin-data/hermes-crm/data.db') as db:
                row=db.execute('SELECT job_id,state FROM crm_scheduled_research_v1 WHERE id=?',(expected['assignment_id'],)).fetchone()
            assert row==(args['job_id'],'resume_unknown'),row
        value=real_cron(args,**context);parsed=json.loads(value)
        if args['action']=='create' and parsed.get('success'):owned_jobs.add(parsed['job_id'])
        return value
    registry.get_entry('cronjob_manage',scope=manager.scope_key).handler=observe
    try:
        contact=tool('crm_contact_create',{'name':'Synthetic research subject','notes':'Private fixture note'})
        task=tool('crm_task_create',{'title':'Synthetic research preparation','contact_id':contact['id'],
            'due_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
        due=datetime.now(timezone.utc)+timedelta(seconds=12)
        def create_intent(run_at,key):
            return tool('crm_scheduled_research_create',{'data':{'task_id':task['id'],'task_version':task['version'],
                'human_owner':'Synthetic owner','target_kind':'contacts','target_id':contact['id'],
                'target_version':contact['version'],'public_question':'Exercise supplied synthetic source storage only; do not browse.',
                'run_at':run_at.isoformat(timespec='microseconds'),'research':'search','propose_note':True,'max_sources':1},
                'idempotency_key':key},parent_agent=creator)
        work=create_intent(due,'synthetic-due-research')
        expected.update(assignment_id=work['id'],task_id=task['id'],target_id=contact['id'])
        work=tool('crm_scheduled_research_schedule',{'assignment_id':work['id']},parent_agent=creator)
        assert work['state']=='scheduled' and observed==['create','resume'],work
        assert not model_requests
        ticker=threading.Thread(target=InProcessCronScheduler().start,args=(stop,),kwargs={'interval':.1},daemon=True)
        ticker.start();await asyncio.sleep(.5)
        assert datetime.now(timezone.utc)<due and not model_requests
        assert executions.list_executions(job_id=work['job_id'])==[]
        deadline=time.monotonic()+70;terminal=None
        while time.monotonic()<deadline:
            rows=executions.list_executions(job_id=work['job_id'])
            if rows and rows[0]['status'] not in {'claimed','running'}:terminal=rows[0];break
            await asyncio.sleep(.1)
        assert terminal and terminal['status']=='completed',(terminal,model_errors)
        result=tool('crm_scheduled_research_get',{'assignment_id':work['id']})
        assert result['state']=='result_reported',result
        receipts={r['kind']:r['result'] for r in result['receipts']}
        assert set(receipts)=={'evidence','proposal','report'},receipts
        report=receipts['report'];identity=report['identity']
        assert identity['execution_id']==terminal['id'] and identity['job_id']==work['job_id']
        assert identity['source']==terminal['source']=='builtin'
        assert identity['scheduled_instant']==terminal['scheduled_instant']==work['payload']['run_at']
        assert identity['profile']=='default' and report['generation']==1
        assert report['awaiting_human_review'] and not report['host_terminal_success_verified']
        assert report['summary']==report_summary
        assert receipts['proposal']['status']=='pending'
        assert receipts['proposal']['evidence_id']==receipts['evidence']['id']
        assert tool('crm_task_get',{'id':task['id']})['status']=='open'
        with sqlite3.connect(home/'plugin-data/hermes-crm/data.db') as db:
            assert db.execute('SELECT notes,version FROM crm_contacts WHERE id=?',(contact['id'],)).fetchone()==('Private fixture note',1)
        approved_due=datetime.fromisoformat(work['payload']['run_at'])
        assert datetime.fromisoformat(terminal['started_at'])>=approved_due
        assert model_request_received_at and all(datetime.fromisoformat(t)>=approved_due for t in model_request_received_at)
        output=list((jobs.get_cron_output_dir()/work['job_id']).glob('*.md'))
        assert len(output)==1 and report_summary in output[0].read_text()
        from hermes_state_keys import CRON_PRINCIPAL_ID,cron_request_id,local_identity
        from hermes_state_runtime import find_session_admission
        from gateway.session_results import admission_result
        request_id=cron_request_id(work['job_id'],terminal['id'])
        session_id=local_identity(authority.profile_id,CRON_PRINCIPAL_ID,request_id)
        admission=find_session_admission(authority.db,principal_id=CRON_PRINCIPAL_ID,session_id=session_id,request_id=request_id)
        assert admission and admission['status']=='terminal' and admission['outcome']=='completed',admission
        saved=admission_result(authority.db,admission['admission_id'])
        assert saved['result']['completed'] is True and saved['result']['failed'] is False
        assert saved['result']['final_response']==report_summary
        before=len(model_requests);await asyncio.sleep(.6)
        assert len(model_requests)==before and len(executions.list_executions(job_id=work['job_id']))==1
        assert len(tool('crm_scheduled_research_get',{'assignment_id':work['id']})['receipts'])==3
        cancelled_due=datetime.now(timezone.utc)+timedelta(seconds=3)
        cancelled=create_intent(cancelled_due,'synthetic-cancelled-research');expected['assignment_id']=cancelled['id']
        cancelled=tool('crm_scheduled_research_schedule',{'assignment_id':cancelled['id']},parent_agent=creator)
        cancelled=tool('crm_scheduled_research_cancel',{'assignment_id':cancelled['id'],'expected_version':cancelled['version']},parent_agent=creator)
        assert cancelled['state']=='cancelled' and jobs.get_job(cancelled['job_id'])['enabled'] is False
        await asyncio.sleep(max(0,(cancelled_due-datetime.now(timezone.utc)).total_seconds())+.4)
        assert len(model_requests)==before and executions.list_executions(job_id=cancelled['job_id'])==[]
        assert tool('crm_scheduled_research_get',{'assignment_id':cancelled['id']})['receipts']==[]
        assert tool('crm_task_get',{'id':task['id']})['status']=='open'
        evidence.update(terminal_status=terminal['status'],actual_report=report,model_requests=before,
            scheduled_discovery=discovery_evidence,canonical_admission_verified=True,local_output_verified=True,
            task_still_open=True,notes_unchanged=True,cancelled_before_due_never_executed=True,
            duplicate_extra_ticks=False,all_model_requests_at_or_after_due=True)
    finally:
        stop.set()
        if ticker:
            await asyncio.to_thread(ticker.join,10);assert not ticker.is_alive()
        registry.get_entry('cronjob_manage',scope=manager.scope_key).handler=real_cron
        for job_id in owned_jobs:
            actions=('pause','remove') if jobs.get_job(job_id).get('enabled') else ('remove',)
            for action in actions:
                value=json.loads(real_cron({'action':action,'job_id':job_id},parent_agent=creator))
                assert value.get('success'),value
        assert jobs.list_jobs(include_disabled=True)==[]
        unbind_owner(authority);creator.close();runner.session_store.close_all_db_handles()
        if runner._executor:runner._executor.shutdown(wait=True)
        evidence['cleanup']={'enabled_jobs':0,'scheduler_stopped':ticker is None or not ticker.is_alive()}
try:
    asyncio.run(run())
finally:
    stop.set();server.shutdown();server.server_close();server_thread.join(10)
    if manager is not None:
        host=getattr(manager,'_plugin_host_instance',None);manager.unload()
        if host is not None:
            host.shutdown();assert not host.alive
        evidence.setdefault('cleanup',{})['plugin_host_stopped']=host is None or not host.alive
    evidence.setdefault('cleanup',{})['endpoint_stopped']=not server_thread.is_alive()
    (root/'evidence.json').write_text(json.dumps(evidence,indent=2))
assert not model_errors,model_errors
print('PASS actual due scheduler and deterministic model')
'''
E2E_CHECK=TRANSPORT+NEXT_STEP+RUN
