"""Portable page contracts reused by disposable PostgreSQL wrappers."""
import pytest
from sqlalchemy import inspect, text
from hermes_crm.domain import CRMError
from hermes_crm.scheduled_research import ScheduledResearchStore
from test_scheduled_research import setup


def test_page_task_filter_total_and_offset(setup):
    crm,store,target,data=setup
    other=crm.create('tasks',{'title':'Other synthetic task','due_at':'2030-04-02T12:00:00Z'})
    # Interleave task rows: filtering must happen before database pagination.
    wanted=[]
    for n in range(3):
        wanted.append(store.create(data,idempotency_key=f'page-{n}'))
        store.create(dict(data,task_id=other['id'],task_version=other['version']),idempotency_key=f'other-{n}')
    reader=ScheduledResearchStore(crm,initialize=False)
    page=reader.page(task_id=data['task_id'],limit=1,offset=1)
    assert page['initialized'] is True and page['storage']=='present'
    assert page['total']==3 and page['limit']==1 and page['offset']==1
    assert [r['id'] for r in page['items']]==[wanted[1]['id']]
    assert reader.page()['total']==6
    assert reader.page(task_id=other['id'])['total']==3
    beyond=reader.page(task_id=data['task_id'],limit=1,offset=3)
    assert beyond['total']==3 and beyond['items']==[]
    assert reader.page(task_id='00000000-0000-0000-0000-000000000001')['total']==0


@pytest.mark.parametrize('damage',['absent','partial','newer','malformed'])
def test_page_optional_schema_is_read_only_and_fail_closed(setup,damage):
    crm,store,_,data=setup
    schema=crm.engine.get_execution_options().get('schema_translate_map',{}).get(None)
    quote=crm.engine.dialect.identifier_preparer.quote
    def qualified(name):return (quote(schema)+'.' if schema else '')+quote(name)
    with crm.engine.begin() as c:
        if damage in ('absent','partial'):c.execute(text('DROP TABLE '+qualified('crm_scheduled_research_ops_v1')))
        if damage=='absent':c.execute(text('DROP TABLE '+qualified('crm_scheduled_research_v1')))
        if damage=='newer':c.execute(text('ALTER TABLE '+qualified('crm_scheduled_research_v1')+' ADD COLUMN future_version TEXT'))
        if damage=='malformed':c.execute(text('ALTER TABLE '+qualified('crm_scheduled_research_v1')+' RENAME COLUMN state TO wrong_state'))
    def snapshot():
        with crm.engine.connect() as c:
            inspector=inspect(c)
            names=inspector.get_table_names(schema=schema)
            return {name:([col['name'] for col in inspector.get_columns(name,schema=schema)],
                [tuple(row) for row in c.execute(text('SELECT * FROM '+qualified(name)))]) for name in names}
    before=snapshot()
    reader=ScheduledResearchStore(crm,initialize=False)
    if damage=='absent':
        assert reader.page(task_id=data['task_id'],limit=2,offset=1)==dict(
            initialized=False,storage='absent',items=[],total=None,limit=2,offset=1)
    else:
        with pytest.raises(CRMError,match='schema|storage|column|incomplete'):
            reader.page(task_id=data['task_id'])
    assert snapshot()==before


def test_postgres_fixture_schema_names_match_current_domain_contract():
    import ast
    import inspect as python_inspect
    import re
    import textwrap
    from hermes_crm.domain import CRM
    from test_scheduled_research_postgres import disposable_schema_name
    # Read the actual constructor's validation literal, rather than duplicating
    # a guessed limit. No CRM instantiation or database connection occurs.
    tree=ast.parse(textwrap.dedent(python_inspect.getsource(CRM.__init__)))
    patterns=[node.args[0].value for node in ast.walk(tree)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
        and node.func.attr=='fullmatch' and len(node.args)==2
        and isinstance(node.args[0],ast.Constant)
        and isinstance(node.args[1],ast.Name) and node.args[1].id=='schema']
    assert patterns==[r'crm_[a-z0-9_]{1,48}']
    names=[disposable_schema_name() for _ in range(100)]
    assert len(set(names))==len(names)
    assert all(re.fullmatch(patterns[0],name) for name in names)
    assert all(name.startswith('crm_sr_test_') and len(name)==44 for name in names)
