// Isolated Workbench structure checks. No live app, provider, account or filesystem dialogs.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
const require = createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React = require('react'), Renderer = require('react-test-renderer');
const {act, createElement: h} = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
async function load(name) {
  const context = vm.createContext({URLSearchParams, TextDecoder, crypto: webcrypto});
  const module = new vm.SourceTextModule(await readFile(new URL(`../desktop/${name}.js`, import.meta.url), 'utf8'), {context});
  await module.link(() => new vm.SyntheticModule(Object.keys(React), function () {
    for (const [key, value] of Object.entries(React)) this.setExport(key, value);
  }, {context}));
  await module.evaluate();
  return module.namespace;
}
const Drawer = ({children}) => h('section', {'aria-label': 'Fixture drawer'}, children);
const text = node => typeof node === 'string' ? node : node?.children?.map(text).join('') || '';
const button = (tree, label) => tree.root.findAllByType('button').find(node => text(node) === label);
const common = {Drawer, workspaceToken: 'fixture-workspace', current: () => true, cancel: () => {}};
let tree, closed = 0;
const {ContactTransferDrawer} = await load('contact-transfer');
await act(async () => { tree = Renderer.create(h(ContactTransferDrawer, {...common, cancel: () => closed++, client: {
  current: () => true, request: async () => ({columns: [{key: 'name', label: 'Name'}], default_columns: ['name']}),
}})); });
const body = tree.root.findByProps({className: 'hc-editor-body hc-transfer-body'});
assert.equal(body.findByProps({type: 'file'}).props.accept, '.csv,text/csv');
assert.equal(body.findAllByType('footer').length, 0, 'Footer must not scroll with CSV rows');
assert.equal(tree.root.findByType('footer').props.className, 'hc-editor-footer hc-transfer-footer');
assert.match(text(body), /CSV is plaintext/);
assert.match(text(body), /Protected notes and keys are never included/);
await act(async () => button(tree, 'Export contacts').props.onClick());
assert.equal(tree.root.findByProps({className: 'hc-transfer-columns'}).type, 'fieldset');
assert.match(text(tree.root), /retained until manually removed/);
assert.equal(button(tree, 'Prepare CSV export').props.disabled, true, 'Consent/capability guard remains intact');
await act(async () => button(tree, 'Close contact transfer').props.onClick());
assert.equal(closed, 1);
await act(async () => tree.unmount());
const {Customization} = await load('customization');
await act(async () => { tree = Renderer.create(h(Customization, {...common, client: {current: () => true}, catalog: {
  stages: [{key: 'incoming', label: 'Incoming', outcome: 'open', version: 1, order: 0}], fields: {contacts: [], deals: [], tasks: []},
}})); });
assert.equal(tree.root.findByProps({className: 'hc-list hc-definition-list'}).children.length, 1);
assert.match(text(tree.root.findByProps({className: 'hc-definition-meta'})), /incoming · open · Version 1/);
await act(async () => button(tree, 'Add stage').props.onClick());
assert.equal(tree.root.findAllByType('label').find(node => text(node).startsWith('Description')).props.className, 'hc-wide');
assert.equal(tree.root.findByProps({className: 'hc-actions hc-definition-actions'}).findByProps({type: 'submit'}).props.className, 'hc-primary');
await act(async () => tree.unmount());
const {ProtectionDrawer} = await load('protection');
await act(async () => { tree = Renderer.create(h(ProtectionDrawer, {...common, record: {kind: 'contacts', id: 'fixture'}, client: {
  current: () => true, request: async path => path.includes('/status') ? {notes_enabled: true, backup_enabled: false} : {record_version: 1, note_version: 0, has_note: false},
}})); });
assert.ok(tree.root.findByProps({className: 'hc-editor-body hc-protection-body'}));
assert.equal(tree.root.findByProps({className: 'hc-evidence-disclosure hc-protection-help'}).type, 'details');
assert.match(text(tree.root), /masking is not encryption/);
assert.match(text(tree.root), /No protected note yet/);
assert.equal(tree.root.findAllByType('textarea').length, 0, 'Presentation must never reveal protected text');
await act(async () => tree.unmount());
const {EmailHistoryPanel, emailHistoryCSS} = await load('email-history');
await act(async () => { tree = Renderer.create(h(EmailHistoryPanel, {...common, routeKey: 'fixture', storageBackend: 'sqlite', contact: {id: 'fixture', version: 1, email: 'person@example.test'}, client: {
  current: () => true, request: async path => path.includes('/contacts/') ? {total: 1, items: [{message_id: 'fixture', labels: ['SENT'], display_headers: {Subject: 'Untrusted subject'}, provenance: {adapter: 'fixture', kind: 'metadata'}}]} : {enabled: true, connected: false, mailbox: null, revision: 0},
}})); });
const evidence = tree.root.findByProps({className: 'hc-email-evidence'});
assert.equal(evidence.type, 'details');
assert.match(text(evidence.findByType('summary')), /Observation provenance/);
assert.match(text(evidence), /not a delivery receipt/);
assert.match(text(tree.root), /gmail.readonly scope can read message bodies/);
assert.match(text(tree.root), /Untrusted subject/);
assert.match(emailHistoryCSS, /color:var\(--hc-secondary\);opacity:1/);
assert.doesNotMatch(emailHistoryCSS, /gradient|box-shadow/);
await act(async () => tree.unmount());
console.log('PASS Workbench settings/transfer/protection/email structure, native disclosures, readable theme tokens and preserved safety controls.');
