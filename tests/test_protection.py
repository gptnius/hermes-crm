import json
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select
from hermes_crm.domain import CRM, CRMError
from hermes_crm.protection import Keyring, ProtectionStore, b64, notes, operations, owned_tables, decrypt_export, canonical

@pytest.fixture
def crm(tmp_path):
    value = CRM('sqlite:///' + str(tmp_path / 'synthetic.db'), profile='synthetic')
    yield value
    value.close()

@pytest.fixture
def ring():
    return Keyring.parse(json.dumps(dict(active='a', keys={'a':b64(bytes(range(32)))})))

def contact(crm):
    return crm.create('contacts', dict(name='Synthetic', notes='ordinary note unchanged'))

def save(store, record, ring, **kwargs):
    return store.save('contacts', record['id'], ring=ring, operation_id=kwargs.pop('operation_id',str(uuid.uuid4())), expected_record_version=kwargs.pop('expected_record_version',1), expected_note_version=kwargs.pop('expected_note_version',0), plaintext=kwargs.pop('plaintext','PROTECTED_SECRET_MARKER_937'), **kwargs)

def test_notes_privacy_and_replay(crm,ring,tmp_path):
    record = contact(crm); store = ProtectionStore(crm); op = str(uuid.uuid4())
    assert store.status('contacts',record['id'])['note_version'] == 0
    result = save(store,record,ring,operation_id=op)
    assert result == {'record_version':2,'note_version':1,'has_note':True}
    assert save(store,record,ring,operation_id=op) == result
    rotated = Keyring('b',dict(ring.keys,b=b'x'*32))
    assert save(store,record,rotated,operation_id=op) == result
    assert store.reveal('contacts',record['id'],rotated)['plaintext'] == 'PROTECTED_SECRET_MARKER_937'
    assert crm.get('contacts',record['id'])['notes'] == 'ordinary note unchanged'
    with pytest.raises(CRMError): save(store,record,ring,operation_id=op,plaintext='different')
    with pytest.raises(CRMError): save(store,record,ring)
    with crm._read_connection() as conn:
        from sqlalchemy import inspect
        for table in owned_tables().values():
            if inspect(conn).has_table(table.name):
                assert 'PROTECTED_SECRET_MARKER_937' not in str(conn.execute(select(table)).all())
    assert b'PROTECTED_SECRET_MARKER_937' not in (tmp_path/'synthetic.db').read_bytes()
    assert 'PROTECTED_SECRET_MARKER_937' not in str(crm.snapshot())

def test_tamper_cross_record_workspace_and_wrong_key(crm,ring):
    a=contact(crm); b=contact(crm); store=ProtectionStore(crm)
    save(store,a,ring); save(store,b,ring)
    with crm.engine.begin() as conn:
        envelope = conn.execute(select(notes.c.envelope).where(notes.c.record_id==a['id'])).scalar_one()
        conn.execute(notes.update().where(notes.c.record_id==b['id']).values(envelope=envelope))
    with pytest.raises(CRMError): store.reveal('contacts',b['id'],ring)
    with pytest.raises(CRMError): store.reveal('contacts',a['id'],Keyring('a',{'a':b'x'*32}))
    store.workspace = str(uuid.uuid4())
    with pytest.raises(CRMError): store.reveal('contacts',a['id'],ring)

@pytest.mark.parametrize('raw',[None,'{}','{"active":"a","keys":{"a":"short"}}','{"active":"a","keys":{"a":"aaa","a":"aaa"}}'])
def test_bad_keys(raw):
    with pytest.raises(CRMError): Keyring.parse(raw)

def test_export_exact_and_bounded(crm,ring):
    record=contact(crm); store=ProtectionStore(crm); save(store,record,ring)
    envelope=store.export(ring)
    assert 'ordinary note unchanged' not in canonical(envelope).decode()
    value=decrypt_export(envelope,ring,workspace=store.workspace,profile='synthetic')
    assert value['tables']['crm_contacts'][0]['notes']=='ordinary note unchanged'
    assert value['tables']['crm_protected_operations'][0]['response']
    with pytest.raises(CRMError): decrypt_export(envelope,ring,workspace=store.workspace,profile='other')
    envelope['purpose']='notes'
    with pytest.raises(CRMError): decrypt_export(envelope,ring,workspace=store.workspace,profile='synthetic')
    with pytest.raises(CRMError): save(store,record,ring,plaintext='x'*16001)

def test_concurrent_zero_note_create(crm,ring):
    record=contact(crm); store=ProtectionStore(crm)
    def attempt(_):
        try: return save(store,record,ring)
        except CRMError as error: return error.status
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(attempt,range(2)))
    assert sum(isinstance(r,dict) for r in results)==1
    assert 409 in results

def test_runtime_no_environment_fallback(monkeypatch):
    from hermes_crm.protection_runtime import resolve_keyring
    monkeypatch.setenv('HERMES_CRM_NOTES_KEYS',json.dumps(dict(active='a',keys={'a':b64(b'x'*32)})))
    with pytest.raises(CRMError): resolve_keyring('notes')

def test_export_artifact_replay_permissions_and_tamper(crm,ring,tmp_path,monkeypatch):
    import sys, types, stat
    from pathlib import Path
    from hermes_crm.protection_runtime import export_artifact
    from hermes_crm.protection import decrypt_export_artifact
    parent=types.ModuleType('plugins'); module=types.ModuleType('plugins.plugin_storage')
    module.plugin_data_dir=lambda name:tmp_path
    monkeypatch.setitem(sys.modules,'plugins',parent)
    monkeypatch.setitem(sys.modules,'plugins.plugin_storage',module)
    record=contact(crm); store=ProtectionStore(crm); operation_id=str(uuid.uuid4())
    result=export_artifact(store,ring,operation_id)
    path=Path(result['stored_path']); original=path.read_bytes()
    assert stat.S_IMODE(path.stat().st_mode)==0o600
    assert b'ordinary note unchanged' not in original
    assert b64(ring.keys['a']).encode() not in original
    crm.update('contacts',record['id'],dict(version=1,notes='later'))
    assert export_artifact(store,ring,operation_id)==result
    assert path.read_bytes()==original
    parsed=json.loads(original)
    restored=decrypt_export_artifact(parsed,ring,workspace=store.workspace,profile='synthetic')
    assert restored['tables']['crm_contacts'][0]['notes']=='ordinary note unchanged'
    parsed['export_id']=str(uuid.uuid4())
    with pytest.raises(CRMError): decrypt_export_artifact(parsed,ring,workspace=store.workspace,profile='synthetic')
    path.write_text('[]')
    with pytest.raises(CRMError): export_artifact(store,ring,operation_id)

def test_write_rollback(crm,ring,monkeypatch):
    from sqlalchemy import event
    record=contact(crm); store=ProtectionStore(crm)
    def fail(conn,cursor,statement,parameters,context,executemany):
        compiled = getattr(context, 'compiled', None)
        command = getattr(compiled, 'statement', None)
        if getattr(command, 'is_insert', False) and command.table.name == 'crm_activity':
            raise RuntimeError('synthetic failure')
    event.listen(crm.engine,'before_cursor_execute',fail)
    with pytest.raises(RuntimeError): save(store,record,ring)
    event.remove(crm.engine,'before_cursor_execute',fail)
    assert store.status('contacts',record['id'])==dict(record_version=1,note_version=0,has_note=False)

def test_cryptographic_tampering(crm,ring):
    from hermes_crm.protection import unseal
    record=contact(crm);store=ProtectionStore(crm);save(store,record,ring)
    with crm._read_connection() as conn: envelope=json.loads(conn.execute(select(notes.c.envelope)).scalar_one())
    context=store._context('contacts',record['id'],1)
    for field,value in [('ciphertext',b64(b'x'*48)),('nonce',b64(b'x'*12)),('key_id','missing'),('purpose','backup'),('version',2)]:
        with pytest.raises(CRMError): unseal(dict(envelope,**{field:value}),ring,'notes',context)

def test_native_api_sanitizes_default_fastapi(crm,ring):
    from contextlib import contextmanager
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from hermes_crm.protection_api import build_router
    record=contact(crm); token=crm.workspace_token()
    @contextmanager
    def service(): yield crm
    def require_workspace(crm,value):
        if value != token: raise CRMError('Workspace changed',409)
    app=FastAPI();app.include_router(build_router(service,require_workspace,lambda _:ring))
    client=TestClient(app)
    path='/protection/notes/contacts/'+record['id']
    valid=dict(workspace_token=token,operation_id=str(uuid.uuid4()),expected_record_version=1,expected_note_version=0,plaintext='API_SECRET_MARKER')
    cases=[json.dumps(dict(valid,extra='API_SECRET_MARKER')),json.dumps(dict(valid,expected_note_version='API_SECRET_MARKER')),'{"plaintext":"API_SECRET_MARKER",','{"plaintext":"API_SECRET_MARKER","plaintext":"API_SECRET_MARKER"}']
    for body in cases:
        response=client.put(path,content=body,headers={'content-type':'application/json'})
        assert response.status_code==422
        assert 'API_SECRET_MARKER' not in response.text
        assert response.headers['cache-control']=='no-store'
    response=client.put(path,json=valid)
    assert response.status_code==200 and 'API_SECRET_MARKER' not in response.text
    reveal=client.post(path+'/reveal',json=dict(workspace_token=token))
    assert reveal.json()['plaintext']=='API_SECRET_MARKER'
    assert reveal.headers['cache-control']=='no-store'

def test_export_in_memory_static_pool(ring,tmp_path,monkeypatch):
    import sys,types
    from hermes_crm.protection_runtime import export_artifact
    module=types.ModuleType('plugins.plugin_storage'); module.plugin_data_dir=lambda _:tmp_path
    monkeypatch.setitem(sys.modules,'plugins',types.ModuleType('plugins'))
    monkeypatch.setitem(sys.modules,'plugins.plugin_storage',module)
    crm=CRM('sqlite:///:memory:',profile='synthetic')
    try:
        contact(crm)
        assert export_artifact(ProtectionStore(crm),ring,str(uuid.uuid4()))['export_id']
    finally: crm.close()

def test_scoped_metadata_receipt(crm,ring):
    a=contact(crm); b=contact(crm); store=ProtectionStore(crm); op=str(uuid.uuid4())
    assert store.operation('contacts',a['id'],op)==dict(operation_id=op,state='unknown')
    result=save(store,a,ring,operation_id=op)
    receipt=store.operation('contacts',a['id'],op)
    assert receipt==dict(result,operation_id=op,state='committed')
    assert 'PROTECTED_SECRET_MARKER' not in str(receipt)
    assert store.operation('contacts',b['id'],op)==dict(operation_id=op,state='unknown')
    store.workspace=str(uuid.uuid4())
    assert store.operation('contacts',a['id'],op)==dict(operation_id=op,state='unknown')

def test_native_service_preserves_sanitized_status(crm,ring,monkeypatch):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from hermes_crm import native_api
    from hermes_crm.protection_api import build_router
    record=contact(crm); token=crm.workspace_token()
    monkeypatch.setattr(native_api,'open_profile_crm',lambda:CRM(crm.url,profile='synthetic'))
    app=FastAPI();app.include_router(build_router(native_api.service,native_api.require_workspace,lambda _:ring))
    client=TestClient(app); path='/protection/notes/contacts/'+record['id']
    body=dict(workspace_token=token,operation_id=str(uuid.uuid4()),expected_record_version=999,expected_note_version=0,plaintext='NEVER_ECHO_MARKER')
    response=client.put(path,json=body)
    assert response.status_code==409 and 'NEVER_ECHO_MARKER' not in response.text
    missing=client.get('/protection/notes/contacts/missing',params={'workspace_token':token})
    assert missing.status_code==404 and missing.headers['cache-control']=='no-store'
    def bad_factory(): raise HTTPException(418,detail='SECRET_HOST_DETAIL')
    monkeypatch.setattr(native_api,'open_profile_crm',bad_factory)
    response=client.get(path,params={'workspace_token':token})
    assert response.status_code==503 and 'SECRET_HOST_DETAIL' not in response.text

@pytest.mark.parametrize('mutation',['missing','nullable','pk','columns','type','version'])
def test_schema_refuses_malformed(crm,ring,mutation):
    from hermes_crm.protection import metadata,state
    store=ProtectionStore(crm);record=contact(crm)
    with crm.engine.begin() as conn:
        store.initialize(conn)
        if mutation=='version': conn.execute(state.update().values(version=2))
        elif mutation=='missing': conn.exec_driver_sql('DROP TABLE crm_protected_operations')
        elif mutation=='columns': conn.exec_driver_sql('ALTER TABLE crm_protected_notes ADD COLUMN unexpected TEXT')
        else:
            conn.exec_driver_sql('DROP TABLE crm_protected_notes')
            if mutation=='nullable': ddl='kind VARCHAR(20),record_id VARCHAR(36),version INTEGER,envelope TEXT,PRIMARY KEY(kind,record_id)'
            elif mutation=='pk': ddl='kind VARCHAR(20) NOT NULL,record_id VARCHAR(36) NOT NULL,version INTEGER NOT NULL,envelope TEXT NOT NULL'
            else: ddl='kind VARCHAR(20) NOT NULL,record_id VARCHAR(36) NOT NULL,version TEXT NOT NULL,envelope TEXT NOT NULL,PRIMARY KEY(kind,record_id)'
            conn.exec_driver_sql('CREATE TABLE crm_protected_notes ('+ddl+')')
    for call in (lambda:store.status('contacts',record['id']),lambda:save(store,record,ring),lambda:store.export(ring)):
        with pytest.raises(CRMError) as caught: call()
        assert caught.value.status==503

def test_export_tombstone_and_readonly_recovery(crm,ring,tmp_path,monkeypatch):
    import sys,types
    from pathlib import Path
    from hermes_crm.protection_runtime import export_artifact,export_operation_status
    module=types.ModuleType('plugins.plugin_storage');module.plugin_data_dir=lambda _:tmp_path
    monkeypatch.setitem(sys.modules,'plugins',types.ModuleType('plugins'));monkeypatch.setitem(sys.modules,'plugins.plugin_storage',module)
    contact(crm);store=ProtectionStore(crm);op=str(uuid.uuid4())
    assert export_operation_status(store,ring,op)['state']=='unknown'
    result=export_artifact(store,ring,op)
    assert export_operation_status(store,ring,op)['state']=='committed'
    Path(result['stored_path']).unlink()
    assert export_operation_status(store,ring,op)['state']=='missing_artifact'
    with pytest.raises(CRMError): export_artifact(store,ring,op)
    assert not Path(result['stored_path']).exists()
    store.workspace=str(uuid.uuid4())
    assert export_operation_status(store,ring,op)['state']=='unknown'

def test_export_rejects_permissive_directory(crm,ring,tmp_path,monkeypatch):
    import sys,types
    from hermes_crm.protection_runtime import export_artifact
    module=types.ModuleType('plugins.plugin_storage');module.plugin_data_dir=lambda _:tmp_path
    monkeypatch.setitem(sys.modules,'plugins',types.ModuleType('plugins'));monkeypatch.setitem(sys.modules,'plugins.plugin_storage',module)
    directory=tmp_path/'exports';directory.mkdir();directory.chmod(0o755)
    with pytest.raises(CRMError): export_artifact(ProtectionStore(crm),ring,str(uuid.uuid4()))

def test_native_service_postcommit_failure_receipt(crm,ring,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from hermes_crm import native_api
    from hermes_crm.protection_api import build_router
    record=contact(crm); token=crm.workspace_token();op=str(uuid.uuid4())
    original_save=ProtectionStore.save
    def save_then_fail(*args,**kwargs):
        original_save(*args,**kwargs)
        raise RuntimeError('POSTCOMMIT_SECRET_MARKER')
    monkeypatch.setattr(ProtectionStore,'save',save_then_fail)
    monkeypatch.setattr(native_api,'open_profile_crm',lambda:CRM(crm.url,profile='synthetic'))
    app=FastAPI();app.include_router(build_router(native_api.service,native_api.require_workspace,lambda _:ring))
    client=TestClient(app);path='/protection/notes/contacts/'+record['id']
    response=client.put(path,json=dict(workspace_token=token,operation_id=op,expected_record_version=1,expected_note_version=0,plaintext='POSTCOMMIT_SECRET_MARKER'))
    assert response.status_code==503 and 'POSTCOMMIT_SECRET_MARKER' not in response.text
    assert response.headers['cache-control']=='no-store'
    receipt=client.get(path+'/operations/'+op,params={'workspace_token':token})
    assert receipt.status_code==200 and receipt.json()['state']=='committed'
    assert 'POSTCOMMIT_SECRET_MARKER' not in receipt.text


def mock_export_directory(monkeypatch,tmp_path):
    import sys,types
    module=types.ModuleType('plugins.plugin_storage');module.plugin_data_dir=lambda _:tmp_path
    monkeypatch.setitem(sys.modules,'plugins',types.ModuleType('plugins'))
    monkeypatch.setitem(sys.modules,'plugins.plugin_storage',module)


def test_fifo_artifact_rejected_promptly(crm,ring,tmp_path,monkeypatch):
    import os,time
    from pathlib import Path
    from hermes_crm.protection_runtime import export_artifact,export_operation_status
    mock_export_directory(monkeypatch,tmp_path)
    store=ProtectionStore(crm);op=str(uuid.uuid4())
    result=export_artifact(store,ring,op);target=Path(result['stored_path'])
    target.unlink();os.mkfifo(target,0o600)
    # Nonblocking writer permits a regressed blocking reader to finish rather
    # than hang the suite, while elapsed time asserts it never waited for one.
    import threading
    stop=threading.Event()
    def unblock_regression():
        if stop.wait(1): return
        try:
            fd=os.open(target,os.O_WRONLY|os.O_NONBLOCK);os.close(fd)
        except OSError: pass
    helper=threading.Thread(target=unblock_regression,daemon=True);helper.start()
    started=time.monotonic()
    try:
        with pytest.raises(CRMError): export_operation_status(store,ring,op)
        assert time.monotonic()-started<0.8
    finally: stop.set();helper.join(timeout=2)


def test_export_snapshot_failure_keeps_reservation(crm,ring,tmp_path,monkeypatch):
    from hermes_crm.protection_runtime import export_artifact,export_operation_status
    mock_export_directory(monkeypatch,tmp_path)
    store=ProtectionStore(crm);op=str(uuid.uuid4());calls=[]
    def fail(*args,**kwargs): calls.append(1);raise RuntimeError('synthetic snapshot failure')
    monkeypatch.setattr(store,'export',fail)
    with pytest.raises(RuntimeError): export_artifact(store,ring,op)
    assert export_operation_status(store,ring,op)['state']=='missing_artifact'
    with pytest.raises(CRMError): export_artifact(store,ring,op)
    assert len(calls)==1


def test_export_file_survives_receipt_rollback(crm,ring,tmp_path,monkeypatch):
    from sqlalchemy import event,select
    from hermes_crm.protection import exports
    from hermes_crm.protection_runtime import export_artifact,export_operation_status
    mock_export_directory(monkeypatch,tmp_path)
    store=ProtectionStore(crm);op=str(uuid.uuid4())
    def fail(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith('UPDATE crm_protected_exports') or ('UPDATE ' in statement and 'crm_protected_exports' in statement):
            raise RuntimeError('synthetic receipt failure')
    event.listen(crm.engine,'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError): export_artifact(store,ring,op)
    finally: event.remove(crm.engine,'before_cursor_execute',fail)
    with crm._read_connection() as conn:
        assert conn.execute(select(exports.c.state).where(exports.c.id==op)).scalar_one()=='reserved'
    recovered=export_operation_status(store,ring,op)
    assert recovered['state']=='committed'
    def never(*args,**kwargs): raise AssertionError('must not recapture')
    monkeypatch.setattr(store,'export',never)
    assert export_artifact(store,ring,op)['stored_path']==recovered['stored_path']


def test_export_concurrent_same_id_one_capture(crm,ring,tmp_path,monkeypatch):
    import threading
    from hermes_crm.protection_runtime import export_artifact,export_operation_status
    mock_export_directory(monkeypatch,tmp_path)
    store=ProtectionStore(crm);op=str(uuid.uuid4());entered=threading.Event();release=threading.Event();calls=[]
    original=store.export
    def blocked(*args,**kwargs):
        calls.append(1);entered.set()
        if not release.wait(5): raise RuntimeError('synthetic wait expired')
        return original(*args,**kwargs)
    monkeypatch.setattr(store,'export',blocked)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(export_artifact,store,ring,op)
        try:
            assert entered.wait(5)
            second=pool.submit(export_artifact,store,ring,op)
            with pytest.raises(CRMError): second.result(timeout=5)
        finally: release.set()
        result=first.result(timeout=5)
    assert len(calls)==1
    assert export_operation_status(store,ring,op)['stored_path']==result['stored_path']
