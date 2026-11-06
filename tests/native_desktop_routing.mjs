// Dependency-free, synchronous SDK transition/legacy-load contract tests.
// Run: node --experimental-vm-modules tests/native_desktop_routing.mjs
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
const source = await readFile(
  new URL("../desktop/plugin.js", import.meta.url),
  "utf8",
);
assert.match(source, /import \* as sdk from ["']@hermes\/plugin-sdk["']/);
function atom(initial) {
  let value = initial;
  const listeners = new Set();
  return {
    get: () => value,
    set(next) {
      if (Object.is(value, next)) return;
      value = next;
      for (const fn of [...listeners]) fn(value);
    },
    listen(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    subscribe(fn) {
      fn(value);
      return this.listen(fn);
    },
    listeners,
  };
}
const h = (type, props, ...children) => ({
  type,
  props: { ...props, children },
});
const react = {
  createElement: h,
  useState() {
    throw Error("Unexpected hook");
  },
  useEffect() {
    throw Error("Unexpected hook");
  },
  useRef() {
    throw Error("Unexpected hook");
  },
};
async function load(sdk) {
  const context = vm.createContext({ Intl, URLSearchParams });
  const module = new vm.SourceTextModule(source, { context });
  await module.link((name) => {
    const exports = name === "@hermes/plugin-sdk" ? sdk : react;
    return new vm.SyntheticModule(
      Object.keys(exports),
      function () {
        for (const [key, value] of Object.entries(exports))
          this.setExport(key, value);
      },
      { context },
    );
  });
  await module.evaluate();
  return module.namespace;
}
const constants = {
  PANES_AREA: "panes",
  ROUTES_AREA: "routes",
  SIDEBAR_NAV_AREA: "sidebar.nav",
  PALETTE_AREA: "palette",
};
const stores = {
  profile: atom("A"),
  connectionId: atom("connection-A"),
  gateway: atom("open"),
};
let epoch = 1;
const sdk = {
  ...constants,
  atom,
  host: { state: stores, navigate() {} },
  useValue: (store) => store.get(),
  gatewayActivationEpoch: () => epoch,
  useGatewayActivationEpoch: () => epoch,
};
const module = await load(sdk);
const callbacks = [],
  calls = [];
let contributions, resolvePending;
const ctx = {
  registerMany(items) {
    contributions = items;
  },
  onDispose(fn) {
    callbacks.push(fn);
  },
  setTimeout() {
    throw Error("No component mounted; timers must not run");
  },
  setInterval() {
    throw Error("No component mounted; timers must not run");
  },
  rest(path, options) {
    calls.push([path, options]);
    return new Promise((resolve) => {
      resolvePending = resolve;
    });
  },
};
module.default.register(ctx);
assert.equal(contributions.length, 4);
for (const store of Object.values(stores))
  assert.equal(
    store.listeners.size,
    1,
    "Observer is installed at register, before React mounting",
  );
const client = () => module.createRouteClient(ctx, module.routeIdentity(ctx));
function rootKey() {
  const wrapper = module.CRMRoot({ ctx });
  return wrapper.type(wrapper.props).props.key;
}
for (const [name, transition] of [
  [
    "gateway reconnect",
    () => {
      stores.gateway.set("closed");
      stores.gateway.set("open");
    },
  ],
  [
    "profile A→B→A",
    () => {
      stores.profile.set("B");
      stores.profile.set("A");
    },
  ],
  [
    "connection A→B→A",
    () => {
      stores.connectionId.set("connection-B");
      stores.connectionId.set("connection-A");
    },
  ],
  [
    "same-valued route activation",
    () => {
      epoch++;
    },
  ],
]) {
  const old = client(),
    before = rootKey(),
    callCount = calls.length;
  const pending = old.request("/snapshot");
  transition(); // Synchronous; no React effect, render, await or timer between values.
  assert.equal(old.current(), false, name);
  assert.notEqual(rootKey(), before, `${name} changes reactive workspace key`);
  resolvePending({ old: true });
  await assert.rejects(pending, /previous connection or profile/, name);
  await assert.rejects(
    old.request("/contacts", { method: "POST", body: { stale: true } }),
    /changed/,
    name,
  );
  assert.equal(
    calls.length,
    callCount + 1,
    `${name} blocks stale writes before transport`,
  );
  assert.equal(client().current(), true, `${name} allows fresh clients`);
}
// Component Strict Mode cleanup/replay must not revive requests from the first mount.
const strictClient = client();
const pendingStrict = strictClient.request("/snapshot");
strictClient.dispose();
strictClient.activate();
resolvePending({ previousMount: true });
await assert.rejects(pendingStrict, /previous connection or profile/);
assert.equal(strictClient.current(), true);
const prior = client();
const pendingUnload = prior.request("/snapshot");
for (const dispose of callbacks) dispose();
prior.activate();
assert.equal(prior.current(), false, "Activation cannot undo plugin unload");
resolvePending({ unloaded: true });
await assert.rejects(pendingUnload, /previous connection or profile/);
for (const store of Object.values(stores))
  assert.equal(store.listeners.size, 0);
module.default.register(ctx);
assert.equal(prior.current(), false, "A reload cannot revive an old lifetime");
assert.equal(client().current(), true);
for (const store of Object.values(stores))
  assert.equal(store.listeners.size, 1);
for (const dispose of callbacks) dispose();
for (const store of Object.values(stores))
  assert.equal(store.listeners.size, 0);

// Exact 0.17 capability shape: namespace import must link even without new exports.
const legacyStores = { profile: atom("default"), gateway: atom("open") };
const legacySDK = {
  ...constants,
  atom,
  useValue: (store) => store.get(),
  host: { state: legacyStores, navigate() {} },
};
function renderText(node) {
  if (node == null || typeof node !== "object") return String(node ?? "");
  if (Array.isArray(node)) return node.map(renderText).join(" ");
  if (typeof node.type === "function") return renderText(node.type(node.props));
  return renderText(node.props.children);
}
for (const [name, exports, missingTimers] of [
  ["Desktop 0.17", legacySDK, true],
  ["current SDK without scoped timers", sdk, true],
]) {
  const loaded = await load(exports);
  let restCalls = 0,
    timerCalls = 0,
    registered;
  const legacyCtx = {
    registerMany(value) {
      registered = value;
    },
    rest() {
      restCalls++;
      throw Error("Legacy REST forbidden");
    },
    onDispose() {},
  };
  // No timer substitutes: missing timers require a compatibility screen.
  if (!missingTimers) {
    legacyCtx.setTimeout = () => timerCalls++;
    legacyCtx.setInterval = () => timerCalls++;
  }
  loaded.default.register(legacyCtx);
  assert.equal(registered[0].data.placement, "main");
  assert.equal(registered[1].data.path, "/hermes-crm");
  const text = renderText(registered[0].render());
  assert.match(text, /needs a newer Desktop SDK/, name);
  assert.match(text, /No CRM data has been read or changed/, name);
  assert.equal(restCalls, 0);
  assert.equal(timerCalls, 0);
  for (const store of Object.values(exports.host.state))
    assert.equal(store.listeners.size, 0);
}
// Registration failures are detected before cleanup registration or subscriptions.
for (const missing of ["registerMany", "navigate", ...Object.keys(constants)]) {
  const exports = { ...sdk, host: { ...sdk.host } };
  let effects = 0;
  const incompleteCtx = {
    registerMany() {
      effects++;
    },
    onDispose() {
      effects++;
    },
    rest() {
      effects++;
    },
    setTimeout() {
      effects++;
    },
    setInterval() {
      effects++;
    },
  };
  if (missing === "registerMany") delete incompleteCtx.registerMany;
  else if (missing === "navigate") delete exports.host.navigate;
  else delete exports[missing];
  const loaded = await load(exports);
  assert.throws(
    () => loaded.default.register(incompleteCtx),
    (error) =>
      /compatibility error/.test(error.message) &&
      error.message.includes(missing),
  );
  assert.equal(
    effects,
    0,
    `${missing}: fail before registration, REST, timers or cleanup callbacks`,
  );
  for (const store of Object.values(stores))
    assert.equal(store.listeners.size, 0, `${missing}: no listener leak`);
}
console.log(
  "PASS pre-mount synchronous generation, same-tick reconnect/profile/source ABA, official epoch, stale reads/writes, Strict Mode request invalidation, permanent unload/reload cleanup, and legacy namespace-import compatibility with zero REST/timers.",
);
