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
    const routes = {
      "/meta": {
        backend: backendKind,
        profile: profile.get(),
        workspace_token: `token-${profile.get()}${backendTokenSuffix}`,
      },
      "/overview": overview,
      "/contacts": profile.get() === "work" ? [contact] : [],
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
  "PASS actual React 19.3.0 Strict Mode: dashboard/contacts/forms, name-only create, versioned edit/complete, exact scheduled timestamp, scoped snapshot/search, captured demo target, workspace token, stale detail navigation, profile/source remount, stale form rejection, subscription/timer cleanup. SDK transport is a fixture; no live Hermes UI QA claimed.",
);
