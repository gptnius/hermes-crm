import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
const context=vm.createContext({URLSearchParams,crypto:webcrypto});
const source=await readFile(new URL('../desktop/contact-transfer.js',import.meta.url),'utf8');
const module=new vm.SourceTextModule(source,{context});
await module.link(()=>new vm.SyntheticModule(['createElement','useEffect','useRef','useState'],function(){for(const key of ['createElement','useEffect','useRef','useState'])this.setExport(key,()=>{});},{context}));await module.evaluate();
const {createContactTransferSession,transferPreview}=module.namespace;
assert.equal(Boolean(transferPreview({headers:['name'],rows:[],counts:{ready:0,duplicate:0,invalid:0}})),false);
const store=new Map();let current=true,finish,id,writes=0,downloads=0,captures=0;let committed=false;
const client={current:()=>current,request:async(path,options)=>{
 if(options){writes++;id=options.body.batch_id||options.body.operation_id;return new Promise((resolve,reject)=>{finish=()=>committed?resolve({batch_id:id,status:'completed',created:[],skipped:[],excluded:[],counts:{created:0,skipped:0,excluded:0}}):reject(new Error('private failure'));});}
 return {batch_id:id,status:'completed',created:[],skipped:[],excluded:[],counts:{created:0,skipped:0,excluded:0}};
}};
const session=()=>createContactTransferSession(client,'ws',()=>current,()=>{captures++;return async()=>{downloads++;};},store);
let own=session();let first=own.importRows({csv_text:'private'});assert.equal(writes,1);assert.equal(await own.importRows({csv_text:'private'}),null);assert.ok(!JSON.stringify([...store.values()]).includes('private'));
own.close();let newer=session();let notifications=0;newer.subscribe(()=>notifications++);finish();await assert.rejects(first);assert.equal(newer.pending().state,'unknown');assert.ok(notifications);const recovered=await newer.recover();assert.equal(recovered.result.batch_id,id);assert.equal(writes,1);assert.equal(newer.pending(),undefined);
let exportId;const exportClient={current:()=>current,request:async(path,options)=>{if(options){exportId=options.body.operation_id;assert.equal(captures,1);}return {operation_id:exportId,state:'committed',stored_path:'/private/export.csv',suggested_name:'contacts.csv',row_count:2,escaped_cells:1};}};
own=createContactTransferSession(exportClient,'export',()=>current,()=>{captures++;return async()=>downloads++;},store);const artifact=await own.export({columns:['name']});assert.equal(downloads,0);assert.equal(artifact.escaped_cells,1);await artifact.download();assert.equal(downloads,1);current=false;assert.equal(await artifact.download(),false);assert.equal(downloads,1);
current=true;own=session();first=own.importRows({});current=false;committed=true;finish();await first;assert.equal(store.get('ws').state,'unknown');current=true;own.close();newer=session();await newer.recover();assert.equal(writes,2);
console.log('contact transfer sessions: passed');
// Invalid success envelopes remain locked. Unknown exports recover their original
// captured owner instead of capturing whichever profile is now focused.
let resolveExport,exportCalls=0,captureCalls=0,ownerDownloads=0,originalId;
const exportStore=new Map();const uncertainClient={current:()=>true,request:async(path,options)=>{if(options){exportCalls++;originalId=options.body.operation_id;return new Promise(resolve=>resolveExport=resolve);}return {operation_id:originalId,state:'committed',stored_path:'/private/original.csv',suggested_name:'contacts.csv',row_count:1,escaped_cells:0};}};
let firstExport=createContactTransferSession(uncertainClient,'same',()=>true,()=>{captureCalls++;return async()=>ownerDownloads++;},exportStore);
const preparing=firstExport.export({});firstExport.close();const reopenedExport=createContactTransferSession(uncertainClient,'same',()=>true,()=>{throw new Error('Must not recapture');},exportStore);resolveExport({invalid:true});await preparing;assert.equal(reopenedExport.pending().state,'unknown');const original=await reopenedExport.recover();assert.equal(captureCalls,1);assert.equal(exportCalls,1);assert.equal(ownerDownloads,0);await original.result.download();assert.equal(ownerDownloads,1);
const absent=createContactTransferSession(uncertainClient,'missing',()=>true,undefined,exportStore);await assert.rejects(absent.export({}));assert.equal(exportCalls,1);assert.equal(absent.pending(),undefined);
const bad=createContactTransferSession({current:()=>true,request:async()=>({headers:['name'],fingerprint:'x',rows:[{row_number:2,status:'ready',errors:[],duplicates:[null]}],counts:{ready:1,duplicate:0,invalid:0},ignored_columns:[]})},'bad',()=>true,undefined,new Map());await assert.rejects(bad.preview({}));
let profileGeneration=1,finishPreview;const captured=profileGeneration;const previewClient={current:()=>profileGeneration===captured,request:()=>new Promise(resolve=>finishPreview=resolve)};const scoped=createContactTransferSession(previewClient,'aba',()=>true,undefined,new Map());const previewing=scoped.preview({});profileGeneration++;profileGeneration++;finishPreview({headers:['name'],needs_mapping:true,suggested_mapping:{name:'name'}});assert.equal(await previewing,null);assert.equal(await scoped.importRows({}),null);
console.log('contact transfer stale, malformed, recovery and capability guards: passed');
