import { createElement as h, useEffect, useRef, useState } from "react";

// A client is bound to a monotonic Desktop route lifetime. Pending/unknown writes
// survive contact-panel remounts; a network exception is never a retry signal.
const emailAttempts = new WeakMap();
export function emailValidStatus(value) {
  if (!value || typeof value.enabled !== "boolean" || typeof value.connected !== "boolean" ||
      !Number.isSafeInteger(value.revision) || value.revision < 0 ||
      !(value.mailbox === null || typeof value.mailbox === "string") ||
      (value.connected && !value.mailbox)) return false;
  const op = value.operation;
  return op == null || (typeof op.id === "string" && typeof op.kind === "string" &&
    ["running", "finished", "partial", "failed", "cancelled"].includes(op.state));
}
export function emailTime(value) {
  if (value === null || value === undefined || value === "") return "Unavailable";
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toISOString().replace("T", " ").replace(".000Z", " UTC") : "Unavailable";
}
export function createEmailHistorySession(client, workspaceToken, contact, isCurrent = () => true) {
  let alive = true, sequence = 0;
  const locks = emailAttempts.get(client) || new Map();
  emailAttempts.set(client, locks);
  const scope = workspaceToken;
  const current = () => alive && client.current() && isCurrent();
  const query = new URLSearchParams({ workspace_token: workspaceToken });
  return {
    current,
    close() { alive = false; sequence++; },
    pending: () => locks.get(scope),
    async load() {
      const ticket = ++sequence;
      const [status, history] = await Promise.all([
        client.request(`/email/status?${query}`),
        client.request(`/email/contacts/${encodeURIComponent(contact.id)}?${query}&limit=100&offset=0`),
      ]);
      if (!current() || ticket !== sequence) return null;
      if (!emailValidStatus(status) || !history || !Array.isArray(history.items) ||
          !Number.isSafeInteger(history.total) || history.total < 0) throw new Error("Invalid local response");
      const pending = locks.get(scope);
      // A durable scoped receipt can reconcile even after another operation.
      let receipt = status.operation;
      if (pending?.id && receipt?.id !== pending.id) {
        try { receipt = await client.request(`/email/operations/${encodeURIComponent(pending.id)}?${query}`); }
        catch { receipt = null; } // Missing/failed lookup is not permission to retry.
      }
      if (!current() || ticket !== sequence) return null;
      if (pending?.id && locks.get(scope) === pending && receipt?.id === pending.id && receipt.kind === pending.kind &&
          ["finished", "partial", "failed", "cancelled"].includes(receipt.state)) locks.delete(scope);
      return { status, history };
    },
    async submit(kind, status, values = {}) {
      const previous = locks.get(scope);
      const invalidateRead = kind === "disconnect" && previous && ["verify", "sync"].includes(previous.kind);
      if (!current() || (previous && !invalidateRead) || !emailValidStatus(status)) return null;
      if (!["verify", "sync", "disconnect", "clear"].includes(kind)) throw new Error("Unsupported operation");
      const id = crypto.randomUUID();
      const body = { workspace_token: workspaceToken, expected_revision: status.revision };
      body.operation_id = id;
      if (["verify", "sync"].includes(kind)) body.consent = true;
      if (kind === "verify") body.mailbox = values.mailbox;
      if (kind === "sync") Object.assign(body, {
        contact_id: contact.id, expected_contact_version: contact.version, days: values.days,
      });
      if (kind === "clear") body.confirm = true;
      const attempt = { id, state: "running", kind };
      locks.set(scope, attempt);
      try {
        if (kind === "disconnect") {
          // Cancellation uses a fresh LOCAL revision; this never reads Gmail.
          const fresh = await client.request(`/email/status?${query}`);
          if (!emailValidStatus(fresh)) throw new Error("Unconfirmed local state");
          if (!current() || locks.get(scope) !== attempt) return null;
          body.expected_revision = fresh.revision;
        }
        const result = await client.request(`/email/${kind}`, { method: "POST", body });
        if (!current() || locks.get(scope) !== attempt) return null;
        if (!emailValidStatus(result) || result.operation?.id !== id || result.operation.kind !== kind ||
            !["finished", "partial", "failed", "cancelled"].includes(result.operation.state)) throw new Error("Unconfirmed result");
        locks.delete(scope);
        return result;
      } catch {
        if (locks.get(scope) !== attempt) return null;
        locks.set(scope, { id, state: "unknown", kind });
        throw new Error("Outcome unknown. Refresh local status to check the recorded result. Do not repeat this action or change accounts while it is unresolved.");
      }
    },
  };
}

export const emailHistoryCSS = `
.hermes-crm-native .hc-email{border:1px solid var(--hc-border);border-radius:4px;padding:24px;min-width:0;overflow-wrap:anywhere;background:var(--hc-panel);color:var(--hc-ink);font-size:14px;line-height:21px}
.hermes-crm-native .hc-email h3{font-size:18px;line-height:24px;margin:0 0 16px}
.hermes-crm-native .hc-email p{margin:0 0 16px}
.hermes-crm-native .hc-email-actions{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
.hermes-crm-native .hc-email-review{border:1px solid var(--hc-border);border-radius:4px;padding:16px;margin:24px 0;display:grid;gap:16px;background:var(--hc-bg)}
.hermes-crm-native .hc-email-review p,.hermes-crm-native .hc-email-review .hc-email-actions{margin:0}
.hermes-crm-native .hc-email-review label{display:grid;gap:8px;font-size:13px;line-height:18px}
.hermes-crm-native .hc-email-review input[type=checkbox]{flex:0 0 auto;width:16px;height:16px;margin:2px 0 0;accent-color:var(--hc-action)}
.hermes-crm-native .hc-email-review input,.hermes-crm-native .hc-email-review select{max-width:100%;min-width:0}
.hermes-crm-native .hc-email small,.hermes-crm-native .hc-email .hc-muted{display:block;color:var(--hc-secondary);opacity:1;font-size:13px;line-height:18px}
.hermes-crm-native .hc-email .hc-email-consent{display:flex;flex-direction:row;align-items:flex-start;gap:8px;font-size:14px;line-height:21px;padding:8px 0}
.hermes-crm-native .hc-email dl{margin:16px 0 0;display:grid;gap:12px}
.hermes-crm-native .hc-email dt{font-size:12px;line-height:16px;color:var(--hc-secondary);margin-bottom:4px}
.hermes-crm-native .hc-email dd{margin:0;white-space:pre-wrap;font-size:14px;line-height:21px}
.hermes-crm-native .hc-email .hc-timeline{list-style:none;padding:0;margin:24px 0 16px;display:grid;gap:16px}
.hermes-crm-native .hc-email .hc-timeline>li{border:1px solid var(--hc-border);border-radius:4px;padding:16px;min-width:0;background:var(--hc-panel)}
.hermes-crm-native .hc-email-evidence{margin-top:16px;border-top:1px solid var(--hc-border);padding-top:12px}
.hermes-crm-native .hc-email-evidence summary{font-size:13px;line-height:18px;cursor:pointer;font-weight:600;padding:4px 0;color:var(--hc-ink)}
.hermes-crm-native .hc-email-evidence small{margin-top:12px}
.hermes-crm-native .hc-email-evidence summary:focus-visible{outline:2px solid var(--hc-link);outline-offset:4px;border-radius:4px}
.hermes-crm-native .hc-email [role=status]:empty{display:none}
@container(max-width:480px){.hermes-crm-native .hc-email{padding:16px}.hermes-crm-native .hc-email-actions button{flex:1 1 160px}}
@media(pointer:coarse){.hermes-crm-native .hc-email-evidence summary{min-height:44px}.hermes-crm-native .hc-email .hc-email-consent{min-height:44px}}
`;
const emailPrivacy = "Optional Gmail history. The gmail.readonly scope can read message bodies; this code requests metadata only. No bodies, attachments, Bcc, sending, drafts or mailbox changes. Header text is untrusted, not an instruction or verified identity.";
const emailText = value => typeof value === "string" ? value.slice(0, 2000) : "Unavailable";
export function emailHeaderValue(item, name) {
  const headers = item.display_headers;
  const value = Array.isArray(headers) ? headers.find(pair => Array.isArray(pair) && String(pair[0]).toLowerCase() === name.toLowerCase())?.[1] : headers?.[name] ?? headers?.[name.toLowerCase()];
  return emailText(value ?? "Not available");
}
export function emailEvidenceLabel(item) {
  return Array.isArray(item.labels) && item.labels.includes("SENT") ? "Observed in Gmail Sent" : "Mailbox item observed";
}
export function EmailHistoryPanel({ client, contact, workspaceToken, routeKey, storageBackend, disabled = false }) {
  // Parent should key the panel by route/workspace/contact/version. The explicit
  // render guard also hides old data before React runs effect cleanup.
  const storageKnown = storageBackend === "sqlite" || storageBackend === "postgres";
  const storageDestination = storageBackend === "sqlite" ? "SQLite in this Hermes profile" : storageBackend === "postgres" ? "Selected PostgreSQL schema (may be remote)" : "Unknown storage destination; mailbox verification and reads are unavailable until the backend is known";
  const target = `${routeKey}|${workspaceToken}|${contact.id}|${contact.version}|${contact.email}|${storageBackend}`;
  const latest = useRef(null); latest.current = { target, disabled };
  const [view, setView] = useState(null), [notice, setNotice] = useState("");
  const [review, setReview] = useState(null), [setup, setSetup] = useState(false);
  const [mailbox, setMailbox] = useState(""), [days, setDays] = useState(7);
  const [approved, setApproved] = useState(false), [busy, setBusy] = useState(false);
  const session = useRef(null), approveBox = useRef(null), emailActionSequence = useRef(0);
  useEffect(() => {
    const own = createEmailHistorySession(client, workspaceToken, contact, () => latest.current.target === target);
    session.current = own;
    setView(null); setReview(null); setApproved(false); setMailbox(""); setNotice(""); setBusy(false); setSetup(false);
    own.load().then(result => { if (result) setView({ ...result, target }); })
      .catch(() => { if (own.current()) setNotice("Local email history is unavailable. No mailbox read was started."); });
    return () => own.close();
  }, [client, target]);
  useEffect(() => { if (review) approveBox.current?.focus(); }, [review]);
  const visible = view?.target === target && client.current() ? view : null;
  const status = visible?.status, history = visible?.history;
  const pending = session.current?.pending();
  const cancellingRead = review === "disconnect" && pending && ["verify", "sync"].includes(pending.kind);
  const formBusy = busy && !cancellingRead;
  const canDisconnect = !disabled && !!status && client.current() &&
    (!pending || ["verify", "sync"].includes(pending.kind)) &&
    (status.connected || status.operation?.state === "running" || !!pending);
  const blocked = disabled || busy || !status || !client.current() || !!pending || status.operation?.state === "running";
  const button = (label, onClick, extra = {}) => h("button", { type: "button", onClick, ...extra }, label);
  async function refresh() {
    const own = session.current;
    setBusy(true);
    try { const result = await own.load(); if (result) { setView({ ...result, target }); setNotice("Local status refreshed. No provider read was started."); } }
    catch { if (own.current()) setNotice("Local status unavailable. Any pending outcome remains unknown."); }
    finally { if (own.current()) setBusy(false); }
  }
  function open(kind) { setApproved(false); setReview(kind); setNotice(""); }
  async function submit(event) {
    event.preventDefault();
    if ((blocked && !(review === "disconnect" && canDisconnect)) || !approved || !review || latest.current.disabled ||
        (["verify", "sync"].includes(review) && !storageKnown)) return;
    const own = session.current;
    const existingAttempt = own.pending();
    if (existingAttempt && !(review === "disconnect" && ["verify", "sync"].includes(existingAttempt.kind))) return;
    const actionTicket = ++emailActionSequence.current;
    const actionCurrent = () => own.current() && actionTicket === emailActionSequence.current;
    setBusy(true);
    try {
      const result = await own.submit(review, status, { mailbox: mailbox.trim(), days });
      if (result && actionCurrent()) {
        setReview(null); setApproved(false);
        const loaded = await own.load(); if (loaded && actionCurrent()) setView({ ...loaded, target });
        if (actionCurrent()) setNotice("Recorded result refreshed. Check the operation state and coverage below.");
      }
    } catch { if (actionCurrent()) setNotice("Outcome unknown. Refresh local status to reconcile. Do not repeat the action or change accounts until resolved."); }
    finally { if (actionCurrent()) setBusy(false); }
  }
  const operation = history?.last_operation || status?.operation;
  const items = Array.isArray(history?.items) ? history.items : [];
  return h("section", { className: "hc-email", "aria-label": "Optional Gmail history" },
    h("style", null, emailHistoryCSS), h("h3", null, "Email history"),
    h("p", { className: "hc-muted" }, emailPrivacy),
    h("p", { className: "hc-muted" }, `Storage destination: ${storageDestination}.`),
    h("p", null, status ? !status.enabled ? "Disabled · optional plugin setting is off" : status.connected && status.mailbox ? `Verified own mailbox: ${emailText(status.mailbox)}` : "Not verified · no connected mailbox" : "Loading local status…"),
    h("div", { className: "hc-email-actions" },
      button(setup ? "Hide setup" : "Setup & privacy", () => setSetup(!setup)),
      button("Refresh local status", refresh, { disabled: disabled || !client.current() }),
      button("Verify own mailbox", () => open("verify"), { disabled: blocked || !storageKnown || !status?.enabled || status?.connected || !!status?.mailbox }),
      button("Read Gmail history", () => open("sync"), { disabled: blocked || !storageKnown || !status?.enabled || !status?.connected || !contact.email })),
    setup && h("div", { className: "hc-email-review" },
      h("strong", null, "User-controlled setup"),
      h("p", null, `Storage destination: ${storageDestination}. This destination holds retained Gmail metadata and identity records.`),
      h("p", null, "Enable the optional Gmail history plugin setting, register your own Google Desktop app client, and configure its client fields through Hermes host-managed secret settings. Review the requested Gmail readonly, OpenID and email identity permissions. Sign in yourself through the Hermes terminal only after approving that account access and persistent grant. This panel does not start sign-in or grant access."),
      h("p", null, "Use only your own mailbox. Keep the selected Hermes profile, account and client configuration unchanged during a read. Verification checks the exact mailbox you enter; each contact/date read needs separate approval. Metadata is stored in this CRM workspace. Forget removes locally retained email history and resets the local identity; disconnect stops the local binding. Neither revokes Google's grant. Manage grant revocation separately in your Google account.")),
    visible && review && h("form", { className: "hc-email-review", onSubmit: submit, "aria-label": "Review email history action" },
      h("strong", null, review === "verify" ? "Review mailbox verification" : review === "sync" ? "Review this bounded read" : review === "clear" ? "Forget local email history" : "Disconnect local mailbox binding"),
      review === "verify" && h("label", null, "Exact own mailbox email", h("input", { type: "email", required: true, value: mailbox, disabled: formBusy, onChange: event => { setMailbox(event.target.value); setApproved(false); }, autoComplete: "off" })),
      review === "verify" && h("p", null, `Verified identity storage destination: ${storageDestination}.`),
      review === "verify" && h("p", null, "Approves a provider identity and Gmail profile check for this exact mailbox, not a message-history read. Requires your separately authorized Hermes sign-in. After disconnecting, forget retained history before verifying again."),
      review === "sync" && h("div", null,
        h("p", null, `Storage destination: ${storageDestination}. Retained observations are saved there until explicitly forgotten.`),
        h("p", null, `Own mailbox: ${emailText(status.mailbox)}. Exact selected contact address: ${emailText(contact.email)}.`),
        h("label", null, "Date window ending at read time", h("select", { value: days, disabled: formBusy, onChange: event => { setDays(Number(event.target.value)); setApproved(false); } }, h("option", { value: 7 }, "Last 7 days"), h("option", { value: 30 }, "Last 30 days"))),
        h("p", null, "Read only selected From, To, Cc, Subject and Date headers, labels, IDs and provider ordering timestamps for this exact address and date range. Store observations in this CRM workspace. Enumeration is bounded and may be partial; absence does not prove no messages exist. No automatic refresh or background sync.")),
      ["verify", "sync"].includes(review) && h("p", null, "This approved operation can finish and save to the original CRM workspace after you navigate away. Navigation hides stale results; it does not cancel the server operation. Use Disconnect locally to invalidate further reads and publication. An already dispatched provider request cannot be recalled."),
      review === "clear" && h("p", null, "Remove all locally retained Gmail history in this workspace, not just this contact, and reset the local mailbox identity and binding. Gmail messages and Google's grant are unaffected."),
      review === "disconnect" && h("p", null, "Disconnect this workspace's local mailbox binding. Retained observations remain until separately forgotten. Any running read is invalidated locally; already dispatched provider requests cannot be recalled. This does not sign out of Hermes or revoke Google's grant."),
      h("label", { className: "hc-email-consent" }, h("input", { ref: approveBox, type: "checkbox", checked: approved, disabled: formBusy, onChange: event => setApproved(event.target.checked) }), "I reviewed and approve this specific action."),
      h("div", { className: "hc-email-actions" }, h("button", { type: "submit", className: "hc-primary", disabled: (blocked && !(review === "disconnect" && canDisconnect)) || !approved }, formBusy ? "Working…" : "Confirm reviewed action"), button("Cancel", () => { setReview(null); setApproved(false); }, { disabled: formBusy }))),
    h("p", { role: "status", "aria-live": "polite" }, pending ? "An operation is pending or its outcome is unknown. Refresh local status; do not resubmit." : notice),
    operation && h("p", { className: "hc-muted" }, `Last operation: ${emailText(operation.kind)} · ${emailText(operation.state)}${operation.reason ? ` · ${emailText(operation.reason)}` : ""}. Coverage is limited to the approved window; not all-time history or proof of delivery.`),
    operation?.days && h("p", { className: "hc-muted" }, `Approved ${operation.days}-day window: ${emailTime(operation.start_ms)} to ${emailTime(operation.end_ms)}. ${operation.coverage === "complete_query" ? "Window query finished" : operation.coverage === "partial" ? "Partial window coverage" : "Coverage unknown"}. Not a transactional mailbox snapshot.`),
    h("p", { className: "hc-muted" }, "Last observed metadata only, not current mailbox state. Labels may have changed since observation. A later query cannot prove deletion or absence of messages it did not return."),
    h("ul", { className: "hc-timeline", "aria-label": "Gmail metadata observations" }, items.map((item, index) => h("li", { key: `${item.message_id}:${index}` },
      h("strong", null, emailEvidenceLabel(item)),
      h("details", { className: "hc-email-evidence" }, h("summary", null, "Observation provenance and read window"),
      h("small", null, `Provider ordering time: ${emailTime(item.internal_date_ms)} (${emailText(String(item.internal_date_ms ?? "Unavailable"))} ms). Not verified send or receive time.`),
      h("small", null, `Recorded observation: ${emailTime(item.observed_at)}. Mailbox at observation: ${emailText(item.mailbox ?? item.provenance?.mailbox)}.`),
      h("small", null, `Provenance: ${emailText(item.provenance?.adapter)} · ${emailText(item.provenance?.kind)}. Read window: ${emailTime(item.provenance?.start_ms)} to ${emailTime(item.provenance?.end_ms)}. This is retained evidence, not a delivery receipt.`)),
      h("dl", null, ["From", "To", "Cc", "Subject", "Date"].map(name => h("div", { key: name }, h("dt", null, name), h("dd", null, emailHeaderValue(item, name))))),
      Array.isArray(item.header_issues) && item.header_issues.length > 0 && h("small", null, "Some header metadata was unavailable or rejected.")))),
    visible && !items.length && h("p", { className: "hc-muted" }, "No locally retained observations for this contact. This does not prove no email exists."),
    visible && h("small", null, `Showing ${items.length} of ${Number.isSafeInteger(history.total) ? history.total : "unknown"} retained observations (maximum 100). Headers are plain text.`),
    visible && h("div", { className: "hc-email-actions" }, button("Disconnect locally", () => open("disconnect"), { disabled: !canDisconnect }), button("Forget local email history", () => open("clear"), { disabled: blocked })));
}
