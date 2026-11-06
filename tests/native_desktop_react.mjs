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
let reportTotal = 1;
let delayReport = false, releaseReport;
let delayDetail = false,
  releaseDetail;
const pluginDisposers = [];
const ctx = {
  onDispose(fn) {
    pluginDisposers.push(fn);
  },
  registerMany() {},
  async rest(path, options) {
    calls.push({ path, profile: profile.get(), connection: connection.get() });
    if (options) {
      writes.push({ path, options, profile: profile.get() });
      return {};
    }
    if (path.split("?")[0] === "/contacts/c1" && delayDetail)
      return new Promise((resolve) => {
        releaseDetail = resolve;
      });
    if (path.startsWith("/reports/contacts?") && delayReport) return new Promise(resolve => { releaseReport = resolve; });
    const routes = {
      "/meta": {
        backend: backendKind,
        profile: profile.get(),
        workspace_token: `token-${profile.get()}${backendTokenSuffix}`,
      },
      "/overview": overview,
      "/contacts": profile.get() === "work" ? [contact] : [],
      "/reports/contacts": { items: profile.get() === "work" ? [{ ...contact, deal_stages: ["lead", "won"] }] : [], total: profile.get() === "work" ? reportTotal : 0, limit: 50, offset: 0 },
      "/deals": [],
      "/tasks": [task],
      "/activity": [],
      "/contacts/c1": { contact, deals: [], tasks: [task], activity: [] },
      "/tasks/t1": task,
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
let root;
await act(async () => {
  root = Renderer.create(
    React.createElement(
      React.StrictMode,
      null,
      React.createElement(module.namespace.CRMRoot, { ctx }),
    ),
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
    target.props.onClick();
  });
  await flush();
};
assert.match(text(), /Relationship intelligence/);
assert.match(text(), /Weighted forecast/);
assert.equal(intervals.size, 1, "Strict Mode replay leaves one live interval");
// Chart geometry, distinct counts, accessible focus/hover, zero and single-stage cases.
assert.match(text(), /No deal value to chart/);
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
await act(async () => control("Company").props.onChange({ target: { value: "unrelated" } }));
await flush();
await click("Overview");
await act(async () => root.root.findAllByType("button").find(node => node.props["aria-label"]?.startsWith("Lead:")).props.onClick());
await flush();
let reportParams = new URLSearchParams(calls.findLast(call => call.path.startsWith("/reports/contacts?")).path.split("?")[1]);
assert.equal(reportParams.get("stage"), "lead");
assert.equal(reportParams.get("company"), null);
assert.equal(reportParams.get("workspace_token"), "token-work");
assert.match(text(), /Linked stages: Lead, Won/);
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
await act(async () => control("Company").props.onChange({ target: { value: "pending-editor" } }));
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
await act(async () => control("Company").props.onChange({ target: { value: "old" } }));
await flush();
const oldReport = releaseReport;
delayReport = false;
await act(async () => control("Company").props.onChange({ target: { value: "new" } }));
await flush();
await act(async () => oldReport({ items: [{ ...contact, name: "Stale filtered person" }], total: 999 }));
assert.doesNotMatch(text(), /Stale filtered person/);
// Changing a filter also invalidates pending record detail.
delayDetail = true;
await act(async () => { root.root.findAllByType("button").find(node => flatten(node.children).includes("Ada Example")).props.onClick(); });
await act(async () => control("Email").props.onChange({ target: { value: "missing" } }));
await act(async () => releaseDetail({ contact, deals: [], tasks: [], activity: [] }));
assert.doesNotMatch(text(), /Record details/);
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
assert.equal(field("Full name").props.autoFocus, true);
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
await click("Activity");
await act(async () => {
  releaseDetail({ contact, deals: [], tasks: [], activity: [] });
});
assert.doesNotMatch(text(), /Record details/);
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
await click("Contacts");
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
await click("Refresh");
await click("Explore demo data");
assert.match(text(), /Sqlite backend/);
backendTokenSuffix = "-changed";
backendKind = "postgres";
await click("Refresh");
assert.match(
  text(),
  /Sqlite backend/,
  "Confirmation preserves the backend named when opened",
);
const demoWriteIndex = writes.length;
await click("Add synthetic records");
assert.equal(writes[demoWriteIndex].path, "/demo");
assert.equal(
  writes[demoWriteIndex].options.body.workspace_token,
  "token-new-agent",
  "Demo cannot silently move to the refreshed backend token",
);
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
  "PASS actual React 19.3.0 Strict Mode: zero/single/multiple charts, focus/hover/keyboard/drillthrough, server filter pagination/races and current-ID preservation, dashboard/contacts/forms, name-only create, versioned edit/complete, exact scheduled timestamp, scoped snapshot/search, captured demo target, workspace token, stale detail navigation, profile/source remount, stale form rejection, subscription/timer cleanup. SDK transport is a fixture; no live Hermes UI QA claimed.",
);
