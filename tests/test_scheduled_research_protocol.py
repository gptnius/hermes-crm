"""Pure synthetic protocol tests; no host/model/process/network execution."""
import ast
import json
import textwrap
from datetime import datetime, timezone

import pytest
from test_scheduled_research_e2e import NEXT_STEP, TRANSPORT


def fixture(tmp_path):
    tree=ast.parse(TRANSPORT+'    pass\n')
    names={'run_catalog','scheduled_catalog','forbidden_descriptions','discovery_evidence'}
    assignments=[node for node in tree.body if isinstance(node,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id in names for t in node.targets)]
    ns=dict(json=json,root=tmp_path,datetime=datetime,timezone=timezone,
            expected={'assignment_id':'a','task_id':'t','target_id':'c'})
    exec(compile(ast.Module(body=assignments,type_ignores=[]),'<catalog>','exec'),ns)
    exec('class Model:\n'+NEXT_STEP,ns)
    data={'tools':[{'function':{'name':n}} for n in ('tool_search','tool_describe','tool_call')],'messages':[]}
    return ns,ns['Model'](),data


def respond(data,name,value):
    ident=str(len(data['messages']))
    data['messages'] += [{'role':'assistant','tool_calls':[{'id':ident,'function':{'name':name}}]},
                        {'role':'tool','tool_call_id':ident,'content':json.dumps(value)}]


def discover(ns,model,data):
    name,args,_=model.next_step(data)
    assert name=='tool_search' and 1<=len(args['queries'])<=7  # pinned literal API limit
    respond(data,name,{'tools':{n:{} for n in ns['run_catalog']},
        'results':[{'matches':sorted(ns['run_catalog'])}]})


def test_complete_protocol_covers_all_positives_and_negatives(tmp_path):
    ns,model,data=fixture(tmp_path);discover(ns,model,data)
    requested=[]
    for _ in range(2):
        name,args,_=model.next_step(data)
        assert name=='tool_describe' and 1<=len(args['names'])<=10  # pinned literal API limit
        requested+=args['names']
        respond(data,name,{'tools':{n:{} for n in args['names'] if n in ns['run_catalog']},
            'not_found':[n for n in args['names'] if n in ns['forbidden_descriptions']]})
    assert len(requested)==14 and len(set(requested))==14
    assert set(requested)==ns['run_catalog']|ns['forbidden_descriptions']
    assert len(ns['run_catalog'])==4 and len(ns['forbidden_descriptions'])==10
    name,args,_=model.next_step(data)
    assert name=='tool_call' and args['calls'][0]['name']=='crm_scheduled_research_run_get'
    assert set(ns['discovery_evidence']['forbidden_unavailable'])==ns['forbidden_descriptions']
    work=dict(task_id='t',target_id='c',target_version=1)
    for value,expected in [(work,'crm_scheduled_research_evidence'),
        ({'id':'e','digest':'d','lifecycle_version':1},'crm_scheduled_research_propose'),
        ({'status':'pending'},'crm_scheduled_research_report')]:
        respond(data,'tool_call',{'ok':True,'data':value})
        name,args,_=model.next_step(data)
        assert args['calls'][0]['name']==expected
    respond(data,'tool_call',{'ok':True,'data':{'awaiting_human_review':True}})
    assert model.next_step(data)[0] is None


@pytest.mark.parametrize('stage',['search','describe','unexpected_positive','missing_negative','run'])
def test_errors_persist_diagnostic_before_propagation(tmp_path,stage):
    ns,model,data=fixture(tmp_path)
    if stage=='search':respond(data,'tool_search',{'error':'too many queries'})
    elif stage=='run':respond(data,'tool_call',{'ok':False,'error':'rejected'})
    else:
        discover(ns,model,data)
        _,args,_=model.next_step(data)
        value={'tools':{n:{} for n in args['names'] if n in ns['run_catalog']},
               'not_found':[n for n in args['names'] if n in ns['forbidden_descriptions']]}
        if stage=='describe':value={'error':'too many names'}
        if stage=='unexpected_positive':value['tools']['terminal']={}
        if stage=='missing_negative':value['not_found'].pop()
        respond(data,'tool_describe',value)
    with pytest.raises(AssertionError):model.next_step(data)
    saved=json.loads((tmp_path/'scheduled-model-errors.jsonl').read_text())
    assert 'AssertionError' in saved['error'] and '_next_step' in saved['traceback']
