// Synthetic native Storage component and SDK navigation checks. No host/network.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const require = createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React = require('react'), Renderer = require('react-test-renderer');
const {act, createElement: h} = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const context = vm.createContext({URLSearchParams});
const module = new vm.SourceTextModule(await readFile(new URL('../desktop/storage-settings.js', import.meta.url), 'utf8'), {context});
await module.link(() => new vm.SyntheticModule(Object.keys(React), function () {
  for (const [key,value] of Object.entries(React)) this.setExport(key,value);
}, {context}));
await module.evaluate();
const {StorageSettings, storageSettingsHref, validateStorageStatus} = module.namespace;
assert.equal(storageSettingsHref(() => '/settings?tab=plugins','work & team'), '/settings?tab=plugins&profile=work+%26+team');
assert.equal(storageSettingsHref(undefined, 'work'), null);
assert.equal(storageSettingsHref(() => 'https://wrong.invalid/settings?tab=plugins','work'), null);
assert.equal(storageSettingsHref(() => '/settings?tab=other','work'), null);
assert.throws(() => validateStorageStatus({backend: 'postgres', configuration:'configured',selection_token:'secret'}));
const token = 'a'.repeat(64), calls = [], navigation = [];
let backend='sqlite', alive=true, blocked=false, resolvePending, mode='', tree;
const client = {current: () => alive, async request(path, options) {
  calls.push([path, options]);
  if (blocked) return new Promise(resolve => {resolvePending = resolve;});
  if (mode === 'fail') throw new Error('postgresql://secret@private.invalid/database');
  if (path === '/storage/status') return {backend, configuration:'configured',selection_token:token, ignored_secret:'never-render'};
  return {backend, selection_token:token, result:'connected',readiness_checked:false};
}};
const props = {client,profile:'work',canOpenHostSettings:true,openHostSettings:() => {navigation.push('settings'); return true;}};
const flatten = node => typeof node === 'string' ? node : node?.children?.map(flatten).join('') || '';
const text = () => flatten(tree.root);
const button = label => tree.root.findAllByType('button').find(node => flatten(node) === label);
async function mount(extra={}) { await act(async () => {tree=Renderer.create(h(React.StrictMode,null,h(StorageSettings,{...props,...extra})));}); }
async function click(label) {await act(async () => {button(label).props.onClick();});}
await mount();
assert.match(text(), /SQLite · local to this gateway and profile/);
assert.match(text(), /does not migrate, upload, merge or delete/);
assert.match(text(), /Masking is not encryption/);
assert.doesNotMatch(text(), /never-render/);
assert.equal(tree.root.findAllByType('input').length,0);
assert.equal(tree.root.findAllByType('details').length,1);
assert.ok(calls.every(([path, options]) => path === '/storage/status' && !options));
assert.equal(calls.filter(([path]) => path === '/storage/check').length,0,'Opening does not probe');
await click('Check saved connection');
assert.match(text(), /Connection succeeded/);
assert.match(text(), /not CRM schema readiness/);
assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))), ['/storage/check',{method:'POST',body:{selection_token:token}}]);
backend='postgres'; await click('Reload storage settings');
assert.match(text(), /PostgreSQL · user-managed database/);
assert.doesNotMatch(text(), /Connection succeeded/);
await click('Open Hermes plugin settings'); assert.equal(navigation.length,1);
await click('Reload storage settings');
// Repeated click race is locked synchronously; closing discards its late result.
blocked=true;
const oldCheck=button('Check saved connection').props.onClick;
await act(async()=>{oldCheck(); oldCheck();});
assert.equal(calls.filter(([path])=>path==='/storage/check').length,2);
await act(async()=>tree.unmount());
await act(async()=>resolvePending({backend,selection_token:token,result:'connected',readiness_checked:false}));
blocked=false;
await mount();
mode='fail';await click('Check saved connection');
assert.match(text(),/check could not be confirmed/);
assert.doesNotMatch(text(),/postgresql:\/\/secret|private\.invalid/);
assert.equal(button('Check saved connection').props.disabled,true);
mode='';await click('Reload storage settings');
// A stale handler from an old profile cannot dispatch after host invalidation.
const stale=button('Check saved connection').props.onClick, before=calls.length;
alive=false;await act(async()=>stale());assert.equal(calls.length,before);
await act(async()=>tree.unmount());alive=true;
// Bad/missing backend status never hides the supported Settings recovery route.
mode='fail';await mount({canOpenHostSettings:false});
assert.match(text(),/Open Hermes Settings → Plugins manually/);
assert.match(text(),/configuration could not be loaded/);
assert.equal(button('Open Hermes plugin settings').props.disabled,true);
assert.doesNotMatch(text(),/private\.invalid/);
await act(async()=>tree.unmount());
// A pending status request must not trap the user away from host settings.
mode=''; blocked=true; await mount();
assert.equal(button('Open Hermes plugin settings').props.disabled,false);
await click('Open Hermes plugin settings'); assert.equal(navigation.length,2);
await act(async()=>tree.unmount());
await act(async()=>resolvePending({backend:'sqlite',configuration:'configured',selection_token:token}));
console.log('PASS Storage settings: explicit-only probes, scope guards, safe SDK handoff, cleanup, redaction and recovery.');
