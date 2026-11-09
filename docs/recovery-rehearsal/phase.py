import os,json,uuid,hashlib,sqlite3
from pathlib import Path
from hermes_crm.domain import CRM, CRMError
from hermes_crm.companies import CompanyStore
from hermes_crm.events import EventStore
from hermes_crm.native_work import NativeWorkStore
from hermes_crm.research_store import ResearchStore
from hermes_crm.protection import Keyring, ProtectionStore, b64
from hermes_crm.protection_runtime import export_artifact
root=Path(os.environ['CRM_E2E_ROOT']); phase=os.environ['REHEARSAL_PHASE']
rings=json.loads((root/'retained-keyrings.json').read_text()); backup=Keyring.parse(json.dumps(rings['backup'])); notes=Keyring.parse(json.dumps(rings['notes']))
state=json.loads((root/'state.json').read_text()) if (root/'state.json').exists() else {}
path=root/'restored/recovery.sqlite3' if phase=='restored' else root/'profile/plugin-data/hermes-crm/data.db'
path.parent.mkdir(parents=True,exist_ok=True)
if phase=='restored':
    manifest=json.loads((root/'restored/manifest.json').read_text())
    # Digest checked before normal reopen/migration.
    state['manifest_keys']=list(manifest)
    expected=(root/'post-reopen.sha256').read_text() if (root/'post-reopen.sha256').exists() else manifest['database_sha256']
    assert expected and hashlib.sha256(path.read_bytes()).hexdigest()==expected,manifest
crm=CRM('sqlite:///'+str(path),profile='synthetic-recovery')
try:
    if phase=='seed':
        crm.create_field('contacts',dict(key='segment',label='Segment',type='text'))
        c=crm.create('contacts',dict(name='Synthetic recovery contact',notes='Ordinary retained note',custom_fields={'segment':'Synthetic A'}),key='contact-create')
        company=CompanyStore(crm).create({'name':'Synthetic recovery company'},actor='test',key='company-create')
        CompanyStore(crm).set_contact_company(c['id'],company['id'],expected_contact_version=c['version'],actor='test',key='company-link')
        event=EventStore(crm).create(dict(title='Synthetic recovery appointment',kind='appointment',starts_at='2030-01-01T12:00:00Z',ends_at='2030-01-01T13:00:00Z',timezone='UTC',contact_id=c['id'],company_id=company['id']),actor='test',key='event-create')
        task=crm.create('tasks',dict(title='Synthetic owned task',due_at='2030-01-01T00:00:00Z',contact_id=c['id'],owner_label='Synthetic owner',owner_policy_version=0),key='task-create')
        NativeWorkStore(crm).create(task_id=task['id'],human_owner='Synthetic owner',prompt='Synthetic analysis',success_criteria='Synthetic report',run_at='2030-01-01T12:00:00Z',idempotency_key='draft-only')
        c=crm.get('contacts',c['id'])
        evidence=ResearchStore(crm).submit(dict(target_kind='contacts',target_id=c['id'],target_version=c['version'],question='Synthetic question',source_url='https://example.test/source',source_title='Synthetic evidence',observed_at='2026-11-08T12:00:00+00:00',claims=['Synthetic claim'],hypotheses=[]),key='evidence-create')
        op=str(uuid.uuid4()); receipt=ProtectionStore(crm).save('contacts',c['id'],ring=notes,operation_id=op,expected_record_version=c['version'],expected_note_version=0,plaintext='SYNTHETIC PROTECTED RECOVERY NOTE')
        state=dict(contact=c['id'],company=company['id'],event=event['id'],task=task['id'],evidence=ResearchStore(crm).get_evidence(evidence['id']),op=op,receipt=receipt,prior_contact_version=c['version'],workspace=crm.workspace_token())
        state['records']={k:crm.get(k,i) for k,i in [('contacts',c['id']),('tasks',task['id'])]}
    else:
        assert crm.workspace_token()==state['workspace']
        assert crm.get('contacts',state['contact'])==state['records']['contacts']
        assert crm.get('tasks',state['task'])==state['records']['tasks']
        assert CompanyStore(crm).get_contact_company(state['contact'])['company_id']==state['company']
        assert EventStore(crm).get(state['event'])['title']=='Synthetic recovery appointment'
        assert ResearchStore(crm).get_evidence(state['evidence']['id'])==state['evidence']
        assert crm.get('tasks',state['task'])['owner_label']=='Synthetic owner'
        assert crm.get('tasks',state['task'])['schedule_status']=='none'
        assert crm.get('tasks',state['task'])['scheduler_job_id'] is None
        assert crm.create('contacts',dict(name='Synthetic recovery contact',notes='Ordinary retained note',custom_fields={'segment':'Synthetic A'}),key='contact-create')['id']==state['contact']
        rotated=Keyring('new',{'new':b'x'*32,**notes.keys})
        assert ProtectionStore(crm).reveal('contacts',state['contact'],rotated)['plaintext']=='SYNTHETIC PROTECTED RECOVERY NOTE'
        assert ProtectionStore(crm).save('contacts',state['contact'],ring=rotated,operation_id=state['op'],expected_record_version=state['prior_contact_version'],expected_note_version=0,plaintext='SYNTHETIC PROTECTED RECOVERY NOTE')==state['receipt']
        with crm.engine.connect() as conn:
            assert conn.exec_driver_sql('select count(*) from crm_research_evidence').scalar()==1
        if phase=='reopen':
            output=export_artifact(ProtectionStore(crm),backup,str(uuid.uuid4())); state['artifact']=output['stored_path']
        if phase=='restored':
            NativeWorkStore(crm)
            with sqlite3.connect(path) as db:
                assert db.execute('select count(*) from crm_native_assignments').fetchone()[0]==0
                assert db.execute('select count(*) from recovery_crm_native_assignments').fetchone()[0]==1
                assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
                assert db.execute('pragma foreign_key_check').fetchall()==[]
            assert b'SYNTHETIC PROTECTED RECOVERY NOTE' not in path.read_bytes()
    (root/'state.json').write_text(json.dumps(state))
finally: crm.close()
if phase=='restored': (root/'post-reopen.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest())
print(json.dumps({'phase':phase,'success':True,'pid':os.getpid()}))
