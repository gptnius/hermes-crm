// Real React lifecycle + pinned public SDK/layout contracts. No live Electron QA.
// HERMES_SOURCE=/path/to/2bd378e node --experimental-vm-modules tests/native_desktop_chat.mjs
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire, stripTypeScriptTypes } from 'node:module';
import { execFileSync } from 'node:child_process';
import { webcrypto } from 'node:crypto';
import vm from 'node:vm';
const require = createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React = require('react'), Renderer = require('react-test-renderer'), { act } = React;
assert.equal(React.version, '19.3.0');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const source = await readFile(new URL('../desktop/plugin.js', import.meta.url), 'utf8');
assert.doesNotMatch(source, /host\.composer\.(?:getDraft|setDraft|insertText|submit|focus)\s*\(|host\.(?:openSession|newChat|request)\s*\(|\bfetch\s*\(/);
function atom(value) {
  const listeners = new Set();
  return { get: () => value, set(next) { if (Object.is(value, next)) return; value = next; for (const fn of [...listeners]) fn(); },
    listen(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }, listeners };
}
const flatten = node => typeof node === 'string' || typeof node === 'number' ? String(node) : Array.isArray(node) ? node.map(flatten).join(' ') : node?.children ? flatten(node.children) : '';
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
async function load(code, values, context = vm.createContext({ console, Intl, URLSearchParams, crypto: webcrypto })) {
  const mod = new vm.SourceTextModule(code, { context });
  await mod.link(specifier => {
    const exports = values[specifier]; assert.ok(exports, `Unexpected import ${specifier}`);
    return new vm.SyntheticModule(Object.keys(exports), function () { for (const [k, v] of Object.entries(exports)) this.setExport(k, v); }, { context });
  });
  await mod.evaluate(); return mod.namespace;
}
let pinnedOpenWorkspace = null, model = null;
const pinned = process.env.HERMES_SOURCE;
if (pinned) {
  assert.equal(execFileSync('git', ['-C', pinned, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), '2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19');
  const sdk = await readFile(`${pinned}/apps/desktop/src/sdk/index.ts`, 'utf8');
  const method = sdk.slice(sdk.indexOf('  openWorkspace: ('), sdk.indexOf('  /** Name a workspace owner', sdk.indexOf('  openWorkspace: (')));
  assert.ok(method.includes('options.dock ??'));
  pinnedOpenWorkspace = stripTypeScriptTypes(`export const host = { ${method} };`);
  model = await load(stripTypeScriptTypes(await readFile(`${pinned}/apps/desktop/src/components/pane-shell/tree/model.ts`, 'utf8')), {});
  // Execute the pinned focused-ID derivation, rather than guessing native
  // pane names. Chrome focus retains the prior tile's stored identity.
  const activeGroup = atom('main'), layoutTree = atom(model.group(['workspace', 'session-tile:draft-A'], { id: 'main', active: 'session-tile:draft-A' }));
  const focus = await load(stripTypeScriptTypes(await readFile(`${pinned}/apps/desktop/src/store/session-focus.ts`, 'utf8')), {
    nanostores: { atom, computed(inputs, fn) { const stores = Array.isArray(inputs) ? inputs : [inputs]; return { get: () => fn(...stores.map(store => store.get())) }; } },
    '@/components/pane-shell/tree/model': { findGroup: model.findGroup, findGroupOfPane: model.findGroupOfPane },
    '@/components/pane-shell/tree/store': { $activeTreeGroup: activeGroup, $layoutTree: layoutTree },
    '@/components/pane-shell/workspace-scope': { $workspaceMode: atom('sessions') },
    './session': { $selectedStoredSessionId: atom('stored-main') },
  });
  assert.equal(focus.TILE_PANE_PREFIX, 'session-tile:');
  assert.equal(focus.$focusedStoredSessionId.get(), 'draft-A');
  console.log('PASS actual pinned focused native tile identity derivation.');
  // Execute the actual pinned composer SDK with a deferred host bus to expose
  // the primary-target race, rather than assuming insertText is an atomic append.
  const active = atom('runtime-A'), selected = atom('stored-A'), states = atom({ 'runtime-A': { storedSessionId: 'stored-A' } });
  const pending = [], drafts = { 'stored-A': 'unsent A', 'stored-B': 'unsent B' };
  const composer = await load(stripTypeScriptTypes(await readFile(`${pinned}/apps/desktop/src/sdk/composer.ts`, 'utf8')), {
    '@/app/chat/composer/focus': {
      requestComposerFocus() {}, requestComposerGetDraft: async () => null,
      requestComposerSetDraft: async () => false, requestComposerSubmit: () => false,
      requestComposerInsertAcked(text, options) { return new Promise(resolve => pending.push(() => { drafts[selected.get()] += text; resolve(options.target); })); },
    },
    '@/store/composer': { freshDraftScope: () => 'fresh', takeSessionDraft: () => ({ text: '' }) },
    '@/store/session': { $activeSessionId: active, $selectedStoredSessionId: selected },
    '@/store/session-states': { $sessionStates: states },
  });
  const insert = composer.composerHost.insertText('stored-A', ' CRM reference');
  selected.set('stored-B'); active.set('runtime-B'); pending[0]();
  assert.equal(await insert, 'main'); assert.equal(drafts['stored-A'], 'unsent A');
  assert.equal(drafts['stored-B'], 'unsent B CRM reference');
  const draftSource = await readFile(`${pinned}/apps/desktop/src/app/chat/composer/hooks/use-composer-draft.ts`, 'utf8');
  const append = draftSource.slice(draftSource.indexOf('  const appendExternalText = useCallback('), draftSource.indexOf('  // Keep-alive tabs keep this composer mounted.'));
  let painted; const mirror = { current: 'saved text' };
  const appendModule = await load(stripTypeScriptTypes(`${append}\nexport { appendExternalText };`), {}, vm.createContext({
    useCallback: fn => fn, draftRef: mirror, paintDraft: text => { painted = text; },
  }));
  appendModule.appendExternalText('CRM reference', 'block');
  assert.equal(painted, 'saved text\n\nCRM reference', 'The pinned append uses the mirror, not independently newer live input');
  console.log('PASS actual pinned SDK composer routing/draft-race reproduction; UI never calls its write/send paths.');
} else console.log('SKIP pinned source contract: set HERMES_SOURCE to the verified checkout.');
async function fixture({ old = false, ignoreDock = false, noClipboard = false } = {}) {
  const state = { profile: atom('work'), connectionId: atom('source-a'), gateway: atom('open'), cwd: atom('/synthetic'),
    activeSessionId: atom('runtime-A'), focusedSessionId: atom('runtime-A'), focusedStoredSessionId: atom('stored-A'),
    focusedSessionOwner: atom({ connectionId: 'source-a', profile: 'work' }) };
  const epoch = atom(1), disposers = [], timers = new Set(), intervals = new Set(), copies = [], calls = [], navigation = [];
  const tiles = new Set();
  const panes = new Map(), closers = new Map(); let currentTab = 'workspace', opens = 0, removals = 0, movedToCenter = false;
  let tree = model?.group(['workspace']);
  const reveal = id => { currentTab = id; if (model && model.findGroupOfPane(tree, id)) tree = model.setActivePane(tree, model.findGroupOfPane(tree, id).id, id); };
  const visible = id => model ? model.findGroupOfPane(tree, id)?.active === id : panes.has(id) ? (!(ignoreDock || movedToCenter) || currentTab === id) : (id === 'workspace' || tiles.has(id)) && (!(ignoreDock || movedToCenter) || currentTab === id);
  const env = { state, epoch, disposers, timers, intervals, copies, calls, navigation, panes, closers,
    get opens() { return opens; }, get removals() { return removals; }, get tree() { return tree; },
    addTile(id) { tiles.add(id); if (model) tree = model.insertAtGroup(tree, model.findGroupOfPane(tree, "workspace").id, id, "center"); reveal(id); },
    copyGate: null, readGate: null, relationshipVersion: 1, token: 'workspace-secret-not-for-chat', version: 3,
    moveToCenter(id) { if (model) { tree = model.removePane(tree, id); tree = model.insertAtGroup(tree, model.findGroupOfPane(tree, 'workspace').id, id, 'center'); } else movedToCenter = true; },
  };
  const host = { state, navigate(path) { navigation.push(path); }, revealPane: reveal, paneVisibility: id => ({ get: () => visible(id) }),
    composer: new Proxy({}, { get() { throw Error('No composer reads or writes are allowed'); } }),
  };
  if (pinnedOpenWorkspace) {
    const actual = await load(pinnedOpenWorkspace, {}, vm.createContext({
      registry: { register(value) {
        opens++; panes.set(value.id, value);
        if (model && !model.findGroupOfPane(tree, value.id)) tree = model.insertAtGroup(tree, model.findGroupOfPane(tree, value.data.dock.pane).id, value.id, ignoreDock ? 'center' : value.data.dock.pos);
        return () => panes.delete(value.id);
      } },
      registerPaneCloser(id, fn) { if (fn) closers.set(id, fn); else closers.delete(id); },
      revealTreePane: reveal,
      removeTreePane(id) { removals++; if (model) tree = model.removePane(tree, id); },
    }));
    host.openWorkspace = actual.host.openWorkspace;
  } else host.openWorkspace = (id, options) => {
    opens++; movedToCenter = false; const paneId = `plugin-workspace:${id}`; panes.set(paneId, options); reveal(paneId);
    const close = () => { panes.delete(paneId); closers.delete(paneId); removals++; options.onClose(); }; closers.set(paneId, close); return close;
  };
  if (old) delete host.openWorkspace;
  const useValue = a => React.useSyncExternalStore(a.subscribe, a.get, a.get);
  const sdk = { host, atom, useValue, gatewayActivationEpoch: epoch.get, useGatewayActivationEpoch: () => useValue(epoch),
    PANES_AREA: 'panes', ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'sidebar.nav', PALETTE_AREA: 'palette' };
  const ctx = { onDispose(fn) { disposers.push(fn); }, registerMany() {},
    setTimeout(fn) { const handle = setTimeout(() => { timers.delete(handle); fn(); }, 1); timers.add(handle); return () => { clearTimeout(handle); timers.delete(handle); }; },
    setInterval(fn) { intervals.add(fn); return () => intervals.delete(fn); },
    os: noClipboard ? {} : { async writeClipboard(text) { copies.push(text); return env.copyGate ? env.copyGate.promise : true; } },
    async rest(path, options) {
      assert.equal(options, undefined, 'Handoff is read-only'); calls.push(path);
      const row = { id: 'c1', name: 'Ada Example', email: 'private@example.com', company: 'Private company', title: 'Owner', lifecycle: 'lead', notes: 'PRIVATE RECORD NOTES', version: env.version };
      if (path === '/snapshot') return { meta: { workspace_token: env.token, backend: 'sqlite', profile: state.profile.get() }, contacts: [row], deals: [], tasks: [], activity: [],
        overview: { contacts: 1, open_deals: 0, pipeline_value: 0, weighted_value: 0, overdue_tasks: 0, stages: [], tasks: [], activity: [] } };
      if (path.startsWith('/contacts/c1?')) return env.readGate ? env.readGate.promise : { contact: row, deals: [], tasks: [], activity: [] };
      if (path.startsWith('/contacts/c1/company?')) return { contact_id: 'c1', contact_version: env.version, company_id: 'co1', company_name: 'Linked Company' };
      if (path.startsWith('/companies/co1?')) return { id: 'co1', name: 'Linked Company', version: env.relationshipVersion };
      if (path.startsWith('/events/e1?')) return { id: 'e1', title: 'Linked Event', version: env.relationshipVersion, kind: 'call', status: 'scheduled', starts_at: '2027-01-02T12:00:00Z', ends_at: '2027-01-02T13:00:00Z', timezone: 'UTC' };
      const linkedTask = { id: 't1', title: 'Linked Task', version: 1, status: 'open', due_at: '2027-01-03T12:00:00Z', priority: 'normal', schedule_status: 'not_scheduled' };
      const paged = items => ({ items, total: 51, limit: 25, offset: Number(new URLSearchParams(path.split('?')[1]).get('offset') || 0) });
      if (path.startsWith('/tasks/t1?')) return linkedTask;
      if (path.startsWith('/companies?')) return paged([{ id: 'co1', name: 'Linked Company' }]);
      if (path.startsWith('/events?') || path.startsWith('/companies/co1/records/events?')) return paged([{ id: 'e1', title: 'Linked Event' }]);
      if (path.startsWith('/companies/co1/records/tasks?') || path.startsWith('/events/e1/tasks?')) return paged([linkedTask]);
      if (path.startsWith('/companies/co1/') || path.startsWith('/events/e1/') || path.startsWith('/relationship-activities?') || path.startsWith('/contacts/c1/relationship-tasks?')) return { items: [], total: 0, limit: 25, offset: 0 };
      if (path.startsWith('/reports/contacts?')) return { items: [row], total: 1, limit: 50, offset: 0 };
      throw Error(`Unexpected read ${path}`);
    },
  };
  const mod = await load(source, { '@hermes/plugin-sdk': sdk, react: React }); mod.default.register(ctx);
  let root;
  const flush = async () => { await act(async () => { await new Promise(resolve => setTimeout(resolve, 5)); }); };
  env.mount = async (element = React.createElement(mod.CRMRoot, { ctx })) => { await act(async () => { root = Renderer.create(React.createElement(React.StrictMode, null, element)); }); await flush(); };
  env.unmount = async () => { if (root) await act(async () => { root.unmount(); root = null; }); };
  env.button = title => root.root.findAllByType('button').find(node => flatten(node.children) === title);
  env.click = async title => { const target = env.button(title); assert.ok(target, `Missing button ${title}`); assert.notEqual(target.props.disabled, true, `Disabled button ${title}`); await act(async () => { target.props.onClick(); }); await flush(); };
  env.text = () => flatten(root.toJSON()); env.root = () => root;
  env.openRecord = async () => { await env.click('Contacts'); const target = root.root.findAllByType('button').find(node => flatten(node.children).includes('Ada Example')); assert.ok(target); await act(async () => { target.props.onClick(); }); await flush(); };
  env.change = async fn => { await act(async () => fn()); await flush(); };
  env.finish = async () => { await env.unmount(); for (const fn of disposers) fn(); assert.equal(timers.size, 0); assert.equal(intervals.size, 0); for (const a of Object.values(state)) assert.equal(a.listeners.size, 0); };
  Object.assign(env, { mod, ctx, host, flush }); return env;
}
// Public split controller: one dock, correct primary route, no session mutation.
{
  const e = await fixture(), identity = e.mod.routeIdentity(e.ctx);
  const binding = e.mod.openChatWorkspace(e.ctx, identity, () => null);
  assert.equal(binding.pane, 'workspace'); assert.equal(e.navigation[0], '/stored-A');
  assert.equal(e.state.activeSessionId.get(), 'runtime-A'); assert.equal(e.opens, 1);
  if (model) assert.equal(e.tree.type, 'split');
  e.mod.openChatWorkspace(e.ctx, identity, () => null); assert.equal(e.opens, 1);
  const lifetimePane = [...e.panes.keys()][0];
  // Closing via host and reopening cannot leave an older plugin disposer live.
  e.closers.get(lifetimePane)(); assert.equal(e.panes.size, 0);
  e.mod.openChatWorkspace(e.ctx, identity, () => null); assert.equal(e.opens, 2);
  e.moveToCenter(lifetimePane);
  assert.throws(() => e.mod.openChatWorkspace(e.ctx, identity, () => null), /visible together/);
  assert.equal(e.panes.size, 0); assert.equal(e.navigation.length, 3);
  e.mod.openChatWorkspace(e.ctx, identity, () => null);
  e.state.profile.set('other'); assert.equal(e.panes.size, 0); assert.equal(binding.current(), false);
  await e.finish();
}
// An activation can change only the SDK epoch while source/profile strings stay
// equal. The stale dock must be replaced, not forever re-front its bound render.
{
  const e = await fixture();
  const oldIdentity = e.mod.routeIdentity(e.ctx), oldRender = () => 'old';
  e.mod.openChatWorkspace(e.ctx, oldIdentity, oldRender);
  e.epoch.set(2);
  const newIdentity = e.mod.routeIdentity(e.ctx), newRender = () => 'new';
  assert.notEqual(oldIdentity, newIdentity);
  e.mod.openChatWorkspace(e.ctx, newIdentity, newRender);
  assert.equal(e.opens, 2); assert.equal(e.removals, 1); assert.equal(e.panes.size, 1);
  assert.equal([...e.panes.values()][0].render, newRender);
  await e.finish();
}
for (const mutation of [
  e => e.state.focusedSessionId.set('tile-runtime'), e => e.state.activeSessionId.set(null),
  e => e.state.focusedStoredSessionId.set(null), e => e.state.focusedSessionOwner.set(null),
  e => e.state.focusedSessionOwner.set({ connectionId: 'source-b', profile: 'work' }),
  e => e.state.focusedSessionOwner.set({ connectionId: 'source-a', profile: 'other' }),
]) {
  const e = await fixture(); mutation(e);
  assert.throws(() => e.mod.openChatWorkspace(e.ctx, e.mod.routeIdentity(e.ctx), () => null));
  assert.equal(e.opens, 0); assert.equal(e.navigation.length, 0); await e.finish();
}
// Pre-send and saved secondary tabs share the same verified native pane.
// Layout never promotes a tile, authorizes context, touches drafts or sends.
for (const stored of ['draft-A', 'saved-secondary-A']) {
  const e = await fixture();
  e.state.focusedSessionId.set('tile-runtime'); e.state.focusedStoredSessionId.set(stored);
  e.addTile(`session-tile:${stored}`);
  const identity = e.mod.routeIdentity(e.ctx), before = e.calls.length;
  assert.throws(() => e.mod.captureChatBinding(e.ctx, identity), /main Hermes chat/);
  const layout = e.mod.openChatWorkspace(e.ctx, identity, () => null);
  assert.equal(layout.pane, `session-tile:${stored}`); assert.equal(layout.route, null);
  assert.equal(layout.sessionId, undefined); assert.equal(layout.profile, undefined);
  assert.equal(e.navigation.length, 0); assert.equal(e.calls.length, before);
  assert.equal(e.state.activeSessionId.get(), 'runtime-A');
  e.mod.openChatWorkspace(e.ctx, identity, () => null); assert.equal(e.opens, 1);
  e.closers.get([...e.panes.keys()][0])();
  e.mod.openChatWorkspace(e.ctx, identity, () => null); assert.equal(e.opens, 2);
  e.state.gateway.set('closed'); e.state.gateway.set('open');
  assert.equal(e.panes.size, 0); assert.equal(layout.current(), false);
  await e.finish();
}
// Closing/hiding a tile inside a synchronous host callback must not resurrect it.
{
  const e = await fixture(), tile = 'session-tile:draft-A';
  e.state.focusedSessionId.set('tile-runtime'); e.state.focusedStoredSessionId.set('draft-A'); e.addTile(tile);
  const open = e.host.openWorkspace, visibility = e.host.paneVisibility, reveal = e.host.revealPane;
  let hidden = false, tileReveals = 0;
  e.host.paneVisibility = id => id === tile && hidden ? { get: () => false } : visibility(id);
  e.host.revealPane = id => { if (id === tile) tileReveals++; reveal(id); };
  e.host.openWorkspace = (...args) => { const close = open(...args); hidden = true; return close; };
  assert.throws(() => e.mod.openChatWorkspace(e.ctx, e.mod.routeIdentity(e.ctx), () => null), /no longer visible/);
  assert.equal(tileReveals, 0); assert.equal(e.panes.size, 0); assert.equal(e.navigation.length, 0);
  await e.finish();
}
// Hidden-at-start tiles are never revealed or recreated.
{
  const e = await fixture(), tile = 'session-tile:draft-A';
  e.state.focusedSessionId.set('tile-runtime'); e.state.focusedStoredSessionId.set('draft-A'); e.addTile(tile);
  const visibility = e.host.paneVisibility;
  e.host.paneVisibility = id => id === tile ? { get: () => false } : visibility(id);
  assert.throws(() => e.mod.openChatWorkspace(e.ctx, e.mod.routeIdentity(e.ctx), () => null), /not visible/);
  assert.equal(e.opens, 0); assert.equal(e.navigation.length, 0); await e.finish();
}
// Real React opens a secondary draft layout and retains the selected CRM record.
{
  const e = await fixture();
  e.state.focusedSessionId.set('tile-runtime'); e.state.focusedStoredSessionId.set('draft-A'); e.addTile('session-tile:draft-A');
  await e.mount(); await e.openRecord();
  const calls = e.calls.length;
  await e.click('Chat with Hermes');
  assert.match(e.text(), /existing native chat tab is beside CRM/);
  assert.equal(e.calls.length, calls); assert.equal(e.navigation.length, 0); assert.equal(e.copies.length, 0);
  const pane = [...e.panes.values()][0]; await e.unmount(); await e.mount(pane.render());
  assert.match(e.text(), /Ada Example/);
  assert.equal(e.root().root.findAll(n => n.props['aria-label'] === 'Record details').length, 1);
  await e.click('Preview record reference');
  assert.match(e.text(), /Open an existing conversation in the main Hermes chat/);
  assert.equal(e.copies.length, 0); assert.equal(e.navigation.length, 0);
  await e.finish();
}
// A true blank main has no safe identity; never manufacture a session.
{
  const e = await fixture();
  for (const key of ['activeSessionId', 'focusedSessionId', 'focusedStoredSessionId']) e.state[key].set(null);
  assert.throws(() => e.mod.openChatWorkspace(e.ctx, e.mod.routeIdentity(e.ctx), () => null), /blank main draft/);
  assert.equal(e.opens, 0); assert.equal(e.navigation.length, 0); assert.equal(e.calls.length, 0);
  await e.finish();
}
// Selection can change in the same tick inside the host layout callback.
{
  const e = await fixture(), open = e.host.openWorkspace;
  e.host.openWorkspace = (...args) => { const close = open(...args); e.state.focusedStoredSessionId.set('other'); return close; };
  assert.throws(() => e.mod.openChatWorkspace(e.ctx, e.mod.routeIdentity(e.ctx), () => null), /selected chat changed/);
  assert.equal(e.panes.size, 0); assert.equal(e.navigation.length, 0); await e.finish();
}
for (const key of ['profile', 'connectionId', 'gateway', 'cwd', 'focusedSessionId', 'focusedStoredSessionId', 'focusedSessionOwner']) {
  const e = await fixture(), bound = e.mod.captureChatBinding(e.ctx, e.mod.routeIdentity(e.ctx)), original = e.state[key].get();
  e.state[key].set(key === 'focusedSessionOwner' ? { connectionId: 'b', profile: 'work' } : 'different'); e.state[key].set(original);
  assert.equal(bound.current(), false, `${key} ABA invalidates context`); await e.finish();
}
{
  const e = await fixture(), bound = e.mod.captureChatBinding(e.ctx, e.mod.routeIdentity(e.ctx)); e.epoch.set(2); assert.equal(bound.current(), false); await e.finish();
}
// Context is a single validated reference, never a transcript, record dump or
// workspace capability. This holds for contacts, opportunities and follow-ups.
{
  const e = await fixture(), binding = e.mod.captureChatBinding(e.ctx, e.mod.routeIdentity(e.ctx));
  const data = { meta: { workspace_token: 'secret-scope' } };
  for (const kind of ['contacts', 'deals', 'tasks']) {
    const row = { id: 'record-1', version: 9, email: 'hidden@example.com', notes: 'hidden note', payload: { prompt: 'hidden assignment' } };
    const detail = { kind, workspaceToken: 'secret-scope', row: kind === 'contacts' ? { contact: row, deals: [{ id: 'other-record' }] } : row };
    const text = e.mod.recordChatContext(detail, data, binding);
    assert.match(text, /"id": "record-1"/); assert.match(text, /"version": 9/);
    assert.doesNotMatch(text, /hidden|other-record|secret-scope/);
    for (const version of [0, -1, 1.5, '9']) {
      const changed = { ...detail, row: { ...row, version } };
      assert.equal(e.mod.recordChatContext(changed, data, binding), null);
    }
    assert.equal(e.mod.recordChatContext({ ...detail, workspaceToken: 'old' }, data, binding), null);
    assert.equal(e.mod.recordChatContext({ ...detail, kind: 'arbitrary' }, data, binding), null);
    assert.equal(e.mod.recordChatContext({ ...detail, row: { id: 'bad\\nID', version: 1 } }, data, binding), null);
  }
  await e.finish();
}
for (const options of [{ old: true }, { ignoreDock: true }]) {
  const e = await fixture(options); await e.mount(); await e.click('Chat with Hermes');
  assert.match(e.text(), /cannot safely open|could not keep/); assert.equal(e.navigation.length, 0); assert.equal(e.panes.size, 0); await e.finish();
}
// Real React state survives relocation, forms never silently relocate, and
// selected-record context is scoped, fresh, minimum data, and user-initiated.
{
  const e = await fixture(); await e.mount(); await e.openRecord();
  await e.click('Edit'); assert.equal(e.button('Chat with Hermes').props.disabled, true);
  const input = e.root().root.findAllByType('input').find(n => n.props.name === 'name');
  await e.change(() => input.props.onChange({ target: { value: 'Unsaved contact' } }));
  const blocked = e.button('Chat with Hermes'); await e.change(() => blocked.props.onClick());
  assert.equal(e.navigation.length, 0); assert.equal(input.props.value, 'Unsaved contact');
  await e.click('Cancel'); assert.ok(e.button('Discard changes')); await e.click('Discard changes'); await e.click('Chat with Hermes');
  const pane = [...e.panes.values()][0]; assert.ok(pane);
  await e.unmount(); await e.mount(pane.render());
  assert.match(e.text(), /Ada Example/); assert.equal(e.root().root.findAll(n => n.props['aria-label'] === 'Record details').length, 1);
  await e.click('Preview record reference');
  const preview = e.root().root.findByProps({ 'aria-label': 'Record reference to copy' });
  assert.equal(preview.props.readOnly, true); assert.match(preview.props.value, /"id": "c1"/);
  assert.doesNotMatch(preview.props.value, /private@example|Private company|PRIVATE RECORD|workspace-secret|runtime-A/);
  assert.equal(e.copies.length, 0);
  await e.click('Copy record reference'); assert.equal(e.copies.length, 1);
  assert.match(e.text(), /not attached or sent/); assert.equal(e.navigation.length, 1);
  assert.match(e.calls.at(-1), /\/contacts\/c1\?workspace_token=workspace-secret/);
  e.version = 4; await e.click('Copy record reference'); assert.equal(e.copies.length, 1); assert.match(e.text(), /record changed/);
  e.version = 3; e.readGate = deferred(); const copier = e.button('Copy record reference').props.onClick;
  await e.change(() => { copier(); copier(); });
  assert.equal(e.button('Checking record…').props.disabled, true);
  const copiesBefore = e.copies.length;
  await e.change(() => { e.state.cwd.set('/other'); e.state.cwd.set('/synthetic'); });
  await e.change(() => e.readGate.resolve({ contact: { id: 'c1', version: 3 } }));
  assert.equal(e.copies.length, copiesBefore); assert.match(e.text(), /scope changed/);
  await e.finish();
}
// Relocating a linked Company/Event retains only its identity, then fetches a fresh record.
for (const [kind, target, title] of [['companies', 'co1', 'Linked Company · co1'], ['events', 'e1', 'Linked Event']]) {
  const e = await fixture(); await e.mount(); await e.openRecord();
  await e.click(title);
  assert.ok(e.button(kind === 'companies' ? 'Edit Company' : 'Edit Event'));
  await e.click('Chat with Hermes');
  const pane = [...e.panes.values()][0]; assert.ok(pane);
  await e.unmount();
  const previousReads = e.calls.filter(path => path.startsWith(`/${kind}/${target}?`)).length;
  e.relationshipVersion = 9;
  await e.mount(pane.render());
  assert.ok(e.button(kind === 'companies' ? 'Edit Company' : 'Edit Event'), 'Exact selected record survives relocation');
  assert.ok(e.calls.filter(path => path.startsWith(`/${kind}/${target}?`)).length > previousReads, 'Relocated record is reread');
  assert.match(e.text(), /Version 9/);
  await e.click('Back to Contacts');
  assert.equal(e.root().root.findAll(n => n.props['aria-label'] === 'Record details').length, 1);
  await e.click('Close');
  assert.equal(e.root().root.findAll(n => n.props['aria-label'] === 'Record details').length, 0);
  await e.finish();
}
// Every relationship-table selection joins the same root history, with list and child-table pages retained.
{
  const e = await fixture(); await e.mount(); await e.click('Companies');
  const panel = () => e.root().root.findByProps({ 'aria-label': 'Companies and relationship events' });
  await e.change(() => panel().findAllByType('input').find(node => node.props.type !== 'checkbox').props.onChange({ target: { value: 'Acme' } }));
  await e.change(() => panel().findAllByType('input').find(node => node.props.type === 'checkbox').props.onChange({ target: { checked: true } }));
  await e.click('Next page');
  await e.click('Linked Company');
  const taskTable = panel().findAllByType('section').find(node => node.findAllByType('h3').length === 1 && flatten(node.findByType('h3').children) === 'tasks');
  await e.change(() => taskTable.findAllByType('button').find(node => flatten(node.children) === 'Next page').props.onClick());
  await e.click('Linked Task');
  await e.click('Chat with Hermes'); const pane = [...e.panes.values()][0]; await e.unmount(); await e.mount(pane.render());
  await e.click('Close');
  assert.ok(e.button('Edit Company'), 'Task Close returns exact parent Company after split relocation');
  assert.equal(new URLSearchParams(e.calls.findLast(path => path.startsWith('/companies/co1/records/tasks?')).split('?')[1]).get('offset'), '25');
  await e.click('Close');
  let params = new URLSearchParams(e.calls.findLast(path => path.startsWith('/companies?')).split('?')[1]);
  assert.equal(params.get('q'), 'Acme'); assert.equal(params.get('include_archived'), 'true'); assert.equal(params.get('offset'), '25');
  assert.equal(e.button('Close'), undefined, 'List has no stale record Close');
  await e.click('Linked Company');
  const staleTaskLink = e.button('Linked Task').props.onClick;
  await e.click('Edit Company');
  await e.change(() => panel().findAllByType('input')[0].props.onChange({ target: { value: 'Dirty Company' } }));
  assert.equal(e.button('Back to companies').props.disabled, true);
  await e.change(() => staleTaskLink());
  assert.ok(e.root().root.findAllByType('form').length, 'Old link cannot discard an open relationship form');
  await e.click('Cancel'); await e.click('Keep editing'); await e.click('Cancel'); await e.click('Discard changes');
  await e.click('Close');
  await e.finish();
}
// Both current and retained Chat handlers must honor the live relationship-form lock.
for (const [entry, edit, dirty] of [['Linked Company · co1', 'Edit Company', 'Unsaved Company name'], ['Linked Event', 'Edit Event', 'Unsaved Event title']]) {
  const e = await fixture(); await e.mount(); await e.openRecord(); await e.click(entry);
  const staleChat = e.button('Chat with Hermes').props.onClick;
  await e.click(edit);
  const textInput = () => e.root().root.findByType('form').findAllByType('input').find(node => node.props.type !== 'datetime-local' && node.props.value !== 'UTC');
  await e.change(() => textInput().props.onChange({ target: { value: dirty } }));
  assert.equal(e.button('Chat with Hermes').props.disabled, true);
  const reads = e.calls.length;
  await e.change(() => { staleChat(); e.button('Chat with Hermes').props.onClick(); });
  assert.equal(e.opens, 0); assert.equal(e.navigation.length, 0); assert.equal(e.panes.size, 0);
  assert.equal(e.calls.length, reads, 'Blocked Chat handlers perform no transport calls');
  assert.equal(textInput().props.value, dirty, 'Blocked relocation preserves the exact unsaved input');
  await e.click('Cancel'); await e.click('Keep editing'); assert.equal(textInput().props.value, dirty);
  await e.click('Cancel'); await e.click('Discard changes');
  await e.click('Chat with Hermes'); assert.equal(e.opens, 1, 'Chat remains available after explicit discard');
  await e.finish();
}
// Contact → Company → Event → Task follows every parent, including after split relocation.
{
  const e = await fixture(); await e.mount(); await e.openRecord();
  await e.click('Linked Company · co1'); await e.click('Linked Event');
  // Repeated current-target callback adds no extra entry.
  const openCurrent = e.root().root.findAll(node => typeof node.type === 'function' && node.type.name === 'Relationships')[0].props.navigateRecord;
  await e.change(() => openCurrent('events', 'e1'));
  await e.click('Chat with Hermes'); const pane = [...e.panes.values()][0]; await e.unmount(); await e.mount(pane.render());
  assert.ok(e.button('Edit Event'));
  await e.click('Linked Task'); await e.click('Close'); assert.ok(e.button('Edit Event'));
  await e.click('Close'); assert.ok(e.button('Edit Company'));
  await e.click('Close'); assert.equal(e.root().root.findAllByProps({ 'aria-label': 'Record details' }).length, 1);
  await e.click('Close'); assert.equal(e.root().root.findAllByProps({ 'aria-label': 'Record details' }).length, 0);
  await e.finish();
}
// Event-list query/status/kind and pagination also survive child navigation.
{
  const e = await fixture(); await e.mount(); await e.click('Events');
  const panel = () => e.root().root.findByProps({ 'aria-label': 'Companies and relationship events' });
  await e.change(() => panel().findByType('input').props.onChange({ target: { value: 'Call' } }));
  await e.change(() => panel().findAllByType('select')[0].props.onChange({ target: { value: 'scheduled' } }));
  await e.change(() => panel().findAllByType('select')[1].props.onChange({ target: { value: 'call' } }));
  await e.click('Next page'); await e.click('Linked Event'); await e.click('Linked Task'); await e.click('Close'); await e.click('Close');
  const params = new URLSearchParams(e.calls.findLast(path => path.startsWith('/events?')).split('?')[1]);
  assert.equal(params.get('q'), 'Call'); assert.equal(params.get('status'), 'scheduled'); assert.equal(params.get('kind'), 'call'); assert.equal(params.get('offset'), '25');
  await e.finish();
}
// Compact context is useful without expanding the preview; nothing copies on
// selection, hiding, or reopening. Copy always revalidates the selected version.
{
  const e = await fixture(); await e.mount(); await e.openRecord();
  assert.equal(e.root().root.findAllByType('textarea').length, 0);
  assert.equal(e.button('Preview record reference').props['aria-expanded'], false);
  assert.equal(e.copies.length, 0);
  await e.click('Copy record reference');
  assert.equal(e.copies.length, 1);
  assert.equal(e.root().root.findAllByType('textarea').length, 0);
  assert.match(e.calls.at(-1), /\/contacts\/c1\?workspace_token=/);
  assert.match(e.text(), /not attached or sent/);
  await e.click('Preview record reference');
  assert.equal(e.button('Hide preview').props['aria-expanded'], true);
  assert.equal(e.root().root.findByProps({ 'aria-label': 'Record reference to copy' }).props.rows, 5);
  await e.click('Hide preview');
  assert.equal(e.root().root.findAllByType('textarea').length, 0);
  assert.equal(e.copies.length, 1);
  await e.click('Preview record reference'); await e.click('Close'); await e.openRecord();
  assert.equal(e.root().root.findAllByType('textarea').length, 0);
  assert.equal(e.copies.length, 1);
  await e.finish();
}
// Stale rendered callbacks cannot act after synchronous Close/Edit even when
// React has not committed a render yet. Closing/reopening preserves selection.
{
  const e = await fixture(); await e.mount(); await e.openRecord(); await e.click('Preview record reference');
  const copy = e.button('Copy record reference').props.onClick, close = e.button('Close').props.onClick;
  const reads = e.calls.length;
  await e.change(() => { close(); copy(); });
  assert.equal(e.calls.length, reads); assert.equal(e.copies.length, 0);
  await e.openRecord();
  const handoff = e.button('Chat with Hermes').props.onClick, edit = e.button('Edit').props.onClick;
  await e.change(() => { edit(); handoff(); });
  assert.equal(e.navigation.length, 0); assert.equal(e.root().root.findAllByType('form').length, 1);
  await e.click('Cancel'); await e.click('Chat with Hermes');
  const [id, pane] = [...e.panes.entries()][0];
  await e.unmount(); await e.mount(pane.render());
  await e.unmount(); e.closers.get(id)(); await e.mount();
  assert.match(e.text(), /Ada Example/); assert.equal(e.root().root.findAll(n => n.props['aria-label'] === 'Record details').length, 1);
  await e.finish();
}
// Pending validation is dropped on selection/record/scope change or disposal.
for (const change of ['record', 'profile', 'source', 'reconnect', 'unmount', 'token']) {
  const e = await fixture(); await e.mount(); await e.openRecord(); await e.click('Preview record reference');
  e.readGate = deferred(); await e.click('Copy record reference');
  if (change === 'record') await e.click('Close');
  else if (change === 'profile') await e.change(() => e.state.profile.set('other'));
  else if (change === 'source') await e.change(() => e.state.connectionId.set('source-b'));
  else if (change === 'reconnect') await e.change(() => { e.state.gateway.set('closed'); e.state.gateway.set('open'); });
  else if (change === 'token') { e.token = 'replacement-workspace'; await e.click('Refresh'); }
  else await e.unmount();
  await e.change(() => e.readGate.resolve({ contact: { id: 'c1', version: 3 } }));
  assert.equal(e.copies.length, 0, `${change} stale copy is dropped`); await e.finish();
}
{
  const e = await fixture({ noClipboard: true }); await e.mount(); await e.openRecord(); await e.click('Preview record reference');
  assert.equal(e.button('Copy record reference').props.disabled, true); assert.match(e.text(), /select and copy the preview manually/); await e.finish();
}
console.log('PASS native chat split lifecycle, primary-only routing, unsupported SDK/docking fallback, retained CRM record/form protection, minimum explicit context, live version/token/source checks, ABA/reconnect/disposal, duplicate clicks, no draft access or submission. SDK transport is a fixture; pinned SDK method/model executed when HERMES_SOURCE is set.');
