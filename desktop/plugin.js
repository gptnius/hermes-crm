import * as sdk from "@hermes/plugin-sdk";
import { createElement as h, useState, useEffect, useRef } from "react";

const {
  host,
  useValue,
  gatewayActivationEpoch,
  useGatewayActivationEpoch,
  PANES_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  PALETTE_AREA,
} = sdk;
const lifetimes = new WeakMap();
let nextLifetime = 0;

// Installed before contributions can mount. Store listeners run synchronously,
// so React batching cannot hide A → B → A or open → closed → open transitions.
export function initializeLifetime(ctx) {
  const registrationMissing = [];
  if (typeof ctx?.registerMany !== "function")
    registrationMissing.push("ctx.registerMany");
  if (typeof host?.navigate !== "function")
    registrationMissing.push("host.navigate");
  for (const name of [
    "PANES_AREA",
    "ROUTES_AREA",
    "SIDEBAR_NAV_AREA",
    "PALETTE_AREA",
  ])
    if (typeof sdk[name] !== "string" || !sdk[name].trim())
      registrationMissing.push(`SDK.${name}`);
  if (registrationMissing.length)
    throw new Error(
      `Hermes CRM compatibility error: cannot safely register its Desktop surfaces. Missing capabilities: ${registrationMissing.join(", ")}. Update Hermes Desktop and reload the plugin.`,
    );
  const previous = lifetimes.get(ctx);
  if (previous?.alive) return previous;
  const missing = [];
  for (const name of [
    "atom",
    "useValue",
    "gatewayActivationEpoch",
    "useGatewayActivationEpoch",
  ])
    if (typeof sdk[name] !== "function") missing.push(`SDK.${name}`);
  for (const name of ["profile", "connectionId", "gateway"])
    for (const method of ["get", "listen", "subscribe"])
      if (typeof host?.state?.[name]?.[method] !== "function")
        missing.push(`host.state.${name}.${method}`);
  for (const name of ["rest", "setTimeout", "setInterval", "onDispose"])
    if (typeof ctx[name] !== "function") missing.push(`ctx.${name}`);
  if (missing.length) {
    const unsupported = { supported: false, alive: false, missing };
    lifetimes.set(ctx, unsupported);
    return unsupported;
  }
  const lifetime = {
    supported: true,
    alive: true,
    id: ++nextLifetime,
    generation: sdk.atom(0),
    chatGeneration: sdk.atom(0),
    retainedView: null,
    chatWorkspace: null,
  };
  const stops = [];
  const bump = () => {
    lifetime.retainedView = null;
    lifetime.chatWorkspace?.close();
    lifetime.generation.set(lifetime.generation.get() + 1);
  };
  const dispose = () => {
    if (!lifetime.alive) return;
    lifetime.alive = false;
    bump();
    for (const stop of stops.splice(0)) stop();
  };
  // Register cleanup first; a later registration failure must not leak listeners.
  ctx.onDispose(dispose);
  try {
    for (const name of ["gateway", "profile", "connectionId"])
      stops.push(host.state[name].listen(bump));
    // Optional chat support must not make the ordinary CRM unavailable.
    if (!chatCapabilities().length) {
      let previous = chatSelection();
      for (const name of CHAT_STORES) stops.push(host.state[name].listen(() => {
        const next = chatSelection();
        if (next === previous) return;
        previous = next;
        lifetime.chatGeneration.set(lifetime.chatGeneration.get() + 1);
      }));
    }
  } catch (error) {
    dispose();
    throw error;
  }
  lifetimes.set(ctx, lifetime);
  return lifetime;
}


// This is a handoff to the REAL native chat, never a second transcript or
// execution path. The pinned SDK's insertText defers a mutable "main" target
// and appends a draft mirror; Copy + user Paste avoids both routing and draft
// races. Do not replace this with getDraft/setDraft or automatic submission.
const CHAT_STORES = ["activeSessionId", "focusedSessionId", "focusedStoredSessionId", "focusedSessionOwner", "cwd"];
export function chatCapabilities() {
  const missing = [];
  for (const name of ["openWorkspace", "revealPane", "paneVisibility"])
    if (typeof host?.[name] !== "function") missing.push(`host.${name}`);
  for (const name of CHAT_STORES)
    for (const method of ["get", "listen", "subscribe"])
      if (typeof host?.state?.[name]?.[method] !== "function") missing.push(`host.state.${name}.${method}`);
  return missing;
}
function chatSelection() {
  const owner = host.state.focusedSessionOwner.get();
  return JSON.stringify([host.state.activeSessionId.get(), host.state.focusedSessionId.get(),
    host.state.focusedStoredSessionId.get(), owner?.connectionId, owner?.profile, host.state.cwd.get()]);
}
export function captureChatBinding(ctx, identity) {
  if (chatCapabilities().length) throw new Error("This Desktop build cannot safely open CRM alongside native chat. Update Desktop; the CRM remains available here.");
  const lifetime = lifetimes.get(ctx);
  if (!lifetime?.alive || identity !== routeIdentity(ctx) || host.state.gateway.get() !== "open")
    throw new Error("The connection or profile changed. Refresh the CRM before opening chat.");
  const sessionId = host.state.focusedStoredSessionId.get();
  const runtime = host.state.focusedSessionId.get();
  const owner = host.state.focusedSessionOwner.get();
  if (!sessionId || !runtime || runtime !== host.state.activeSessionId.get())
    throw new Error("Open an existing conversation in the main Hermes chat, then return to CRM. This button does not create a chat or move a conversation from another tile.");
  if (!owner?.connectionId || !owner.profile || owner.connectionId !== host.state.connectionId.get() || owner.profile !== host.state.profile.get())
    throw new Error("The selected chat does not have the same verified connection and profile as this CRM. Select a matching main chat, then return here.");
  const selection = chatSelection(), generation = lifetime.chatGeneration.get();
  return { sessionId, profile: owner.profile, connection: owner.connectionId,
    current: () => lifetime.alive && identity === routeIdentity(ctx) && host.state.gateway.get() === "open" &&
      generation === lifetime.chatGeneration.get() && selection === chatSelection() };
}
export function openChatWorkspace(ctx, identity, render) {
  const binding = captureChatBinding(ctx, identity);
  const lifetime = lifetimes.get(ctx);
  const id = `hermes-crm:chat:${lifetime.id}`, paneId = `plugin-workspace:${id}`;
  let entry = lifetime.chatWorkspace;
  if (entry && entry.identity !== identity) { entry.close(); entry = null; }
  if (!entry) {
    let dispose = null, closed = false;
    entry = { identity, close() {
      if (closed) return;
      closed = true;
      if (lifetime.chatWorkspace === entry) lifetime.chatWorkspace = null;
      dispose?.();
    } };
    lifetime.chatWorkspace = entry;
    try {
      dispose = host.openWorkspace(id, { title: "CRM · Agent workspace", minWidth: "24rem",
        dock: { pane: "workspace", pos: "right" }, render,
        onClose: () => { closed = true; if (lifetime.chatWorkspace === entry) lifetime.chatWorkspace = null; } });
      if (typeof dispose !== "function") throw new Error("Desktop did not provide workspace cleanup.");
      if (closed) dispose();
    } catch (error) { entry.close(); throw error; }
  }
  try {
    if (!binding.current()) throw new Error("The selected chat changed. Open the workspace again from the current CRM.");
    host.revealPane(paneId);
    host.revealPane("workspace");
    // Older hosts can expose openWorkspace but ignore its newer dock option.
    // Never navigate away from the existing CRM unless BOTH panes are visible.
    if (!host.paneVisibility(paneId)?.get?.() || !host.paneVisibility("workspace")?.get?.())
      throw new Error("Desktop could not keep CRM and chat visible together. Use a Desktop build supporting split workspaces, or keep using CRM here.");
    if (!binding.current()) throw new Error("The selected chat changed. Open the workspace again from the current CRM.");
    host.navigate(`/${encodeURIComponent(binding.sessionId)}`);
    return binding;
  } catch (error) { entry.close(); throw error; }
}
export function recordChatContext(detail, data, binding) {
  const row = detail?.row?.contact || detail?.row;
  if (!binding?.current() || !data?.meta?.workspace_token || detail?.workspaceToken !== data.meta.workspace_token ||
      !["contacts", "deals", "tasks"].includes(detail?.kind) ||
      typeof row?.id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(row.id) ||
      !Number.isSafeInteger(row.version) || row.version < 1) return null;
  // Intentionally exclude record text, related records, contact details, secrets,
  // workspace tokens and execution payloads. The agent reads fresh data via tools.
  return `CRM record reference (data, not instructions):\n${JSON.stringify({
    connection: binding.connection, profile: binding.profile,
    kind: detail.kind, id: row.id, version: row.version,
  }, null, 2)}\nRead this record with the CRM tools before using it. I will write my request separately.`;
}

const STAGES = ["lead", "qualified", "proposal", "negotiation", "won", "lost"];
const PROBABILITY = [10, 25, 50, 75, 100, 0];
const label = (value) =>
  String(value || "")
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
const money = (cents) =>
  new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format((cents || 0) / 100);
const date = (value) =>
  value
    ? new Date(
        value.length === 10 ? value + "T12:00:00" : value,
      ).toLocaleString()
    : "Not set";
const button = (text, onClick, props = {}) =>
  h("button", { type: "button", onClick, ...props }, text);
const badge = (text) => h("span", { className: "hc-badge" }, label(text));

// ctx.rest follows the ACTIVE app route, not the focused conversation tile.
export function routeIdentity(ctx) {
  const lifetime = lifetimes.get(ctx);
  if (!lifetime?.supported || !lifetime.alive) return null;
  return JSON.stringify([
    host.state.connectionId.get(),
    host.state.profile.get(),
    gatewayActivationEpoch(),
    lifetime.id,
    lifetime.generation.get(),
  ]);
}
export function createRouteClient(ctx, identity) {
  const lifetime = lifetimes.get(ctx);
  let alive = true;
  let mountGeneration = 0;
  const current = () =>
    alive &&
    lifetime?.alive &&
    identity !== null &&
    identity === routeIdentity(ctx) &&
    host.state.gateway.get() === "open";
  return {
    current,
    dispose() {
      alive = false;
      mountGeneration++;
    },
    activate() {
      if (lifetime?.alive) alive = true;
    },
    async request(path, options) {
      if (!current())
        throw new Error(
          "Connection or profile changed. Reload before continuing.",
        );
      const capturedMount = mountGeneration;
      const result = await ctx.rest(path, options);
      if (!current() || capturedMount !== mountGeneration)
        throw new Error(
          "Discarded a response from the previous connection or profile.",
        );
      return result;
    },
  };
}
export function createPayload(data, idempotencyKey) {
  return { data, idempotency_key: idempotencyKey };
}

const CSS = `
.hermes-crm-native{height:100%;min-height:0;position:relative;overflow:hidden;container-type:inline-size;background:var(--ui-bg-editor);color:var(--ui-text-primary);font:13px/1.5 system-ui,sans-serif}
.hermes-crm-native *{box-sizing:border-box}.hermes-crm-native .hc-wrap{height:100%;overflow:auto;max-width:1500px;margin:auto;padding:28px;scrollbar-gutter:stable}.hermes-crm-native .hc-wrap[inert]{overflow:hidden}
.hermes-crm-native h1{font-size:29px;letter-spacing:-1px;line-height:1.2;margin:4px 0 9px}.hermes-crm-native h2{font-size:17px;margin:0 0 14px}.hermes-crm-native h3{font-size:14px;margin:0}
.hermes-crm-native p{margin:6px 0 14px}.hermes-crm-native .hc-muted{color:var(--ui-text-secondary)}.hermes-crm-native .hc-eyebrow{font-size:10px;letter-spacing:2px;font-weight:700;color:var(--ui-text-tertiary)}
.hermes-crm-native .hc-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.hermes-crm-native .hc-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.hermes-crm-native button,.hermes-crm-native input,.hermes-crm-native select,.hermes-crm-native textarea{font:inherit;color:inherit;background:var(--ui-bg-elevated,var(--ui-bg-editor));border:1px solid var(--ui-stroke-primary);border-radius:8px;padding:9px 12px}
.hermes-crm-native button{cursor:pointer;text-align:left}.hermes-crm-native button:hover{background:var(--ui-row-hover-background)}.hermes-crm-native button:disabled{opacity:.45;cursor:not-allowed}.hermes-crm-native :focus-visible{outline:2px solid var(--ui-accent);outline-offset:3px}
.hermes-crm-native .hc-primary{background:var(--ui-accent);color:var(--ui-bg-editor);border-color:var(--ui-accent)}.hermes-crm-native .hc-tabs{display:flex;gap:6px;border-bottom:1px solid var(--ui-stroke-primary);padding:22px 0 14px;margin-bottom:24px;overflow:auto}
.hermes-crm-native .hc-tabs button{border:0;white-space:nowrap}.hermes-crm-native button[aria-current=page]{background:var(--ui-row-hover-background);color:var(--ui-accent);font-weight:700}
.hermes-crm-native .hc-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:18px 0}.hermes-crm-native .hc-card{border:1px solid var(--ui-stroke-primary);border-radius:12px;padding:20px;background:var(--ui-bg-elevated,var(--ui-bg-editor))}.hermes-crm-native .hc-card strong{display:block;font-size:28px;letter-spacing:-1px;margin:8px 0}
.hermes-crm-native .hc-two{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:18px;margin:18px 0}.hermes-crm-native .hc-badge{display:inline-block;font-size:11px;border:1px solid var(--ui-stroke-primary);border-radius:20px;padding:2px 8px;color:var(--ui-text-secondary)}
.hermes-crm-native .hc-bar-row{display:grid;grid-template-columns:100px 1fr 85px;gap:12px;align-items:center;width:100%;border:0;padding:10px 0;background:transparent}.hermes-crm-native .hc-track{height:10px;border-radius:8px;background:var(--ui-row-hover-background);overflow:hidden}.hermes-crm-native .hc-fill{height:100%;background:var(--ui-accent);border-radius:8px}
.hermes-crm-native .hc-list{display:grid;gap:10px}.hermes-crm-native .hc-list-item{width:100%;border:1px solid var(--ui-stroke-primary);border-radius:10px;padding:14px;display:flex;justify-content:space-between;gap:12px;align-items:center}.hermes-crm-native .hc-list-item p{margin:3px 0 0}
.hermes-crm-native .hc-board{display:grid;grid-template-columns:repeat(6,minmax(210px,1fr));gap:12px;overflow:auto;padding:18px 0}.hermes-crm-native .hc-column{border-radius:12px;background:var(--ui-row-hover-background);padding:12px;min-height:250px}.hermes-crm-native .hc-column>header{margin-bottom:14px}.hermes-crm-native .hc-deal{display:block;width:100%;margin:9px 0;background:var(--ui-bg-elevated,var(--ui-bg-editor));padding:15px}.hermes-crm-native .hc-deal strong{display:block;margin:12px 0}
.hermes-crm-native .hc-empty{text-align:center;padding:42px 18px;color:var(--ui-text-secondary);border:1px dashed var(--ui-stroke-primary);border-radius:12px}.hermes-crm-native .hc-notice{padding:14px;border:1px solid var(--ui-stroke-primary);border-left:3px solid var(--ui-accent);border-radius:8px;margin:14px 0;overflow-wrap:anywhere}
.hermes-crm-native .hc-editor{border:1px solid var(--ui-accent);border-radius:12px;padding:22px;margin:18px 0}.hermes-crm-native .hc-fields{display:grid;grid-template-columns:1fr 1fr;gap:14px}.hermes-crm-native label{display:flex;flex-direction:column;gap:5px}.hermes-crm-native textarea{min-height:90px;resize:vertical}.hermes-crm-native .hc-wide{grid-column:1/-1}.hermes-crm-native .hc-details{white-space:pre-wrap;overflow-wrap:anywhere}.hermes-crm-native .hc-footer{margin-top:26px;border-top:1px solid var(--ui-stroke-primary);padding-top:14px;font-size:11px;color:var(--ui-text-tertiary)}
/* Record workspaces and pane-scoped drawers share the host theme. */
.hermes-crm-native [hidden]{display:none!important}.hermes-crm-native .hc-record{margin:18px 0;min-width:0}.hermes-crm-native .hc-record-header{padding:22px;border:1px solid var(--ui-stroke-primary);border-radius:12px;background:var(--ui-bg-elevated,var(--ui-bg-editor))}
.hermes-crm-native .hc-identity{display:flex;align-items:center;gap:14px;min-width:0}.hermes-crm-native .hc-identity>div:last-child{min-width:0}.hermes-crm-native .hc-identity h2{font-size:24px;letter-spacing:-.5px;line-height:1.25;margin:4px 0;overflow-wrap:anywhere}.hermes-crm-native .hc-avatar{width:48px;height:48px;flex-shrink:0;display:grid;place-items:center;border-radius:12px;background:var(--ui-row-hover-background);color:var(--ui-accent);font-size:18px;font-weight:700}
.hermes-crm-native .hc-record-actions{margin-top:18px;padding-top:16px;border-top:1px solid var(--ui-stroke-primary)}.hermes-crm-native .hc-record-layout{display:grid;grid-template-columns:minmax(210px,.8fr) minmax(280px,1.5fr) minmax(210px,.85fr);align-items:start;gap:16px;margin-top:16px}.hermes-crm-native .hc-record-layout>*{min-width:0}.hermes-crm-native .hc-stack{display:grid;gap:16px}.hermes-crm-native .hc-section-title{margin-bottom:14px}.hermes-crm-native .hc-section-title h3{font-size:14px}
.hermes-crm-native .hc-properties{margin:0;display:grid;gap:15px}.hermes-crm-native .hc-properties dt{font-size:11px;color:var(--ui-text-secondary);margin-bottom:3px}.hermes-crm-native .hc-properties dd{margin:0;overflow-wrap:anywhere}.hermes-crm-native .hc-properties.hc-inline-properties{grid-template-columns:repeat(3,minmax(0,1fr));margin-top:20px;padding-top:16px;border-top:1px solid var(--ui-stroke-primary)}
.hermes-crm-native .hc-timeline{list-style:none;margin:0;padding:0}.hermes-crm-native .hc-timeline>li{position:relative;padding:0 0 22px 23px;border-left:1px solid var(--ui-stroke-primary);margin-left:5px;overflow-wrap:anywhere}.hermes-crm-native .hc-timeline>li:last-child{padding-bottom:0;border-left-color:transparent}.hermes-crm-native .hc-timeline>li:before{content:"";position:absolute;width:9px;height:9px;border:2px solid var(--ui-bg-elevated,var(--ui-bg-editor));background:var(--ui-accent);border-radius:50%;top:5px;left:-5px}.hermes-crm-native .hc-timeline p{margin:4px 0}.hermes-crm-native .hc-related{display:grid;gap:10px}.hermes-crm-native .hc-related button{width:100%;display:block;padding:13px;overflow-wrap:anywhere}.hermes-crm-native .hc-related strong{font-size:13px;letter-spacing:0;margin:0 0 4px}.hermes-crm-native .hc-related small{display:block;margin-top:5px;color:var(--ui-text-secondary)}.hermes-crm-native .hc-record-meta{font-size:11px;color:var(--ui-text-tertiary);overflow-wrap:anywhere;margin-top:18px}
.hermes-crm-native .hc-stage-path{list-style:none;display:flex;gap:5px;margin:20px 0 0;padding:0;flex-wrap:wrap}.hermes-crm-native .hc-stage-path li{flex:1;min-width:85px;padding:7px 10px;text-align:center;border-radius:6px;border:1px solid var(--ui-stroke-primary);color:var(--ui-text-secondary);font-size:11px}.hermes-crm-native .hc-stage-path li[aria-current=step]{border-color:var(--ui-accent);background:var(--ui-row-hover-background);color:var(--ui-accent);font-weight:700}
.hermes-crm-native .hc-overlay{position:absolute;inset:0;z-index:10;background:rgb(0 0 0 / .32);display:flex;justify-content:flex-end;min-height:0}.hermes-crm-native .hc-drawer{width:min(600px,100%);height:100%;min-height:0;display:flex;flex-direction:column;background:var(--ui-bg-editor);border-left:1px solid var(--ui-stroke-primary);box-shadow:-12px 0 36px rgb(0 0 0 / .18)}
.hermes-crm-native .hc-drawer-header{padding:22px 24px 18px;border-bottom:1px solid var(--ui-stroke-primary);flex-shrink:0}.hermes-crm-native .hc-drawer-header h2{font-size:21px;margin:4px 0}.hermes-crm-native .hc-drawer-header p{margin:8px 0 0}.hermes-crm-native .hc-editor{display:flex;flex-direction:column;border:0;border-radius:0;padding:0;margin:0;flex:1;min-height:0}.hermes-crm-native .hc-editor-body{overflow:auto;overscroll-behavior:contain;flex:1;min-height:0;padding:22px 24px}.hermes-crm-native .hc-form-section{border:0;margin:0 0 24px;padding:0;min-width:0}.hermes-crm-native .hc-form-section:last-child{margin-bottom:0}.hermes-crm-native .hc-form-section legend{font-size:13px;font-weight:700;padding:0;margin:0 0 12px}.hermes-crm-native .hc-form-section p{font-size:12px;margin:0 0 14px}.hermes-crm-native .hc-fields{grid-template-columns:repeat(2,minmax(0,1fr));gap:17px 14px}.hermes-crm-native .hc-fields label{font-size:12px;font-weight:600;min-width:0}.hermes-crm-native .hc-fields input,.hermes-crm-native .hc-fields select,.hermes-crm-native .hc-fields textarea{width:100%;min-width:0;font-size:13px;font-weight:400;padding:10px 12px}.hermes-crm-native .hc-field-hint{font-size:11px;font-weight:400;color:var(--ui-text-secondary)}.hermes-crm-native .hc-required{color:var(--ui-accent)}.hermes-crm-native .hc-editor-footer{padding:16px 24px;border-top:1px solid var(--ui-stroke-primary);background:var(--ui-bg-elevated,var(--ui-bg-editor));flex-shrink:0}.hermes-crm-native .hc-editor-footer .hc-notice{margin:0 0 14px}.hermes-crm-native .hc-work-item{border-top:1px solid var(--ui-stroke-primary);padding-top:15px;margin-top:15px}.hermes-crm-native .hc-work-item summary{cursor:pointer;font-weight:600}.hermes-crm-native .hc-work-item .hc-properties{margin:14px 0}.hermes-crm-native .hc-work-item .hc-notice{font-size:12px}
@container(max-width:1050px){.hermes-crm-native .hc-record-layout{grid-template-columns:minmax(200px,.8fr) minmax(260px,1.4fr)}.hermes-crm-native .hc-record-related{grid-column:1/-1;grid-template-columns:repeat(2,minmax(0,1fr))}}
@container(max-width:640px){.hermes-crm-native .hc-record-layout{grid-template-columns:minmax(0,1fr)}.hermes-crm-native .hc-record-related{grid-column:auto;grid-template-columns:minmax(0,1fr)}.hermes-crm-native .hc-inline-properties{grid-template-columns:minmax(0,1fr)!important}.hermes-crm-native .hc-record-header{padding:18px}.hermes-crm-native .hc-drawer-header,.hermes-crm-native .hc-editor-body{padding:18px}.hermes-crm-native .hc-editor-footer{padding:14px 18px}}
@container(max-width:850px){.hermes-crm-native .hc-grid{grid-template-columns:1fr 1fr}.hermes-crm-native .hc-two{grid-template-columns:1fr}.hermes-crm-native .hc-wrap{padding:18px}}
@container(max-width:480px){.hermes-crm-native .hc-grid,.hermes-crm-native .hc-fields{grid-template-columns:1fr}.hermes-crm-native .hc-bar-row{grid-template-columns:85px 1fr 70px}.hermes-crm-native h1{font-size:24px}}
`;

function Shell({ children, overlay, rootRef }) {
  return h(
    "section",
    { className: "hermes-crm-native", "aria-label": "Hermes CRM", ref: rootRef },
    h("style", null, CSS),
    h("div", { className: "hc-wrap", inert: overlay ? true : undefined }, children),
    overlay,
  );
}
export function CRMRoot({ ctx, boundIdentity }) {
  const lifetime = lifetimes.get(ctx);
  if (!lifetime?.supported)
    return h(
      Shell,
      null,
      h("h1", null, "Hermes CRM needs a newer Desktop SDK"),
      h(
        "p",
        { role: "status", className: "hc-notice" },
        "This Hermes Desktop build lacks the routing and cleanup capabilities required for safe CRM access. No CRM data has been read or changed.",
      ),
      h(
        "p",
        null,
        "Use a Desktop build providing connection identity, gateway activation epochs, and scoped plugin timers, with a backend matching the compatibility guide, then reload this plugin. Updating only the backend does not upgrade Desktop.",
      ),
      h(
        "p",
        { className: "hc-muted" },
        `Missing capabilities: ${lifetime?.missing?.join(", ") || "plugin registration"}`,
      ),
    );
  return h(SupportedRoot, { ctx, lifetime, boundIdentity });
}
function SupportedRoot({ ctx, lifetime, boundIdentity }) {
  const generation = useValue(lifetime.generation);
  const profile = useValue(host.state.profile);
  const connection = useValue(host.state.connectionId);
  const gateway = useValue(host.state.gateway);
  const epoch = useGatewayActivationEpoch();
  const identity = JSON.stringify([
    connection,
    profile,
    epoch,
    lifetime.id,
    generation,
  ]);
  if (!lifetime.alive)
    return h(
      Shell,
      null,
      h(
        "p",
        { role: "status" },
        "Hermes CRM has been unloaded. Re-enable the plugin to continue.",
      ),
    );
  if (gateway !== "open")
    return h(
      Shell,
      null,
      h("h1", null, "Hermes CRM"),
      h(
        "div",
        { role: "status", className: "hc-notice" },
        "Connecting to the active agent… CRM reads and changes are paused.",
      ),
      h(
        "p",
        null,
        `Active app profile: ${profile} · Connection: ${connection || "local"} · ${gateway}`,
      ),
    );
  if (boundIdentity && boundIdentity !== identity)
    return h(Shell, null, h("p", { role: "status", className: "hc-notice" }, "This agent workspace belongs to an earlier connection. Reopen CRM for the current connection and profile."));
  // Keying the entire workspace prevents even one render of previous-profile records/forms.
  return h(Workspace, { key: identity, ctx, identity, profile, connection });
}


function AgentContext({ ctx, identity, client, data, detail, disabled, viewRequest }) {
  const viewRevision = viewRequest.current;
  const lifetime = lifetimes.get(ctx);
  useValue(lifetime.chatGeneration);
  const [binding, setBinding] = useState(null);
  const [status, setStatus] = useState("");
  const [copying, setCopying] = useState(false);
  const lock = useRef(false), mounted = useRef(false), action = useRef(0);
  const latest = useRef(null);
  latest.current = { detail, data, disabled };
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; action.current++; }; }, []);
  const text = recordChatContext(detail, data, binding);
  function preview() {
    if (disabled || viewRevision !== viewRequest.current || !client.current()) return;
    try { setBinding(captureChatBinding(ctx, identity)); setStatus(""); }
    catch (error) { setBinding(null); setStatus(error.message); }
  }
  async function copy() {
    if (lock.current || disabled || viewRevision !== viewRequest.current || !text || !client.current() || typeof ctx.os?.writeClipboard !== "function") return;
    lock.current = true; setCopying(true); setStatus("");
    const ticket = ++action.current, selected = detail, snapshot = data;
    const current = () => mounted.current && ticket === action.current && viewRevision === viewRequest.current && client.current() && binding.current() &&
      latest.current.detail === selected && latest.current.data?.meta?.workspace_token === snapshot.meta.workspace_token && !latest.current.disabled;
    try {
      const row = selected.row.contact || selected.row;
      const fresh = await client.request(`/${selected.kind}/${encodeURIComponent(row.id)}?${new URLSearchParams({ workspace_token: selected.workspaceToken })}`);
      if (!current()) return;
      const freshRow = fresh.contact || fresh;
      if (freshRow.id !== row.id || freshRow.version !== row.version)
        throw new Error("This record changed. Reopen the record and preview its current reference before copying.");
      if (!current()) return;
      const copied = await ctx.os.writeClipboard(text);
      if (current()) setStatus(copied ? "Reference copied, not attached or sent. Paste it into the matching native chat, add your request, review the draft, then use Send." : "Desktop could not copy the reference. Select the preview text and copy it manually.");
    } catch (error) { if (current()) setStatus(error.message); }
    finally { lock.current = false; if (mounted.current && ticket === action.current) setCopying(false); }
  }
  if (!detail || detail.workspaceToken !== data?.meta?.workspace_token) return null;
  return h("section", { className: "hc-notice", "aria-label": "Agent record context" },
    h("div", { className: "hc-row" }, h("strong", null, "Discuss this record"),
      button("Preview record reference", preview, { disabled: disabled || copying })),
    h("p", { className: "hc-muted" }, "Share only this record’s ID and version with your matching native chat. The agent can read its current details through CRM tools."),
    binding && (text ? h("div", null,
      h("label", null, "Record reference to copy", h("textarea", { readOnly: true, value: text, rows: 10, "aria-label": "Record reference to copy", spellCheck: false })),
      button(copying ? "Checking record…" : "Copy record reference", copy, { disabled: disabled || copying || typeof ctx.os?.writeClipboard !== "function" }),
      typeof ctx.os?.writeClipboard !== "function" && h("p", null, "Clipboard access is unavailable in this Desktop build. Select and copy the preview manually."),
      h("p", { className: "hc-muted" }, "Copying does not attach context or send a message. Paste and review in native chat before pressing Send. Hermes keeps its normal approval prompts."))
      : h("p", { role: "status" }, "The chat or CRM scope changed. Preview the reference again for the current matching chat.")),
    status && h("p", { role: "status" }, status));
}

function Activity({ rows = [] }) {
  return h(
    "div",
    { className: "hc-list" },
    rows.length
      ? rows.map((row) =>
          h(
            "div",
            { className: "hc-list-item", key: row.id },
            h(
              "div",
              null,
              h("div", null, row.summary),
              h(
                "small",
                { className: "hc-muted" },
                `${row.actor} · ${date(row.created_at)}`,
              ),
            ),
            badge(row.action),
          ),
        )
      : h(
          "p",
          { className: "hc-muted" },
          "Your team’s changes will appear here.",
        ),
  );
}
function Empty({ children }) {
  return h("div", { className: "hc-empty" }, children);
}
// All six stages are included. Contacts may appear in several stage reports.
export function stageChartRows(stages = []) {
  const rows = STAGES.map(stage => ({ stage, value: 0, count: 0, contact_count: 0,
    ...stages.find(row => row.stage === stage) }));
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  return { total, rows: rows.map(row => ({ ...row, share: total ? row.value / total : 0 })) };
}
const STAGE_COLORS = ["#4779ce", "#9b69c6", "#c67e24", "#338b95", "#32825e", "#b85f67"];
export function StageChart({ stages, onStage }) {
  const { total, rows } = stageChartRows(stages);
  const [active, setActive] = useState(null);
  let offset = 0;
  const describe = row => `${label(row.stage)}: ${money(row.value)} USD · ${(row.share * 100).toFixed(1)}% · ${row.count} deals · ${row.contact_count} distinct contacts`;
  return h("section", { className: "hc-card" },
    h("h2", null, "Deal value by stage"),
    h("p", { className: "hc-muted" }, "All stages, including Won and Lost. Contacts may have multiple linked stages."),
    h("p", null, `Total deal value: ${money(total)}`),
    total > 0 ? h("svg", { viewBox: "0 0 120 120", width: 240, height: 240,
      role: "group", "aria-label": "Deal value by stage. Select a stage to view linked contacts." },
      rows.map((row, index) => {
        const start = offset;
        offset += row.share * 100;
        if (!row.value) return null;
        return h("circle", { key: row.stage, cx: 60, cy: 60, r: 44,
          fill: "none", stroke: STAGE_COLORS[index], strokeWidth: 24,
          pathLength: 100, strokeDasharray: `${row.share * 100} ${100 - row.share * 100}`,
          strokeDashoffset: -start, transform: "rotate(-90 60 60)",
          role: "button", tabIndex: 0, "aria-label": `${describe(row)}. View contacts.`,
          style: { cursor: "pointer" },
          onMouseEnter: () => setActive(row), onMouseLeave: () => setActive(null),
          onFocus: () => setActive(row), onBlur: () => setActive(null),
          onClick: () => onStage(row.stage),
          onKeyDown: event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); onStage(row.stage); } },
        }, h("title", null, describe(row)));
      })) : h(Empty, null, "No deal value to chart. Stage summaries remain available."),
    h("p", { role: "status", className: "hc-muted" }, active ? describe(active) : "Hover or focus a segment for details. Select a segment or summary to view contacts."),
    h("div", { className: "hc-list" }, rows.map((row, index) => button(
      describe(row), () => onStage(row.stage), { key: row.stage, className: "hc-list-item",
        style: { borderLeft: `5px solid ${STAGE_COLORS[index]}` },
        "aria-label": `${describe(row)}. View contacts.` })))
  );
}
const EMPTY_FILTERS = { contact_type: "", company: "", email: "", followup: "", priority: "", due: "", min_value: "", max_value: "" };
export function dollarFilter(value) {
  if (value === "") return "";
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) throw new Error("Enter non-negative dollar amounts with at most two decimal places.");
  const [whole, fraction = ""] = value.split(".");
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  if (!Number.isSafeInteger(cents) || cents > 2000000000) throw new Error("Dollar amount must be at most $20,000,000.");
  return String(cents);
}
function Workspace({ ctx, identity, profile, connection }) {
  const lifetime = lifetimes.get(ctx);
  const saved = useRef(lifetime.retainedView?.identity === identity ? lifetime.retainedView.value : {}).current;
  const shellRef = useRef(null);
  const clientRef = useRef(null);
  if (!clientRef.current) clientRef.current = createRouteClient(ctx, identity);
  const client = clientRef.current;
  const [page, setPage] = useState(saved.page ?? "overview");
  const [data, setData] = useState(saved.data ?? null);
  // Advance only for an accepted snapshot so auxiliary detail reads refresh
  // with both the manual control and the profile-local polling interval.
  const [snapshotGeneration, setSnapshotGeneration] = useState(saved.snapshotGeneration ?? 0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(saved.query ?? "");
  const [stage, setStage] = useState(saved.stage ?? "");
  const [status, setStatus] = useState(saved.status ?? "open");
  const [filters, setFilters] = useState(saved.filters ?? EMPTY_FILTERS);
  const [offset, setOffset] = useState(saved.offset ?? 0);
  const [filterGeneration, setFilterGeneration] = useState(0);
  const [editor, setEditor] = useState(null);
  const [detail, setDetail] = useState(saved.detail ?? null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [demoConfirm, setDemoConfirm] = useState(null);
  const [searchResult, setSearchResult] = useState(null);
  const [chatNotice, setChatNotice] = useState("");
  const view = { page, data, snapshotGeneration, query, stage, status, filters, offset, detail };
  useEffect(() => {
    if (identity === routeIdentity(ctx)) lifetime.retainedView = { identity, value: view };
  }, [page, data, snapshotGeneration, query, stage, status, filters, offset, detail]);
  const serial = useRef(0);
  const mutationLock = useRef(false);
  const viewRequest = useRef(0);
  const viewRevision = viewRequest.current;
  // Record editors/details do not own list requests. Only filter/navigation
  // changes invalidate a matching report, independently of record panels.
  const reportRequest = useRef(0);
  async function refresh() {
    const ticket = ++serial.current;
    setLoading(true);
    try {
      const snapshot = await client.request("/snapshot");
      if (client.current() && ticket === serial.current) {
        setData(snapshot);
        setSnapshotGeneration(value => value + 1);
        setError("");
      }
    } catch (e) {
      if (client.current() && ticket === serial.current) setError(e.message);
    } finally {
      if (client.current() && ticket === serial.current) setLoading(false);
    }
  }
  useEffect(() => {
    // Recreate after effect cleanup too (React Strict Mode's development replay).
    client.activate();
    const stop = ctx.setInterval(() => {
      if (!mutationLock.current) refresh();
    }, 30000);
    refresh();
    return () => {
      stop();
      client.dispose();
      clientRef.current.dispose();
      serial.current++;
    };
  }, []);
  useEffect(() => {
    let live = true;
    const reportTicket = reportRequest.current;
    setSearchResult(null);
    if (!data || !["contacts", "pipeline", "tasks"].includes(page)) return;
    const kind = page === "pipeline" ? "deals" : page;
    const params = new URLSearchParams({
      workspace_token: data.meta.workspace_token,
    });
    if (query) params.set("q", query);
    if (["deals", "contacts"].includes(kind) && stage) params.set("stage", stage);
    if (kind === "tasks" && status !== "all") params.set("status", status);
    const names = kind === "contacts" ? ["contact_type", "company", "email", "followup"]
      : kind === "deals" ? ["company", "min_value", "max_value"] : ["priority", "due"];
    if (kind === "contacts") { params.set("limit", "50"); params.set("offset", String(offset)); }
    const stop = ctx.setTimeout(async () => {
      try {
        for (const name of names) if (filters[name]) params.set(name,
          name.endsWith("_value") ? dollarFilter(filters[name]) : filters[name]);
        const result = await client.request(`/${kind === "contacts" ? "reports/contacts" : kind}?${params}`);
        if (live && client.current() && reportTicket === reportRequest.current) {
          setError("");
          setSearchResult({ key: searchKey, rows: kind === "contacts" ? result.items : result,
            total: kind === "contacts" ? result.total : null });
        }
      } catch (e) {
        if (live && client.current() && reportTicket === reportRequest.current) setError(e.message);
      }
    }, 200);
    return () => { live = false; stop(); };
  }, [page, query, stage, status, filters, offset, filterGeneration, data]);
  const searchKey = JSON.stringify([page, query, stage, status, filters, offset, filterGeneration, data?.meta.workspace_token]);
  const searchReady = searchResult?.key === searchKey;
  const searchRows = () => (searchReady ? searchResult.rows : []);
  function invalidateView() {
    viewRequest.current++;
    reportRequest.current++;
    setFilterGeneration(value => value + 1);
    setDetail(null); setDetailLoading(false); setEditor(null); setOffset(0); setError("");
  }
  function changeFilter(name, value) {
    invalidateView(); setFilters(old => ({ ...old, [name]: value }));
  }
  function navigate(next, selectedStage = "", followup = "") {
    invalidateView();
    setPage(next); setQuery(""); setStage(selectedStage); setStatus("open");
    setFilters({ ...EMPTY_FILTERS, ...(followup ? { contact_type: "lead", followup } : {}) });
    setNotice("");
  }
  async function write(path, options) {
    if (mutationLock.current || !client.current()) return false;
    mutationLock.current = true;
    setBusy(true);
    setError("");
    try {
      await client.request(path, options);
      if (!client.current()) return false;
      setNotice("Saved to this agent’s CRM.");
      setEditor(null);
      setDetail(null);
      setDetailLoading(false);
      setDemoConfirm(false);
      await refresh();
      return true;
    } catch (e) {
      if (client.current())
        setError(
          `${e.message} If the request may have reached the backend, refresh before trying again. Creates retain their retry key.`,
        );
      return false;
    } finally {
      mutationLock.current = false;
      if (client.current()) setBusy(false);
    }
  }
  async function open(kind, id) {
    const viewTicket = ++viewRequest.current;
    const workspaceToken = data.meta.workspace_token;
    setError("");
    setDetail(null);
    setEditor(null);
    setDetailLoading(true);
    try {
      const row = await client.request(
        `/${kind}/${encodeURIComponent(id)}?${new URLSearchParams({ workspace_token: workspaceToken })}`,
      );
      if (client.current() && viewTicket === viewRequest.current)
        setDetail({ kind, row, workspaceToken });
    } catch (e) {
      if (client.current() && viewTicket === viewRequest.current)
        setError(e.message);
    } finally {
      if (client.current() && viewTicket === viewRequest.current) setDetailLoading(false);
    }
  }
  function closeDetail() {
    viewRequest.current++;
    setDetailLoading(false);
    setDetail(null);
  }
  function edit(kind, row = null, workspaceToken = data.meta.workspace_token, initial = {}) {
    viewRequest.current++;
    setEditor({
      kind,
      row,
      key: crypto.randomUUID(),
      workspaceToken,
      initial,
      returnFocus: shellRef.current?.ownerDocument.activeElement,
    });
    setDetailLoading(false);
    setError("");
  }
  const heading = {
    overview: [
      "Relationship intelligence",
      "A clear view of your next opportunity.",
    ],
    contacts: [
      "Contacts",
      "People, context, and the conversations that matter.",
    ],
    pipeline: ["Deal pipeline", "Move the right opportunities forward."],
    tasks: ["Follow-ups", "Keep your promises. Make the next step clear."],
    activity: ["Activity", "CRM record changes by people and agents. Mailbox history is not synced."],
  }[page];
  const overview = data?.overview;
  const disabled = busy || loading || !data || !client.current();
  return h(
    Shell,
    { rootRef: shellRef, overlay: editor && data ? h(Editor, {
      key: editor.key, editor, data, busy: disabled, error,
      cancel: () => { setEditor(null); setError(""); },
      save: (values) => write(
        `/${editor.kind}${editor.row ? "/" + encodeURIComponent(editor.row.id) : ""}`,
        { method: editor.row ? "PATCH" : "POST", body: {
          ...(editor.row ? { data: { ...values, version: editor.row.version } } : createPayload(values, editor.key)),
          workspace_token: editor.workspaceToken,
        } },
      ),
    }) : null },
    h(
      "header",
      { className: "hc-row" },
      h(
        "div",
        null,
        h("div", { className: "hc-eyebrow" }, "HERMES / CRM"),
        h("h1", null, heading[0]),
        h("p", { className: "hc-muted" }, heading[1]),
      ),
      h(
        "div",
        { className: "hc-actions" },
        badge(profile),
        button("Chat with Hermes", () => {
          if (disabled || editor || detailLoading || mutationLock.current || viewRevision !== viewRequest.current || !client.current()) return;
          try {
            lifetime.retainedView = { identity, value: view };
            openChatWorkspace(ctx, identity, () => h(CRMRoot, { ctx, boundIdentity: identity }));
            setChatNotice("Use the native Hermes chat beside CRM. Nothing has been added to or sent from your draft.");
          } catch (error) { if (client.current()) setChatNotice(error.message); }
        }, { disabled: disabled || Boolean(editor) || detailLoading }),
        button(loading ? "Refreshing…" : "Refresh", refresh, {
          disabled: busy || loading,
        }),
      ),
    ),
    h(
      "div",
      { className: "hc-muted" },
      `Active app profile: ${profile} · Connection: ${connection || "local"}${data ? ` · ${label(data.meta.backend)} backend` : ""}`,
    ),
    h("p", { className: "hc-muted" }, "Work alongside your existing main chat. Save or cancel an open record form first."),
    chatNotice && h("p", { className: "hc-notice", role: "status" }, chatNotice),
    h(AgentContext, { ctx, identity, client, data, detail, viewRequest, disabled: disabled || Boolean(editor) || detailLoading }),
    h(
      "nav",
      { className: "hc-tabs", "aria-label": "CRM sections" },
      ["overview", "contacts", "pipeline", "tasks", "activity"].map((tab) =>
        button(label(tab), () => navigate(tab), {
          key: tab,
          "aria-current": page === tab ? "page" : undefined,
          disabled: busy,
        }),
      ),
    ),
    error && !editor &&
      h(
        "div",
        { role: "alert", className: "hc-notice" },
        h("strong", null, "CRM could not complete this request. "),
        error,
        !data &&
          h(
            "p",
            null,
            "Enable both the Hermes CRM Desktop component and the agent/backend plugin for this profile in Capabilities → Plugins, then restart the gateway from Hermes and refresh. Remote hosts also need the backend installed there. No separate web server is needed.",
          ),
      ),
    notice && h("div", { role: "status", className: "hc-notice" }, notice),
    !data &&
      !error &&
      h("p", { role: "status" }, "Loading this agent’s workspace…"),
    data &&
      h(
        "div",
        null,
        data.meta.demo &&
          h(
            "div",
            { className: "hc-notice" },
            "Demo workspace · These records are synthetic.",
          ),
        detailLoading && h("div", { className: "hc-notice", role: "status" },
          h("div", { className: "hc-row" }, "Loading record…", button("Cancel loading", closeDetail))),
        detail && detail.workspaceToken === data.meta.workspace_token && h(Detail, {
          key: `${detail.kind}:${(detail.row.contact || detail.row).id}`,
          detail, data, disabled, client, snapshotGeneration,
          close: closeDetail,
          edit: () => edit(detail.kind, detail.row.contact || detail.row, detail.workspaceToken),
          open,
          create: (kind, initial) => edit(kind, null, detail.workspaceToken, initial),
        }),
        h("div", { hidden: Boolean(detail && detail.workspaceToken === data.meta.workspace_token) },
        page === "overview" &&
          h(
            "div",
            null,
            h(
              "div",
              { className: "hc-grid" },
              [
                [
                  "Open pipeline",
                  money(overview.pipeline_value),
                  "pipeline",
                  `${overview.open_deals} active deals`,
                ],
                [
                  "Weighted forecast",
                  money(overview.weighted_value),
                  "pipeline",
                  "Value × probability",
                ],
                [
                  "Contacts",
                  overview.contacts,
                  "contacts",
                  "Relationships in this workspace",
                ],
                [
                  "Open follow-ups",
                  overview.open_tasks,
                  "tasks",
                  `${overview.overdue_tasks} overdue`,
                ],
              ].map(([title, value, target, caption]) =>
                button(
                  h(
                    "div",
                    null,
                    h("span", { className: "hc-muted" }, title),
                    h("strong", null, value),
                    h("small", { className: "hc-muted" }, caption),
                  ),
                  () => navigate(target),
                  { className: "hc-card", key: title },
                ),
              ),
            ),
            h("section", { className: "hc-card" },
              h("h2", null, "Lead attention"),
              h("p", { className: "hc-muted" }, "Stored follow-ups for lead contacts, not agent execution coverage."),
              h("div", { className: "hc-actions" },
                button(`${overview.lead_attention?.no_open_followup ?? 0} leads with no open follow-up`, () => navigate("contacts", "", "missing")),
                button(`${overview.lead_attention?.overdue_followup ?? 0} leads with overdue follow-up`, () => navigate("contacts", "", "overdue")))),
            h(
              "div",
              { className: "hc-two" },
              h(StageChart, { stages: overview.stages, onStage: stage => navigate("contacts", stage) }),
              h(
                "section",
                { className: "hc-card" },
                h(
                  "div",
                  { className: "hc-row" },
                  h("h2", null, "Up next"),
                  button("View all", () => navigate("tasks")),
                ),
                overview.tasks.length
                  ? overview.tasks.map((task) =>
                      button(
                        h(
                          "div",
                          null,
                          task.title,
                          h(
                            "p",
                            { className: "hc-muted" },
                            `${date(task.due_at)} · ${label(task.priority)}`,
                          ),
                        ),
                        () => open("tasks", task.id),
                        { key: task.id, className: "hc-list-item" },
                      ),
                    )
                  : h(
                      Empty,
                      null,
                      "No open follow-ups. Start with a contact or a task.",
                    ),
              ),
            ),
            h(
              "section",
              { className: "hc-card" },
              h("h2", null, "Latest activity"),
              h(Activity, { rows: overview.activity }),
            ),
            !overview.contacts &&
              !overview.open_deals &&
              !overview.open_tasks &&
              h(
                "div",
                { className: "hc-notice" },
                h(
                  "h3",
                  null,
                  "Your workspace, ready for the first relationship",
                ),
                h(
                  "p",
                  null,
                  "Create real records or explore with synthetic demo data. Demo data can only be added to an empty workspace.",
                ),
                h(
                  "div",
                  { className: "hc-actions" },
                  button("Create contact", () => edit("contacts"), {
                    disabled,
                  }),
                  button(
                    "Explore demo data",
                    () =>
                      setDemoConfirm({
                        workspaceToken: data.meta.workspace_token,
                        backend: data.meta.backend,
                      }),
                    {
                      disabled,
                    },
                  ),
                ),
                demoConfirm &&
                  h(
                    "div",
                    null,
                    h(
                      "p",
                      null,
                      `Add synthetic contacts, deals, and follow-ups to ${profile} on ${connection || "local"} (${label(demoConfirm.backend)} backend)?`,
                    ),
                    button(
                      "Add synthetic records",
                      () =>
                        write("/demo", {
                          method: "POST",
                          body: {
                            confirm: true,
                            workspace_token: demoConfirm.workspaceToken,
                          },
                        }),
                      { disabled },
                    ),
                    button("Cancel", () => setDemoConfirm(false)),
                  ),
              ),
          ),
        ["contacts", "pipeline", "tasks"].includes(page) &&
          h(
            "div",
            { className: "hc-row" },
            h(
              "div",
              { className: "hc-actions" },
              h("input", {
                type: "search",
                maxLength: 200,
                value: query,
                onChange: (e) => { invalidateView(); setQuery(e.target.value); },
                placeholder: `Search ${page}…`,
                "aria-label": `Search ${page}`,
              }),
              ["pipeline", "contacts"].includes(page) &&
                h(
                  "select",
                  {
                    value: stage,
                    onChange: (e) => { invalidateView(); setStage(e.target.value); },
                    "aria-label": "Stage",
                  },
                  h("option", { value: "" }, "All stages"),
                  (page === "contacts" ? [...STAGES, "unassigned"] : STAGES).map((s) =>
                    h("option", { key: s, value: s }, label(s)),
                  ),
                ),
              page === "tasks" &&
                h(
                  "select",
                  {
                    value: status,
                    onChange: (e) => { invalidateView(); setStatus(e.target.value); },
                    "aria-label": "Task status",
                  },
                  ["open", "done", "all"].map((s) =>
                    h("option", { key: s, value: s }, label(s)),
                  ),
                ),
            ),
            h("div", { className: "hc-actions" },
              (page === "contacts" ? [["contact_type", "Contact type", ["lead", "customer", "partner"]],
                ["email", "Email", ["present", "missing"]], ["followup", "Follow-up", ["missing", "overdue", "upcoming"]]]
                : page === "tasks" ? [["priority", "Priority", ["normal", "high"]], ["due", "Due", ["overdue", "upcoming"]]] : [])
                .map(([name, title, options]) => h("label", { key: name }, title,
                  h("select", { value: filters[name], "aria-label": title, onChange: e => changeFilter(name, e.target.value) },
                    h("option", { value: "" }, `Any ${title.toLowerCase()}`), options.map(value => h("option", { key: value, value }, label(value)))))),
              ["contacts", "pipeline"].includes(page) && h("label", null, "Company",
                h("input", { value: filters.company, "aria-label": "Company", maxLength: 200, onChange: e => changeFilter("company", e.target.value) })),
              page === "pipeline" && ["min_value", "max_value"].map(name => h("label", { key: name }, name === "min_value" ? "Minimum value (USD)" : "Maximum value (USD)",
                h("input", { value: filters[name], type: "number", min: "0", step: "0.01", "aria-label": name === "min_value" ? "Minimum value (USD)" : "Maximum value (USD)", onChange: e => changeFilter(name, e.target.value) }))),
              button("Clear filters", () => navigate(page))),
            button(
              `+ ${page === "contacts" ? "Contact" : page === "pipeline" ? "Deal" : "Follow-up"}`,
              () => edit(page === "pipeline" ? "deals" : page),
              { className: "hc-primary", disabled },
            ),
          ),
        !searchReady &&
          ["contacts", "pipeline", "tasks"].includes(page) &&
          h("p", { role: "status" }, "Loading matching records…"),
        page === "contacts" && searchReady && h("div", { className: "hc-row", style: { marginTop: 18 } },
          h("p", { role: "status" }, `${stage === "unassigned" ? "Contacts without linked deals · " : stage ? `Contacts linked to ${label(stage)} stage · ` : filters.followup ? `${filters.contact_type === "lead" ? "Lead attention" : "Contacts"} · ${label(filters.followup)} follow-up · ` : ""}${searchResult.total} matching contacts · ${searchResult.total ? offset + 1 : 0}–${offset + searchRows().length} shown`),
          h("div", { className: "hc-actions" },
            button("Previous", () => { closeDetail(); reportRequest.current++; setEditor(null); setOffset(Math.max(0, offset - 50)); }, { disabled: offset === 0 }),
            button("Next", () => { closeDetail(); reportRequest.current++; setEditor(null); setOffset(offset + 50); }, { disabled: offset + searchRows().length >= searchResult.total }))),
        page === "contacts" &&
          searchReady &&
          h(
            "div",
            { className: "hc-list", style: { marginTop: 18 } },
            searchRows("contacts").length
              ? searchRows("contacts").map((c) =>
                  button(
                    h(
                      "div",
                      { className: "hc-row", style: { width: "100%" } },
                      h(
                        "div",
                        null,
                        h("h3", null, c.name),
                        h(
                          "p",
                          { className: "hc-muted" },
                          [c.title, c.company, c.email]
                            .filter(Boolean)
                            .join(" · "),
                        ),
                      ),
                      h("div", null, h("p", null, `Contact type: ${label(c.lifecycle)}`), h("p", null, `Linked stages: ${(c.deal_stages || []).map(label).join(", ") || "Unassigned"}`)),
                    ),
                    () => open("contacts", c.id),
                    { key: c.id, className: "hc-list-item" },
                  ),
                )
              : h(
                  Empty,
                  null,
                  "No contacts match. Add your first relationship or change your search.",
                ),
          ),
        page === "pipeline" &&
          searchReady &&
          h(
            "div",
            { className: "hc-board" },
            STAGES.filter((s) => !stage || stage === s).map((s) => {
              const rows = searchRows("deals").filter((d) => d.stage === s);
              return h(
                "section",
                { className: "hc-column", key: s },
                h(
                  "header",
                  { className: "hc-row" },
                  h("h3", null, label(s)),
                  badge(rows.length),
                ),
                h(
                  "p",
                  { className: "hc-muted" },
                  money(rows.reduce((sum, d) => sum + d.value, 0)),
                ),
                rows.length
                  ? rows.map((d) =>
                      button(
                        h(
                          "div",
                          null,
                          h("h3", null, d.title),
                          h("strong", null, money(d.value)),
                          h("p", { className: "hc-muted" }, d.contact_name),
                          h(
                            "small",
                            { className: "hc-muted" },
                            `${d.probability}% · ${d.close_date || "No close date"}`,
                          ),
                        ),
                        () => open("deals", d.id),
                        { key: d.id, className: "hc-deal" },
                      ),
                    )
                  : h(
                      "p",
                      { className: "hc-muted" },
                      "No opportunities here yet.",
                    ),
              );
            }),
          ),
        page === "tasks" &&
          searchReady &&
          h(
            "div",
            null,
            h(
              "p",
              { className: "hc-notice" },
              "Tasks are saved here. To schedule a native reminder, ask the existing Hermes agent in this profile to use crm_followup_schedule with the task ID. Scheduling requires an active agent context; this pane does not create cron jobs. A scheduled badge confirms registration, not execution.",
            ),
            h(
              "div",
              { className: "hc-list" },
              searchRows("tasks")
                .filter((t) => status === "all" || t.status === status)
                .map((t) =>
                  h(
                    "div",
                    { className: "hc-list-item", key: t.id },
                    button(
                      h(
                        "div",
                        null,
                        h("h3", null, t.title),
                        h(
                          "p",
                          { className: "hc-muted" },
                          `${date(t.due_at)} · ${label(t.priority)} · ${t.contact_name || "Unlinked"}`,
                        ),
                        badge(`Reminder: ${t.schedule_status}`),
                      ),
                      () => open("tasks", t.id),
                    ),
                    button(
                      t.status === "done" ? "Reopen" : "Complete",
                      () =>
                        write(`/tasks/${encodeURIComponent(t.id)}`, {
                          method: "PATCH",
                          body: {
                            data: {
                              version: t.version,
                              status: t.status === "done" ? "open" : "done",
                            },
                            workspace_token: data.meta.workspace_token,
                          },
                        }),
                      { disabled },
                    ),
                  ),
                ),
            ),
            !searchRows("tasks").filter(
              (t) => status === "all" || t.status === status,
            ).length &&
              h(Empty, null, "No matching follow-ups. You’re clear for now."),
          ),
        page === "activity" && h(Activity, { rows: data.activity }),
        ),
      ),
    h(
      "footer",
      { className: "hc-footer" },
      "Profile-local CRM · Desktop and agent tools share the same records · Refreshes every 30 seconds · Contact reports use server pagination. Deal/task lists and form choices show up to 500 records; displayed deal totals cover returned records only. The active app profile controls this view, not a focused chat in another profile.",
    ),
  );
}

function Properties({ rows, inline = false }) {
  return h("dl", { className: `hc-properties${inline ? " hc-inline-properties" : ""}` },
    rows.map(([title, value]) => h("div", { key: title },
      h("dt", null, title), h("dd", null, value === "" || value == null ? "Not set" : value))));
}
function RecordSection({ title, action, children, className = "" }) {
  return h("section", { className: `hc-card ${className}`, "aria-label": title },
    h("div", { className: "hc-row hc-section-title" }, h("h3", null, title), action), children);
}
function Timeline({ rows }) {
  return rows.length ? h("ol", { className: "hc-timeline", "aria-label": "CRM activity timeline" },
    rows.map(row => h("li", { key: row.id },
      h("div", { className: "hc-row" }, h("b", null, label(row.action)),
        h("time", { dateTime: row.created_at, title: row.created_at, className: "hc-muted" }, date(row.created_at))),
      h("p", null, row.summary), h("small", { className: "hc-muted" }, `Recorded by ${row.actor}`))))
    : h("p", { className: "hc-muted" }, "No CRM changes in the available history.");
}
function AssignedWork({ client, task, workspaceToken, snapshotGeneration }) {
  const [result, setResult] = useState(null);
  const [failure, setFailure] = useState(null);
  const [reload, setReload] = useState(0);
  const [expanded, setExpanded] = useState({});
  const scope = { client, taskId: task.id, workspaceToken, snapshotGeneration, reload };
  const sameTarget = value => value && value.client === client && value.taskId === task.id && value.workspaceToken === workspaceToken;
  const current = value => sameTarget(value) && value.snapshotGeneration === snapshotGeneration && value.reload === reload;
  const history = sameTarget(result) ? result.rows : null;
  const error = current(failure) ? failure.message : "";
  const refreshing = !current(result) && !error;
  const stale = history !== null && !current(result);
  useEffect(() => {
    let live = true;
    // Keep keyed reports mounted while refreshing so open panels and reading
    // position survive polling. Their observation age remains explicit below.
    client.request(`/work?${new URLSearchParams({ task_id: task.id, workspace_token: workspaceToken, limit: "100" })}`)
      .then(rows => {
        if (!Array.isArray(rows)) throw new Error("The backend did not return a supported history response.");
        if (live && client.current()) {
          setResult({ ...scope, rows });
          setFailure(null);
        }
      }).catch(e => { if (live && client.current()) setFailure({ ...scope, message: e.message }); });
    return () => { live = false; };
  }, [client, task.id, workspaceToken, snapshotGeneration, reload]);
  return h(RecordSection, { title: "Assigned agent work" },
    h("p", { className: "hc-muted" }, "Read-only assignment history. Registration does not prove execution. Agent reports require human review and do not complete this follow-up."),
    error && h("div", { role: "status", className: "hc-notice" },
      h("p", null, history === null
        ? "Assigned-work history is unavailable. This does not mean no assignments exist."
        : "Assigned-work history could not be refreshed. Showing the last successful observations, which may be out of date."),
      h("p", null, error), button("Retry history", () => setReload(n => n + 1))),
    refreshing && h("p", { role: "status", className: "hc-muted" }, history === null
      ? "Loading assigned-work history…"
      : "Refreshing assigned-work history… Showing the last successful observations until this check completes."),
    history !== null && (history.length ? h("div", { "aria-busy": refreshing },
        h("p", { className: "hc-muted" }, `${history.length} assignments shown · up to the first 100 registered assignments.`),
        history.map(work => h("details", { className: "hc-work-item", key: work.id,
          open: Boolean(expanded[work.id]),
          onToggle: event => {
            const open = event.currentTarget.open;
            setExpanded(previous => previous[work.id] === open ? previous : { ...previous, [work.id]: open });
          },
        },
          h("summary", null, `${label(work.state)} · ${date(work.payload?.run_at)}`),
          h(Properties, { rows: [
            ["Human owner", work.payload?.human_owner], ["Requested run", date(work.payload?.run_at)],
            ["Assignment ID", work.id], ["Native job ID", work.job_id],
            ["Observation", label(work.reason)], ["Source task", work.source_task_current
              ? stale ? "Current at last successful refresh; not reverified" : "Current"
              : "Changed since assignment"],
          ] }),
          h("h3", null, "Assignment"), h("p", { className: "hc-details" }, work.payload?.prompt || "Not recorded"),
          h("h3", null, "Success criteria"), h("p", { className: "hc-details" }, work.payload?.success_criteria || "Not recorded"),
          h("h3", null, "Agent reports"),
          (work.reports || []).length ? work.reports.map(report => h("div", { key: report.id, className: "hc-notice" },
            h("b", null, `Agent reported: ${label(report.outcome)}`),
            h("p", null, `${label(report.review_status || "awaiting_human_review")} · ${date(report.created_at)}`),
            h("p", { className: "hc-details" }, report.summary),
            h("small", { className: "hc-muted" }, "Host terminal success has not been verified by this record.")))
            : h("p", { className: "hc-muted" }, "No agent report recorded."),
          h("h3", null, "Recorded observations"),
          h("ol", { className: "hc-timeline" }, (work.events || []).map(event => h("li", { key: event.id },
            h("b", null, label(event.kind)), h("p", { className: "hc-muted" }, date(event.created_at))))))))
        : h("p", { className: "hc-muted" }, stale
          ? "The last successful history check found no assignments; this has not been reverified."
          : "No native assignments are recorded for this follow-up.")));
}
function Detail({ detail, data, disabled, client, snapshotGeneration, close, edit, open, create }) {
  const row = detail.row.contact || detail.row;
  const isContact = detail.kind === "contacts", isDeal = detail.kind === "deals";
  const title = row.name || row.title;
  const linkedContact = data.contacts.find(item => item.id === row.contact_id);
  const linkedDeal = data.deals.find(item => item.id === row.deal_id);
  const deals = isContact ? detail.row.deals : isDeal ? [row] : linkedDeal ? [linkedDeal] : [];
  const tasks = isContact ? detail.row.tasks : isDeal ? data.tasks.filter(task => task.deal_id === row.id) : [];
  const upcoming = tasks.filter(task => task.status === "open").slice().sort((a, b) => String(a.due_at).localeCompare(String(b.due_at)));
  const activity = isContact ? detail.row.activity : data.activity.filter(item => item.entity_id === row.id);
  const initialTask = isContact ? { contact_id: row.id } : isDeal ? { contact_id: row.contact_id, deal_id: row.id } : {};
  const headingRef = useRef(null);
  useEffect(() => { headingRef.current?.focus(); }, []);
  const linkedButton = (kind, id, name) => id ? button(name || `Open linked ${kind === "contacts" ? "contact" : "deal"}`, () => open(kind, id), { disabled }) : "Not linked";
  const facts = isContact ? [["Email", row.email], ["Company", row.company], ["Job title", row.title], ["Contact type", label(row.lifecycle)]]
    : isDeal ? [["Contact", linkedButton("contacts", row.contact_id, linkedContact?.name)], ["Deal value", money(row.value)], ["Stage", label(row.stage)], ["Probability", `${row.probability}%`], ["Expected close", row.close_date || "Not set"]]
    : [["Due", h("time", { dateTime: row.due_at, title: row.due_at }, date(row.due_at))], ["Priority", label(row.priority)], ["Status", label(row.status)], ["Reminder registration", label(row.schedule_status)], ["Contact", linkedButton("contacts", row.contact_id, linkedContact?.name)], ["Deal", linkedButton("deals", row.deal_id, linkedDeal?.title)]];
  return h("section", { className: "hc-record", "aria-label": "Record details" },
    h("div", { className: "hc-record-header" },
      h("div", { className: "hc-row" },
        h("div", { className: "hc-identity" },
          h("div", { className: "hc-avatar", "aria-hidden": true }, isContact ? title.trim().split(/\s+/).slice(0, 2).map(word => word[0]).join("").toUpperCase() : isDeal ? "$" : "→"),
          h("div", null, h("div", { className: "hc-eyebrow" }, isContact ? "CONTACT" : isDeal ? "DEAL" : "FOLLOW-UP"),
            h("h2", { ref: headingRef, tabIndex: -1 }, title),
            h("p", { className: "hc-muted" }, isContact ? [row.title, row.company].filter(Boolean).join(" at ") || "Relationship record" : isDeal ? linkedContact?.name || "Linked opportunity" : `${label(row.status)} · ${label(row.priority)} priority`))),
        button("Close", close, { "aria-label": "Close record details" })),
      h("div", { className: "hc-actions hc-record-actions" },
        button("Edit", edit, { className: "hc-primary", disabled }),
        (isContact || isDeal) && button("Create follow-up", () => create("tasks", initialTask), { disabled }),
        isContact && button("Create deal", () => create("deals", { contact_id: row.id }), { disabled }),
        badge(isContact ? `Contact type: ${label(row.lifecycle)}` : isDeal ? row.stage : row.status)),
      isContact ? h(Properties, { inline: true, rows: [["Email", row.email], ["Company", row.company], ["Linked deal stages", [...new Set(deals.map(deal => label(deal.stage)))].join(", ") || "Unassigned"]] })
        : isDeal ? h("ol", { className: "hc-stage-path", "aria-label": "Deal stage" }, STAGES.map(stage => h("li", { key: stage, "aria-current": row.stage === stage ? "step" : undefined }, label(stage))))
          : h(Properties, { inline: true, rows: [["Due", date(row.due_at)], ["Reminder registration", label(row.schedule_status)], ["Record version", row.version]] })),
    h("div", { className: "hc-record-layout" },
      h("aside", { className: "hc-stack", "aria-label": "Record properties" },
        h(RecordSection, { title: "About this record" }, h(Properties, { rows: facts }),
          h("p", { className: "hc-record-meta" }, `ID: ${row.id} · Version ${row.version}`),
          row.created_at && h("p", { className: "hc-record-meta" }, `Created ${date(row.created_at)}`),
          row.updated_at && h("p", { className: "hc-record-meta" }, `Updated ${date(row.updated_at)}`)),
        h(RecordSection, { title: "Notes" }, h("p", { className: "hc-details" }, row.notes || "No notes yet. Use Edit to add context."))),
      h("section", { className: "hc-stack", "aria-label": "Record history and next steps" },
        (isContact || isDeal) && h(RecordSection, { title: "Upcoming follow-ups", action: badge(upcoming.length) },
          upcoming.length ? h("div", { className: "hc-related" }, upcoming.map(task => button(
            h("div", null, h("b", null, task.title), h("small", null, `${date(task.due_at)} · ${label(task.priority)}`),
              h("small", null, `Reminder registration: ${label(task.schedule_status)}`)),
            () => open("tasks", task.id), { key: task.id, disabled })))
            : h("p", { className: "hc-muted" }, "No open follow-ups in the available records. Create one to record the next step.")),
        h(RecordSection, { title: "Activity timeline" },
          h("p", { className: "hc-muted" }, "CRM record changes only. Sent and received emails are not synced here."),
          h(Timeline, { rows: activity || [] }),
          h("p", { className: "hc-record-meta" }, isContact ? "Up to 100 recent CRM changes for this contact and its linked records." : "Matching changes from the latest 100 workspace activity records.")),
        !isContact && !isDeal && h(AssignedWork, { client, task: row, workspaceToken: detail.workspaceToken, snapshotGeneration })),
      h("aside", { className: "hc-stack hc-record-related", "aria-label": "Related records" },
        h(RecordSection, { title: isDeal ? "Linked contact" : "Related deals", action: isContact ? badge(deals.length) : null },
          isDeal ? h(Properties, { rows: [["Contact", linkedButton("contacts", row.contact_id, linkedContact?.name)]] })
            : deals.length ? h("div", { className: "hc-related" }, deals.map(deal => button(
              h("div", null, h("b", null, deal.title), h("small", null, `${money(deal.value)} · ${label(deal.stage)}`)),
              () => open("deals", deal.id), { key: deal.id, disabled })))
              : row.deal_id ? linkedButton("deals", row.deal_id, null) : h("p", { className: "hc-muted" }, "No linked deals.")),
        (isContact || isDeal) && h(RecordSection, { title: "Completed follow-ups" },
          tasks.some(task => task.status === "done") ? h("div", { className: "hc-related" }, tasks.filter(task => task.status === "done").map(task => button(
            h("div", null, h("b", null, task.title), h("small", null, date(task.due_at))),
            () => open("tasks", task.id), { key: task.id, disabled }))) : h("p", { className: "hc-muted" }, "No completed follow-ups in the available records.")),
        h("p", { className: "hc-record-meta" }, "Related record lists show up to 500 loaded records. Contact type and deal stage are separate fields."))));
}

// Use only elements in this pane. The host page's body, scroll, and global
// listeners are untouched; inert isolates the underlying CRM workspace.
function Drawer({ title, subtitle, busy, cancel, children, returnFocus }) {
  const panel = useRef(null);
  useEffect(() => {
    const node = panel.current;
    if (!node) return;
    const previous = returnFocus || node.ownerDocument.activeElement;
    (node.querySelector("[data-autofocus]") || node).focus();
    return () => {
      if (previous?.isConnected && !previous.closest?.("[inert]")) previous.focus();
    };
  }, []);
  function onKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault(); event.stopPropagation();
      if (!busy) cancel();
    }
    if (event.key !== "Tab") return;
    const nodes = [...(panel.current?.querySelectorAll("button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex='0']") || [])];
    const first = nodes[0], last = nodes[nodes.length - 1];
    const active = panel.current?.ownerDocument.activeElement;
    if (!first) { event.preventDefault(); panel.current?.focus(); }
    else if (event.shiftKey && (active === first || active === panel.current)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (active === last || active === panel.current)) { event.preventDefault(); first.focus(); }
  }
  return h("div", { className: "hc-overlay" },
    h("section", { className: "hc-drawer", role: "dialog", "aria-modal": true, "aria-label": title, tabIndex: -1, ref: panel, onKeyDown },
      h("header", { className: "hc-drawer-header" },
        h("div", { className: "hc-row" }, h("div", null, h("div", { className: "hc-eyebrow" }, "HERMES / CRM"), h("h2", null, title)),
          button("Close", cancel, { disabled: busy, "aria-label": "Close form" })),
        h("p", { className: "hc-muted" }, subtitle)), children));
}

function Editor({ editor, data, busy, error, save, cancel }) {
  const { kind, row } = editor;
  const [values, setValues] = useState(() => {
    const keys = kind === "contacts" ? ["name", "email", "company", "title", "lifecycle", "notes"]
      : kind === "deals" ? ["title", "contact_id", "value", "stage", "probability", "close_date", "notes"]
        : ["title", "contact_id", "deal_id", "due_at", "priority", "status", "notes"];
    const defaults = { lifecycle: "lead", stage: "lead", probability: 10, priority: "normal", status: "open", value: 0, ...editor.initial };
    return Object.fromEntries(keys.map(key => [key,
      key === "value" ? String((row?.value || 0) / 100)
        : key === "due_at" && row?.due_at ? new Date(new Date(row.due_at).getTime() - new Date(row.due_at).getTimezoneOffset() * 60000).toISOString().slice(0, 16)
          : (row?.[key] ?? defaults[key] ?? "")]));
  });
  const initialDueInput = useRef(values.due_at);
  const [validation, setValidation] = useState("");
  const [invalidField, setInvalidField] = useState("");
  const formRef = useRef(null);
  // Prevent callbacks retained from dismissed/replaced editors from writing.
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  function dismiss() { if (busy) return; active.current = false; cancel(); }
  function update(key, value) {
    setValues(old => ({ ...old, [key]: value,
      ...(key === "stage" ? { probability: PROBABILITY[STAGES.indexOf(value)] } : {}),
    }));
    if (invalidField === key) { setInvalidField(""); setValidation(""); }
  }
  function fail(key, message) {
    setInvalidField(key); setValidation(message);
    formRef.current?.querySelector(`[name="${key}"]`)?.focus();
  }
  const selectOptions = items => items.map(value => [value, label(value)]);
  const field = (key, title, type = "text", options = null, hint = "", wide = false) => {
    const required = key === "name" || key === "due_at" || (key === "title" && kind !== "contacts") || (key === "contact_id" && kind === "deals");
    const props = { name: key, value: values[key], onChange: e => update(key, e.target.value), required, disabled: busy,
      "aria-invalid": invalidField === key ? true : undefined,
      "aria-describedby": invalidField === key ? `${editor.key}-validation` : hint ? `${editor.key}-${key}-hint` : undefined };
    return h("label", { key, className: wide || key === "notes" || key === "name" || (key === "title" && kind !== "contacts") ? "hc-wide" : undefined },
      h("span", null, title, required && h("span", { className: "hc-required", "aria-hidden": true }, " *")),
      options ? h("select", props,
        (values[key] && !options.some(([value]) => String(value) === String(values[key]))
          ? [...options, [values[key], `Current selection (${values[key]}) · outside loaded choices`]] : options)
          .map(([value, text]) => h("option", { key: value, value }, text)))
        : h(key === "notes" ? "textarea" : "input", { ...props, type: key === "notes" ? undefined : type,
          "data-autofocus": key === (kind === "contacts" ? "name" : "title") ? true : undefined,
          placeholder: key === "notes" ? "Useful context for the next conversation…" : undefined,
          maxLength: key === "notes" ? 10000 : key === "email" ? 254 : key === "title" && kind !== "contacts" ? 200 : 160,
          min: type === "number" ? 0 : undefined, max: key === "probability" ? 100 : key === "value" ? 20000000 : undefined,
          step: key === "value" ? ".01" : type === "number" ? "1" : undefined,
        }),
      hint && h("span", { id: `${editor.key}-${key}-hint`, className: "hc-field-hint" }, hint));
  };
  async function submit(event) {
    event.preventDefault();
    if (!active.current || busy) return;
    setValidation(""); setInvalidField("");
    const payload = { ...values };
    const titleKey = kind === "contacts" ? "name" : "title";
    if (!String(payload[titleKey]).trim()) return fail(titleKey, kind === "contacts" ? "Enter the contact’s full name." : "Enter a title for this record.");
    // Local domains are supported. Native type=email handles browser syntax.
    if (kind === "contacts" && payload.email && !/^[^\s@]+@[^\s@]+$/.test(payload.email)) return fail("email", "Enter a valid email address, or leave email blank.");
    if (kind === "deals") {
      if (!payload.contact_id) return fail("contact_id", "Choose the contact for this deal.");
      try { payload.value = Number(dollarFilter(payload.value)); }
      catch (e) { return fail("value", e.message); }
      if (payload.value === "" || String(values.value).trim() === "") return fail("value", "Enter a deal value, or use 0 when it is not known yet.");
      payload.probability = Number(payload.probability);
      if (values.probability === "" || !Number.isInteger(payload.probability) || payload.probability < 0 || payload.probability > 100) return fail("probability", "Probability must be a whole number from 0 to 100.");
      payload.currency = "USD"; payload.close_date ||= null;
    }
    if (kind === "tasks") {
      if (!payload.due_at || Number.isNaN(new Date(payload.due_at).getTime())) return fail("due_at", "Choose a valid local due date and time.");
      payload.due_at = row?.due_at && payload.due_at === initialDueInput.current ? row.due_at : new Date(payload.due_at).toISOString();
      payload.contact_id ||= null; payload.deal_id ||= null;
    }
    await save(payload);
  }
  const section = (title, fields, description) => h("fieldset", { key: title, className: "hc-form-section", disabled: busy },
    h("legend", null, title), description && h("p", { className: "hc-muted" }, description), h("div", { className: "hc-fields" }, fields));
  const contactOptions = [["", kind === "deals" ? "Select a contact" : "No contact"], ...data.contacts.map(c => [c.id, `${c.name} · ${c.company || c.email || c.id.slice(0, 8)}`])];
  const linkedFields = [field("contact_id", kind === "deals" ? "Contact (required)" : "Contact (optional)", "text", contactOptions, "Choices show up to 500 contacts. An existing link is retained even if it is not in this list.", true)];
  if (kind === "tasks") linkedFields.push(field("deal_id", "Deal (optional)", "text", [["", "No deal"], ...data.deals.filter(deal => !values.contact_id || deal.contact_id === values.contact_id).map(deal => [deal.id, deal.title])], "Changing the contact does not silently clear an existing deal link.", true));
  return h(Drawer, {
    title: `${row ? "Edit" : "New"} ${kind === "contacts" ? "contact" : kind === "deals" ? "deal" : "follow-up"}`,
    subtitle: `${row ? "Update the details for this record." : "Start with the essentials. You can add more context later."} Fields marked * are required.`,
    busy, cancel: dismiss, returnFocus: editor.returnFocus,
  }, h("form", { className: "hc-editor", ref: formRef, onSubmit: submit, "aria-label": `${row ? "Edit" : "Create"} ${kind}`, "aria-busy": busy },
    h("div", { className: "hc-editor-body" },
      kind === "contacts" ? [
        section("Contact details", [field("name", "Full name"), field("email", "Email", "email", null, "Optional. Saving an email does not send a message or sync a mailbox.", true), field("company", "Company"), field("title", "Job title")]),
        section("Relationship", [field("lifecycle", "Contact type", "text", selectOptions(["lead", "customer", "partner"]), "Contact type is separate from the stage of any linked deal.", true)]),
      ] : [section(kind === "deals" ? "Opportunity" : "Follow-up details", [field("title", "Title")]),
        section("Linked records", linkedFields),
        kind === "deals" ? section("Pipeline details", [field("value", "Deal value (USD)", "number"), field("stage", "Stage", "text", selectOptions(STAGES)), field("probability", "Probability (%)", "number", null, "Changing stage sets a suggested probability. You can adjust it."), field("close_date", "Expected close", "date")])
          : section("Timing and status", [field("due_at", "Due date and time (your local timezone)", "datetime-local", null, "Saving a follow-up does not schedule agent work or a reminder.", true), field("priority", "Priority", "text", selectOptions(["normal", "high"])), field("status", "Status", "text", selectOptions(["open", "done"]))]),
      ],
      section("Notes", [field("notes", "Notes", "text", null, "Context stored on this CRM record.")])),
    h("footer", { className: "hc-editor-footer" },
      (validation || error) && h("div", { id: `${editor.key}-validation`, role: "alert", className: "hc-notice" }, validation || error),
      h("div", { className: "hc-row" }, h("small", { className: "hc-muted" }, row ? "Changes are checked against the saved version." : "Saved to this agent’s CRM."),
        h("div", { className: "hc-actions" }, button("Cancel", dismiss, { disabled: busy }),
          h("button", { type: "submit", className: "hc-primary", disabled: busy }, busy ? "Saving…" : "Save record"))))));
}

export default {
  id: "hermes-crm",
  name: "Hermes CRM",
  defaultEnabled: false,
  register(ctx) {
    initializeLifetime(ctx);
    const render = () => h(CRMRoot, { ctx });
    ctx.registerMany([
      {
        id: "pane",
        area: PANES_AREA,
        title: "CRM",
        data: { placement: "main" },
        render,
      },
      { id: "page", area: ROUTES_AREA, data: { path: "/hermes-crm" }, render },
      {
        id: "navigation",
        area: SIDEBAR_NAV_AREA,
        data: { path: "/hermes-crm", label: "CRM", codicon: "organization" },
      },
      {
        id: "open",
        area: PALETTE_AREA,
        data: {
          id: "hermes-crm.open",
          label: "Open Hermes CRM",
          keywords: ["contacts", "sales", "pipeline", "follow-ups"],
          run: () => host.navigate("/hermes-crm"),
        },
      },
    ]);
  },
};
