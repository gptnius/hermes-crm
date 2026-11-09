// Synthetic React lifecycle coverage for detail composition and lossless field visibility.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
const require=createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React=require('react'),Renderer=require('react-test-renderer');
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const source=readFileSync(new URL('../desktop/plugin.js',import.meta.url),'utf8');
const body=source.slice(source.indexOf('function Detail('),source.indexOf('\n// Use only elements'));
const h=React.createElement, noop=()=>{};
const component=name=>props=>h('div',{'data-component':name},props.children);
const context={h,useRef:React.useRef,useEffect:React.useEffect,workspaceCatalog:data=>data.meta.catalog,label:String,date:String,money:String,stageLabel:(_,s)=>s,taskOwnerText:()=>'',analyticsOperationStore:()=>({}),emailBridgeMemory:()=>({}),lifetimes:new Map(),badge:x=>h('span',null,x),button:(text,onClick,props)=>h('button',{...props,onClick},text),Properties:({rows})=>h('dl',null,rows.map(([k,v])=>h('div',{key:k},h('dt',null,k),h('dd',null,v)))),RecordSection:({title,children})=>h('section',null,h('h3',null,title),children),Timeline:component('Timeline')};
for(const name of ['ContactCompany','ContactRelationships','ContactLogPanel','EmailBridgePanel','EmailHistoryPanel','TaskEventRelationship','TaskScheduledResearch','TaskWork'])context[name]=component(name);
const Detail=vm.runInNewContext(body+';Detail',context);
const base={disabled:false,ctx:{},identity:'test',client:{},detail:{kind:'contacts',workspaceToken:'synthetic',row:{contact:{id:'c1',name:'Casey Lane',version:1,custom_fields:{}},deals:[],tasks:[],activity:[]}},data:{contacts:[],deals:[],tasks:[],activity:[],meta:{catalog:{fields:{contacts:[]}}}},viewRequest:{current:1},close:noop,edit:noop,open:noop,create:noop,startRelatedCreate:noop,protect:noop,research:noop};
let tree;
for(const [fields,values,expected] of [
 [[],{},[]],
 [[{key:'defined',label:'Defined'}],{},['Defined','Not set']],
 [[{key:'archived',label:'Archived',archived:true}],{},[]],
 [[{key:'archived',label:'Archived',archived:true}],{archived:false},['Archived (archived)','No']],
 [[{key:'count',label:'Count'}],{count:0},['Count','0']],
 [[],{retained:'preserved'},['retained (stored field)','preserved']],
]){
 const props={...base,detail:{...base.detail,row:{...base.detail.row,contact:{...base.detail.row.contact,custom_fields:values}}},data:{...base.data,meta:{catalog:{fields:{contacts:fields}}}}};
 await React.act(async()=>{if(tree)tree.update(h(Detail,props));else tree=Renderer.create(h(Detail,props));});
 const json=JSON.stringify(tree.toJSON());
 assert.equal(json.includes('Custom fields'),expected.length>0);
 for(const text of expected)assert.ok(json.includes(text),text);
 const grid=tree.root.findByProps({className:'hc-contact-grid'});
 assert.equal(grid.findAllByProps({'data-component':'ContactCompany'}).length,1);
 assert.equal(grid.findAllByProps({'data-component':'ContactRelationships'}).length,1);
 assert.deepEqual(grid.findAll(node=>node.type==='div' && node.props['data-component']).map(node=>node.props['data-component']), ['ContactCompany','ContactLogPanel','ContactRelationships','EmailBridgePanel','EmailHistoryPanel']);
 const history=tree.root.findByProps({'aria-label':'Record history and next steps'});
 assert.equal(history.findAllByProps({'data-component':'ContactRelationships'}).length,0);
 assert.deepEqual(values,props.detail.row.contact.custom_fields);
}
await React.act(async()=>tree.unmount());
// Standalone field composition has the same inclusion and false/zero semantics.
const web=readFileSync(new URL('../hermes_crm/static/app.js',import.meta.url),'utf8');
const fn=web.slice(web.indexOf('function customFieldDetails('),web.indexOf('\nconst label ='));
const render=vm.runInNewContext(fn+';customFieldDetails',{catalog:{fields:{contacts:[{key:'empty',label:'Empty'},{key:'old',label:'Old',archived:true}]}},esc:x=>String(x)});
assert.match(render('contacts',{custom_fields:{old:false,other:0}}),/Not set/);
assert.match(render('contacts',{custom_fields:{old:false,other:0}}),/No/);
assert.match(render('contacts',{custom_fields:{old:false,other:0}}),/>0</);
console.log('PASS contact detail custom fields and full-width lower section composition');

const css=readFileSync(new URL('../desktop/design-system.css',import.meta.url),'utf8');
assert.match(css,/\.hc-contact-grid\{display:grid;grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
assert.match(css,/@container\(max-width:640px\)\{\.hermes-crm-native \.hc-contact-grid\{grid-template-columns:minmax\(0,1fr\)/);

assert.match(css,/\.hc-contact-relationships\{display:contents\}/);
const relationships=readFileSync(new URL('../desktop/relationships.js',import.meta.url),'utf8');
assert.match(relationships,/return h\('div', \{ className: 'hc-contact-relationships' \}/);

assert.match(css,/\.hc-record>nav>span\{min-width:0;max-width:100%;overflow-wrap:anywhere\}/);
assert.match(css,/\.hc-record-header \.hc-identity\{flex:1 1 240px;max-width:100%\}/);
assert.match(css,/\.hc-identity p\{overflow-wrap:anywhere\}/);

assert.match(css,/\.hc-contact-grid>\.hc-contact-log\{margin-top:0\}/);
