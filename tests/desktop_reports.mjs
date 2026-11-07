// Local-only report contract and real React lifecycle tests; no providers or accounts.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { webcrypto } from 'node:crypto';
const require = createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React = require('react'), Renderer = require('react-test-renderer');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const source = await readFile(new URL('../desktop/reports.js', import.meta.url), 'utf8');
const context = vm.createContext({ URLSearchParams, crypto: webcrypto, console });
const module = new vm.SourceTextModule(source, { context });
await module.link(() => new vm.SyntheticModule(['createElement','useEffect','useRef','useState'], function () { for (const key of ['createElement','useEffect','useRef','useState']) this.setExport(key, React[key]); }, { context }));
await module.evaluate();
const { reportSession, reportPreset, reportCleanFilter, reportChartModel, reportCardPayload, reportLineModel, reportSectorPath, FlexibleReports, ReportResult } = module.namespace;
const plain = value => JSON.parse(JSON.stringify(value));
assert.doesNotMatch(source, /dangerouslySetInnerHTML|\bfetch\s*\(|href:|src:|setInterval|localStorage/);
assert.equal(reportPreset('won').filter.value, 'won');
assert.deepEqual(plain(reportPreset('daily').group_by), { field: 'created_at', interval: 'day' });
assert.equal(reportCleanFilter({ all: [] }), null);
assert.deepEqual(plain(reportCleanFilter({ all: [{ any: [] }, { field: 'id', op: 'eq', value: 'x' }] })), { all: [{ field: 'id', op: 'eq', value: 'x' }] });
assert.equal(reportChartModel({ groups: [{ value: 1 }], truncated: true }, 'donut').graphical, false);
assert.equal(reportChartModel({ groups: [{ value: 0 }] }, 'donut').graphical, false);
assert.equal(reportChartModel({ groups: [{ value: null }] }, 'bar').graphical, false);
assert.deepEqual(plain(reportCardPayload({ id: 'c', report_id: 'r', report_version: 1, visualization: 'table', report: { secret: 1 }, reference_status: 'active' })), { id: 'c', report_id: 'r', report_version: 1, visualization: 'table' });
let calls = [], current = true, fail = true;
const client = { current: () => current, async request(path, options) { calls.push({ path, options }); if (fail) throw Error('lost response'); return { id: 'saved', version: 1 }; } };
let session = reportSession(client, 'scope');
const mutable = { title: 'A', definition: { filter: { field: 'stage', op: 'eq', value: 'won' } } };
await assert.rejects(session.write('/analytics/reports', mutable), /unknown/);
mutable.definition.filter.value = 'lost';
calls[0].options.body.definition.filter.value = 'transport mutation';
const key = calls[0].options.body.idempotency_key;
assert.equal(await session.write('/analytics/reports', { title: 'B' }), null);
session.close(); session = reportSession(client, 'scope'); fail = false;
await session.write('/wrong', { title: 'changed' }, true);
assert.equal(calls[1].path, '/analytics/reports');
assert.equal(calls[1].options.body.title, 'A');
assert.equal(calls[1].options.body.definition.filter.value, 'won');
assert.equal(calls[1].options.body.idempotency_key, key);
assert.equal(session.pending(), undefined);
current = false; assert.equal(await session.run(reportPreset('leads')), null); assert.equal(calls.length, 2);
let release; current = true;
client.request = () => new Promise(resolve => { release = resolve; });
const pendingRead = session.read('/analytics/catalog'); session.close(); release({ stale: true }); assert.equal(await pendingRead, null);

const field = (type = 'text', extra = {}) => ({ type, label: 'Field', selectable: true, sortable: true, groupable: true, operators: ['eq','is_null','is_not_null'], ...extra });
const catalog = { entities: { contacts: { label: 'Contacts', fields: { id: field(), name: field(), contact_type: field('text', { choices: ['lead','customer'] }), linked_stages: field('set', { sortable: false, groupable: false, operators: ['has_any','is_empty'], choices: ['won'] }), last_logged_contact_at: field('datetime'), next_followup_at: field('datetime'), created_at: field('datetime'), deal_count: field('integer') } }, deals: { label: 'Deals', fields: { id: field(), stage: field('text', { choices: ['won','lost'] }), value: field('integer') } } }, measures: ['count','sum','avg','min','max'] };
let reports = [], dashboard = { id: null, version: 0, cards: [] }, delayedRun = null;
calls = [];
const uiClient = { current: () => true, async request(path, options) {
  calls.push({ path, options });
  if (path.startsWith('/analytics/catalog')) return catalog;
  if (path.startsWith('/analytics/reports?')) { const params = new URLSearchParams(path.split('?')[1]), offset = Number(params.get('offset')), limit = Number(params.get('limit')); const filtered = reports.filter(record => params.get('include_archived') === 'true' || !record.archived_at); return { items: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit }; }
  if (path.startsWith('/analytics/dashboard') && !options) return dashboard;
  if (path === '/analytics/run') {
    if (delayedRun) return new Promise(resolve => { delayedRun.resolve = resolve; });
    return { definition: options.body.definition, evaluated_at: '2030-01-01T00:00:00Z', total: 0, items: [], units: {} };
  }
  if (/\/analytics\/reports\/[^/]+\/(archive|restore)$/.test(path) && options) { const id = path.split('/')[3], archive = path.endsWith('/archive'); const record = reports.find(item => item.id === id); assert.equal(options.body.expected_version, record.version); Object.assign(record, { version: record.version + 1, archived_at: archive ? '2030-01-01T00:00:00Z' : null }); return record; }
  if (path === '/analytics/reports' && options) { const record = { id: 'report-1', version: 1, title: options.body.title, definition: options.body.definition }; reports = [record]; return record; }
  if (path === '/analytics/dashboard' && options) { dashboard = { ...dashboard, id: 'dashboard-1', version: dashboard.version + 1, cards: options.body.cards.map(card => ({ ...card, reference_status: 'active', report: reports[0] })) }; return dashboard; }
  throw Error(`Unexpected ${path}`);
} };
let tree;
await React.act(async () => { tree = Renderer.create(React.createElement(FlexibleReports, { client: uiClient, workspaceToken: 'w', routeKey: 'one' })); });
const buttons = () => tree.root.findAllByType('button');
const button = text => buttons().find(node => node.children.join('') === text);
await React.act(async () => button('Build a report').props.onClick());
assert.ok(button('Preview live'));
assert.equal(button('Save report').props.disabled, true);
assert.equal(calls.filter(call => call.options).length, 0);
const stalePreset = button('Preset: closed won').props.onClick;
await React.act(async () => button('Preset: leads per day').props.onClick());
await React.act(async () => stalePreset());
assert.ok(JSON.stringify(tree.toJSON()).includes('Leads created per UTC day'));
await React.act(async () => button('Preview live').props.onClick());
assert.equal(button('Save report').props.disabled, false);
const save = button('Save report').props.onClick;
await React.act(async () => { save(); save(); });
assert.equal(calls.filter(call => call.path === '/analytics/reports' && call.options).length, 1);
assert.equal(button('Add saved version to dashboard').props.disabled, true);
await React.act(async () => button('Preview live').props.onClick());
await React.act(async () => button('Add saved version to dashboard').props.onClick());
assert.equal(dashboard.cards.length, 1);
assert.equal(dashboard.cards[0].report_version, 1);
assert.ok(button('Run live'));
// Editing the definition invalidates preview and cannot attach a misleading old version.
const inputs = tree.root.findAllByType('input');
const checkbox = inputs.find(node => node.props.type === 'checkbox' && !node.props['aria-label']);
await React.act(async () => checkbox.props.onChange({ target: { checked: !checkbox.props.checked } }));
await React.act(async () => button('Preview live').props.onClick());
assert.equal(button('Add saved version to dashboard').props.disabled, true);
// Old profile responses cannot populate the new profile or keep its lock held.
delayedRun = {};
let runPromise;
await React.act(async () => { runPromise = button('Preview live').props.onClick(); });
await React.act(async () => tree.update(React.createElement(FlexibleReports, { client: uiClient, workspaceToken: 'other', routeKey: 'two' })));
await React.act(async () => { delayedRun.resolve({ definition: reportPreset('leads'), evaluated_at: 'STALE-PROFILE', items: [], total: 99 }); await runPromise; });
assert.ok(!JSON.stringify(tree.toJSON()).includes('STALE-PROFILE'));
assert.ok(button('Build a report'));
await React.act(async () => tree.unmount());
// A reconnect receives a new route client but shares registration-lifetime uncertainty.
const operationStore = new Map();
let firstClientCalls = 0, replacementCalls = [];
const firstClient = { current: () => true, request: async () => { firstClientCalls++; throw Error('unknown'); } };
let persisted = reportSession(firstClient, 'persisted', () => true, operationStore);
await assert.rejects(persisted.write('/analytics/reports', { title: 'Original', definition: reportPreset('leads') }), /unknown/);
const persistedKey = persisted.pending().bodyJSON;
persisted.close();
const replacement = { current: () => true, request: async (path, options) => { replacementCalls.push({ path, options }); return { id: 'restored', version: 1 }; } };
persisted = reportSession(replacement, 'persisted', () => true, operationStore);
assert.equal(await persisted.write('/analytics/reports', { title: 'New intent' }), null);
assert.equal(replacementCalls.length, 0);
await persisted.write('/ignored', {}, true);
assert.equal(firstClientCalls, 1);
assert.equal(JSON.stringify(replacementCalls[0].options.body), persistedKey);
assert.equal(operationStore.size, 0);
// Saved report browsing supports all pages and explicit reversible versioned archiving.
reports = Array.from({ length: 121 }, (_, index) => ({ id: `paged-${index}`, version: 1, title: `Report ${index}`, definition: reportPreset('leads'), archived_at: index === 120 ? 'archived' : null }));
delayedRun = null; dashboard = { id: null, version: 0, cards: [] };
await React.act(async () => { tree = Renderer.create(React.createElement(FlexibleReports, { client: uiClient, workspaceToken: 'paged', routeKey: 'paged' })); });
assert.ok(button('Next saved reports'));
assert.equal(button('Previous saved reports').props.disabled, true);
await React.act(async () => button('Next saved reports').props.onClick());
assert.ok(button('Report 50 · v1'));
await React.act(async () => button('Next saved reports').props.onClick());
assert.ok(button('Report 119 · v1'));
assert.equal(button('Next saved reports').props.disabled, true);
const showArchived = tree.root.findByProps({ 'aria-label': 'Include archived reports' });
await React.act(async () => showArchived.props.onChange({ target: { checked: true } }));
assert.ok(button('Report 0 · v1'));
assert.equal(button('Previous saved reports').props.disabled, true);
const archive = tree.root.findByProps({ 'aria-label': 'Archive Report 0, version 1' }).props.onClick;
await React.act(async () => { archive(); archive(); });
assert.equal(calls.filter(call => call.path === '/analytics/reports/paged-0/archive').length, 1);
assert.ok(button('Report 0 · v2 · archived'));
await React.act(async () => tree.root.findByProps({ 'aria-label': 'Restore Report 0, version 2' }).props.onClick());
assert.ok(button('Report 0 · v3'));
const archiveRequest = calls.find(call => call.path === '/analytics/reports/paged-0/archive');
assert.equal(archiveRequest.options.body.expected_version, 1);
assert.ok(archiveRequest.options.body.idempotency_key);
await React.act(async () => tree.unmount());
// Untrusted rows are plain text; canonical group drilldown + exact evaluation time passed.
let drillArgs;
await React.act(async () => { tree = Renderer.create(React.createElement(ReportResult, { kind: 'donut', onDrill: (...args) => { drillArgs = args; }, result: { definition: reportPreset('daily'), evaluated_at: 'instant', total: 1, total_groups: 1, truncated: true, groups: [{ key: '<img onerror=evil>', value: 1, count: 1, detail_definition: reportPreset('leads') }] } })); });
assert.equal(tree.root.findAllByProps({ role: 'img' }).length, 0);
await React.act(async () => tree.root.findByType('button').props.onClick());
assert.equal(drillArgs[1], 'instant'); assert.deepEqual(plain(drillArgs[0]), plain(reportPreset('leads')));
await React.act(async () => tree.unmount());
// UTC spacing uses actual elapsed days, independent of input order; invalid/null buckets stay out of the plot.
const dateGroups = [{ key: '2030-01-11', value: 3 }, { key: null, value: 5 }, { key: '2030-01-02', value: 2 }, { key: '2030-01-01', value: 0 }, { key: '2030-02-30', value: 1 }, { key: '2030-01-04', value: null }];
const line = reportLineModel(dateGroups);
assert.deepEqual(plain(line.points.map(point => point.group.key)), ['2030-01-01','2030-01-02','2030-01-11']);
assert.deepEqual(plain(line.points.map(point => point.x)), [15,42,285]);
assert.equal(line.omitted.length, 3);
assert.equal((reportSectorPath(0, 1).match(/A 60/g) || []).length, 2);
for (const kind of ['donut', 'line']) {
  const groups = [{ key: '2030-01-01', value: 2, count: 2, detail_definition: reportPreset('leads'), evaluated_at: 'bucket-instant' }, { key: '2030-01-03', value: 1, count: 1, detail_definition: reportPreset('won') }];
  await React.act(async () => { tree = Renderer.create(React.createElement(ReportResult, { kind, onDrill: (...args) => { drillArgs = args; }, result: { definition: reportPreset('daily'), evaluated_at: 'result-instant', total: 3, total_groups: 2, groups } })); });
  const controls = tree.root.findAllByProps({ role: 'button' });
  assert.equal(controls.length, 2); assert.equal(controls[0].props.tabIndex, 0);
  assert.ok(controls[0].findByType('title').children.join('').includes('2 records'));
  let prevented = false;
  await React.act(async () => controls[0].props.onKeyDown({ key: ' ', preventDefault: () => { prevented = true; } }));
  assert.equal(prevented, true); assert.equal(drillArgs[1], 'bucket-instant');
  await React.act(async () => controls[1].props.onClick());
  assert.deepEqual(plain(drillArgs[0]), plain(reportPreset('won'))); assert.equal(drillArgs[1], 'result-instant');
  await React.act(async () => tree.update(React.createElement(ReportResult, { kind, disabled: true, onDrill: () => { throw Error('Disabled chart activated'); }, result: { definition: reportPreset('daily'), groups } })));
  const disabledControl = tree.root.findAllByProps({ role: 'button' })[0]; assert.equal(disabledControl.props.tabIndex, -1);
  await React.act(async () => disabledControl.props.onClick());
  await React.act(async () => tree.unmount());
}
console.log('desktop reports: session, idempotency, typed forms, saved versions, stale handlers, profile races, charts and drilldown passed');
