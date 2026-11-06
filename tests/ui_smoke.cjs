// Lightweight, dependency-free UI logic regression tests. This is not a browser/layout test.
// Run from any directory: node /path/to/hermes-crm/tests/ui_smoke.cjs
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");

const nodes = new Map();
const handlers = {};
const requests = [];
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
  fetch: async (url) => {
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

  run("closeModal()");
  finish = defer("contacts?q=");
  request = run("state.page='contacts';render()");
  await run("state.page='activity';render()");
  finish([{ id: "stale", name: "Stale" }]);
  await request;
  assert(!run('state.contacts.some(c=>c.id==="stale")'));

  finish = defer("tasks?status=open");
  request = run("state.page='tasks';state.taskFilter='open';render()");
  await run("state.taskFilter='done';render()");
  finish([{ id: "stale-task", status: "open" }]);
  await request;
  assert(!run('state.tasks.some(t=>t.id==="stale-task")'));
  console.log("PASS: stale contact and task list responses cannot replace caches");
  console.log("All UI VM smoke checks passed.");
})().catch((error) => { console.error(error); process.exitCode = 1; });

const scheduledTime = "2026-11-10T12:34:56.123456+00:00";
context.scheduledRecord = { due_at: scheduledTime };
assert.equal(vm.runInContext("taskDuePayload(localTime(scheduledRecord.due_at), scheduledRecord)", context), scheduledTime);
assert.notEqual(vm.runInContext("taskDuePayload('2026-11-11T12:35', scheduledRecord)", context), scheduledTime);
console.log("PASS: unchanged scheduled due dates retain exact seconds and microseconds");
