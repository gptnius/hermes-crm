import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
const require = createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React=require('react'), Renderer=require('react-test-renderer'), {act}=React, h=React.createElement;
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const context=vm.createContext({URLSearchParams,crypto:webcrypto,console});
const module=new vm.SourceTextModule(await readFile(new URL('../desktop/plugin.js',import.meta.url),'utf8'),{context});
await module.link(name=>{const exports=name==='react'?React:{};return new vm.SyntheticModule(Object.keys(exports),function(){for(const [key,value] of Object.entries(exports))this.setExport(key,value);},{context});});await module.evaluate();
const {Editor,taskOwnerText,taskOwnerPolicy}=module.namespace;
const policy={version:4,required:true,default_owner_label:'Reviewed default',legacy_edit_rule:'owner_required_on_edit'};
const data={contacts:[],deals:[],meta:{task_owner_policy:policy}};
const task={id:'task-one',version:7,title:'Review proposal',due_at:'2030-06-12T10:23:56.123456-04:00',priority:'normal',status:'open',owner_label:null};
let tree,saves=[],cancelled=0;
const save=async value=>{saves.push(JSON.parse(JSON.stringify(value)));return false;};
const editor={kind:'tasks',row:task,key:'editor',workspaceToken:'ws'};
const mount=async(props={})=>{await act(async()=>{tree=Renderer.create(h(Editor,{editor,data,busy:false,error:'',save,cancel:()=>cancelled++,...props}));});};
const input=name=>tree.root.findAllByType('input').find(n=>n.props.name===name);
const click=async title=>{const b=tree.root.findAllByType('button').find(n=>n.children.join('')===title);assert.ok(b,title);await act(async()=>b.props.onClick());};
const submit=async()=>act(async()=>tree.root.findByType('form').props.onSubmit({preventDefault(){}}));
const change=async(name,value)=>act(async()=>input(name).props.onChange({target:{value}}));
const text=()=>JSON.stringify(tree.toJSON());
assert.equal(taskOwnerText(task),'Task owner (human): Not recorded');
assert.equal(taskOwnerPolicy({meta:{}}).version,0);
assert.equal(taskOwnerPolicy({meta:{task_owner_policy:{version:4}}}),null);
await mount();assert.equal(input('owner_label').props.value,'');assert.equal(input('owner_label').props.required,true);
await submit();assert.equal(saves.length,0);assert.match(text(),/Choose a human task owner/);
await click('Use configured default: Reviewed default');assert.equal(input('owner_label').props.value,'Reviewed default');await submit();
assert.equal(saves[0].owner_label,'Reviewed default');assert.equal(saves[0].owner_source,'default');assert.equal(saves[0].owner_policy_version,4);assert.equal(saves[0].due_at,task.due_at);assert.equal(saves[0].status,'open');
await submit();assert.deepEqual(saves[1],saves[0]);assert.ok(input('owner_label').props.disabled);
await act(async()=>tree.unmount());
saves=[];await mount();await change('owner_label','Accountable person');await submit();assert.equal(saves[0].owner_source,'explicit');assert.equal(saves[0].owner_label,'Accountable person');assert.equal(saves[0].due_at,task.due_at);await act(async()=>tree.unmount());
// All ordinary new-task launch paths converge on Editor, preserving direct contact/deal initial context.
for(const initial of [{},{contact_id:'contact-one'},{contact_id:'contact-one',deal_id:'deal-one'}]){
 saves=[];await mount({editor:{...editor,row:null,initial}});assert.equal(input('owner_label').props.value,'');await change('title','New task');await change('due_at','2030-06-12T10:00');await click('Use configured default: Reviewed default');await submit();assert.equal(saves[0].owner_label,'Reviewed default');assert.equal(saves[0].contact_id,initial.contact_id||null);assert.equal(saves[0].deal_id,initial.deal_id||null);await act(async()=>tree.unmount());
}
// A policy refresh never adopts a new version or default into a dirty draft.
saves=[];await mount();await change('owner_label','Deliberate');await act(async()=>tree.update(h(Editor,{editor,data:{...data,meta:{task_owner_policy:{...policy,version:5}}},busy:false,save,cancel:()=>cancelled++})));await submit();assert.equal(saves.length,0);assert.match(text(),/Close and reopen/);await act(async()=>tree.unmount());
// A retained callback from a dismissed form cannot save.
await mount();const stale=tree.root.findByType('form').props.onSubmit;await act(async()=>tree.unmount());await stale({preventDefault(){}});assert.equal(saves.length,0);
// Optional legacy policy permits honest missing owner, never assignment-owner inference.
await mount({data:{...data,meta:{}},editor:{...editor,row:{...task,agent_work:{human_owner:'Not the task owner'}}}});await submit();assert.equal(saves[0].owner_label,null);assert.equal(saves[0].owner_policy_version,0);await act(async()=>tree.unmount());
// Event-created tasks capture policy independently and require a deliberate selection.
const rel=new vm.SourceTextModule(await readFile(new URL('../desktop/relationships.js',import.meta.url),'utf8'),{context});await rel.link(()=>new vm.SyntheticModule(['createElement','useEffect','useRef','useState'],function(){for(const k of ['createElement','useEffect','useRef','useState'])this.setExport(k,React[k]);},{context}));await rel.evaluate();
const {RelationshipForm}=rel.namespace;
const session={read:async(path)=>path==='/task-owner-policy'?policy:{items:[],total:0}};
saves=[];await act(async()=>{tree=Renderer.create(h(RelationshipForm,{kind:'events',action:'task',row:{id:'event-one',contact_id:'contact-one',timezone:'UTC'},session,submit:value=>saves.push(value),cancel:()=>{},busy:false,pending:false}));});
assert.equal(input('owner_label').props.value,'');await click('Use configured default: Reviewed default');
const label=caption=>tree.root.findAllByType('label').find(n=>n.children[0]===caption).findByType('input');
await act(async()=>{label('title').props.onChange({target:{value:'Event task'}});tree.root.findAllByType('input').find(n=>n.props.type==='datetime-local').props.onChange({target:{value:'2030-06-12T10:00'}});});await submit();assert.equal(saves[0].owner_source,'default');assert.equal(saves[0].owner_policy_version,4);assert.equal(saves[0].owner_label,'Reviewed default');assert.equal(saves[0].contact_id,'contact-one');await act(async()=>tree.unmount());
// Receipt matching checks exact record versions, submitted core values and microseconds.
const receiptData={title:'  Reviewed title  ',contact_id:null,deal_id:null,due_at:'2030-06-12T10:23:56.123456-04:00',priority:'high',status:'open',notes:'  Reviewed notes  ',owner_label:'Human owner',owner_source:'explicit',owner_policy_version:4};
for(const method of ['POST','PATCH']) {
 const body={...receiptData,...(method==='PATCH'?{version:7}:{})};const options={method,body:{data:body}};const path=method==='POST'?'/tasks':'/tasks/task-one';
 const receipt={...body,id:'task-one',version:method==='POST'?1:8,title:'Reviewed title',notes:'Reviewed notes',due_at:'2030-06-12T14:23:56.123456+00:00'};
 assert.equal(module.namespace.confirmedTaskReceipt(path,options,receipt),true);
 for(const patch of [{version:receipt.version+1},{version:receipt.version-1},{due_at:null},{due_at:'2030-06-12T14:23:56.123457Z'},{title:'Unrelated'},{notes:'Other notes'},{contact_id:'other-contact'},{deal_id:'other-deal'},{status:'done'},{priority:'normal'},{owner_label:'Other owner'},{owner_source:'default'}]) assert.equal(module.namespace.confirmedTaskReceipt(path,options,{...receipt,...patch}),false,JSON.stringify(patch));
}
console.log('native task ownership forms: PASS');
