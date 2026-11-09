// Actual React 19.3.0 lifecycle/component tests, with an explicit Hermes SDK fixture.
// Setup (test dependencies only; never shipped with the plugin):
// npm install --prefix /tmp/hermes-crm-desktop-test --cache /tmp/hermes-crm-npm-cache --ignore-scripts --no-audit --no-fund react@19.3.0 react-test-renderer@19.3.0
// Run: node --experimental-vm-modules tests/native_desktop_react.mjs
// Override HERMES_CRM_REACT_TEST_ROOT to use another test dependency directory.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { webcrypto } from "node:crypto";
const require = createRequire(
  `${process.env.HERMES_CRM_REACT_TEST_ROOT || "/tmp/hermes-crm-desktop-test"}/package.json`,
);
const React = require("react");
const Renderer = require("react-test-renderer");
const { act } = React;
assert.equal(React.version, "19.3.0");
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
function atom(initial) {
  let value = initial;
  const listeners = new Set();
  return {
    get: () => value,
    set(next) {
      value = next;
      for (const fn of listeners) fn();
    },
    listen(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    listeners,
  };
}
const profile = atom("work"),
  connection = atom("source-a"),
  gateway = atom("open"),
  epoch = atom(1);
const useValue = (value) =>
  React.useSyncExternalStore(value.subscribe, value.get, value.get);
const host = {
  state: { profile, connectionId: connection, gateway },
  navigate() {},
};
const sdk = {
  atom,
  host,
  useValue,
  gatewayActivationEpoch: epoch.get,
  useGatewayActivationEpoch: () => useValue(epoch),
  PANES_AREA: "panes",
  ROUTES_AREA: "routes",
  SIDEBAR_NAV_AREA: "sidebar.nav",
  PALETTE_AREA: "palette",
};
const source = await readFile(
  new URL("../desktop/plugin.js", import.meta.url),
  "utf8",
);
const context = vm.createContext({
  console,
  Intl,
  URLSearchParams,
  crypto: webcrypto,
});
const module = new vm.SourceTextModule(source, { context });
await module.link((specifier) => {
  const values = specifier === "@hermes/plugin-sdk" ? sdk : React;
  return new vm.SyntheticModule(
    Object.keys(values),
    function () {
      for (const [key, value] of Object.entries(values))
        this.setExport(key, value);
    },
    { context },
  );
});
await module.evaluate();
const contact = {
  id: "c1",
  name: "Ada Example",
  company: "",
  email: "",
  title: "",
  lifecycle: "lead",
  notes: "",
  version: 3,
};
const task = {
  id: "t1",
  title: "Follow up",
  due_at: "2027-01-02T12:00:27.123456+00:00",
  contact_id: "c1",
  deal_id: null,
  priority: "normal",
  status: "open",
  notes: "",
  schedule_status: "scheduled",
  version: 4,
};
const deal = { id: "d1", title: "Example opportunity", contact_id: "c1", value: 25000,
  currency: "USD", stage: "proposal", probability: 50, close_date: "2027-02-01", notes: "A real linked note", version: 2 };
const relatedDeals = [], activityRows = [];
const overview = {
  contacts: 1,
  open_deals: 0,
  pipeline_value: 0,
  weighted_value: 0,
  won_value: 0,
  open_tasks: 1,
  overdue_tasks: 0,
  stages: ["lead", "qualified", "proposal", "negotiation", "won", "lost"].map(
    (stage) => ({ stage, count: 0, value: 0 }),
  ),
  tasks: [task],
  activity: [],
};
const writes = [],
  calls = [],
  timers = new Set(),
  intervals = new Set();
let backendTokenSuffix = "",
  backendKind = "sqlite";
let workspaceSeeded = true;
let reportTotal = 1;
let snapshotError = "", testCatalog, testOwnerPolicy;
let delayReport = false, releaseReport;
let delayDetail = false,
  releaseDetail;
let delayTaskDetail = false;
const releaseTaskDetails = [];
let workRows = [], workError = "", delayWork = false, releaseWork;
let companyMissing = false;
let createdEvent = null, companyArchived = false, contactFailureStatus = 0;
let taskFailureStatus = 0, taskReceiptPatch = null;
let writeError = "", delayWrite = false, releaseWrite;
const pluginDisposers = [];
const ctx = {
  onDispose(fn) {
    pluginDisposers.push(fn);
  },
  registerMany() {},
  async rest(path, options) {
    calls.push({ path, profile: profile.get(), connection: connection.get() });
    if (path === "/snapshot" && snapshotError) throw new Error(snapshotError);
    if (options) {
      writes.push({ path, options, profile: profile.get() });
      if (writeError) throw Object.assign(new Error(writeError), taskFailureStatus ? {status:taskFailureStatus} : {});
      if (delayWrite) return new Promise(resolve => { releaseWrite = resolve; });
      if (path === "/events") { createdEvent = {...options.body.data,id:'event-created',version:1,status:'scheduled'}; return createdEvent; }
      if (path === '/relationship-contacts' && contactFailureStatus) throw Object.assign(new Error('Company changed'), {status:contactFailureStatus});
      if (path === "/relationship-contacts") return {contact:{...contact,version:1},company_link:{contact_id:contact.id,contact_version:1,company_id:options.body.company_id,company_link_basis:options.body.company_id ? 'explicit' : 'unlinked'}};
      if (path === "/tasks" || path.startsWith("/tasks/")) return {owner_label:null,owner_source:null,...task, ...options.body.data, version:(options.body.data.version || 0)+1, ...taskReceiptPatch};
      return options.method === "POST" && ["/contacts", "/tasks", "/deals"].includes(path) ? { id: path === "/contacts" ? "c1" : path === "/tasks" ? "t1" : "d1" } : {};
    }
    if (path.startsWith('/events/event-created?')) return createdEvent;
    if (path.startsWith('/events?') || path.startsWith('/relationship-selectors/') || path.startsWith('/relationship-activities?') || path.startsWith('/companies/co1/records/') || path.startsWith('/events/event-created/tasks?')) return {items:[],total:0};
    if (path.startsWith('/companies/co1?') && companyMissing) throw Object.assign(new Error('Original Company removed'),{status:404});
    if (path.startsWith('/companies/co2?')) return {id:'co2',name:'Other Company',version:1};
    if (path.startsWith('/companies/co2/records/')) return {items:[],total:0};
    if (path.startsWith("/companies?")) return {items:[{id:"co1",name:"Exact Company",version:1},{id:'co2',name:'Other Company',version:1}],total:2};
    if (path.startsWith("/reports/work?")) {
      if (workError) throw new Error(workError);
      if (delayWork) return new Promise(resolve => { releaseWork = resolve; });
    }
    if (path.split("?")[0] === "/contacts/c1" && delayDetail)
      return new Promise((resolve) => {
        releaseDetail = resolve;
      });
    if (path.split("?")[0] === "/tasks/t1" && delayTaskDetail)
      return new Promise(resolve => releaseTaskDetails.push(resolve));
    if (path.startsWith("/reports/contacts?") && delayReport) return new Promise(resolve => { releaseReport = resolve; });
    const routes = {
      "/meta": {
        ...(testCatalog ? {catalog:testCatalog} : {}),
        ...(testOwnerPolicy ? {task_owner_policy:testOwnerPolicy} : {}),
        backend: backendKind,
        demo: workspaceSeeded,
        profile: profile.get(),
        workspace_token: `token-${profile.get()}${backendTokenSuffix}`,
      },
      "/task-owner-policy": testOwnerPolicy || {version:0,required:false,default_owner_label:null,legacy_edit_rule:"owner_required_on_edit"},
      "/overview": overview,
      "/contacts": profile.get() === "work" ? [contact] : [],
      "/reports/contacts": { items: profile.get() === "work" ? [{ ...contact, deal_stages: ["lead", "won"] }] : [], total: profile.get() === "work" ? reportTotal : 0, limit: 50, offset: 0 },
      "/deals": relatedDeals,
      "/deals/d1": deal,
      "/tasks": [task],
      "/activity": activityRows,
      "/contacts/c1/company": { contact_id: "c1", contact_version: contact.version, company_id: "co1", company_name: "Exact Company" },
      "/companies/co1": { id: "co1", name: "Exact Company", version: 1, archived_at:companyArchived ? "2026-01-01" : null },
      "/contacts/c1": { contact, deals: relatedDeals, tasks: [task], activity: activityRows },
      "/contacts/outside": { contact: {...contact, id: "outside", name: "Fresh outside contact"}, deals: [], tasks: [], activity: activityRows },
      "/tasks/t1": task,
      "/work": workRows,
      "/work-operations": { items: [], total: 0, limit: 25, offset: Number(new URLSearchParams(path.split("?")[1]).get("offset") || 0), workspace_token: `token-${profile.get()}${backendTokenSuffix}`, profile: profile.get(), task_id: task.id, observed_at: "2026-11-07T13:00:00Z" },
      "/reports/work": { items: workRows, total: workRows.length, limit: 25, offset: Number(new URLSearchParams(path.split("?")[1]).get("offset") || 0), observed_at: "2026-11-06T13:00:00+00:00" },
      "/reports/coverage": { items: [], total: 0, limit: 50, offset: 0, workspace_token: `token-${profile.get()}${backendTokenSuffix}`, observed_at: "2026-11-06T13:00:00+00:00" },
    };
    const value =
      path === "/snapshot"
        ? Object.fromEntries(
            Object.entries(routes)
              .filter(([key]) => !key.slice(1).includes("/"))
              .map(([key, item]) => [key.slice(1), item]),
          )
        : routes[path.split("?")[0]];
    if (path !== "/snapshot")
      assert.equal(
        new URLSearchParams(path.split("?")[1]).get("workspace_token"),
        `token-${profile.get()}${backendTokenSuffix}`,
      );
    assert.notEqual(value, undefined, `Unexpected route ${path}`);
    return structuredClone(value);
  },
  setTimeout(fn) {
    const timer = setTimeout(() => {
      timers.delete(timer);
      fn();
    }, 0);
    timers.add(timer);
    return () => {
      clearTimeout(timer);
      timers.delete(timer);
    };
  },
  setInterval(fn) {
    intervals.add(fn);
    return () => intervals.delete(fn);
  },
};
module.namespace.default.register(ctx);
// Minimal element refs let actual React effects exercise focus ownership and
// keyboard boundaries. This is DOM behavior modeled with refs, not pixel QA.
const focusLog = [];
const mockDocument = { activeElement: null };
function focusable(name) {
  return { name, isConnected: true, closest: () => null,
    focus() { mockDocument.activeElement = this; focusLog.push(name); } };
}
const opener = focusable("opener");
mockDocument.activeElement = opener;
let drawerNode;
function createNodeMock(element) {
  if (element.props.className === "hermes-crm-native") return { ownerDocument: mockDocument };
  if (element.props.className === "hc-drawer") {
    const close = focusable("drawer-close"), firstInput = focusable("first-input"), save = focusable("save");
    drawerNode = { ...focusable("drawer"), ownerDocument: mockDocument, controls: [close, firstInput, save],
      querySelector: () => firstInput, querySelectorAll: () => [close, firstInput, save] };
    return drawerNode;
  }
  if (element.type === "form") return { querySelector: selector => focusable(selector) };
  return focusable(element.type);
}
let root;
await act(async () => {
  root = Renderer.create(
    React.createElement(
      React.StrictMode,
      null,
      React.createElement(module.namespace.CRMRoot, { ctx }),
    ),
    { createNodeMock },
  );
});
const flatten = (node) =>
  typeof node === "string" || typeof node === "number"
    ? String(node)
    : Array.isArray(node)
      ? node.map(flatten).join(" ")
      : node?.children
        ? flatten(node.children)
        : "";
const text = () => flatten(root.toJSON());
const button = (title) =>
  root.root
    .findAllByType("button")
    .find((node) => flatten(node.children) === title);
const flush = async () => {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 15));
  });
};
const click = async (title) => {
  const target = button(title);
  assert.ok(target, `Missing button ${title}`);
  await act(async () => {
    mockDocument.activeElement = opener;
    target.props.onClick();
  });
  await flush();
};
assert.match(text(), /Overview/);
assert.match(text(), /Weighted forecast/);
assert.equal(intervals.size, 1, "Strict Mode replay leaves one live interval");
// Settings is a normal native route: local-only, no Contact prerequisite or extra poller.
const settingsWriteStart=writes.length;
await click('Settings');
assert.match(text(), /Workspace settings/);assert.match(text(), /no mailbox connection or email synchronization/);
assert.equal(button('Verify existing connection'), undefined);
assert.equal(writes.length,settingsWriteStart);assert.equal(intervals.size,1);
assert.equal(calls.filter(call=>/\/email(?:-bridge)?\//.test(call.path)).length, 0, 'Core edition never reads or polls provider routes');
assert.equal(button('Edit contact email aliases'),undefined);
await click('Overview');assert.match(text(),/Weighted forecast/);
// Dashboard rows distinguish task ownership from saved agent intent and read exact tasks.
assert.match(text(), /Upcoming Tasks/);
assert.doesNotMatch(text(), /Up next/);
assert.match(text(), /Task owner \(human\): Not recorded/);
assert.match(text(), /Agent work: Unavailable/);
assert.doesNotMatch(text(), /Agent executor: Hermes/); // Reminder scheduling is not assigned work.
overview.tasks = [{...task, title:'Cached dashboard title', contact_name:'Linked contact outside cache', linked_contact_id:'outside', due_at:'2000-01-01T00:00:00Z', priority:'high', agent_work:{status:'available',total:0,items:[]}}];
await click('Refresh');
assert.equal(button('Cached dashboard title').props.className, 'hc-link-button hc-task-title');
assert.match(text(), /Agent work: None saved/);
assert.match(text(), /Overdue/);
assert.match(text(), /High priority/);
assert.ok(button('Contact: Linked contact outside cache'));
const beforeUpcomingWrites = writes.length;
task.notes = 'Fresh task notes retained';
await click('Cached dashboard title');
assert.ok(calls.some(call => call.path === '/tasks/t1?workspace_token=token-work'));
assert.match(text(), /Fresh task notes retained/);
assert.match(flatten(root.root.findByProps({className:'hc-record'}).children), /Follow up/);
assert.equal(writes.length, beforeUpcomingWrites);
await click('Close');
task.notes = '';
overview.tasks[0].agent_work = {status:'available',total:5,items:[
  {id:'w1',executor:'Hermes',human_owner:'A real owner',state:'pending',source_task_current:true},
  {id:'w2',executor:'Hermes',human_owner:'Former owner',state:'cancelled',source_task_current:false},
  {id:'w3',executor:'Hermes',human_owner:'Other owner',state:'unknown',source_task_current:true},
]};
await click('Refresh');
assert.match(text(), /Agent executor: Hermes · Human owner \(agent work\): A real owner · Saved, not scheduled/);
assert.match(text(), /Cancelled intent; schedule status not checked · Earlier task version/);
assert.match(text(), /Scheduling outcome unknown/);
assert.match(text(), /5 saved assignments; latest 3 shown/);
const validAssignmentSummary = overview.tasks[0].agent_work;
const validAssignmentItem = validAssignmentSummary.items[0];
for (const malformed of [
  {total:1,items:[null]}, {total:-1,items:[]}, {total:1,items:[]}, {total:0,items:[validAssignmentItem]},
  ...[{human_owner:{}},{human_owner:' '},{source_task_current:undefined},{executor:'Made-up agent'},
    {state:'constructor'},{state:'__proto__'},{state:'unrecognized'}].map(patch => ({total:1,items:[{...validAssignmentItem,...patch}]})),
]) {
  overview.tasks[0].agent_work = {status:'available',...malformed};
  await click('Refresh');
  assert.match(text(), /Agent work: Unavailable/);
  assert.doesNotMatch(text(), /Agent work: None saved|Agent executor: Hermes|\[object Object\]/);
}
overview.tasks[0].agent_work = validAssignmentSummary;
await click('Refresh');
delayTaskDetail = true;
await click('Cached dashboard title');
await click('Overview');
await act(async()=>releaseTaskDetails.shift()({...task, notes:'Late navigation record'}));
assert.equal(root.root.findAllByProps({className:'hc-record'}).length, 0);
assert.doesNotMatch(text(), /Late navigation record/);
await click('Cached dashboard title');
await click('Cached dashboard title');
await act(async()=>releaseTaskDetails.shift()({...task, notes:'Older repeated click'}));
assert.equal(root.root.findAllByProps({className:'hc-record'}).length, 0);
await act(async()=>releaseTaskDetails.shift()({...task, notes:'Latest repeated click'}));
assert.match(text(), /Latest repeated click/);
assert.doesNotMatch(text(), /Older repeated click/);
await click('Close');
await click('Cached dashboard title');
await click('Cancel loading');
await act(async()=>releaseTaskDetails.shift()({...task, notes:'Cancelled task read'}));
assert.equal(root.root.findAllByProps({className:'hc-record'}).length, 0);
await click('Cached dashboard title');
await act(async()=>releaseTaskDetails.shift()({...task, id:'wrong-id', notes:'Wrong task response'}));
assert.equal(root.root.findAllByProps({className:'hc-record'}).length, 0);
assert.match(text(), /task could not be verified/);
delayTaskDetail = false;
overview.tasks = [task];
await click('Refresh');
assert.equal(writes.length, beforeUpcomingWrites);
// Verified activity links do not depend on the capped contact snapshot.
const auditRows = Array.from({length: 7}, (_, i) => ({id: `audit-${i}`, summary: `Audit summary ${i}`, actor: 'Human', action: 'updated', created_at: '2026-11-07T13:00:00Z', linked_contact_id: 'outside', linked_contact_name: 'Ada Example', link_basis: 'current_relationship'}));
auditRows[1].linked_contact_id = '../bad';
auditRows[2].link_basis = null;
auditRows[3].linked_contact_name = {};
auditRows[4].linked_contact_id = null;
overview.activity = auditRows;
activityRows.push(...auditRows);
await click('Refresh');
assert.match(text(), /Recent record history/);
assert.match(text(), /Audit summary 4/);
assert.equal(root.root.findAll(node => node.type === "div" && /^Audit summary \d$/.test(flatten(node.children))).length, 5);
assert.doesNotMatch(text(), /Audit summary 5/);
assert.equal(root.root.findAllByType('button').filter(n => flatten(n.children).startsWith('Current contact:')).length, 1);
assert.equal(button('Current contact: Ada Example').props.className, 'hc-link-button');
assert.equal(root.root.findAllByProps({className:'hc-activity-meta'}).length, 5);
assert.ok(root.root.findAllByProps({className:'hc-activity-meta'}).every(node => node.findAllByType('button').length === 0));
const beforeActivityWrites = writes.length;
await click('Current contact: Ada Example');
assert.ok(calls.some(call => call.path.startsWith('/contacts/outside?')));
assert.match(text(), /Fresh outside contact/);
assert.ok(text().indexOf('Recent CRM activity') < text().indexOf('Upcoming follow-ups'));
assert.match(text(), /Older record history \(2 available\)/);
assert.match(text(), /older history may not be included/);
assert.match(text(), /Audit summary 6/);
assert.equal(writes.length, beforeActivityWrites);
await click('Close');
await click('View record history');
assert.match(text(), /Audit summary 6/);
overview.activity = [];
activityRows.length = 0;
await click('Overview');
await click('Refresh');
// Catalog refresh failures are distinct from an unknown mutation outcome.
testCatalog = {schema_version:1, stages:[{key:'lead',label:'Incoming',outcome:'open',probability:40,order:0,color:'#123456',version:1,archived:false}, ...['open','done','all'].map((key,i)=>({key,label:`Deal ${key}`,outcome:'open',probability:20,order:i+1,color:'#123456',version:1,archived:false}))],fields:{contacts:[],deals:[],tasks:[]}};
await click('Refresh');
await click('Tasks');
assert.deepEqual(root.root.findByProps({'aria-label':'Task status'}).findAllByType('option').map(node=>flatten(node.children)), ['Open','Done','All']);
for (const method of ['POST','PATCH']) {
  await click('Customize');
  if (method === 'POST') await click('Add stage');
  else await act(async()=>root.root.findAllByType('button').find(node=>flatten(node.children).startsWith('Incoming')).props.onClick());
  const definitionField = name => root.root.findAllByType('label').find(node=>node.findAllByType('span').some(span=>flatten(span.children)===name)).findAll(node=>['input','select','textarea'].includes(node.type))[0];
  if (method === 'POST') {
    await act(async()=>definitionField('Label').props.onChange({target:{value:'New stage'}}));
    await act(async()=>definitionField('Internal key').props.onChange({target:{value:'new_stage'}}));
  }
  const before = writes.length;
  snapshotError = 'Snapshot unavailable';
  await act(async()=>root.root.findByProps({'aria-label':'Definition editor'}).props.onSubmit({preventDefault(){}}));
  await flush();
  assert.equal(writes.length,before+1);
  assert.equal(writes.at(-1).options.method,method);
  assert.match(text(), /Your changes were saved, but the latest catalog could not be loaded/);
  assert.equal(definitionField('Label').props.disabled,true);
  assert.equal(button('Retry exact save'),undefined);
  await click('Refresh saved catalog');
  assert.equal(writes.length,before+1,'refresh retry never resends confirmed mutation');
  assert.match(text(), /Your changes were saved/);
  snapshotError = '';
  testCatalog.stages[0].version++;
  await click('Refresh saved catalog');
  assert.equal(root.root.findAllByProps({'aria-label':'Definition editor'}).length,0);
  assert.equal(writes.length,before+1);
  await click('Close');
}
testCatalog = undefined;
writes.length = 0;
await click('Refresh');
await click('Overview');
// Every section uses a compact title; descriptions and routine help live in
// an accessible information drawer instead of taking record viewport space.
for (const title of ['Overview', 'Contacts', 'Pipeline', 'Tasks', 'Record history']) {
  await click(title);
  assert.equal(flatten(root.root.findByType('h1').children), title);
  const header = root.root.findByProps({ className: 'hc-row hc-workspace-header' });
  assert.equal(header.findAllByType('p').length, 0);
  assert.doesNotMatch(text(), /synthetic|demo data|sample data/);
  assert.equal(header.findAllByProps({ className: 'hc-eyebrow' }).length, 0);
  await click('ⓘ');
  const dialog = root.root.findByProps({ role: 'dialog' });
  assert.equal(dialog.props['aria-label'], `About ${title}`);
  assert.equal(dialog.props['aria-modal'], true);
  assert.equal(root.root.findByProps({ className: 'hc-wrap' }).props.inert, true);
  assert.match(text(), /Active app profile: work/);
  assert.match(text(), /HermesCRM · Intelligent Relationship Management/);
  assert.match(text(), /Workspace provenance: this workspace was seeded with synthetic records/);
  for (const name of ["Test workspace setup", "Prepare test records", "Add test records"]) {
    assert.equal(button(name), undefined, "Existing provenance does not expose a seed action");
  }
  assert.equal(root.root.findAllByProps({ 'aria-label': 'Close information' }).length, 1);
  mockDocument.activeElement = drawerNode.controls[2];
  let trapped = false;
  await act(async () => dialog.props.onKeyDown({ key: 'Tab', preventDefault() { trapped = true; } }));
  assert.equal(trapped, true); assert.equal(mockDocument.activeElement, drawerNode.controls[0]);
  await act(async () => dialog.props.onKeyDown({ key: 'Escape', preventDefault() {}, stopPropagation() {} }));
  assert.equal(root.root.findAllByProps({ role: 'dialog' }).length, 0);
  assert.equal(mockDocument.activeElement, opener);
  await click('ⓘ'); await click('Close');
  assert.equal(root.root.findAllByProps({ role: 'dialog' }).length, 0);
}
await click('Overview');
// Chart geometry, distinct counts, accessible focus/hover, zero and single-stage cases.
assert.match(text(), /No deal value to chart/);
assert.equal(module.namespace.badge(0).props.children, "0", "Zero-count stages and related records remain visible");
const chartRows = module.namespace.stageChartRows([{ stage: "lead", value: 30000, count: 3, contact_count: 1 }, { stage: "won", value: 10000, count: 1, contact_count: 1 }]);
assert.equal(chartRows.total, 40000);
assert.equal(chartRows.rows[0].share, .75);
assert.equal(chartRows.rows[0].contact_count, 1, "Do not equate deals with unique contacts");
assert.equal(module.namespace.dollarFilter("12.34"), "1234");
assert.equal(module.namespace.dollarFilter("0.01"), "1");
assert.throws(() => module.namespace.dollarFilter("1.001"));
let chart;
const selected = [];
await act(async () => { chart = Renderer.create(React.createElement(module.namespace.StageChart, { stages: chartRows.rows, onStage: stage => selected.push(stage) })); });
assert.equal(chart.root.findAllByType("circle").length, 2);
let segment = chart.root.findAllByType("circle")[0];
assert.equal(segment.props.strokeDasharray, "75 25");
await act(async () => segment.props.onFocus());
assert.match(flatten(chart.toJSON()), /75.0% · 3 deals · 1 distinct contacts/);
await act(async () => segment.props.onMouseEnter());
await act(async () => segment.props.onKeyDown({ key: "Enter", preventDefault() {} }));
assert.equal(selected.at(-1), "lead");
await act(async () => chart.root.findAllByType("button")[4].props.onClick());
assert.equal(selected.at(-1), "won");
await act(async () => chart.update(React.createElement(module.namespace.StageChart, { stages: [{ stage: "lost", value: 42, count: 1, contact_count: 1 }], onStage: stage => selected.push(stage) })));
assert.equal(chart.root.findAllByType("circle")[0].props.strokeDasharray, "100 0");
await act(async () => chart.unmount());
// Presets clear unrelated filters and retain scoped transport and exact server totals.
await click("Contacts");
const control = name => root.root.findAll(node => node.props["aria-label"] === name && ["input", "select"].includes(node.type))[0];
await act(async () => control("Legacy company text").props.onChange({ target: { value: "unrelated" } }));
await flush();
await click("Overview");
await act(async () => root.root.findAllByType("button").find(node => node.props["aria-label"]?.startsWith("Lead:")).props.onClick());
await flush();
let reportParams = new URLSearchParams(calls.findLast(call => call.path.startsWith("/reports/contacts?")).path.split("?")[1]);
assert.equal(reportParams.get("stage"), "lead");
assert.equal(reportParams.get("company"), null);
assert.equal(reportParams.get("workspace_token"), "token-work");
assert.match(text(), /Linked deal stages/);
assert.match(text(), /Lead, Won/);
assert.equal(root.root.findAllByProps({ className: "hc-table" }).length, 1);
assert.doesNotMatch(text(), /Lifecycle/);
reportTotal = 101;
await click("Refresh");
await click("Next");
reportParams = new URLSearchParams(calls.findLast(call => call.path.startsWith("/reports/contacts?")).path.split("?")[1]);
assert.equal(reportParams.get("offset"), "50");
assert.equal(reportParams.get("limit"), "50");
assert.match(text(), /101 matching contacts/);
await act(async () => control("Contact type").props.onChange({ target: { value: "partner" } }));
await flush();
reportParams = new URLSearchParams(calls.findLast(call => call.path.startsWith("/reports/contacts?")).path.split("?")[1]);
assert.equal(reportParams.get("offset"), "0");
assert.equal(reportParams.get("contact_type"), "partner");
// Opening/cancelling an editor must not invalidate an unrelated pending report.
delayReport = true;
await act(async () => control("Legacy company text").props.onChange({ target: { value: "pending-editor" } }));
await flush();
const editorPendingReport = releaseReport;
await click("+ Contact");
await click("Cancel");
delayReport = false;
await act(async () => editorPendingReport({ items: [{ ...contact, deal_stages: ["lead"] }], total: 1, limit: 50, offset: 0 }));
assert.doesNotMatch(text(), /Loading matching records/);
assert.match(text(), /Ada Example/);
// A late filter response must not replace a newer filtered result.
delayReport = true;
await act(async () => control("Legacy company text").props.onChange({ target: { value: "old" } }));
await flush();
const oldReport = releaseReport;
delayReport = false;
await act(async () => control("Legacy company text").props.onChange({ target: { value: "new" } }));
await flush();
await act(async () => oldReport({ items: [{ ...contact, name: "Stale filtered person" }], total: 999 }));
assert.doesNotMatch(text(), /Stale filtered person/);
// Changing a filter also invalidates pending record detail.
delayDetail = true;
await act(async () => { root.root.findAllByType("button").find(node => flatten(node.children).includes("Ada Example")).props.onClick(); });
await act(async () => control("Email").props.onChange({ target: { value: "missing" } }));
await act(async () => releaseDetail({ contact, deals: [], tasks: [], activity: [] }));
assert.equal(root.root.findAll(node => node.props["aria-label"] === "Record details").length, 0);
delayDetail = false;
reportTotal = 1;
await click("Overview");
await click("0 leads with no open follow-up");
reportParams = new URLSearchParams(calls.findLast(call => call.path.startsWith("/reports/contacts?")).path.split("?")[1]);
assert.equal(reportParams.get("contact_type"), "lead");
assert.equal(reportParams.get("followup"), "missing");
assert.equal(reportParams.get("stage"), null);
await click("Pipeline");
await act(async () => control("Minimum value (USD)").props.onChange({ target: { value: "12.34" } }));
await flush();
assert.equal(new URLSearchParams(calls.findLast(call => call.path.startsWith("/deals?")).path.split("?")[1]).get("min_value"), "1234");
await click("Tasks");
await act(async () => { control("Priority").props.onChange({ target: { value: "high" } }); control("Due").props.onChange({ target: { value: "overdue" } }); });
await flush();
const followupParams = new URLSearchParams(calls.findLast(call => call.path.startsWith("/tasks?")).path.split("?")[1]);
assert.equal(followupParams.get("priority"), "high");
assert.equal(followupParams.get("due"), "overdue");
await act(async()=>{control("Task owner").props.onChange({target:{value:"missing"}});control("Exact owner label").props.onChange({target:{value:"Case-sensitive owner"}});});await flush();
const ownerFilters=new URLSearchParams(calls.findLast(call=>call.path.startsWith("/tasks?")).path.split("?")[1]);assert.equal(ownerFilters.get("owner"),"missing");assert.equal(ownerFilters.get("owner_label"),"Case-sensitive owner");
await click("Clear filters");
task.contact_id = "outside-loaded-contacts";
await act(async () => { root.root.findAllByType("button").find(node => flatten(node.children).includes("Follow up")).props.onClick(); });
await click("Edit");
assert.ok(root.root.findAllByType("option").some(node => node.props.value === "outside-loaded-contacts"), "Bounded selector preserves current contact ID");
await click("Cancel");
task.contact_id = "c1";
await click("Contacts");
assert.match(text(), /Ada Example/);
await click("+ Contact");
let form = root.root.findByType("form");
assert.equal(form.props["aria-label"], "Create contacts");
const field = (title) =>
  root.root
    .findAllByType("label")
    .find((node) => flatten(node.children).startsWith(title))
    .findByType("input");
assert.equal(field("Job title").props.required, false);
assert.equal(field("Full name").props["data-autofocus"], true);
await act(async () =>
  field("Full name").props.onChange({ target: { value: "Name only" } }),
);
await act(async () => {
  await root.root.findByType("form").props.onSubmit({ preventDefault() {} });
});
assert.equal(writes.length, 1);
assert.equal(writes[0].options.body.data.name, "Name only");
assert.equal(writes[0].options.body.data.title, "");
assert.equal(writes[0].options.body.workspace_token, "token-work");
assert.match(writes[0].options.body.idempotency_key, /^[0-9a-f-]{36}$/);
await flush();
// A detail response from a prior section must not reopen a panel after navigation.
delayDetail = true;
await act(async () => {
  root.root
    .findAllByType("button")
    .find((node) => flatten(node.children).includes("Ada Example"))
    .props.onClick();
});
await click("Record history");
await act(async () => {
  releaseDetail({ contact, deals: [], tasks: [], activity: [] });
});
assert.equal(root.root.findAll(node => node.props["aria-label"] === "Record details").length, 0);
delayDetail = false;
await click("Tasks");
await act(async () =>
  root.root
    .findAllByType("input")
    .find((node) => node.props.type === "search")
    .props.onChange({ target: { value: "Follow" } }),
);
await flush();
const taskSearch = calls.findLast((call) => call.path.startsWith("/tasks?"));
assert.equal(
  new URLSearchParams(taskSearch.path.split("?")[1]).get("q"),
  "Follow",
  "Task query is applied server-side before list limits",
);
assert.equal(
  new URLSearchParams(taskSearch.path.split("?")[1]).get("status"),
  "open",
);
await click("Complete");
assert.equal(writes[1].path, "/tasks/t1");
assert.equal(writes[1].options.body.data.version, 4);
assert.equal(writes[1].options.body.data.status, "done");
assert.equal(writes[1].options.body.workspace_token, "token-work");
await click("Contacts");
await act(async () => {
  root.root
    .findAllByType("button")
    .find((node) => flatten(node.children).includes("Ada Example"))
    .props.onClick();
});
await click("Edit");
await act(async () => {
  await root.root.findByType("form").props.onSubmit({ preventDefault() {} });
});
assert.equal(writes[2].options.method, "PATCH");
assert.equal(writes[2].options.body.data.version, 3);
await click("Tasks");
await act(async () => {
  root.root
    .findAllByType("button")
    .find((node) => flatten(node.children).includes("Follow up"))
    .props.onClick();
});
await click("Edit");
await act(async () =>
  field("Title").props.onChange({ target: { value: "Updated title only" } }),
);
await act(async () => {
  await root.root.findByType("form").props.onSubmit({ preventDefault() {} });
});
assert.equal(
  writes[3].options.body.data.due_at,
  task.due_at,
  "Unchanged datetime control preserves exact scheduled timestamp, including microseconds",
);
assert.equal(writes[3].options.body.data.title, "Updated title only");
// The record workspace replaces the raw-property dump with honest, working
// associations, audit history, and prefilled record creation.
relatedDeals.push(deal);
activityRows.push({ id: "a1", entity_id: "c1", action: "updated", actor: "desktop",
  summary: "Ada Example · updated", created_at: "2026-11-06T17:00:00+00:00" });
await click("Refresh");
await click("Contacts");
const openRecord = async title => {
  const target = root.root.findAllByType("button").find(node => flatten(node.children).includes(title));
  assert.ok(target, `Missing record ${title}`);
  await act(async () => { target.props.onClick(); });
  await flush();
};
const recordDetails = () => root.root.findAll(node => node.props["aria-label"] === "Record details");
const input = name => root.root.findAllByType("input").find(node => node.props.name === name);
const select = name => root.root.findAllByType("select").find(node => node.props.name === name);
const change = async (node, value) => act(async () => node.props.onChange({ target: { value } }));
const submitForm = async () => act(async () => { await root.root.findByType("form").props.onSubmit({ preventDefault() {} }); });
const dialog = () => root.root.findAll(node => node.props.role === "dialog")[0];
const press = async (key, shiftKey = false) => {
  let prevented = false, stopped = false;
  await act(async () => dialog().props.onKeyDown({ key, shiftKey,
    preventDefault() { prevented = true; }, stopPropagation() { stopped = true; } }));
  return { prevented, stopped };
};
await openRecord("Ada Example");
assert.equal(recordDetails().length, 1);
assert.match(text(), /CRM record changes only. Sent and received emails are not synced here/);
assert.match(text(), /Upcoming follow-ups/);
assert.match(text(), /Example opportunity/);
assert.match(text(), /Recorded by desktop/);
assert.doesNotMatch(text(), /Human owner/);
assert.equal(root.root.findAllByType("button").some(node => /Send email|Send message/.test(flatten(node.children))), false);
await click("Create follow-up");
assert.equal(select("contact_id").props.value, "c1");
assert.equal(recordDetails().length, 1, "The contact remains behind the drawer for cancellation");
assert.equal(root.root.findAll(node => node.props.className === "hc-wrap")[0].props.inert, true);
assert.equal(dialog().props["aria-modal"], true);
assert.equal(mockDocument.activeElement.name, "first-input");
const staleCreateFollowup = root.root.findByType("form").props.onSubmit;
await change(input("title"), "Draft follow-up");
await change(input("due_at"), "2027-01-02T12:00");
mockDocument.activeElement = drawerNode.controls.at(-1);
assert.equal((await press("Tab")).prevented, true);
assert.equal(mockDocument.activeElement.name, "drawer-close");
assert.equal((await press("Tab", true)).prevented, true);
assert.equal(mockDocument.activeElement.name, "save");
assert.deepEqual(await press("Escape"), { prevented: true, stopped: true });
assert.equal(root.root.findAllByType("form").length, 1);
assert.match(text(), /Discard unsaved changes/);
await click("Keep editing");
assert.equal(input("title").props.value, "Draft follow-up");
await press("Escape");
await click("Discard changes");
assert.equal(root.root.findAllByType("form").length, 0);
assert.equal(mockDocument.activeElement, opener, "Dismissal restores focus to the captured opener");
assert.equal(root.root.findAll(node => node.props.className === "hc-wrap")[0].props.inert, undefined);
const beforeStaleDraft = writes.length;
await act(async () => staleCreateFollowup({ preventDefault() {} }));
assert.equal(writes.length, beforeStaleDraft, "A dismissed valid form callback cannot write");
await click("Create deal");
assert.equal(select("contact_id").props.value, "c1");
await change(input("title"), "New opportunity");
await change(select("stage"), "negotiation");
assert.equal(input("probability").props.value, 75);
await change(input("value"), "1.001");
await submitForm();
assert.equal(writes.length, beforeStaleDraft);
assert.equal(input("value").props.value, "1.001");
assert.equal(input("value").props["aria-invalid"], true);
assert.match(text(), /at most two decimal places/);
await change(input("value"), "12.34");
await change(input("probability"), "101");
await submitForm();
assert.match(text(), /whole number from 0 to 100/);
await click("Cancel");
await click("Discard changes");
await openRecord("Example opportunity");
assert.match(text(), /Linked contact/);
assert.equal(root.root.findAll(node => node.props["aria-current"] === "step")[0].children[0], "Proposal");
await click("Create follow-up");
assert.equal(select("contact_id").props.value, "c1");
assert.equal(select("deal_id").props.value, "d1");
await click("Cancel");
await click("Close");
assert.match(flatten(recordDetails()[0].children), /Ada Example/);
await click("Back to Contacts");
assert.equal(recordDetails().length, 0);
// Cycles are bounded to 20 identities; repeated current-record opens do not add entries.
await openRecord("Ada Example");
await openRecord("Ada Example");
await click("Close");
assert.equal(recordDetails().length, 0);
await openRecord("Ada Example");
for (let index = 0; index < 22; index++) {
  await openRecord("Example opportunity");
  await openRecord("Ada Example");
}
for (let index = 0; index < 20; index++) await click("Close");
assert.equal(recordDetails().length, 0, "Record navigation history is bounded");
// Crossing into Company records preserves the contact trail and original list.
await openRecord("Ada Example");
await click("Exact Company · co1");
assert.match(text(), /Exact Company/);
await click("Back to Contacts");
assert.match(flatten(recordDetails()[0].children), /Ada Example/);
await click("Close");
assert.equal(recordDetails().length, 0);
// Child creation opens its confirmed exact ID, preserving parent and list context.
await openRecord("Ada Example");
await click("Create follow-up");
await change(input("title"), "Child follow-up");
await change(input("due_at"), "2027-04-03T10:00");
const beforeChildCreate = writes.length;
await submitForm();
assert.equal(writes.length, beforeChildCreate + 1);
assert.equal(writes.at(-1).options.body.data.contact_id, "c1");
assert.match(flatten(recordDetails()[0].children), /Follow up/);
const beforeBackReads = calls.filter(call => call.path.startsWith("/contacts/c1?")).length;
await click("Back to Contacts");
assert.equal(calls.filter(call => call.path.startsWith("/contacts/c1?")).length, beforeBackReads + 1, "Back re-reads the exact parent, never uses a cached version");
assert.match(flatten(recordDetails()[0].children), /Ada Example/);
await click("Close");
assert.equal(recordDetails().length, 0);
const afterChildCreate = writes.length;
// Repeated opens create independent drafts, preserve the page/filter state, and
// never retain a cancelled value or create a write as a side effect.
for (let i = 0; i < 3; i++) {
  await click("+ Contact");
  assert.equal(input("name").props.value, "");
  await change(input("name"), `Cancelled ${i}`);
  await click("Cancel");
  await click("Discard changes");
}
assert.equal(writes.length, afterChildCreate);
await click("+ Contact");
await submitForm();
assert.match(text(), /Enter the contact’s full name/);
assert.equal(writes.length, afterChildCreate);
await change(input("name"), "Retained contact");
await change(input("email"), "not-an-email");
await submitForm();
assert.match(text(), /Enter a valid email address/);
assert.equal(input("name").props.value, "Retained contact");
await change(input("email"), "retained@example.test");
writeError = "Validation rejected by the CRM";
await submitForm();
assert.equal(root.root.findAllByType("form").length, 1);
assert.equal(input("name").props.value, "Retained contact");
assert.equal(input("email").props.value, "retained@example.test");
assert.match(flatten(dialog().children), /Outcome unknown/);
const retryKey = writes.at(-1).options.body.idempotency_key;
writeError = ""; delayWrite = true;
const pendingSubmit = root.root.findByType("form").props.onSubmit;
let savePromise;
const beforeDoubleSave = writes.length;
await act(async () => {
  savePromise = pendingSubmit({ preventDefault() {} });
  await pendingSubmit({ preventDefault() {} });
});
assert.equal(writes.length, beforeDoubleSave + 1, "Repeated Save only sends one in-flight mutation");
assert.equal(writes.at(-1).options.body.idempotency_key, retryKey);
assert.equal(button("Cancel").props.disabled, true);
await press("Escape");
assert.equal(root.root.findAllByType("form").length, 1, "Pending mutations cannot be dismissed");
delayWrite = false;
await act(async () => { releaseWrite({}); await savePromise; });
assert.equal(root.root.findAllByType("form").length, 1, "Missing confirmed ID retains the original form");
assert.match(text(), /Outcome unknown/);
await submitForm();
assert.equal(writes.at(-1).options.body.idempotency_key, retryKey);
const afterConfirmedRetry = writes.length;
await flush();
assert.equal(root.root.findAllByType("form").length, 0);
await act(async () => pendingSubmit({ preventDefault() {} }));
assert.equal(writes.length, afterConfirmedRetry, "A saved/unmounted callback cannot create again");
// Native type=email and the backend permit local domains. An unchanged
// owner@intranet address must not block an unrelated edit to an existing record.
contact.email = "owner@intranet";
await click("Contacts");
await openRecord("Ada Example");
await click("Edit");
assert.equal(input("email").props.type, "email");
assert.equal(input("email").props.value, "owner@intranet");
await change(input("name"), "Updated local-domain contact");
const beforeLocalEmailEdit = writes.length;
await submitForm();
assert.equal(writes.length, beforeLocalEmailEdit + 1);
assert.equal(writes.at(-1).options.body.data.email, "owner@intranet");
assert.equal(writes.at(-1).options.body.data.name, "Updated local-domain contact");
assert.equal(writes.at(-1).options.body.data.version, contact.version);
contact.email = "";
await flush();
await click("+ Contact");
await change(input("name"), "Email validation draft");
for (const email of ["not-an-email", "owner@", "@intranet", "owner@@intranet", "owner @intranet", "owner@intra net"]) {
  await change(input("email"), email);
  await submitForm();
  assert.equal(writes.length, beforeLocalEmailEdit + 1, `Malformed email must not write: ${email}`);
  assert.equal(input("email").props.value, email, "Validation preserves the entered address");
  assert.match(text(), /Enter a valid email address/);
}
await click("Cancel");
await click("Discard changes");
// Successful deal and task writes still use existing endpoint payloads. A
// missing selector choice is visible and retained, never silently unlinked.
await click("Pipeline");
await click("+ Deal");
await change(input("title"), "Created opportunity");
await change(select("contact_id"), "c1");
await change(input("value"), "123.45");
await change(select("stage"), "qualified");
await change(input("probability"), "30");
await submitForm();
assert.equal(writes.at(-1).path, "/deals");
assert.equal(writes.at(-1).options.method, "POST");
assert.equal(writes.at(-1).options.body.data.value, 12345);
assert.equal(writes.at(-1).options.body.data.currency, "USD");
assert.equal(writes.at(-1).options.body.data.probability, 30);
assert.equal(writes.at(-1).options.body.data.stage, "qualified");
assert.equal(writes.at(-1).options.body.data.contact_id, "c1");
await flush();
await openRecord("Example opportunity");
await click("Edit");
await change(input("title"), "Updated opportunity title");
await submitForm();
assert.equal(writes.at(-1).path, "/deals/d1");
assert.equal(writes.at(-1).options.body.data.version, 2);
assert.equal(writes.at(-1).options.body.data.value, 25000);
assert.equal(writes.at(-1).options.body.data.close_date, "2027-02-01");
await click("Tasks");
await click("+ Follow-up");
await change(input("title"), "Created task");
const beforeInvalidDue = writes.length;
await submitForm();
assert.equal(writes.length, beforeInvalidDue);
assert.match(text(), /Choose a valid local due date and time/);
await change(input("due_at"), "2027-03-04T09:15");
await submitForm();
assert.equal(writes.at(-1).path, "/tasks");
assert.equal(writes.at(-1).options.body.data.due_at, new Date("2027-03-04T09:15").toISOString());
assert.equal(writes.at(-1).options.body.data.contact_id, null);
assert.equal(writes.at(-1).options.body.data.deal_id, null);
await flush();
task.contact_id = "outside-contact"; task.deal_id = "outside-deal";
await openRecord("Follow up");
await click("Edit");
assert.ok(root.root.findAllByType("option").some(node => node.props.value === "outside-contact"));
assert.ok(root.root.findAllByType("option").some(node => node.props.value === "outside-deal"));
await change(input("title"), "Preserve links");
await submitForm();
assert.equal(writes.at(-1).options.body.data.contact_id, "outside-contact");
assert.equal(writes.at(-1).options.body.data.deal_id, "outside-deal");
assert.equal(writes.at(-1).options.body.data.due_at, task.due_at);
task.contact_id = "c1"; task.deal_id = null;
await flush();
await openRecord("Follow up");
let detailComplete = recordDetails()[0].findAllByType("button").find(node => flatten(node.children) === "Complete");
await act(async () => detailComplete.props.onClick());
assert.equal(writes.at(-1).options.body.data.version, task.version);
assert.equal(writes.at(-1).options.body.data.status, "done");
assert.equal(recordDetails().length, 1);
const staleComplete = detailComplete.props.onClick;
await click("Contacts");
const afterDetailComplete = writes.length;
await act(async () => staleComplete());
assert.equal(writes.length, afterDetailComplete, "Dismissed detail callback cannot write");
await click("Tasks");
await openRecord("Follow up");
task.status = "done";
await click("Edit");
await click("Cancel");
await openRecord("Follow up");
const detailReopen = recordDetails()[0].findAllByType("button").find(node => flatten(node.children) === "Reopen");
await act(async () => detailReopen.props.onClick());
assert.equal(writes.at(-1).options.body.data.status, "open");
assert.equal(recordDetails().length, 1);
task.status = "open";
// Required ownership only interrupts genuinely ownerless task mutations.
testOwnerPolicy = {version:3,required:true,default_owner_label:"Configured person",legacy_edit_rule:"owner_required_on_edit"};
await click("Tasks"); await click("Refresh"); await flush();
let ownerWrites = writes.length;
await click("Task ownership");assert.match(text(),/Current policy · Version 3/);assert.equal(writes.length,ownerWrites);await click("Close");
await click("Complete");
assert.equal(writes.length,ownerWrites);assert.ok(input("owner_label"));assert.equal(input("owner_label").props.value,"");
assert.match(text(),/Choose a human task owner before completing/);
await click("Cancel");
await openRecord("Follow up");await click("Complete");assert.equal(writes.length,ownerWrites);assert.equal(select("status").props.value,"open");
await click("Use configured default: Configured person");await change(select("status"),"done");
writeError="Network response lost";await submitForm();
const frozenOwnerWrite=JSON.stringify(writes.at(-1).options);
assert.equal(writes.at(-1).options.body.data.owner_source,"default");assert.equal(writes.at(-1).options.body.data.owner_policy_version,3);assert.equal(writes.at(-1).options.body.data.due_at,task.due_at);
await click("Cancel");await click("Discard changes");await click("Edit");
assert.equal(input("owner_label").props.value,"Configured person");assert.equal(input("owner_label").props.disabled,true);
writeError="";await submitForm();assert.equal(JSON.stringify(writes.at(-1).options),frozenOwnerWrite,"Owner PATCH retry retains original body and idempotency key across remount");
task.owner_label="Existing owner";task.owner_source="default";
await click("Refresh");await openRecord("Follow up");
ownerWrites=writes.length;await click("Complete");assert.equal(writes.length,ownerWrites+1);assert.equal(root.root.findAllByType("form").length,0);assert.equal(writes.at(-1).options.body.data.owner_policy_version,3);assert.equal(writes.at(-1).options.body.data.owner_label,undefined);
await click("Edit");await change(input("title"),"Keep existing ownership provenance");await submitForm();assert.equal(writes.at(-1).options.body.data.owner_label,undefined);assert.equal(writes.at(-1).options.body.data.owner_source,undefined);assert.equal(writes.at(-1).options.body.data.due_at,task.due_at);
delete task.owner_label;delete task.owner_source;testOwnerPolicy=undefined;await click("Refresh");
console.log("PASS native task owner required completion guard, direct owned completion, exact due/source preservation and same-key frozen unknown PATCH recovery across dismissal.");
// A definitive rejection is retained, never retried, until an explicit fresh review.
for (const create of [false,true]) {
  await click("Tasks"); if(create) await click("+ Follow-up"); else {await openRecord("Follow up");await click("Edit");}
  await change(input("title"),create ? "Retained rejected create" : "Retained rejected update");
  if(create) await change(input("due_at"),"2030-06-12T10:00");
  writeError="Outcome unknown";await submitForm();
  const unknownBody=JSON.stringify(writes.at(-1).options);
  taskFailureStatus=409;writeError="Task or policy conflict";await submitForm();assert.equal(JSON.stringify(writes.at(-1).options),unknownBody);
  let count=writes.length;await submitForm();assert.equal(writes.length,count,"Definitive rejection cannot replay Save");
  await click("Cancel");await click("Discard changes");await click("Contacts");await click("Tasks");
  if(create) await click("+ Follow-up");else {await openRecord("Follow up");await click("Edit");}
  assert.equal(input("title").props.value,create ? "Retained rejected create" : "Retained rejected update");assert.equal(input("title").props.disabled,true);
  taskFailureStatus=0;writeError="";await click("Review current task and policy");assert.equal(writes.length,count,"Fresh review only reads");assert.equal(input("title").props.disabled,false);assert.match(text(),/Current saved record and retained draft/);
  await change(input("title"),create ? "Corrected new task" : "Corrected existing task");await submitForm();assert.equal(writes.length,count+1);assert.notEqual(writes.at(-1).options.body.idempotency_key,JSON.parse(unknownBody).body.idempotency_key);assert.equal(root.root.findAllByType("form").length,0);
}
// Correct IDs/owners/status cannot turn a malformed business-record receipt into success.
for (const create of [false,true]) {
  await click("Tasks");if(create) await click("+ Follow-up");else {await openRecord("Follow up");await click("Edit");}
  await change(input("title"),"Reviewed receipt fields");if(create)await change(input("due_at"),"2030-06-12T10:00");
  taskReceiptPatch={due_at:null,title:"Unrelated record"};await submitForm();assert.match(text(),/receipt did not match/);assert.equal(root.root.findAllByType("form").length,1);
  const malformedBody=JSON.stringify(writes.at(-1).options);taskReceiptPatch=null;await submitForm();assert.equal(JSON.stringify(writes.at(-1).options),malformedBody);assert.equal(root.root.findAllByType("form").length,0);
}
console.log("PASS native definitive task rejection retained across navigation, unknown-to-conflict exact retry, fresh review/corrected new key and malformed create/update receipt recovery.");
const beforeHistoryWrites = writes.length;
// Optional native-work capability must distinguish missing/failed from empty.
await click("Tasks");
workError = "404: route unavailable";
await openRecord("Follow up");
assert.match(text(), /history is unavailable/);
assert.doesNotMatch(text(), /No native assignments are recorded/);
workError = "";
workRows = [{ id: "w1", state: "result_reported", reason: "native_run_reported", source_task_current: true,
  job_id: "job1", payload: { human_owner: "Review owner", run_at: task.due_at, prompt: "Research the contact", success_criteria: "Provide sourced findings" },
  reports: [{ id: "r1", outcome: "completed", summary: "Research draft ready", review_status: "awaiting_human_review", created_at: task.due_at }],
  events: [{ id: "e1", kind: "registered", created_at: task.due_at }] }];
await click("Refresh saved status");
assert.match(text(), /Human owner/);
assert.match(text(), /Review owner/);
assert.match(text(), /Agent reported: Completed/);
assert.match(text(), /Source current at evidence read/);
assert.match(text(), /does not verify host terminal success/);
const workParams = new URLSearchParams(calls.findLast(call => call.path.startsWith("/reports/work?")).path.split("?")[1]);
assert.equal(workParams.get("task_id"), "t1");
assert.equal(workParams.get("workspace_token"), "token-work");
assert.equal(workParams.get("limit"), "25");
assert.equal(writes.length, beforeHistoryWrites, "History is read-only");
// Both accepted manual and interval snapshots refetch assigned-work history.
// A superseded request cannot overwrite the newest assignment observation.
const historySummary = () => flatten(root.root.findAllByType("summary").map(node => node.children));
const expandedReport = root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function");
await act(async () => expandedReport.props.onToggle({ currentTarget: { open: true } }));
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function").props.open, true);
let historyCalls = calls.filter(call => call.path.startsWith("/reports/work?")).length;
workRows = [{ ...workRows[0], state: "cancelled", source_task_current: false }];
await click("Refresh");
assert.equal(calls.filter(call => call.path.startsWith("/reports/work?")).length, historyCalls + 1);
assert.match(historySummary(), /Cancelled/);
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function"), expandedReport, "Manual refresh retains the keyed report panel");
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function").props.open, true, "Manual refresh preserves expansion");
assert.doesNotMatch(historySummary(), /Result Reported/);
assert.match(text(), /Changed or completed since assignment/);
historyCalls++;
workRows = [{ ...workRows[0], state: "superseded" }];
await act(async () => { for (const tick of intervals) tick(); });
await flush();
assert.equal(calls.filter(call => call.path.startsWith("/reports/work?")).length, historyCalls + 1);
assert.match(historySummary(), /Superseded/);
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function"), expandedReport, "Polling does not unmount the keyed report panel");
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function").props.open, true, "Polling preserves expansion");
delayWork = true;
await click("Refresh");
const staleHistoryRefresh = releaseWork;
assert.match(text(), /Refreshing assigned-work history/);
assert.match(text(), /Showing the last successful observations/);
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function"), expandedReport, "Pending refresh retains the readable report");
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function").props.open, true);
delayWork = false;
workRows = [{ ...workRows[0], state: "cancelled", payload: { ...workRows[0].payload, human_owner: "Current review owner" } }];
await click("Refresh");
assert.match(text(), /Current review owner/);
await act(async () => staleHistoryRefresh([{ ...workRows[0], state: "result_reported", source_task_current: true,
  payload: { ...workRows[0].payload, human_owner: "Stale refresh owner" } }]));
assert.match(historySummary(), /Cancelled/);
assert.doesNotMatch(text(), /Stale refresh owner/);
assert.match(text(), /Changed or completed since assignment/);
assert.equal(writes.length, beforeHistoryWrites, "Refreshed history remains read-only");
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function"), expandedReport);
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function").props.open, true);
// Errors keep the expanded report readable, but never silently imply that the
// last loaded source-task status was reverified. Recovery clears stale status.
workRows = [{ ...workRows[0], state: "result_reported", source_task_current: true }];
await click("Refresh");
workError = "History refresh failed";
await click("Refresh");
assert.match(text(), /history could not be refreshed/);
assert.match(text(), /last successful observations, which may be out of date/);
assert.match(text(), /Current at last successful refresh; not reverified/);
assert.doesNotMatch(text(), /No native assignments are recorded/);
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function"), expandedReport);
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function").props.open, true, "Failed refresh preserves expansion");
workError = "";
workRows = [{ ...workRows[0], state: "cancelled", source_task_current: false }];
await click("Refresh saved status");
assert.match(historySummary(), /Cancelled/);
assert.doesNotMatch(text(), /not reverified|could not be refreshed/);
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function").props.open, true, "Recovery preserves expansion");
await act(async () => root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function").props.onToggle({ currentTarget: { open: false } }));
await click("Refresh");
assert.equal(root.root.findAllByType("details").find(node => typeof node.props.onToggle === "function").props.open, false, "Refresh also preserves user-collapsed state");
await click("Close");
workRows = { unsupported: true };
await openRecord("Follow up");
assert.match(text(), /Saved history could not be read/);
assert.doesNotMatch(text(), /No native assignments are recorded/);
workRows = [];
await click("Refresh saved status");
assert.match(text(), /No native assignments are recorded/);
workError = "Empty history could not be refreshed";
await click("Refresh");
assert.match(text(), /last successful history check found no assignments; this has not been reverified/);
assert.doesNotMatch(text(), /No native assignments are recorded/);
workError = "";
await click("Close");
delayWork = true;
await openRecord("Follow up");
assert.match(text(), /Loading assigned-work history/);
await click("Contacts");
delayWork = false;
await act(async () => releaseWork([{ id: "stale-assignment", payload: { human_owner: "Stale hidden owner" } }]));
assert.doesNotMatch(text(), /Stale hidden owner/);
assert.equal(recordDetails().length, 0);
// Explicit cancellation wins over a pending detail response.
delayDetail = true;
await openRecord("Ada Example");
await click("Cancel loading");
await act(async () => releaseDetail({ contact, deals: relatedDeals, tasks: [task], activity: activityRows }));
assert.equal(recordDetails().length, 0);
assert.doesNotMatch(text(), /Loading record…/);
delayDetail = false;
// Retried creates retain their original payload AND original ID-only return context.
testCatalog={schema_version:1,stages:[],fields:{contacts:[{key:'zero',label:'Zero value',type:'number',version:1,archived:false},{key:'flag',label:'False value',type:'boolean',version:1,archived:false}],deals:[],tasks:[]}};
await click('Refresh');
for (const scenario of ['linked','unlinked','conflict','panel','panel-conflict','panel-null-conflict','missing-source']) {
  await click('Contacts');
  if(!['unlinked','panel-null-conflict'].includes(scenario)){await openRecord('Ada Example');await click('Exact Company · co1');await click('Create contact');}
  else await click('+ Contact');
  const originalName=`Original ${scenario} child`;
  await change(input('name'),originalName);
  await change(input('custom_zero'),'0');await change(select('custom_flag'),'false');
  writeError='Lost creation receipt';await submitForm();
  const original=writes.at(-1), beforeRetry=writes.length;
  await click('Cancel');await click('Discard changes');
  await click('Companies');await openRecord('Other Company');
  assert.match(text(),/Original pending creation/);
  if(scenario.startsWith('panel')) {
    writeError='';if(scenario.includes('conflict'))contactFailureStatus=409;await click('Retry original request');
  } else {
    assert.equal(button('Create contact').props.disabled,false,'Context action can reopen the original unknown create');
    await click('Create contact');
    assert.equal(input('name').props.value,originalName);
    assert.equal(input('name').props.disabled,true);
    assert.doesNotMatch(flatten(dialog().children),/Selected exact ID: co2/);
    assert.match(flatten(dialog().children),scenario==='unlinked'?/Primary Company: Not linked/:/Primary Company: co1/);
    writeError='';if(scenario==='conflict')contactFailureStatus=409;if(scenario==='missing-source')companyMissing=true;
    await submitForm();
  }
  assert.equal(writes.length,beforeRetry+1,'Recovery sends exactly one original mutation');
  assert.equal(JSON.stringify(writes.at(-1).options.body),JSON.stringify(original.options.body),'Original body and key remain byte-for-byte stable');
  assert.equal(Object.hasOwn(writes.at(-1).options.body,'context'),false,'Navigation metadata never enters transport');
  if(scenario.includes('conflict')) {
    assert.equal(input('name').props.value,originalName);assert.equal(input('name').props.disabled,false);
    assert.equal(Number(input('custom_zero').props.value),0);assert.equal(select('custom_flag').props.value,'false');
    if(scenario==='panel-null-conflict')assert.doesNotMatch(flatten(dialog().children),/Selected exact ID: co[12]/);else assert.match(flatten(dialog().children),/Selected exact ID: co1/);
    assert.match(flatten(dialog().children),/Company changed/);
    assert.equal(writes.length,beforeRetry+1,'Restoring rejected draft does not submit it');
    contactFailureStatus=0;if(scenario!=='panel-null-conflict'){await click('Refresh selected Company');await click('Use reviewed Company version');}await submitForm();
    assert.notEqual(writes.at(-1).options.body.idempotency_key,original.options.body.idempotency_key);
    assert.equal(writes.at(-1).options.body.company_id,scenario==='panel-null-conflict'?null:'co1');assert.equal(writes.at(-1).options.body.data.name,originalName);
    assert.equal(writes.at(-1).options.body.data.custom_fields.zero,0);assert.equal(writes.at(-1).options.body.data.custom_fields.flag,false);
  }
  assert.match(flatten(recordDetails()[0].children),/Ada Example/);
  if(['unlinked','panel-null-conflict','missing-source'].includes(scenario)) {
    if(scenario==='missing-source')assert.match(text(),/original source is unavailable/);
    await click('Back to Contacts');assert.equal(recordDetails().length,0);assert.doesNotMatch(text(),/Other Company/);
  } else {
    await click('Back to Companies');assert.match(text(),/Exact Company/);assert.doesNotMatch(text(),/Other Company/);
  }
  companyMissing=false;
}
testCatalog=undefined;await click('Refresh');
await click('Contacts');
console.log('PASS unknown A→B and null→B original frozen preview/body/key, restored original parent/list, known409 original-draft review/new key, panel null/A409 preserving ordinary/custom0/false with no auto-write, panel recovery, missing-source fallback and no transport navigation metadata.');
// Canonical Company creation and exact contextual Event actions use the ordinary native editors.
await openRecord('Ada Example');
await click('Exact Company · co1');
const beforeContext = writes.length;
await click('Create contact');
assert.equal(input('company').props.value, '', 'Canonical Company must never populate legacy text');
assert.match(text(), /Selected exact ID: co1/);
await change(input('name'),'Contextual child');
await change(input('company'),'Independent legacy');
contactFailureStatus=409;await submitForm();
assert.equal(input('name').props.value,'Contextual child');
assert.equal(input('name').props.disabled,false,'Definitive stale rejection permits reviewing retained draft');
assert.match(text(),/Refresh the record and review/);
const rejectedKey=writes.at(-1).options.body.idempotency_key;
contactFailureStatus=0;
await click('Refresh selected Company');await click('Use reviewed Company version');await submitForm();
assert.equal(writes.at(-1).path,'/relationship-contacts');
assert.equal(writes.at(-1).options.body.company_id,'co1');
assert.equal(writes.at(-1).options.body.expected_company_version,1);
assert.equal(writes.at(-1).options.body.data.company,'Independent legacy');
assert.notEqual(writes.at(-1).options.body.idempotency_key,rejectedKey);
assert.match(flatten(recordDetails()[0].children),/Ada Example/);
await click('Back to Companies');assert.match(text(),/Exact Company/);
for (const sourceKind of ['companies','contacts','deals']) {
  if(sourceKind==='contacts'){await click('Back to Contacts');}
  if(sourceKind==='deals'){await openRecord('Example opportunity');}
  const count=writes.length;
  await click('Create Event');
  const key=sourceKind==='companies'?'company_id':sourceKind==='contacts'?'contact_id':'deal_id';
  const exact=sourceKind==='companies'?'co1':sourceKind==='contacts'?'c1':'d1';
  assert.match(flatten(dialog().children),new RegExp('Selected exact ID: '+exact));
  assert.equal(root.root.findByType('form').props['aria-label'],'Create events');
  assert.equal(writes.length,count,'Opening contextual Event never writes');
  const eventForm=root.root.findByType('form');
  const title=eventForm.findAllByType('label').find(n=>flatten(n.children).startsWith('title')).findByType('input');
  await change(title,'Context Event');
  const times=eventForm.findAllByType('input').filter(n=>n.props.type==='datetime-local');
  await change(times[0],'2027-04-03T10:00');await change(times[1],'2027-04-03T11:00');
  await submitForm();
  assert.equal(writes.at(-1).path,'/events');assert.equal(writes.at(-1).options.method,'POST');
  for(const association of ['company_id','contact_id','deal_id'])assert.equal(writes.at(-1).options.body.data[association],association===key?exact:null);
  assert.match(text(),/Context Event/);
  await click('Back to '+(sourceKind==='companies'?'Companies':sourceKind==='contacts'?'Contacts':'Deals'));
}
await click('Contacts');await openRecord('Ada Example');companyArchived=true;await click('Exact Company · co1');
assert.equal(button('Create contact').props.disabled,true);assert.equal(button('Create Event').props.disabled,true);
companyArchived=false;await click('Contacts');
console.log('PASS contextual native Company contact creation, stale-version draft review, independent legacy text, confirmed child and Back, archived source blocking and Company/Contact/Deal Event POST with only exact source association.');
await click("+ Contact");
for (const [name, transition] of [
  [
    "reconnect",
    () => {
      gateway.set("closed");
      gateway.set("open");
    },
  ],
  [
    "profile ABA",
    () => {
      profile.set("temporary");
      profile.set("work");
    },
  ],
  [
    "source ABA",
    () => {
      connection.set("temporary-source");
      connection.set("source-a");
    },
  ],
  ["same-value activation", () => epoch.set(epoch.get() + 1)],
]) {
  await change(input("name"), `Valid ${name} draft`);
  await change(input("email"), "owner@intranet");
  const staleCallback = root.root.findByType("form").props.onSubmit;
  const count = writes.length;
  await act(async () => {
    transition();
    await staleCallback({ preventDefault() {} });
  });
  assert.equal(
    writes.length,
    count,
    `${name}: old callback is blocked before effects`,
  );
  assert.equal(
    root.root.findAllByType("form").length,
    0,
    `${name}: reactive generation remounts workspace`,
  );
  await click("Contacts");
  await click("+ Contact");
}
await change(input("name"), "Valid old-profile draft");
await change(input("email"), "owner@intranet");
const staleSubmit = root.root.findByType("form").props.onSubmit;
const before = writes.length;
await act(async () => {
  profile.set("new-agent");
  epoch.set(epoch.get() + 1);
});
assert.doesNotMatch(text(), /Ada Example/);
assert.equal(root.root.findAllByType("form").length, 0);
await act(async () => {
  await staleSubmit({ preventDefault() {} });
});
assert.equal(writes.length, before, "Unmounted old-profile form cannot write");
await act(async () => {
  connection.set("source-b");
  epoch.set(epoch.get() + 1);
});
assert.match(text(), /source-b/);
overview.contacts = 0;
overview.open_tasks = 0;
workspaceSeeded = false;
await click("Refresh");
assert.doesNotMatch(text(), /Explore demo|synthetic|sample data/);
await click("Contacts");
assert.ok(button("+ Contact"), "Empty workspaces use ordinary contact creation");
const emptyWorkspaceWrites = writes.length;
await click("ⓘ");
assert.doesNotMatch(text(), /Workspace provenance|test records|Test workspace setup|demo data|sample data/);
for (const name of ["Test workspace setup", "Prepare test records", "Add test records"]) {
  assert.equal(button(name), undefined, "Empty workspace About contains no seed controls");
}
assert.match(text(), /Sqlite backend/);
await click("Close");
backendTokenSuffix = "-changed";
backendKind = "postgres";
await click("Refresh");
await click("ⓘ");
assert.match(text(), /Postgres backend/);
assert.doesNotMatch(text(), /Workspace provenance|test records|Test workspace setup|demo data|sample data/);
assert.equal(writes.length, emptyWorkspaceWrites, "Opening help or refreshing never populates records");
assert.equal(writes.some(({path}) => path === "/demo"), false, "Production navigation never calls the seed API");
await click("Close");
await act(async () => {
  gateway.set("connecting");
});
assert.match(text(), /paused/);
assert.equal(intervals.size, 0);
await act(async () => {
  root.unmount();
});
assert.equal(timers.size, 0);
for (const dispose of pluginDisposers) dispose();
assert.equal(profile.listeners.size, 0);
assert.equal(epoch.listeners.size, 0);
console.log(
  "PASS actual React 19.3.0 Strict Mode: zero/single/multiple charts, focus/hover/keyboard/drillthrough, server filter pagination/races and current-ID preservation, cohesive record workspace/related prefills, bounded parent Back/Close and Company return, confirmed child-ID navigation/unknown-ID retry retention, explicit dirty discard/keep, detail Complete/Reopen/stale callback rejection, accessible drawer ref focus and keyboard boundaries, repeated cancel/save and mutation lock, retained client/backend validation input, honest read-only assignment history/manual+interval refresh/retained panel expansion/stale-error signals/latest-response guards, local-domain email edits/malformed input validation, name-only create, versioned edit/complete, exact scheduled timestamp, empty-first controls with conditional provenance and no seed writes, workspace token, stale detail navigation/cancellation, valid-input profile/source ABA remount, stale form rejection, subscription/timer cleanup. SDK transport is a fixture; no live Hermes UI QA claimed.",
);

// A relationship save must not reopen a detail after navigation wins the refresh race.
for (const change of ['navigation', 'workspace', 'client', 'unchanged']) {
  let settle, live = true, opened = 0;
  const view = { current: 3 }, workspace = { current: 'captured' };
  const done = module.namespace.refreshDetailAfterRelationshipWrite(() => new Promise(resolve => settle = resolve), () => opened++, { current: () => live }, view, workspace, {kind:'contacts',row:{id:'contact'},workspaceToken:'captured'});
  if (change === 'navigation') view.current++;
  if (change === 'workspace') workspace.current = 'other';
  if (change === 'client') live = false;
  settle(true); await done; assert.equal(opened, change === 'unchanged' ? 1 : 0);
}
console.log('PASS relationship-save refresh does not resurrect closed, navigated or old-workspace details.');
