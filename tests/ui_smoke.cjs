// Lightweight, dependency-free UI logic regression tests. This is not a browser/layout test.
// Run from any directory: node /path/to/hermes-crm/tests/ui_smoke.cjs
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");

const nodes = new Map();
const handlers = {};
const requests = [];
const methods = [];
const pending = new Map();
function node() {
  return {
    innerHTML: "", textContent: "", dataset: {}, open: false, hidden: false,
    classList: { toggle() {} }, setAttribute() {}, removeAttribute() {},
    addEventListener(key, callback) { this[key] = callback; },
    querySelector() { return node(); }, focus() {},
    close() { this.open = false; }, showModal() { this.open = true; },
  };
}
const fixtures = {
  meta: { profile: "default", demo: true },
  overview: {
    profile: "default", contacts: 2, open_deals: 1, pipeline_value: 12345,
    weighted_value: 5000, won_value: 0, open_tasks: 0, overdue_tasks: 0,
    stages: [{ stage: "lead", count: 1, value: 12345 }], tasks: [], activity: [],
  },
};
const context = {
  console, Intl, Date, Number, String, Array, Object, Map, Math, Promise, Error,
  encodeURIComponent, setTimeout, clearTimeout,
  crypto: require("node:crypto").webcrypto,
  location: { hash: "#overview" },
  window: { addEventListener() {} },
  document: {
    querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, node());
      return nodes.get(selector);
    },
    querySelectorAll() { return []; },
    addEventListener(key, callback) { handlers[key] = callback; },
    contains() { return true; },
  },
  fetch: async (url, options) => {
    methods.push(options?.method || "GET");
    requests.push(url);
    const endpoint = url.slice(5);
    const data = pending.has(endpoint)
      ? await pending.get(endpoint)
      : fixtures[endpoint] || [];
    return { ok: true, json: async () => data };
  },
};
vm.createContext(context);
vm.runInContext(
  fs.readFileSync(path.join(__dirname, "../hermes_crm/static/app.js"), "utf8"),
  context,
);
const run = (source) => vm.runInContext(source, context);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
function defer(endpoint) {
  let resolve;
  pending.set(endpoint, new Promise((done) => { resolve = done; }));
  return (value) => { pending.delete(endpoint); resolve(value); };
}

(async () => {
  await tick();
  assert(nodes.get("#content").innerHTML.includes("Sales pipeline"));
  const auditRows = Array.from({length:7}, (_,i)=>({id:`audit-${i}`,summary:`Audit summary ${i}`, actor:'Human', created_at:'2026-11-07', linked_contact_id:'outside', linked_contact_name:'<Ada>', link_basis:'current_relationship'}));
  auditRows[1].linked_contact_id='../bad';
  auditRows[2].link_basis=null;
  auditRows[3].linked_contact_name={};
  auditRows[4].linked_contact_id=null;
  fixtures.overview.activity=auditRows;
  await run("state.page='overview';render()");
  const feed=nodes.get('#content').innerHTML;
  assert.equal((feed.match(/class="activity-row"/g)||[]).length,5);
  assert.equal((feed.match(/Current contact:/g)||[]).length,1);
  assert(feed.includes('Current contact: &lt;Ada&gt;'));
  assert(feed.includes('class="subtitle activity-disclaimer"'));
  assert(!feed.includes('Audit summary 5'));
  fixtures['contacts/outside']={contact:{id:'outside',name:'Fresh contact'},deals:[],tasks:[],activity:auditRows};
  const priorMethods = methods.length;
  handlers.click({target:{closest:()=>({dataset:{action:'contact',id:'outside'}})}});
  await tick();
  assert(requests.includes('/api/contacts/outside'));
  assert(methods.slice(priorMethods).every(method => method === 'GET'));
  const detail=nodes.get('#modal-body').innerHTML;
  assert(detail.includes('Fresh contact'));
  assert(!detail.includes('Current contact:'));
  assert(run(`contactActivity([{summary:'Other record',linked_contact_id:'another',linked_contact_name:'Other contact',link_basis:'current_relationship'}], 'outside')`).includes('Current contact: Other contact'));
  assert(run(`activityRows([{summary:'Record',linked_contact_id:'outside',linked_contact_name:'Dashboard contact',link_basis:'current_relationship'}])`).includes('Current contact: Dashboard contact'));
  assert(detail.indexOf('Record history')<detail.indexOf('<h3>Tasks</h3>'));
  assert(detail.includes('Older Record history (2 available)'));
  assert(detail.includes('Audit summary 6'));
  assert(detail.includes('older history may not be included'));
  run('closeModal()');
  fixtures.overview.activity=[];
  for (const page of ["contacts", "deals", "tasks", "activity"]) {
    await run(`state.page='${page}';render()`);
    assert(!nodes.get("#content").innerHTML.includes('role="alert"'));
  }
  assert.equal(run("esc('<script>')"), "&lt;script&gt;");
  assert.equal(run("money(12345)"), "$123.45");
  console.log("PASS: section rendering, empty states, HTML escaping, currency");

  for (const [filter, url] of [
    ["open", "/api/tasks?status=open"],
    ["done", "/api/tasks?status=done"],
    ["", "/api/tasks"],
  ]) {
    await run(`state.page='tasks';state.taskFilter='${filter}';render()`);
    assert.equal(requests.at(-1), url);
  }
  // An open task must remain visible even when the unfiltered endpoint is full of completed work.
  fixtures.tasks = Array.from({ length: 500 }, (_, i) => ({ id: `done-${i}`, status: "done" }));
  fixtures["tasks?status=open"] = [{ id: "open-1", status: "open", title: "Follow up now" }];
  await run("state.page='tasks';state.taskFilter='open';render()");
  assert(nodes.get("#content").innerHTML.includes("Follow up now"));
  console.log("PASS: server-side task filtering precedes result limits");

  let finish = defer("contacts");
  let request = run("openForm('deal')");
  run("location.hash='#activity';route()");
  finish([]);
  await request;
  assert.equal(nodes.get("#modal").open, false);

  finish = defer("contacts");
  request = run("openForm('deal')");
  handlers.keydown({ key: "Escape" });
  finish([]);
  await request;
  assert.equal(nodes.get("#modal").open, false);
  console.log("PASS: navigation and Escape cancel pending forms");

  finish = defer("contacts/c");
  request = run("contactDetail('c')");
  run("closeModal()");
  finish({ contact: { id: "c", name: "Old" }, deals: [{ id: "d", version: 99 }], tasks: [], activity: [] });
  await request;
  assert.equal(nodes.get("#modal").open, false);
  assert(!run('state.deals.some(d=>d.id==="d")'));

  run("state.deals=[{id:'d',version:1}];state.tasks=[{id:'t',version:1}]");
  fixtures["contacts/c"] = {
    contact: { id: "c", name: "Fresh" }, deals: [{ id: "d", version: 2 }],
    tasks: [{ id: "t", version: 3 }], activity: [],
  };
  await run("contactDetail('c')");
  assert.equal(run("state.deals[0].version"), 2);
  assert.equal(run("state.tasks[0].version"), 3);
  console.log("PASS: cancelled details do not mutate cache; fresh details replace versions");

  // Dashboard titles open freshly read task records, not contacts or cached edits.
  run('closeModal()');
  fixtures.overview.tasks = [{id:'t',title:'Cached task',status:'open',priority:'high',due_at:'2000-01-01T00:00:00Z',contact_name:'<Linked person>',linked_contact_id:'outside',agent_work:{status:'available',total:0,items:[]}}];
  await run("state.page='overview';render()");
  const upcoming = nodes.get('#content').innerHTML;
  assert(upcoming.includes('Upcoming Tasks') && upcoming.includes('class="name-button task-title"'));
  assert(upcoming.includes('Contact: &lt;Linked person&gt;'));
  assert(upcoming.includes('Task assignee: Not recorded') && upcoming.includes('Agent work: None saved'));
  assert(upcoming.includes('High priority') && upcoming.includes('Overdue'));
  fixtures.meta = {profile:'default',catalog:{stages:[],fields:{tasks:[{key:'test_value',label:'Custom value'}]}}};
  fixtures['tasks/t'] = {id:'t',title:'Fresh exact task',version:12,status:'open',priority:'normal',due_at:'2030-01-01T00:00:00Z',notes:'Existing private task notes',custom_fields:{test_value:'Retained custom data'}};
  const beforeTaskReads = requests.length, beforeTaskMethods = methods.length;
  handlers.click({target:{closest:()=>({dataset:{action:'task',id:'t'}})}});
  await tick();
  const freshTask = nodes.get('#modal-body').innerHTML;
  assert(freshTask.includes('Fresh exact task') && freshTask.includes('Existing private task notes'));
  assert(freshTask.includes('Retained custom data'));
  assert(requests.slice(beforeTaskReads).includes('/api/tasks/t'));
  assert(!requests.slice(beforeTaskReads).some(url => url.includes('/contacts/')));
  assert(methods.slice(beforeTaskMethods).every(method => method === 'GET'));
  assert.equal(run("state.tasks.find(t=>t.id==='t').version"),12);
  await nodes.get('#edit-task').onclick();
  assert(nodes.get('#modal-body').innerHTML.includes('Existing private task notes'));
  assert(nodes.get('#modal-body').innerHTML.includes('Retained custom data'));
  run('closeModal()');
  let finishTask = defer('tasks/t');
  let taskRequest = run("taskDetail('t')");
  run("location.hash='#activity';route()");
  finishTask({...fixtures['tasks/t'],title:'Late task',version:99});
  await taskRequest;
  assert.equal(nodes.get('#modal').open,false);
  assert.equal(run("state.tasks.find(t=>t.id==='t').version"),12);
  finishTask = defer('tasks/t');
  taskRequest = run("taskDetail('t')");
  handlers.keydown({key:'Escape'});
  finishTask(fixtures['tasks/t']);
  await taskRequest;
  assert.equal(nodes.get('#modal').open,false);
  finishTask = defer('tasks/t');
  taskRequest = run("taskDetail('t')");
  pending.delete('tasks/t');
  await run("taskDetail('t')");
  finishTask({...fixtures['tasks/t'],title:'Older repeated task',version:100});
  await taskRequest;
  assert(nodes.get('#modal-body').innerHTML.includes('Fresh exact task'));
  assert(!nodes.get('#modal-body').innerHTML.includes('Older repeated task'));
  run('closeModal()');
  fixtures['tasks/t'] = {id:'wrong',title:'Wrong record'};
  await run("taskDetail('t')");
  assert.equal(nodes.get('#modal').open,false);
  assert(nodes.get('#toast').textContent.includes('could not be verified'));
  const savedLines = run(`taskAssignmentLines({agent_work:{status:'available',total:5,items:[
    {id:'w1',executor:'Hermes',human_owner:'Real owner',state:'pending',source_task_current:true},
    {id:'w2',executor:'Hermes',human_owner:'Former',state:'cancelled',source_task_current:false},
    {id:'w3',executor:'Hermes',human_owner:'Reviewer',state:'result_reported',source_task_current:true}
  ]}}).join(' | ')`);
  assert(savedLines.includes('Human owner (agent work): Real owner · Saved, not scheduled'));
  assert(savedLines.includes('Cancelled intent; schedule status not checked · Earlier task version'));
  assert(savedLines.includes('Result reported; awaiting human review'));
  assert(savedLines.includes('5 saved assignments; latest 3 shown'));
  assert(run("taskAssignmentLines({schedule_status:'scheduled'}).join(' ')").includes('Unavailable'));
  assert(!run("taskAssignmentLines({schedule_status:'scheduled'}).join(' ')").includes('Agent executor: Hermes'));
  const validItem = {id:'w',executor:'Hermes',human_owner:'Owner',state:'scheduled',source_task_current:true};
  for (const malformed of [
    {total:1,items:[null]}, {total:-1,items:[]}, {total:1,items:[]}, {total:0,items:[validItem]},
    ...[{human_owner:{}},{human_owner:' '},{source_task_current:undefined},{executor:'Made-up agent'},
      {state:'constructor'},{state:'__proto__'},{state:'unrecognized'}].map(patch => ({total:1,items:[{...validItem,...patch}]})),
  ]) {
    const result = run(`taskAssignmentLines(${JSON.stringify({agent_work:{status:'available',...malformed}})}).join(' ')`);
    assert(result.includes('Unavailable'));
    assert(!result.includes('None saved') && !result.includes('Schedule recorded') && !result.includes('[object Object]'));
  }
  fixtures.overview.tasks = [];
  fixtures.meta = {profile:'default',demo:true};
  console.log('PASS: factual upcoming task cards, exact fresh task data, notes/custom fields, read-only opening and navigation/Escape/repeated-click guards');

  run("closeModal()");
  finish = defer("reports/contacts?limit=50&offset=0");
  request = run("state.page='contacts';render()");
  await run("state.page='activity';render()");
  finish({items:[{ id: "stale", name: "Stale" }],total:1});
  await request;
  assert(!run('state.contacts.some(c=>c.id==="stale")'));

  finish = defer("tasks?status=open");
  request = run("state.page='tasks';state.taskFilter='open';render()");
  await run("state.taskFilter='done';render()");
  finish([{ id: "stale-task", status: "open" }]);
  await request;
  assert(!run('state.tasks.some(t=>t.id==="stale-task")'));
  console.log("PASS: stale contact and task list responses cannot replace caches");

  // A unique-contact count is supplied by the server, never derived from deals.
  const chart = run(`stageChart([{stage:'lead',value:300,count:4,contact_count:2},{stage:'won',value:100,count:1,contact_count:1}])`);
  assert(chart.includes('$4') && chart.includes('total deal value'));
  assert(chart.includes('75.0% · 4 deals · 2 distinct contacts'));
  assert.equal((chart.match(/class="donut-segment"/g) || []).length,2);
  assert.equal((run('stageChart([])').match(/class="donut-segment"/g) || []).length,0);
  assert(run('stageChart([])').includes('No deal value to chart'));
  const single = run(`stageChart([{stage:'lead',value:100,count:1,contact_count:1}])`);
  assert(single.includes('stroke-dasharray="100 0"'));
  assert(single.includes('tabindex="0"') && single.includes('<title>Lead:'));
  assert.equal(run('dollarCents("12.34")'),1234);
  assert.throws(() => run('dollarCents("1.001")'));
  assert.throws(() => run('dollarCents("-1")'));
  assert.throws(() => run('dollarCents("20000000.01")'));
  assert.equal(run(`preserveSelection([], 'outside', '', 'contact')[0].id`),'outside');
  assert.equal(run(`preserveSelection([{id:'outside',name:'Present'}], 'outside', '', 'contact').length`),1);
  console.log('PASS: zero/single/multi-stage chart, distinct counts, accessible details, cents, selector preservation');

  run(`location.hash='#contacts';state.query='unrelated';state.filters={company:'unrelated'};openReport({stage:'won'},'Won stage report')`);
  await tick();
  assert.equal(requests.at(-1),'/api/reports/contacts?stage=won&limit=50&offset=0');
  assert.equal(run('state.query'),'');
  assert.equal(run('state.filters.company'),undefined);
  assert(nodes.get('#content').innerHTML.includes('Won stage report'));
  fixtures['reports/contacts?stage=won&limit=50&offset=50'] = {items:[{id:'c',name:'<script>',lifecycle:'lead',deal_stages:['won','lead']}], total:101};
  await run('state.offset=50;render()');
  assert.equal(requests.at(-1),'/api/reports/contacts?stage=won&limit=50&offset=50');
  assert(nodes.get('#content').innerHTML.includes('101 matching contacts'));
  assert(nodes.get('#content').innerHTML.includes('&lt;script&gt;'));
  assert(!nodes.get('#content').innerHTML.includes('Lifecycle'));
  const release = defer('contacts/pending');
  const detailRequest = run("contactDetail('pending')");
  handlers.change({target:{dataset:{filter:'company'},value:'Literal %_'}});
  release({contact:{name:'Obsolete'},deals:[],tasks:[],activity:[]});
  await detailRequest; await tick();
  assert.equal(nodes.get('#modal').open,false);
  assert.equal(run('state.offset'),0);
  assert(requests.at(-1).includes('company=Literal%20%25_'));
  await run(`state.page='deals';state.query='deal';state.stage='won';state.filters={company:'Acme',min_value:'12.34',max_value:'99'};render()`);
  assert.equal(requests.at(-1),'/api/deals?q=deal&stage=won&company=Acme&min_value=1234&max_value=9900');
  await run(`state.page='tasks';state.taskFilter='open';state.filters={priority:'high',due:'overdue'};render()`);
  assert.equal(requests.at(-1),'/api/tasks?q=deal&status=open&priority=high&due=overdue');
  console.log('PASS: preset filter reset, real totals and pagination, escaping, filter cancellation and filter transport');
  run(`adoptCatalog({catalog:{stages:[
    {key:'lead',label:'Discovery & qualify',color:'#123456',probability:40,archived:false},
    {key:'contract',label:'Contract <review>',color:'#654321',probability:80,archived:false},
    {key:'retired',label:'Retired',color:'#999999',probability:10,archived:true}
  ],fields:{contacts:[{key:'zero',label:'Score',type:'number'},{key:'flag',label:'Opt-in',type:'boolean'},
    {key:'old',label:'Old field',type:'text',archived:true}]}}})`);
  assert.equal(run('stages.join(",")'),'lead,contract');
  assert.equal(run('stageLabel("lead")'),'Discovery & qualify');
  assert(run('badge("lead")').includes('>Lead<'), 'Contact type must not adopt stage labels');
  const customChart = run(`stageChart([{stage:'contract',value:100,count:1,contact_count:1}])`);
  assert(customChart.includes('Contract &lt;review&gt;') && customChart.includes('stroke="#654321"'));
  assert(customChart.includes('data-stage="contract"'));
  const customDetails = run(`customFieldDetails('contacts',{custom_fields:{zero:0,flag:false,old:'<value>'}})`);
  assert(customDetails.includes('<dd>0</dd>') && customDetails.includes('<dd>No</dd>'));
  assert(customDetails.includes('(archived)') && customDetails.includes('&lt;value&gt;'));
  assert(customDetails.includes('Edit custom fields in Hermes Desktop.'));
  console.log('PASS: dynamic stage identity/label/color, separate contact types and retained custom values');
  const overdue = run(`taskRows([{id:'late',title:'Call customer',status:'open',due_at:'2020-01-01T12:00:00Z'}])`);
  assert(overdue.includes('Overdue · '), 'Overdue state must not depend on color');
  assert(overdue.includes('aria-pressed="false"'));
  assert(run(`taskRows([{id:'done',title:'Finished',status:'done'}])`).includes('aria-pressed="true"'));
  assert(run(`contactTable([{id:'c',name:'Ada'}])`).includes('role="region" aria-label="Contacts table" tabindex="0"'));
  assert(run('stageChart([])').includes('class="donut-track"'));
  for (const kind of ['contact','deal','task']) {
    await run(`openForm('${kind}')`);
    assert(nodes.get('#modal').open);
    assert(nodes.get('#modal-body').innerHTML.includes('id="dialog-title"'));
    assert(nodes.get('#modal-body').innerHTML.includes('data-action="close">Cancel'));
    run('closeModal()');
  }
  console.log('PASS: non-color overdue labels, completion state, keyboard scroll region, all editor shells');
  console.log("All UI VM smoke checks passed.");
})().catch((error) => { console.error(error); process.exitCode = 1; });

const scheduledTime = "2026-11-10T12:34:56.123456+00:00";
context.scheduledRecord = { due_at: scheduledTime };
assert.equal(vm.runInContext("taskDuePayload(localTime(scheduledRecord.due_at), scheduledRecord)", context), scheduledTime);
assert.notEqual(vm.runInContext("taskDuePayload('2026-11-11T12:35', scheduledRecord)", context), scheduledTime);
console.log("PASS: unchanged scheduled due dates retain exact seconds and microseconds");
