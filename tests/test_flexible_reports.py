import pytest
from pydantic import ValidationError
from sqlalchemy import insert, update
from hermes_crm.domain import CRM, contacts, deals, tasks
from hermes_crm.reports import ReportEngine, ReportDefinition

@pytest.fixture
def setup():
    crm=CRM('sqlite:///:memory:')
    yield crm,ReportEngine(crm)
    crm.close()

def condition(field,op,value): return dict(field=field,op=op,value=value)
def contact(crm,name='Person',**kw): return crm.create('contacts',dict(name=name,**kw))
def deal(crm,c,stage='lead',value=100): return crm.create('deals',dict(title='Deal',contact_id=c['id'],stage=stage,value=value))

def test_complete_dataset_aggregates_and_pages(setup):
    crm,e=setup
    rows=[dict(id=f'{i:04}',name=f'N{i}',email='',company='',title='',lifecycle='lead',notes='',version=1,created_at='2026-01-01T00:00:00.000000+00:00',updated_at='2026-01-01T00:00:00.000000+00:00') for i in range(601)]
    with crm.engine.begin() as conn: conn.execute(insert(contacts),rows)
    result=e.run(dict(entity='contacts',columns=['id'],measure={'op':'count'}),limit=100,offset=500)
    assert result['total']==result['metric']==601
    assert result['items'][0]['id']=='0500' and len(result['items'])==100
    grouped=e.run(dict(entity='contacts',group_by={'field':'created_at','interval':'day'}))
    assert grouped['groups'][0]['value']==601
    detail=e.run(grouped['groups'][0]['detail_definition'],evaluated_at=grouped['evaluated_at'])
    assert detail['total']==601

def test_correlated_counts_stages_and_double_links(setup):
    crm,e=setup;c=contact(crm); d=deal(crm,c,'won');deal(crm,c,'lead');contact(crm,'Empty')
    crm.create('tasks',dict(title='T',contact_id=c['id'],deal_id=d['id'],due_at='2026-01-01T00:00:00Z'))
    definition=dict(entity='contacts',columns=['name','linked_stages','deal_count','open_followup_count','overdue_followup_count'],filter=condition('linked_stages','has_all',['won','lead']))
    r=e.run(definition,evaluated_at='2026-02-01T00:00:00Z')
    assert r['total']==1 and r['items'][0]['deal_count']==2
    assert r['items'][0]['open_followup_count']==r['items'][0]['overdue_followup_count']==1
    assert r['items'][0]['linked_stages']==['lead','won']
    assert e.run(dict(entity='contacts',filter=condition('linked_stages','has_none',['won'])))['total']==1
    assert e.run(dict(entity='contacts',filter=condition('linked_stages','is_empty',True)))['total']==1

def test_nulls_literal_text_any_all_and_injection(setup):
    crm,e=setup;contact(crm,'100%_safe');contact(crm,'Other')
    for query in ['%_',"' OR 1=1 --"]:
        r=e.run(dict(entity='contacts',filter=condition('name','contains',query)))
        assert r['total']==(1 if query=='%_' else 0)
    filt={'all':[condition('last_logged_contact_at','is_null',None),{'any':[condition('name','eq','Other'),condition('name','contains','safe')]}]}
    assert e.run(dict(entity='contacts',filter=filt))['total']==2

def test_sum_avg_day_and_null_drilldowns(setup):
    crm,e=setup;c=contact(crm)
    a=deal(crm,c,'won',200); b=deal(crm,c,'won',200);deal(crm,c,'lost',999)
    with crm.engine.begin() as conn:
        conn.execute(update(deals).where(deals.c.id==a['id']).values(created_at='2026-01-01T23:59:59.000000+00:00'))
        conn.execute(update(deals).where(deals.c.id==b['id']).values(created_at='2026-01-02T00:00:00.000000+00:00'))
    d=dict(entity='deals',filter=condition('stage','eq','won'),measure=dict(op='sum',field='value'),group_by=dict(field='created_at',interval='day'))
    result=e.run(d)
    assert result['metric']==400 and len(result['groups'])==2
    assert e.run(result['detail_definition'],evaluated_at=result['evaluated_at'])['total']==2
    for bucket in result['groups']:
        detail=e.run(bucket['detail_definition'],evaluated_at=bucket['evaluated_at'])
        assert detail['total']==bucket['count']==1
        metric=e.run(dict(bucket['detail_definition'],measure={'op':'sum','field':'value'}))
        assert metric['metric']==bucket['value']
    null=e.run(dict(entity='deals',group_by={'field':'expected_close_date'}))
    assert null['groups'][0]['key'] is None
    assert e.run(null['groups'][0]['detail_definition'])['total']==3

@pytest.mark.parametrize('change',[
 {'wat':1},{'schema_version':True},{'columns':['notes']},{'columns':['id']*21},
 {'filter':{'all':[]}},{'filter':condition('name','gt','x')},
 {'filter':condition('deal_count','eq',True)},{'filter':condition('name','in',[])},
 {'filter':condition('name','in',['x']*101)},{'filter':condition('created_at','gte','2026-01-01')},
 {'sort':[{'field':'linked_stages'}]},{'group_by':{'field':'linked_stages'}},
 {'measure':{'op':'sum','field':'name'}},{'timezone':'America/New_York'},
 {'filter':condition('name','eq',None)}, {'filter':condition('name','is_null',True)},
])
def test_rejects_invalid(change):
    with pytest.raises((ValidationError,ValueError)):
        ReportDefinition.model_validate(dict(entity='contacts',**change))

def test_stable_order_group_cap_and_no_mutation(setup):
    crm,e=setup
    for i in range(105): contact(crm,f'N{i:03}')
    definition={'entity':'contacts','group_by':{'field':'name'}}
    result=e.run(definition)
    assert result['total_groups']==105 and result['truncated'] and len(result['groups'])==100
    assert definition=={'entity':'contacts','group_by':{'field':'name'}}
    a=e.run({'entity':'contacts','columns':['id','company'],'sort':[{'field':'company'}]},limit=50)
    b=e.run({'entity':'contacts','columns':['id','company'],'sort':[{'field':'company'}]},limit=50,offset=50)
    assert not ({r['id'] for r in a['items']}&{r['id'] for r in b['items']})

def test_task_inherited_contact_name_and_frozen_overdue(setup):
    crm,e=setup;c=contact(crm,'Parent');d=deal(crm,c)
    crm.create('tasks',dict(title='Inherited',deal_id=d['id'],due_at='2026-02-01T00:00:00Z'))
    assert e.run(dict(entity='tasks',columns=['contact_name']))['items']==[{'contact_name':'Parent'}]
    definition=dict(entity='contacts',columns=['overdue_followup_count','next_followup_at'])
    assert e.run(definition,evaluated_at='2026-01-01T00:00:00Z')['items'][0]['overdue_followup_count']==0
    assert e.run(definition,evaluated_at='2026-03-01T00:00:00Z')['items'][0]['overdue_followup_count']==1

def test_derived_measure_filters_and_empty_aggregate(setup):
    crm,e=setup;a=contact(crm,'A');b=contact(crm,'B');contact(crm,'C')
    deal(crm,a);deal(crm,a);deal(crm,b)
    definition=dict(entity='contacts',filter=condition('deal_count','gte',1),measure={'op':'sum','field':'deal_count'},group_by={'field':'contact_type'})
    result=e.run(definition)
    assert result['total']==2 and result['metric']==3
    assert result['groups'][0]['value']==3
    assert e.run(result['groups'][0]['detail_definition'])['total']==2
    empty=dict(entity='deals',filter=condition('value','gt',999),measure={'op':'sum','field':'value'})
    assert e.run(empty)['metric']==0
    empty['measure']['op']='avg'
    assert e.run(empty)['metric'] is None

def test_bounds_and_canonical_timestamp(setup):
    crm,e=setup
    for limit,offset in [(0,0),(101,0),(True,0),(5,-1),(5,False)]:
        with pytest.raises(Exception): e.run({'entity':'contacts'},limit=limit,offset=offset)
    a=e.run(dict(entity='contacts',filter=condition('created_at','gte','2026-01-01T02:00:00+02:00')))
    b=e.run(dict(entity='contacts',filter=condition('created_at','gte','2026-01-01T00:00:00Z')))
    assert a['definition_hash']==b['definition_hash']
    with pytest.raises(ValidationError):
        ReportDefinition.model_validate(dict(entity='contacts',group_by={'field':'company'},filter={'all':[condition('name','ne',str(i)) for i in range(31)]}))

def test_last_contact_ledger_and_read_only_initialization(setup):
    from sqlalchemy import inspect
    from hermes_crm.report_interactions import InteractionStore
    crm,e=setup;c=contact(crm)
    before=inspect(crm.engine).get_table_names()
    definition=dict(entity='contacts',columns=['last_logged_contact_at'])
    assert e.run(definition)['items']==[{'last_logged_contact_at':None}]
    assert inspect(crm.engine).get_table_names()==before
    store=InteractionStore(crm)
    older=store.create(dict(contact_id=c['id'],happened_at='2025-01-01T00:00:00Z',kind='call',summary='One'),1,'test','interaction-one')
    newer=store.create(dict(contact_id=c['id'],happened_at='2025-02-01T00:00:00Z',kind='call',summary='Two'),1,'test','interaction-two')
    assert e.run(definition)['items'][0]['last_logged_contact_at']==newer['happened_at']
    store.void(newer['id'],1,'Correction','test','interaction-void')
    assert e.run(definition)['items'][0]['last_logged_contact_at']==older['happened_at']
    from sqlalchemy import event
    checkouts=[]
    def checked_out(*args): checkouts.append(True)
    event.listen(crm.engine.pool,'checkout',checked_out)
    try: e.run(definition)
    finally: event.remove(crm.engine.pool,'checkout',checked_out)
    assert len(checkouts)==1, 'Ledger schema, scope and rows must use the report snapshot connection'


def test_fractional_average_is_json_safe(setup):
    import json
    crm,e=setup;c=contact(crm);deal(crm,c,value=100);deal(crm,c,value=101)
    result=e.run(dict(entity='deals',measure={'op':'avg','field':'value'},group_by={'field':'stage'}))
    assert result['metric']==100.5 and result['groups'][0]['value']==100.5
    json.dumps(result)


def test_one_response_uses_repeatable_snapshot(setup):
    """Commit a new row after the count, before items/metric/bucket queries."""
    from tempfile import TemporaryDirectory
    from sqlalchemy import event
    crm,_=setup
    with TemporaryDirectory() as directory:
        local=CRM('sqlite:///'+directory+'/snapshot.db') if crm.backend=='sqlite' else crm
        try:
            if local.backend=='sqlite':
                # Test-only WAL allows a genuinely independent writer to commit
                # while the report's read transaction remains open.
                with local.engine.connect() as conn: conn.exec_driver_sql('PRAGMA journal_mode=WAL')
            engine=ReportEngine(local)
            for grouped in (False,True):
                contact(local,'Before')
                before=len(local.list('contacts'))
                inserted=[]
                def insert_after_count(conn,cursor,statement,parameters,context,executemany):
                    if not inserted and statement.startswith('SELECT count(*) AS count_1') and 'crm_contacts' in statement:
                        inserted.append(True)
                        contact(local,'Concurrent')
                definition=dict(entity='contacts',columns=['id'],measure={'op':'count'})
                if grouped: definition['group_by']={'field':'contact_type'}
                event.listen(local.engine,'after_cursor_execute',insert_after_count)
                try: result=engine.run(definition)
                finally: event.remove(local.engine,'after_cursor_execute',insert_after_count)
                assert inserted
                assert result['total']==result['metric']==before
                if grouped: assert sum(bucket['count'] for bucket in result['groups'])==before
                else: assert len(result['items'])==before
                # Separate requests are live and see the committed change.
                assert engine.run(definition)['total']==before+1
        finally:
            if local is not crm: local.close()


def test_maximum_day_drilldown(setup):
    crm,e=setup;c=contact(crm)
    crm.create('tasks',dict(title='Last day',due_at='9999-12-31T12:00:00Z'))
    crm.create('deals',dict(title='Last date',contact_id=c['id'],close_date='9999-12-31'))
    for entity,field in [('tasks','due_at'),('deals','expected_close_date')]:
        result=e.run(dict(entity=entity,group_by={'field':field,'interval':'day'}))
        assert result['groups'][0]['key']=='9999-12-31'
        detail=e.run(result['groups'][0]['detail_definition'])
        assert detail['total']==result['groups'][0]['count']==1
