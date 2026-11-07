import { createElement as h, useEffect, useRef, useState } from "react";

const transferStores = new WeakMap(), transferListeners = new WeakMap();
const transferBase = '/contact-transfer';
const transferInteger = n => Number.isSafeInteger(n) && n >= 0;
const transferColumn = key => ['name', 'email', 'company', 'title', 'lifecycle', 'notes'].includes(key) || /^custom\.[a-z][a-z0-9_]{0,63}$/.test(key);
export function transferPreview(value) {
  if (!value || !Array.isArray(value.headers) || value.headers.length > 106 ||
      !value.headers.every(x => typeof x === 'string') || new Set(value.headers).size !== value.headers.length) return false;
  if (value.needs_mapping === true) return value.suggested_mapping && typeof value.suggested_mapping === 'object' &&
    value.headers.every(header => value.suggested_mapping[header] == null || transferColumn(value.suggested_mapping[header]));
  if (typeof value.fingerprint !== 'string' || !Array.isArray(value.rows) || value.rows.length > 1000 ||
      !Array.isArray(value.ignored_columns) || !value.ignored_columns.every(x => value.headers.includes(x)) ||
      !value.counts || !['ready', 'duplicate', 'invalid'].every(key => transferInteger(value.counts[key]))) return false;
  if (!value.rows.every(row => row && Number.isSafeInteger(row.row_number) && row.row_number >= 2 &&
      ['ready', 'duplicate', 'invalid'].includes(row.status) && Array.isArray(row.errors) && row.errors.every(x => typeof x === 'string') &&
      Array.isArray(row.duplicates) && row.duplicates.every(d => d && ['workspace', 'file'].includes(d.source) && typeof d.reason === 'string'))) return false;
  return new Set(value.rows.map(row => row.row_number)).size === value.rows.length &&
    ['ready', 'duplicate', 'invalid'].every(status => value.counts[status] === value.rows.filter(row => row.status === status).length);
}
export function createContactTransferSession(client, workspaceToken, isCurrent, captureDownload, operationStore) {
  let alive = true;
  const store = operationStore || transferStores.get(client) || new Map(); transferStores.set(client, store);
  const listeners = transferListeners.get(store) || new Set(); transferListeners.set(store, listeners);
  const scope = workspaceToken;
  const current = () => alive && client.current() && isCurrent();
  const notify = () => { for (const fn of listeners) fn(scope); };
  const finish = op => { if (store.get(scope) === op) store.delete(scope); notify(); };
  const query = new URLSearchParams({workspace_token: workspaceToken});
  function receipt(result, op) {
    if (op.kind === 'import') {
      if (!result || result.batch_id !== op.id || result.status !== 'completed' || !Array.isArray(result.created) || !Array.isArray(result.skipped) || !Array.isArray(result.excluded) || !result.excluded.every(row=>row&&Number.isSafeInteger(row.row_number)&&['invalid','not_selected'].includes(row.reason)) || !result.created.every(row=>row&&Number.isSafeInteger(row.row_number)&&typeof row.id==='string') || !result.skipped.every(row=>row&&Number.isSafeInteger(row.row_number)&&typeof row.reason==='string') || !result.counts || !transferInteger(result.counts.created) || !transferInteger(result.counts.skipped) || result.counts.created!==result.created.length || result.counts.skipped!==result.skipped.length || !transferInteger(result.counts.excluded) || result.counts.excluded!==result.excluded.length) throw new Error('Invalid import receipt.');
      return result;
    }
    if (!result || result.operation_id !== op.id || result.state !== 'committed' || typeof result.stored_path !== 'string' || !result.stored_path || typeof result.suggested_name !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,180}$/.test(result.suggested_name) || !transferInteger(result.row_count) || !transferInteger(result.escaped_cells)) throw new Error('Invalid export receipt.');
    return {row_count:result.row_count,escaped_cells:result.escaped_cells,name:result.suggested_name,async download(){if(!current())return false;await op.download(result.stored_path,result.suggested_name);return current();}};
  }
  async function write(kind, body) {
    if (!current() || store.has(scope)) return null;
    let download;
    if (kind === 'export') { if(typeof captureDownload !== 'function')throw new Error('Update Hermes Desktop to download CSV.'); download=captureDownload();if(typeof download !== 'function')throw new Error('Download unavailable.'); }
    const op={id:crypto.randomUUID(),kind,state:'pending',download};store.set(scope,op);notify();
    try {
      const result=await client.request(`${transferBase}/${kind}`,{method:'POST',body:{...body,workspace_token:workspaceToken,[kind==='import'?'batch_id':'operation_id']:op.id}});
      if(!current()){op.state='unknown';notify();return null;}
      const verified=receipt(result,op);finish(op);return verified;
    } catch(error) {
      if([400,403,404,409,413,422].includes(error?.status)){finish(op);throw new Error('Request rejected. Close and reopen to review fresh data.');}
      op.state='unknown';notify();throw new Error('Outcome unknown. Do not repeat this operation. Check the original receipt.');
    }
  }
  return {current,close(){alive=false;},pending:()=>store.get(scope),subscribe(fn){const own=changed=>{if(changed===scope&&current())fn();};listeners.add(own);return()=>listeners.delete(own);},
    async catalog(){if(!current())return null;const result=await client.request(`${transferBase}/catalog?${query}`);if(!current())return null;if(!result||!Array.isArray(result.columns)||!result.columns.every(c=>typeof c.key==='string'&&transferColumn(c.key)&&typeof c.label==='string')||!Array.isArray(result.default_columns)||!result.default_columns.every(k=>k!=='notes'&&!k.startsWith('custom.')&&result.columns.some(c=>c.key===k)))throw new Error('Transfer catalog unavailable.');return result;},
    async preview(body){if(!current()||store.has(scope))return null;const result=await client.request(`${transferBase}/preview`,{method:'POST',body:{...body,workspace_token:workspaceToken}});if(!current())return null;if(!transferPreview(result))throw new Error('Invalid preview response.');return result;},
    import:body=>write('import',body),export:body=>write('export',body),
    async recover(){const op=store.get(scope);if(!current()||op?.state!=='unknown')return null;const path=op.kind==='import'?`imports/${encodeURIComponent(op.id)}`:`export/operations/${encodeURIComponent(op.id)}`;const result=await client.request(`${transferBase}/${path}?${query}`);if(!current())return null;const verified=receipt(result,op);finish(op);return {kind:op.kind,result:verified};},
  };
}

// Use native details/description lists so every mapped value is reviewable
// without a wide spreadsheet or a developer-facing JSON representation.
export function ContactTransferRowValues({ row, mapping, columns }) {
  const values = row.values || {};
  const display = value => value === undefined ? 'Not provided' : value === null ? 'Not set' :
    value === '' ? 'Empty text' : value === false ? 'No (false)' : value === true ? 'Yes (true)' : String(value);
  const identity = ['name', 'email', 'company'].filter(key => values[key] !== undefined && values[key] !== null && values[key] !== '');
  const fields = Object.entries(mapping || {}).filter(([, target]) => target !== null);
  return h('div', null,
    h('p', null, identity.length ? identity.map(key => `${columns.find(column => column.key === key)?.label || key}: ${display(values[key])}`).join(' · ') : 'No contact identity supplied'),
    h('details', null, h('summary', null, `Review ${fields.length} mapped fields for row ${row.row_number}`),
      h('dl', null, ...fields.map(([header, target]) => h('div', { key: header },
        h('dt', null, `${columns.find(column => column.key === target)?.label || target} · CSV column: ${header}`),
        h('dd', { style: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' } },
          display(target.startsWith('custom.') ? values.custom_fields?.[target.slice(7)] : values[target])))))));
}

export function ContactTransferDrawer({Drawer,client,workspaceToken,current,invalidated=false,captureDownload,operationStore,filters={},cancel,returnFocus,onImported}) {
  const [catalog,setCatalog]=useState(null),[mode,setMode]=useState('import'),[csv,setCsv]=useState(''),[fileName,setFileName]=useState('');
  const [mapping,setMapping]=useState(null),[preview,setPreview]=useState(null),[duplicates,setDuplicates]=useState('skip'),[selected,setSelected]=useState([]);
  const [columns,setColumns]=useState([]),[consent,setConsent]=useState(false),[confirmed,setConfirmed]=useState(false);
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[result,setResult]=useState(null),[artifact,setArtifact]=useState(null),[,update]=useState(0);
  const latest=useRef(null);latest.current={current,invalidated};const session=useRef(null),lock=useRef(false),readId=useRef(0),draftRevision=useRef(0),approvalRevision=useRef(null),input=useRef(null);
  const clear=()=>{readId.current++;draftRevision.current++;approvalRevision.current=null;setSelected([]);setCsv('');setFileName('');setMapping(null);setPreview(null);setConfirmed(false);if(input.current)input.current.value='';};
  useEffect(()=>{const own=createContactTransferSession(client,workspaceToken,()=>!latest.current.invalidated&&latest.current.current(),captureDownload,operationStore);session.current=own;const stop=own.subscribe(()=>{if(own.pending())clear();update(n=>n+1);});own.catalog().then(v=>{if(v){setCatalog(v);setColumns(v.default_columns);}}).catch(()=>{if(own.current())setNotice('Contact transfer catalog could not be loaded.');});return()=>{stop();own.close();readId.current++;session.current=null;};},[client,workspaceToken]);
  useEffect(()=>{if(invalidated){clear();setArtifact(null);setResult(null);}},[invalidated]);
  const own=session.current,pending=own?.pending(),valid=()=>session.current?.current(),renderedRevision=draftRevision.current;
  const disabled=busy||Boolean(pending)||!catalog||invalidated||!client.current();
  const close=()=>{clear();setArtifact(null);setResult(null);session.current?.close();cancel();};
  async function perform(fn){if(!valid()||lock.current||renderedRevision!==draftRevision.current)return;lock.current=true;setBusy(true);setNotice('');try{await fn(session.current);}catch{if(valid())setNotice(session.current.pending()?'Outcome unknown. Check the original receipt before doing anything else.':'Operation could not be completed. Review your settings or close and reopen.');}finally{lock.current=false;if(valid())setBusy(false);}}
  async function chooseFile(event){const file=event.target.files?.[0];event.target.value='';if(!valid()||lock.current||pending||!file)return;clear();const ticket=++readId.current;setNotice('');if(file.size>2*1024*1024){setNotice('Choose a CSV file no larger than 2 MB.');return;}try{const bytes=await file.arrayBuffer();const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);if(!valid()||ticket!==readId.current)return;setCsv(text);setFileName(file.name);}catch{if(valid()&&ticket===readId.current)setNotice('The selected file could not be read.');}}
  const actButton=(text,fn,off=disabled)=>h('button',{type:'button',disabled:off,onClick:()=>perform(fn)},text);
  const revokeApproval=()=>{draftRevision.current++;approvalRevision.current=null;setConfirmed(false);};
  const changeImport=fn=>{if(!valid()||disabled||lock.current)return;revokeApproval();setPreview(null);setSelected([]);fn();};
  const showPreview=async own=>{
    const revision=draftRevision.current, fileRevision=readId.current;
    const v=await own.preview({csv_text:csv,mapping,spreadsheet_safe:false});
    if(!v||!own.current()||session.current!==own||revision!==draftRevision.current||fileRevision!==readId.current)return;
    revokeApproval();setPreview(v);setSelected(v.needs_mapping?[]:v.rows.filter(row=>row.status==='ready').map(row=>row.row_number));
    if(v.needs_mapping)setMapping(Object.fromEntries(v.headers.map(k=>[k,catalog.columns.some(column=>!column.archived&&column.key===v.suggested_mapping[k])?v.suggested_mapping[k]:null])));
  };
  return h(Drawer,{title:'Contact CSV transfer',subtitle:'Local, contact-first import and export',cancel:close,busy:false,returnFocus,closeLabel:'Close contact transfer'},
    h('p',null,'Spreadsheet-safe exports escape formula-like text; review these values deliberately before reimporting. Import preserves apostrophes; existing contact validation and whitespace normalization apply. CSV is plaintext. Protected notes and keys are never included. File contents are sent to this Hermes workspace only when you choose Preview or Import.'),
    invalidated?h('p',{role:'status'},'Workspace or view changed. Close and reopen.'):h('div',null,
      h('div',{className:'hc-actions'},...['import','export'].map(value=>h('button',{key:value,type:'button',disabled, 'aria-pressed':mode===value,onClick:()=>{if(!valid()||disabled)return;clear();setMode(value);setNotice('');setConsent(false);setArtifact(null);setResult(null);}},value==='import'?'Import contacts':'Export contacts'))),
      pending&&h('p',{role:'status'},`${pending.kind} ${pending.state}. Original request: ${pending.id}. No new operation can run until its outcome is confirmed.`),
      pending?.state==='unknown'&&actButton('Check original receipt',async session=>{const recovered=await session.recover();if(recovered){if(recovered.kind==='export')setArtifact(recovered.result);else{setResult(recovered.result);onImported?.();}setNotice('Original operation confirmed.');}},busy),
      mode==='import'?h('section',null,
        h('label',null,'Choose contact CSV',h('input',{ref:input,type:'file',accept:'.csv,text/csv',disabled,onChange:chooseFile})),fileName&&h('p',null,`Selected: ${fileName}`),
        mapping&&h('fieldset',{disabled},h('legend',null,'Map every column, or explicitly ignore it'),...Object.keys(mapping).map(header=>h('label',{key:header},header,h('select',{'aria-label':`Map column ${header}`,value:mapping[header]||'',onChange:e=>changeImport(()=>setMapping(old=>({...old,[header]:e.target.value||null})))},h('option',{value:''},'Ignore this column'),...catalog.columns.filter(column=>!column.archived).map(column=>h('option',{key:column.key,value:column.key},column.label)))))),
        actButton(mapping?'Preview mapped rows':'Preview CSV columns',showPreview,disabled||!csv),
        preview&&!preview.needs_mapping&&h('div',null,
          h('p',null,`${preview.counts.ready} ready; ${preview.counts.duplicate} duplicates; ${preview.counts.invalid} invalid. Existing contacts are never overwritten.`),
          h('p',{role:'status'},`${selected.length} ready rows selected; ${preview.counts.ready-selected.length+preview.counts.invalid} rows excluded; ${preview.counts.duplicate} duplicates will be skipped (or reject the import).`),
          h('p',null,`Ignored columns: ${(preview.ignored_columns||[]).join(', ')||'None'}`),
          h('label',null,'Duplicate handling',h('select',{value:duplicates,disabled,onChange:e=>{if(!valid()||disabled||lock.current)return;revokeApproval();setDuplicates(e.target.value);}},h('option',{value:'skip'},'Skip duplicates'),h('option',{value:'reject'},'Reject import if duplicates exist'))),
          h('ol',null,...preview.rows.map(row=>h('li',{key:row.row_number},
            h('p',null,`Row ${row.row_number} · ${row.status==='ready'?'Ready to import':row.status==='duplicate'?'Duplicate (will not be created)':'Invalid (excluded)'}`),
            row.status==='ready'&&h('label',null,h('input',{type:'checkbox','aria-label':`Select row ${row.row_number}`,checked:selected.includes(row.row_number),disabled,onChange:e=>{if(!valid()||disabled||lock.current)return;revokeApproval();setSelected(old=>e.target.checked?[...old.filter(n=>n!==row.row_number),row.row_number]:old.filter(n=>n!==row.row_number));}}),'Import this row'),
            row.errors.length>0&&h('ul',{'aria-label':`Validation errors for row ${row.row_number}`},...row.errors.map((error,index)=>h('li',{key:index},error))),
            row.duplicates.length>0&&h('ul',{'aria-label':`Duplicate matches for row ${row.row_number}`},...row.duplicates.map((duplicate,index)=>h('li',{key:index},`${duplicate.source==='workspace'?'Existing contact':'CSV row '+duplicate.row_number}: matching ${duplicate.reason==='name_company'?'name and company':duplicate.reason}${duplicate.id?' ('+duplicate.id+')':''}`))),
            h(ContactTransferRowValues,{row,mapping,columns:catalog.columns})))),
          h('label',null,h('input',{type:'checkbox','aria-label':'Confirm selected rows',checked:confirmed,disabled,onChange:e=>{if(!valid()||disabled||lock.current)return;if(renderedRevision!==draftRevision.current)return;approvalRevision.current=e.target.checked?draftRevision.current:null;setConfirmed(e.target.checked);}}),'I reviewed ignored columns and row results. Import only my selected valid, nonduplicate rows.'),
          actButton('Import valid rows',async session=>{if(approvalRevision.current!==draftRevision.current)return;const body={csv_text:csv,mapping,spreadsheet_safe:false,expected_fingerprint:preview.fingerprint,approved_rows:preview.rows.filter(r=>r.status==='duplicate'||(r.status==='ready'&&selected.includes(r.row_number))).map(r=>r.row_number),duplicate_policy:duplicates};clear();const done=await session.import(body);if(done){setResult(done);setNotice('Import completed.');onImported?.();}},disabled||!confirmed||!selected.length||(duplicates==='reject'&&preview.counts.duplicate>0))),
        result&&h('div',{role:'status'},h('p',null,`Batch ${result.batch_id}: ${result.counts.created} created; ${result.counts.skipped} skipped; ${result.counts.excluded} excluded.`),h('ul',null,...[...result.skipped.map(row=>({...row,outcome:'skipped'})),...result.excluded.map(row=>({...row,outcome:'excluded'}))].map((row,index)=>h('li',{key:index},`Row ${row.row_number}: ${row.outcome} (${row.reason})`)))))
      :h('section',null,
        h('p',null,`Export all contacts matching the current filters, not only the visible page: ${JSON.stringify(filters)}`),
        h('fieldset',{disabled},h('legend',null,'Columns to include'),...(catalog?.columns||[]).map(column=>h('label',{key:column.key},h('input',{type:'checkbox',checked:columns.includes(column.key),onChange:e=>{setColumns(old=>e.target.checked?[...old,column.key]:old.filter(k=>k!==column.key));setConsent(false);setArtifact(null);}}),column.label+(column.archived?' (archived)':'')))),
        h('p',null,'Preparing creates a private plaintext CSV artifact on the Hermes host. It is retained until manually removed; closing this drawer does not delete it. Download creates another plaintext copy. Notes and custom fields require explicit column selection.'),
        h('label',null,h('input',{type:'checkbox',checked:consent,disabled,onChange:e=>{setConsent(e.target.checked);if(!e.target.checked)setArtifact(null);}}),'I approve these fields, filters and plaintext export retention.'),
        typeof captureDownload!=='function'&&h('p',null,'Update Hermes Desktop to enable supported CSV downloads.'),
        actButton('Prepare CSV export',async session=>{setArtifact(null);const prepared=await session.export({filters,columns,spreadsheet_safe:true});if(prepared)setArtifact(prepared);},disabled||!consent||!columns.length||typeof captureDownload!=='function'),
        artifact&&h('div',null,h('p',null,`${artifact.row_count} contacts. ${artifact.escaped_cells} cells escaped for spreadsheet safety.`),actButton('Download CSV',async()=>{if(await artifact.download())setNotice('Save dialog requested. This does not confirm the file was saved.');},busy||invalidated)))),
    notice&&h('p',{role:'status'},notice));
}
