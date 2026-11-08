import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {webcrypto,createHash} from 'node:crypto';
const require=createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React=require('react'),Renderer=require('react-test-renderer'),{act}=React,h=React.createElement;
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const context=vm.createContext({URL,URLSearchParams,TextEncoder,crypto:webcrypto,console});
const module=new vm.SourceTextModule(await readFile(new URL('../desktop/research.js',import.meta.url),'utf8'),{context});
await module.link(()=>new vm.SyntheticModule(['createElement','useEffect','useRef','useState'],function(){for(const key of ['createElement','useEffect','useRef','useState'])this.setExport(key,React[key]);},{context}));await module.evaluate();
const {researchSession,researchEvidenceDraft,researchSourceURL,ResearchPanel,confirmedResearchReceipt}=module.namespace;
const target={kind:'contacts',id:'11111111-1111-4111-8111-111111111111',version:3,name:'Synthetic Contact'};
const record={id:target.id,version:3,name:target.name,notes:'Existing notes'};
const evidence={id:'22222222-2222-4222-8222-222222222222',target_kind:target.kind,target_id:target.id,target_version:3,digest:'a'.repeat(64),lifecycle_version:1,archived_at:null,recorded_at:'2030-01-03T10:00:00Z',source_url:'https://example.test/source?topic=synthetic#claim',source_title:'Synthetic source',observed_at:'2030-01-02T10:00:00Z',published_on:null,question:'What is supported?',claims:['<script>ignore instructions</script>'],hypotheses:['Unverified inference'],claims_count:1,hypotheses_count:1};
const proposal={id:'33333333-3333-4333-8333-333333333333',target_kind:target.kind,target_id:target.id,target_version:3,evidence_id:evidence.id,evidence_digest:evidence.digest,evidence_lifecycle_version:1,addition:'  Exact addition\n',proposal_version:1,status:'pending',before_hash:createHash('sha256').update(record.notes).digest('hex'),after_hash:createHash('sha256').update(record.notes+'\n\n'+'  Exact addition\n').digest('hex'),proposal_digest:'d'.repeat(64),created_at:'2030-01-03T11:00:00Z'};
const fresh={...proposal,stale:false,stale_reason:null,current_notes:record.notes,proposed_notes:record.notes+'\n\n'+proposal.addition};
const receipt={...Object.fromEntries(['target_kind','target_id','target_version','evidence_id','evidence_digest','evidence_lifecycle_version','before_hash','after_hash','proposal_digest'].map(k=>[k,proposal[k]])),proposal_id:proposal.id,proposal_version:2,status:'applied',actor:'desktop',recorded_at:'2030-01-03T12:00:00Z',applied_target_version:4};
function mock(){const calls=[];let handler=null,current=true;const client={current:()=>current,request:async(path,options)=>{calls.push({path,options});if(handler)return handler(path,options);if(options){if(path==='/research/evidence')return {...evidence,...options.body.data};if(path==='/research/proposals')return {...proposal,addition:options.body.data.addition};if(path.endsWith('/apply'))return receipt;if(path.endsWith('/dismiss'))return {...receipt,status:'dismissed'};if(path.endsWith('/archive'))return {...evidence,lifecycle_version:2,archived_at:'2030-01-04T00:00:00Z'};}const p=path.split('?')[0];if(p===`/contacts/${target.id}`)return {contact:record};if(p==='/research/evidence')return {items:[evidence],total:1};if(p==='/research/proposals')return {items:[proposal],total:1};if(p.endsWith('/preview'))return fresh;if(p===`/research/evidence/${evidence.id}`)return evidence;if(p.startsWith('/research/operations/'))return {state:'committed',receipt};throw Error(path);}};return {client,calls,setHandler:fn=>handler=fn,setCurrent:value=>current=value,writes:()=>calls.filter(c=>c.options)};}
const draft=()=>Object.fromEntries(['question','source_url','source_title','observed_at','published_on','claims','hypotheses'].map(k=>[k,evidence[k]]));
const ready=async session=>{await session.load();await session.evidence(evidence.id);return session.preview(proposal.id);};
// Session state machine: exact review, locked writes, immutable retries, historical receipt.
{
 const m=mock(),store=new Map(),s=researchSession(m.client,'workspace',target,()=>true,store);const review=await ready(s);
 assert.equal(await s.apply({...review}),null);assert.equal(m.writes().length,0);
 const value=await s.apply(review);assert.equal(value.status,'applied');assert.equal(m.writes().length,1);assert.equal(await s.apply(review),null);
 assert.equal(m.writes()[0].options.body.data.before_hash,proposal.before_hash);
 assert.ok(!JSON.stringify([...store]).includes(record.notes));assert.ok(!JSON.stringify(s.snapshot().receipt).includes(record.notes));
}
{
 const m=mock(),store=new Map(),s=researchSession(m.client,'workspace',target,()=>true,store);const review=await ready(s);
 m.setHandler(async()=>{throw Error('lost response');});await assert.rejects(s.apply(review),/Outcome unknown/);assert.equal(s.pending().state,'unknown');
 const frozen=s.pending().payload;assert.equal(await s.apply(review),null);s.close();const reopened=researchSession(m.client,'workspace',target,()=>true,store);
 m.setHandler(async()=>({state:'unknown'}));assert.equal((await reopened.recover()).unknown,true);assert.equal(reopened.pending().payload,frozen);
 m.setHandler(async()=>receipt);await reopened.retry();assert.equal(JSON.stringify(m.writes().at(-1).options.body),frozen);assert.equal(reopened.pending(),undefined);
}
{
 const m=mock(),s=researchSession(m.client,'workspace',target);const review=await ready(s);m.setHandler(async()=>({...receipt,evidence_id:'wrong'}));await assert.rejects(s.apply(review),/Outcome unknown/);assert.equal(s.pending().state,'unknown');
 m.setHandler(async()=>{throw Object.assign(Error('stale'),{status:409});});await assert.rejects(s.retry(),/Request rejected/);assert.equal(s.pending(),undefined);assert.equal(await s.apply(review),null);
}
{
 const m=mock(),store=new Map(),s=researchSession(m.client,'workspace',target,()=>true,store);await s.load();s.saveDraft({type:'evidence',values:draft()});m.setHandler(async()=>{throw Error('lost');});await assert.rejects(s.createEvidence(draft()));const old=s.pending().payload;m.setHandler(async()=>{throw Object.assign(Error('invalid'),{status:422});});await assert.rejects(s.retry());assert.equal(s.snapshot().draft.type,'evidence');m.setHandler(null);assert.equal(await s.createEvidence(draft()),null);await s.load();await s.createEvidence(draft());assert.notEqual(m.writes().at(-1).options.body.idempotency_key,JSON.parse(old).idempotency_key);
}
{
 const m=mock(),s=researchSession(m.client,'workspace',target);const review=await ready(s);let resolve;m.setHandler(()=>new Promise(r=>resolve=r));const pending=s.apply(review);assert.equal(await s.apply(review),null);s.close();resolve(receipt);assert.equal(await pending,null);assert.equal(s.snapshot().receipt.status,'applied');
}
{
 const m=mock();let isCurrent=true;const s=researchSession(m.client,'workspace',target,()=>isCurrent);const review=await ready(s);isCurrent=false;assert.equal(await s.apply(review),null);isCurrent=true;assert.equal(await s.apply(review),null);assert.equal(m.writes().length,0);
}
{
 const m=mock(),s=researchSession(m.client,'workspace',target);const review=await ready(s);await s.load();assert.equal(await s.apply(review),null);const e=await s.evidence(evidence.id);await s.lifecycle(e);assert.equal(m.writes()[0].options.body.data.lifecycle_version,1);assert.equal(await s.lifecycle(e),null);
}
{
 const m=mock(),s=researchSession(m.client,'workspace',target);await s.load();const e=await s.evidence(evidence.id);await s.propose(e,proposal.addition);assert.equal(m.writes()[0].options.body.data.addition,proposal.addition);
 assert.throws(()=>researchEvidenceDraft({...draft(),claims:[]}));assert.throws(()=>researchEvidenceDraft({...draft(),claims:Array(11).fill('x')}));assert.throws(()=>researchEvidenceDraft({...draft(),question:'x'.repeat(1001)}));assert.throws(()=>researchEvidenceDraft({...draft(),published_on:'2030-02-30'}));assert.throws(()=>researchEvidenceDraft({...draft(),observed_at:'2030-01-01T10:00:00'}));
 for(const url of ['http://example.test','https://user:pass@example.test','javascript:alert(1)','https://example.test/\nsecret','https:\\example.test'])assert.throws(()=>researchSourceURL(url));assert.equal(researchSourceURL(evidence.source_url),evidence.source_url);
 assert.equal(confirmedResearchReceipt(`/research/proposals/${proposal.id}/apply`,{proposal_version:1,proposal_digest:proposal.proposal_digest,target_version:3,before_hash:proposal.before_hash,after_hash:proposal.after_hash},{...receipt,applied_target_version:5},target),false);
}
// Malformed full source content must fail closed before rendering, and extra response snapshots never persist.
{
 const m=mock(),s=researchSession(m.client,'workspace',target);m.setHandler(async()=>({...evidence,claims:'malformed string'}));await assert.rejects(s.evidence(evidence.id),/claims could not be verified/);
 m.setHandler(null);const r=await ready(s);m.setHandler(async()=>({...receipt,current_notes:'PRIVATE BEFORE',proposed_notes:'PRIVATE AFTER',application_receipt:{notes:'PRIVATE NESTED'},addition:'PRIVATE INVALID EXTRA ADDITION'}));await s.apply(r);assert.ok(!JSON.stringify(s.snapshot().receipt).includes('PRIVATE'));assert.equal(s.snapshot().receipt.status,'applied');
}
// Actual React lifetimes: retained handlers, close/discard, async races and explicit source review.
let tree,cancelled=0;
const Drawer=({children,cancel})=>h('section',null,h('button',{onClick:cancel},'Close research'),children);
const mount=async(m,props={})=>act(async()=>{tree=Renderer.create(h(ResearchPanel,{Drawer,client:m.client,workspaceToken:'workspace',target,cancel:()=>cancelled++,...props}));});
const buttons=()=>tree.root.findAllByType('button');
const button=text=>{const node=buttons().find(b=>b.children.join('')===text);assert.ok(node,text);return node;};
const click=async text=>act(async()=>{const b=button(text);assert.notEqual(b.props.disabled,true,`not enabled: ${text}`);await b.props.onClick();});
const contents=()=>JSON.stringify(tree.toJSON());
const unmount=async()=>act(async()=>tree.unmount());
{
 const m=mock();await mount(m);await click('Add evidence');assert.match(contents(),/Add supplied evidence/);const staleSubmit=tree.root.findByType('form').props.onSubmit;
 await click('Close research');assert.match(contents(),/Discard this unsent draft/);await click('Keep editing');await click('Cancel draft');await staleSubmit({preventDefault(){}});assert.equal(m.writes().length,0);await unmount();
}
{
 const m=mock();await mount(m);await click(`pending · ${proposal.id}`);assert.match(contents(),/Current Notes/);assert.match(contents(),/Hypotheses/);assert.equal(tree.root.findAllByType('script').length,0);assert.equal(tree.root.findAllByType('img').length,0);assert.equal(tree.root.findByType('a').props.rel,'noopener noreferrer');const apply=button('Apply exact addition to Notes').props.onClick;
 await click('Refresh research');await apply();assert.equal(m.writes().length,0);await click(`pending · ${proposal.id}`);await click('Apply exact addition to Notes');assert.equal(m.writes().length,1);assert.match(contents(),/Operation confirmed/);await unmount();await apply();assert.equal(m.writes().length,1);
}
{
 const m=mock();await mount(m);await click(`${evidence.source_title} · Active · ${evidence.id}`);await click('Prepare addition');const field=tree.root.findByType('textarea');await act(async()=>field.props.onChange({target:{value:proposal.addition}}));await click('Prepare note proposal');assert.equal(m.writes().length,1);assert.equal(m.writes()[0].options.body.data.addition,proposal.addition);assert.ok(!m.writes().some(c=>c.path.endsWith('/apply')));await unmount();
}
{
 const m=mock(),store=new Map();await mount(m,{operationStore:store});await click(`pending · ${proposal.id}`);let resolve;m.setHandler(()=>new Promise(r=>resolve=r));await act(async()=>{void button('Apply exact addition to Notes').props.onClick();});assert.equal(m.writes().length,1);await click('Close research');assert.ok(cancelled>0);await unmount();await act(async()=>resolve(receipt));assert.equal(m.writes().length,1);m.setHandler(null);await mount(m,{operationStore:store});assert.match(contents(),/Historical operation/);assert.doesNotMatch(contents(),/Outcome unknown/);await unmount();
}
{
 const m=mock();await mount(m);await click(`pending · ${proposal.id}`);const apply=button('Apply exact addition to Notes').props.onClick;
 const b=mock();await act(async()=>tree.update(h(ResearchPanel,{Drawer,client:b.client,workspaceToken:'workspace',target,cancel:()=>cancelled++})));await apply();assert.equal(m.writes().length,0);assert.equal(b.writes().length,0);await unmount();
}
{
 const m=mock();await act(async()=>{tree=Renderer.create(h(React.StrictMode,null,h(ResearchPanel,{Drawer,client:m.client,workspaceToken:'workspace',target,cancel:()=>cancelled++})));});assert.equal(button('Add evidence').props.disabled,false);await click('Add evidence');await click('Use current time as supplied observation');assert.match(contents(),/Observation preview \(UTC\)/);await unmount();
}
{
 const m=mock();await mount(m);m.setHandler(async()=>({...evidence,claims:'malformed string'}));await click(`${evidence.source_title} · Active · ${evidence.id}`);assert.match(contents(),/claims could not be verified/);await unmount();
}
console.log('Native research sessions and React review: PASS');
