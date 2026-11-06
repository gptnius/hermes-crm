// Dependency-free contract harness. These are SDK doubles, not an Electron/browser QA run.
// Run: node --experimental-vm-modules tests/native_desktop_smoke.mjs
// Set HERMES_SOURCE to a pinned Hermes checkout for optional SDK theme checks.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { webcrypto } from "node:crypto";
const source = await readFile(
  new URL("../desktop/plugin.js", import.meta.url),
  "utf8",
);
const imports = [...source.matchAll(/from\s+['"]([^'"]+)['"]/g)].map(
  (m) => m[1],
);
assert.deepEqual(imports, ["@hermes/plugin-sdk", "react"]);
assert.doesNotMatch(
  source,
  /\bfetch\s*\(|iframe|window\.|document\.|localhost|https?:\/\//,
);
assert.match(source, /workspace_token: editor.workspaceToken/);
try {
  const styles = await readFile(
    `${process.env.HERMES_SOURCE || "/nonexistent-hermes-source"}/apps/desktop/src/styles.css`,
    "utf8",
  );
  for (const match of source.matchAll(/var\((--ui-[a-z-]+)/g))
    assert.ok(
      styles.includes(match[1] + ":"),
      `Unknown SDK theme variable ${match[1]}`,
    );
} catch (e) {
  if (e.code !== "ENOENT") throw e;
  console.log(
    "Pinned Hermes CSS absent; skipping optional source compatibility assertion.",
  );
}
assert.match(source, /workspace_token: data.meta.workspace_token/);
let epoch = 1,
  connection = "local-a",
  profile = "work",
  gateway = "open";
let navigated;
const atom = (get) => ({
  get,
  listen: () => () => {},
  subscribe: () => () => {},
});
const mutableAtom = (initial) => {
  let value = initial;
  return {
    get: () => value,
    set(next) {
      value = next;
    },
  };
};
const host = {
  state: {
    connectionId: atom(() => connection),
    profile: atom(() => profile),
    gateway: atom(() => gateway),
  },
  navigate(path) {
    navigated = path;
  },
};
const sdk = {
  atom: mutableAtom,
  host,
  useValue: (a) => a.get(),
  gatewayActivationEpoch: () => epoch,
  useGatewayActivationEpoch: () => epoch,
  PANES_AREA: "panes",
  ROUTES_AREA: "routes",
  SIDEBAR_NAV_AREA: "sidebar.nav",
  PALETTE_AREA: "palette",
};
const hookStates = new Map();
let current,
  hookIndex,
  effects = [];
const react = {
  createElement(type, props, ...children) {
    return {
      type,
      props: {
        ...props,
        ...(children.length ? { children: children.flat(Infinity) } : {}),
      },
    };
  },
  useState(initial) {
    const i = hookIndex++,
      state = current;
    if (!(i in state))
      state[i] = typeof initial === "function" ? initial() : initial;
    return [
      state[i],
      (value) => {
        state[i] = typeof value === "function" ? value(state[i]) : value;
      },
    ];
  },
  useRef(value) {
    const i = hookIndex++;
    return (current[i] ||= { current: value });
  },
  useEffect(fn, deps) {
    const i = hookIndex++;
    if (!(i in current) || deps.some((v, j) => v !== current[i][j])) {
      current[i] = deps;
      effects.push(fn);
    }
  },
};
const context = vm.createContext({
  console,
  Intl,
  URLSearchParams,
  crypto: webcrypto,
});
const module = new vm.SourceTextModule(source, { context });
await module.link((specifier) => {
  const values = specifier === "@hermes/plugin-sdk" ? sdk : react;
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
const {
  default: plugin,
  routeIdentity,
  initializeLifetime,
  createRouteClient,
  createPayload,
  CRMRoot,
} = module.namespace;
assert.equal(plugin.id, "hermes-crm");
assert.equal(plugin.defaultEnabled, false);
let contributions;
plugin.register({
  registerMany(value) {
    contributions = value;
  },
});
assert.equal(contributions.length, 4);
assert.equal(contributions[0].area, "panes");
assert.equal(contributions[0].data.placement, "main");
assert.equal(contributions[1].data.path, "/hermes-crm");
assert.equal(contributions[2].data.path, "/hermes-crm");
contributions[3].data.run();
assert.equal(navigated, "/hermes-crm");
assert.deepEqual(
  JSON.parse(JSON.stringify(createPayload({ name: "Ada" }, "retry-key"))),
  { data: { name: "Ada" }, idempotency_key: "retry-key" },
);

const calls = [];
let release;
const delayed = {
  registerMany() {},
  onDispose() {},
  setTimeout() {},
  setInterval() {},
  rest(path, options) {
    calls.push([path, options]);
    return new Promise((resolve) => {
      release = resolve;
    });
  },
};
initializeLifetime(delayed);
let client = createRouteClient(delayed, routeIdentity(delayed));
let pending = client.request("/contacts");
profile = "other";
release([{ name: "PRIVATE old profile" }]);
await assert.rejects(pending, /previous connection or profile/);
await assert.rejects(
  client.request("/contacts", { method: "POST" }),
  /changed/,
);
assert.equal(calls.length, 1);
profile = "work";
client = createRouteClient(delayed, routeIdentity(delayed));
pending = client.request("/meta");
connection = "remote-b";
release({});
await assert.rejects(pending, /previous connection or profile/);
client = createRouteClient(delayed, routeIdentity(delayed));
pending = client.request("/meta");
epoch++;
release({});
await assert.rejects(pending, /previous connection or profile/);
client = createRouteClient(delayed, routeIdentity(delayed));
pending = client.request("/tasks");
client.dispose();
release([]);
await assert.rejects(pending, /previous connection or profile/);
client = createRouteClient(delayed, routeIdentity(delayed));
gateway = "connecting";
await assert.rejects(client.request("/tasks", { method: "POST" }), /changed/);
gateway = "open";

function render(node) {
  if (!node || typeof node !== "object") return node;
  if (typeof node.type === "function") {
    const key = node.type.name + ":" + (node.props.key || "");
    current = hookStates.get(key) || [];
    hookStates.set(key, current);
    hookIndex = 0;
    return render(node.type(node.props));
  }
  return {
    ...node,
    props: { ...node.props, children: (node.props.children || []).map(render) },
  };
}
function all(node, predicate) {
  return !node || typeof node !== "object"
    ? []
    : [
        ...(predicate(node) ? [node] : []),
        ...(node.props.children || []).flatMap((child) =>
          all(child, predicate),
        ),
      ];
}
function text(node) {
  return typeof node !== "object"
    ? String(node ?? "")
    : (node?.props.children || []).map(text).join(" ");
}
const sample = {
  "/meta": { profile, backend: "sqlite", workspace_token: "workspace-a" },
  "/overview": {
    contacts: 1,
    open_deals: 1,
    pipeline_value: 50000,
    weighted_value: 25000,
    won_value: 0,
    open_tasks: 0,
    overdue_tasks: 0,
    stages: [{ stage: "lead", count: 1, value: 50000 }],
    activity: [],
    tasks: [],
  },
  "/contacts": [
    {
      id: "c1",
      version: 1,
      name: "Ada",
      email: "ada@example.test",
      company: "Synthetic",
      lifecycle: "lead",
    },
  ],
  "/deals": [],
  "/tasks": [],
  "/activity": [],
};
const writes = [],
  cleanups = [];
const ctx = {
  registerMany() {},
  onDispose() {},
  async rest(path, options) {
    if (options) {
      writes.push([path, options]);
      return {};
    }
    if (path === "/snapshot")
      return Object.fromEntries(
        Object.entries(sample).map(([key, value]) => [key.slice(1), value]),
      );
    if (path.startsWith("/reports/contacts?")) return { items: sample["/contacts"], total: 1, limit: 50, offset: 0 };
    return sample[path.split("?")[0]];
  },
  setInterval() {
    return () => cleanups.push("interval");
  },
  setTimeout(fn) {
    Promise.resolve().then(fn);
    return () => cleanups.push("timeout");
  },
};
initializeLifetime(ctx);
const root = () => render({ type: CRMRoot, props: { ctx } });
root();
const disposers = effects
  .splice(0)
  .map((fn) => fn())
  .filter(Boolean);
await new Promise((resolve) => setImmediate(resolve));
let tree = root();
assert.match(text(tree), /Relationship intelligence/);
assert.match(text(tree), /Weighted forecast/);
assert.match(text(tree), /Active app profile: work/);
all(
  tree,
  (n) => n.type === "button" && text(n) === "Contacts",
)[0].props.onClick();
tree = root();
for (const fn of effects.splice(0)) fn();
await new Promise((resolve) => setImmediate(resolve));
tree = root();
assert.match(text(tree), /Ada/);
all(
  tree,
  (n) => n.type === "button" && text(n) === "+ Contact",
)[0].props.onClick();
tree = root();
const nameField = all(
  tree,
  (n) => n.type === "label" && text(n).startsWith("Full name"),
)[0];
nameField.props.children
  .find((n) => n?.type === "input")
  .props.onChange({ target: { value: "New contact" } });
tree = root();
const form = all(tree, (n) => n.type === "form")[0];
await form.props.onSubmit({ preventDefault() {} });
assert.equal(writes.length, 1);
assert.equal(writes[0][0], "/contacts");
assert.equal(writes[0][1].body.workspace_token, "workspace-a");
assert.equal(writes[0][1].body.data.name, "New contact");
assert.match(writes[0][1].body.idempotency_key, /^[0-9a-f-]{36}$/);
// Route transition removes old records synchronously, before any new read settles.
profile = "fresh-profile";
tree = root();
assert.doesNotMatch(text(tree), /Ada/);
gateway = "connecting";
tree = root();
assert.match(text(tree), /paused/);
assert.equal(all(tree, (n) => n.type === "form").length, 0);
for (const dispose of disposers) dispose();
assert.ok(cleanups.includes("interval"));
console.log(
  "PASS native SDK registration, import allowlist, scoped REST, stale response/write rejection, component render, create payload, profile-remount, timer cleanup. React behavior is modeled by test doubles; no live Hermes/browser verification.",
);
