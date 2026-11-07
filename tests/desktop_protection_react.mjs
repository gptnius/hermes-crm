import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';
const require = createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-docs-check.UuZaYi/react-test-deps'}/package.json`);
const React = require('react'), Renderer = require('react-test-renderer');
const {act} = React; globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const context = vm.createContext({URLSearchParams,crypto:webcrypto});
const module = new vm.SourceTextModule(await readFile(new URL('../desktop/protection.js',import.meta.url),'utf8'),{context});
await module.link(() => new vm.SyntheticModule(['createElement','useEffect','useRef','useState'],function(){for(const key of ['createElement','useEffect','useRef','useState'])this.setExport(key,React[key]);},{context})); await module.evaluate();
const {ProtectionDrawer} = module.namespace;
const h = React.createElement;
function Drawer({children,cancel}) {return h('section',null,h('button',{onClick:cancel},'Close'),children);}
const calls = []; let enabled = true, stale = false, refreshFailure = false, writeCount = 0, downloads = 0, cancelCount = 0, captureCount = 0;
const metadata = {record_version:1,note_version:0,has_note:true};
const client = {current:()=>!stale,request:async(path,options)=>{
  calls.push({path,options});
  if(path.startsWith('/protection/status')) {if(refreshFailure && writeCount)throw new Error('unsafe');return {notes_enabled:enabled,backup_enabled:enabled};}
  if(path.endsWith('/reveal'))return {...metadata,plaintext:'SECRET_FIXTURE'};
  if(path==='/protection/export')return {export_id:'fixture',stored_path:'/private/path',suggested_name:'crm.enc'};
  if(options?.method==='PUT'){writeCount++;return {...metadata,note_version:1};}
  return metadata;
}};
let props = {Drawer,client,workspaceToken:'ws',record:{kind:'contacts',id:'1'},current:()=>!stale,cancel:()=>cancelCount++};
let tree;
const render = async()=>{await act(async()=>{if(tree)tree.update(h(ProtectionDrawer,props));else tree=Renderer.create(h(ProtectionDrawer,props));});};
const text =()=>JSON.stringify(tree.toJSON());
const button = label=>tree.root.findAllByType('button').find(n=>n.children.join('')===label);
const click=async label=>{await act(async()=>{const b=button(label);assert.ok(b,label);assert.ok(!b.props.disabled,label);b.props.onClick();});};
await render(); assert.ok(calls.every(c=>!c.options)); assert.ok(!text().includes('SECRET_FIXTURE'));
await click('Reveal protected note'); assert.ok(text().includes('SECRET_FIXTURE')); assert.equal(writeCount,0);
await click('Cancel and hide'); assert.ok(!text().includes('SECRET_FIXTURE'));
await click('Reveal protected note'); await click('Edit protected note');
refreshFailure=true; await click('Save protected note'); assert.equal(writeCount,1); assert.ok(!text().includes('SECRET_FIXTURE')); assert.match(text(),/saved, but metadata refresh failed/);
refreshFailure=false;
await click('Reveal protected note'); stale=true; props={...props,invalidated:true}; await render(); assert.ok(!text().includes('SECRET_FIXTURE')); await click('Close'); assert.equal(cancelCount,1);
await act(async()=>tree.unmount());tree=null; stale=false;enabled=false;props={...props,invalidated:false};await render();assert.equal(button('Reveal protected note'),undefined);
await act(async()=>tree.unmount());tree=null;enabled=true;
props={...props,record:null,captureDownload:()=>{captureCount++;return async()=>{downloads++;};}};await render();assert.equal(captureCount,0);assert.equal(downloads,0);
await click('Prepare encrypted export');assert.equal(captureCount,1);assert.equal(downloads,0);assert.ok(!text().includes('/private/path'));
await click('Download encrypted export');assert.equal(downloads,1);assert.match(text(),/does not confirm the file was saved/);
await click('Download encrypted export');assert.equal(downloads,2);
await act(async()=>tree.unmount());tree=null;props={...props,captureDownload:undefined};await render();assert.ok(button('Prepare encrypted export').props.disabled);assert.match(text(),/Update Hermes Desktop/);
await act(async()=>tree.unmount());
// Deferred reveal is discarded after a view invalidation; writes are gated
// synchronously even when React has not yet committed its disabled button.
tree=null; let finishReveal, finishSave, unknown=true, receiptState='unknown';
const deferredClient={current:()=>true,request:async(path,options)=>{
  if(path.startsWith('/protection/status'))return {notes_enabled:true,backup_enabled:true};
  if(path.endsWith('/reveal'))return new Promise(resolve=>{finishReveal=resolve;});
  if(path.includes('/operations/'))return {...metadata,operation_id:pendingId,state:receiptState};
  if(options?.method==='PUT'){writeCount++;pendingId=options.body.operation_id;return new Promise((resolve,reject)=>{finishSave=()=>unknown?reject(Object.assign(new Error('sensitive transport text'), {status:503})):resolve(metadata);});}
  return metadata;
}};
let pendingId;
stale=false;props={Drawer,client:deferredClient,workspaceToken:'deferred',record:{kind:'deals',id:'2'},current:()=>!stale,cancel:()=>{},operationStore:new Map()};await render();
await click('Reveal protected note'); stale=true;props={...props,invalidated:true};await render();
await act(async()=>finishReveal({...metadata,plaintext:'LATE_SECRET'}));assert.ok(!text().includes('LATE_SECRET'));
await act(async()=>tree.unmount());tree=null;stale=false;props={...props,invalidated:false,workspaceToken:'save'};await render();
await click('Reveal protected note');await act(async()=>finishReveal({...metadata,plaintext:'SAVE_SECRET'}));await click('Edit protected note');
const beforeWrites=writeCount;
await act(async()=>{const handler=button('Save protected note').props.onClick;handler();handler();});assert.equal(writeCount,beforeWrites+1);
await act(async()=>finishSave());assert.match(text(),/Save outcome unknown/);
assert.ok(!text().includes('SAVE_SECRET'), '503 must clear plaintext without another gesture');
assert.equal(tree.root.findAllByType('textarea').length,0);
assert.ok(button('Reveal protected note').props.disabled);
await click('Check save outcome');assert.match(text(),/save remains locked/);
receiptState='committed';await click('Check save outcome');assert.match(text(),/save confirmed/);assert.ok(!text().includes('SAVE_SECRET'));assert.equal(writeCount,beforeWrites+1);
await act(async()=>tree.unmount());
// Reopen while a request is in flight. Its eventual unknown transition must
// update the new drawer without a manual refresh or unrelated render.
tree=null;props={...props,workspaceToken:'reopened'};await render();
await click('Reveal protected note');await act(async()=>finishReveal({...metadata,plaintext:'REOPEN_SECRET'}));await click('Edit protected note');await click('Save protected note');
assert.ok(!text().includes('REOPEN_SECRET'), 'dispatch clears local plaintext');
await act(async()=>tree.unmount());tree=null;await render();assert.equal(button('Check save outcome'),undefined);
await act(async()=>finishSave());assert.ok(button('Check save outcome'));assert.ok(!button('Check save outcome').props.disabled);
assert.ok(!text().includes('REOPEN_SECRET'));
await act(async()=>tree.unmount());
// The same shared-store notifications update reopened export drawers.
tree=null;let finishExport;
const exportClient={current:()=>true,request:async(path,options)=>{
  if(path.startsWith('/protection/status'))return {notes_enabled:true,backup_enabled:true};
  if(options)return new Promise((resolve,reject)=>{finishExport=()=>reject(Object.assign(new Error('proxy fixture'),{status:503}));});
  return {state:'unknown'};
}};
props={...props,client:exportClient,workspaceToken:'export-reopened',record:null,captureDownload:()=>async()=>{}};await render();
await click('Prepare encrypted export');await act(async()=>tree.unmount());tree=null;await render();
assert.equal(button('Check export outcome'),undefined);await act(async()=>finishExport());
assert.ok(button('Check export outcome'));assert.ok(!button('Check export outcome').props.disabled);assert.ok(button('Prepare encrypted export').props.disabled);
await act(async()=>tree.unmount());
console.log('PASS React protection gestures, plaintext clearing, stale dismissal, key-disabled state, committed refresh failure, SDK absence and export dialog semantics.');
