// Execute pinned public SDK forwarding/retention methods with inert transports.
// No native instance, credentials, network, jobs, model or source modification.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { stripTypeScriptTypes } from 'node:module';
import vm from 'node:vm';
const root=process.env.HERMES_SOURCE;
if(!root){console.log('SKIP exact SDK source contract: set HERMES_SOURCE to pinned isolated checkout.');process.exit(0);}
assert.equal(execFileSync('git',['-C',root,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),'2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19');
const sdk=await readFile(root+'/apps/desktop/src/sdk/index.ts','utf8');
const select=name=>{const start=sdk.indexOf(`  ${name}: async `);assert.ok(start>0);return sdk.slice(start,sdk.indexOf('\n  /**',start+20));};
const calls=[];let released=0;const inventory={connectionId:'isolated-remote',profile:'desktop-alias',targetProfile:'actual-backend',mode:'remote'};let refreshFails=false;
const context=vm.createContext({window:{hermesDesktop:{getProfileRoutes:async names=>{calls.push(['inventory',...names]);return[inventory];}}},$profiles:{get:()=>[{name:'cached-profile'}]},refreshProfiles:async()=>{if(refreshFails)throw Error('Synthetic inventory read failure');return[{name:'current-profile'}];},requestPluginProfile:async(...args)=>{calls.push(['request',...args]);return{type:'exec',output:'synthetic-command-result'};},retainGatewayForAgent:async(...args)=>{calls.push(['retain',...args]);return()=>released++;}});
const mod=new vm.SourceTextModule(stripTypeScriptTypes('export const host={'+select('requestProfile')+select('retainProfile')+select('profileRoutes')+'};'),{context});await mod.link(()=>{throw Error('No imports expected');});await mod.evaluate();
assert.deepEqual(await mod.namespace.host.profileRoutes(),[inventory]);assert.deepEqual(calls.pop(),['inventory','current-profile']);refreshFails=true;assert.deepEqual(await mod.namespace.host.profileRoutes(),[inventory]);assert.deepEqual(calls.pop(),['inventory','cached-profile']);
const route={connectionId:'isolated-remote',profile:'desktop-alias',targetProfile:'actual-backend',mode:'remote'};
const release=await mod.namespace.host.retainProfile(route,{spawnPriority:'foreground'});
assert.deepEqual(calls[0],['retain','isolated-remote','desktop-alias',{spawnPriority:'foreground'}]);
const parameters={session_id:'exact-existing-session',profile:'actual-backend',name:'crm-assignment-'+ 'a'.repeat(32),arg:'00000000-0000-4000-8000-000000000001'};
assert.deepEqual(await mod.namespace.host.requestProfile(route,'command.dispatch',parameters,30000),{type:'exec',output:'synthetic-command-result'});
assert.deepEqual(calls[1],['request',route,'command.dispatch',parameters,30000,undefined]);release();assert.equal(released,1);
const loader=await readFile(root+'/apps/desktop/src/contrib/runtime-loader.ts','utf8');assert.match(loader,/runtime plugins may only import @hermes\/plugin-sdk and react/);
const controls=await readFile(root+'/gateway/session_controls.py','utf8');assert.match(controls, /'commands\.catalog': self\.command_catalog/);
const contracts=await readFile(root+'/tui_gateway/contracts/tools_commands.py','utf8');assert.match(contracts, /method\("commands\.catalog", params=CommandsCatalogParams/);
const command=await readFile(root+'/gateway/session_commands.py','utf8');assert.match(command,/return \{'type': 'exec', 'output': _text\(output\)\}/);
const info=await readFile(root+'/gateway/session_local.py','utf8');assert.match(info,/'profile_name': served_profile_name\(authority\.profile_id\)/);assert.match(info,/'profile_id': authority\.profile_id, 'desktop_protocol': CANONICAL_GATEWAY_PROTOCOL/);
const source=await readFile(new URL('../desktop/plugin.js',import.meta.url),'utf8');assert.match(source, /requestProfile\(route, 'commands\.catalog'/);assert.doesNotMatch(source, /'command\.catalog'/);assert.doesNotMatch(source,/prompt\.submit|ask_choice|clarify\.response|openSession\s*\(|refreshInPlace|native-chat-requests/);
console.log('PASS exact pinned SDK profileRoutes + requestProfile + retainProfile execution (inert inventory refresh/cache): descriptor route and backend target remain distinct, UUID-only command payload forwarded unchanged, explicit timeout and lease cleanup; host result/session metadata contract checked. All transport dependencies inert.');
// Opt-in official dependency fixture only. Never install, fetch, or infer a private path here.
const fixture=process.env.HERMES_CRM_NANOSTORES_FIXTURE;
if(!fixture){console.log('SKIP actual nanostores visibility execution: provide HERMES_CRM_NANOSTORES_FIXTURE pointing to a separately verified official 1.4.2 package.');}
else {
  const {createHash,webcrypto}=await import('node:crypto');const {dirname,join}=await import('node:path');const {pathToFileURL}=await import('node:url');
  const integrity='sha512-Wxv8Roefr2nqtiRG0bnaFlpYqpIVtOEeJZHaH+4nGgOK1/7n6OHOuHCb/bhqrNQgZM8fyd0s1PqhdrJc9Ib44g==';
  const verified=JSON.parse(await readFile(join(dirname(fixture),'VERIFIED.json'),'utf8'));
  assert.equal(verified.source,'https://registry.npmjs.org/nanostores/1.4.2');assert.equal(verified.integrity,integrity);
  assert.equal('sha512-'+createHash('sha512').update(await readFile(join(dirname(fixture),'nanostores-1.4.2.tgz'))).digest('base64'),integrity);
  assert.ok(Object.keys(verified.files_sha256).length>20);
  for(const[path,digest]of Object.entries(verified.files_sha256)){assert.ok(!path.includes('..')&&!path.startsWith('/'));assert.equal(createHash('sha256').update(await readFile(join(fixture,path))).digest('hex'),digest);}
  const pkg=JSON.parse(await readFile(join(fixture,'package.json'),'utf8'));assert.equal(pkg.name,'nanostores');assert.equal(pkg.version,'1.4.2');
  const {atom,computed}=await import(pathToFileURL(join(fixture,'index.js')).href);
  const modelText=await readFile(root+'/apps/desktop/src/components/pane-shell/tree/model.ts','utf8');
  const modelContext=vm.createContext({crypto:webcrypto});const modelModule=new vm.SourceTextModule(stripTypeScriptTypes(modelText),{context:modelContext});await modelModule.link(()=>{throw Error('Unexpected model import');});await modelModule.evaluate();const model=modelModule.namespace;
  const pane='plugin-workspace:hermes-crm:chat:1';let tree=model.group(['workspace']);tree=model.insertAtGroup(tree,model.findGroupOfPane(tree,'workspace').id,pane,'right');
  const layout=atom(tree),dismissed=atom(new Set()),hidden=atom(new Set()),collapsed=atom(new Set());
  const storeText=await readFile(root+'/apps/desktop/src/components/pane-shell/tree/store.ts','utf8');
  const groupStart=storeText.indexOf('function paneGroup('), groupEnd=storeText.indexOf('\n}',groupStart)+2;
  const start=storeText.indexOf('export function isPaneVisible('),end=storeText.indexOf('\n/**',storeText.indexOf('export function $paneVisible(',start)+20);
  const visibilitySource=storeText.slice(groupStart,groupEnd)+'\n'+storeText.slice(start,end)+'\nexport const host={'+sdk.match(/  paneVisibility:.*\n/)[0]+'};';
  const visibleContext=vm.createContext({computed,$layoutTree:layout,$dismissedPanes:dismissed,$hiddenTreePanes:hidden,$collapsedTreeSides:collapsed,findGroupOfPane:model.findGroupOfPane,
    // Physical column classification is a layout fixture. Visibility predicate,
    // model lookup/cache/SDK wrapper and actual computed/listen are pinned code.
    treeSideOfPane:id=>id===pane?'right':null});
  const visibleModule=new vm.SourceTextModule(stripTypeScriptTypes(visibilitySource),{context:visibleContext});await visibleModule.link(()=>{throw Error('Unexpected visibility import');});await visibleModule.evaluate();const visibility=visibleModule.namespace.host;
  const main=visibility.paneVisibility('workspace'),companion=visibility.paneVisibility(pane);assert.equal(visibility.paneVisibility(pane),companion);assert.equal(main.get(),true);assert.equal(companion.get(),true);
  const observed=[];const stop=companion.listen(v=>observed.push(v));const stopMain=main.listen(v=>observed.push('main:'+v));
  hidden.set(new Set([pane]));assert.equal(observed.at(-1),false);hidden.set(new Set());assert.deepEqual(observed,[false,true],'Actual non-batched nanostores listener must expose hide→show synchronously');
  dismissed.set(new Set(['workspace']));assert.equal(observed.at(-1),'main:false');dismissed.set(new Set());assert.equal(observed.at(-1),'main:true');
  collapsed.set(new Set(['right']));assert.equal(observed.at(-1),false);collapsed.set(new Set());assert.equal(observed.at(-1),true);
  const group=model.findGroupOfPane(layout.get(),pane);layout.set(model.setGroupMinimized(layout.get(),group.id,true));assert.equal(observed.at(-1),false);layout.set(tree);assert.equal(observed.at(-1),true);
  stop();stopMain();assert.equal(main.lc,0);assert.equal(companion.lc,0);const count=observed.length;hidden.set(new Set([pane]));hidden.set(new Set());assert.equal(observed.length,count);
  await new Promise(r=>setTimeout(r,1100));for(const store of [layout,dismissed,hidden,collapsed])assert.equal(store.lc,0);
  console.log('PASS exact pinned paneVisibility/isPaneVisible/cache + tree model using official integrity-verified nanostores 1.4.2: real synchronous non-batched hide/show, dismissal/collapse/minimize observations, memoized subscription identity and cleanup after native unmount delay. Physical column classification is synthetic; no native windows opened.');
}
// Produce catalog fixtures by executing the exact pinned server catalog builder,
// with inert loaders only. No host/plugin/profile modules or user files import.
const scopedName='crm-assignment-'+ 'a'.repeat(32);
const catalogProgram=String.raw`
import importlib.util,json,sys,types
path=sys.argv[1]+'/tui_gateway/command_discovery.py';name=sys.argv[2]
spec=importlib.util.spec_from_file_location('isolated_catalog_fixture',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module._skill_usage_lookup=lambda:(lambda name:0,lambda name:'local')
def catalog(kind):
    registry=types.SimpleNamespace(COMMAND_REGISTRY=[],SUBCOMMANDS={})
    plugin=types.SimpleNamespace(get_plugin_commands=lambda:{name:{'description':'Synthetic CRM','argument_mode':'text','args_hint':'<operation UUID>'}})
    skills=types.SimpleNamespace(get_interactive_skill_commands=lambda:{('/'+name):{'name':name,'description':'Synthetic collision'}} if kind=='skill' else {})
    def load(module_name):
        if kind=='plugin-error' and module_name=='hermes_cli.plugins':raise RuntimeError('Synthetic discovery failure')
        return {'hermes_cli.commands':registry,'hermes_cli.plugins':plugin,'agent.skill_commands':skills}[module_name]
    quick={name:{'type':kind,'target':'/unrelated','command':'synthetic-only'}} if kind in ('alias','exec') else {}
    return module.command_catalog(load_cfg=lambda:{'quick_commands':quick},module_loader=load)
print(json.dumps({kind:catalog(kind) for kind in ('clean','alias','exec','skill','plugin-error')}))
`;
const catalogs=JSON.parse(execFileSync(process.env.HERMES_CRM_TEST_PYTHON||'python3',['-c',catalogProgram,root,scopedName],{encoding:'utf8',env:{PATH:process.env.PATH,PYTHONDONTWRITEBYTECODE:'1'}}));
const validatorSource=source.slice(source.indexOf('export function validateWorkCommandCatalog('),source.indexOf('export function createWorkCommandController('));
const validator=new vm.SourceTextModule(validatorSource,{context:vm.createContext({})});await validator.link(()=>{throw Error('Unexpected validator import');});await validator.evaluate();
validator.namespace.validateWorkCommandCatalog(catalogs.clean,scopedName);for(const kind of ['alias','exec','skill','plugin-error'])assert.throws(()=>validator.namespace.validateWorkCommandCatalog(catalogs[kind],scopedName),undefined,kind);
console.log('PASS exact pinned command_catalog builder with inert loaders: unique plugin-only entry accepted; same-name quick alias/exec, skill and discovery-error catalog rejected. High-entropy naming plus catalog checks mitigate accidental collisions in trusted operator configuration; they are not owner attestation.');
