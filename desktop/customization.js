import { createElement as h, useEffect, useRef, useState } from "react";

export function catalogStages(catalog, includeArchived = false) {
  return (catalog?.stages || []).filter(stage => includeArchived || !stage.archived).slice().sort((a, b) => a.order - b.order || a.key.localeCompare(b.key));
}
export function customFieldValue(field, value) {
  if (value === "") return null;
  if (field.type === "number") {
    const number = Number(value);
    if (!Number.isFinite(number)) throw new Error(`${field.label} must be a finite number.`);
    return number;
  }
  if (field.type === "boolean") return value === true || value === "true";
  return value;
}
export function CustomFieldInputs({ fields, values, update, disabled }) {
  return fields.filter(field => !field.archived).map(field => {
    const raw = values[field.key];
    const value = raw == null ? "" : field.type === "boolean" ? String(raw) : raw;
    const props = { name: `custom_${field.key}`, value, disabled, onChange: e => update(field.key, customFieldValue(field, e.target.value)) };
    return h("label", { key: field.key }, h("span", null, field.label),
      field.type === "boolean" || field.type === "single-select" ? h("select", props,
        h("option", { value: "" }, "Not set"),
        (field.type === "boolean" ? [["true", "Yes"], ["false", "No"]] : (field.choices || []).map(choice => typeof choice === "string" ? [choice, choice] : [choice.key, choice.label])).map(([key, label]) => h("option", { key, value: key }, label)))
        : h("input", { ...props, type: field.type === "number" ? "number" : field.type === "date" ? "date" : "text", step: field.type === "number" ? "any" : undefined }),
      field.description && h("small", null, field.description));
  });
}
export function Customization({ catalog, client, workspaceToken, current, onSaved, cancel, returnFocus, Drawer }) {
  const [tab, setTab] = useState("stages"), [kind, setKind] = useState("contacts");
  const [draft, setDraft] = useState(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(null);
  const [savedPendingRefresh, setSavedPendingRefresh] = useState(false);
  const confirmed = useRef(false);
  const live = useRef(true), lock = useRef(false), currentRef = useRef(current);
  currentRef.current = current;
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  const valid = () => live.current && client.current() && currentRef.current();
  const records = tab === "stages" ? catalogStages(catalog, true) : catalog.fields[kind];
  function change(key, value) { if (valid() && !lock.current && !attempt) setDraft(old => ({ ...old, [key]: value, ...(key === "outcome" ? { probability: value === "won" ? 100 : value === "lost" ? 0 : 10 } : {}) })); }
  function choose(value) { if (valid() && !lock.current && !attempt) { setDraft(value); setError(""); } }
  async function refreshSaved() {
    try {
      const refreshed = await onSaved();
      if (!valid()) return;
      if (refreshed !== true) throw new Error("Catalog refresh failed.");
      setAttempt(null); setDraft(null); setSavedPendingRefresh(false); setError("");
      confirmed.current = false;
    } catch (e) {
      if (valid()) {
        setSavedPendingRefresh(true);
        setError("Your changes were saved, but the latest catalog could not be loaded. Refresh the catalog before editing again. This does not resend the saved change.");
      }
    }
  }
  async function retryRefresh() {
    if (!valid() || lock.current || !confirmed.current) return;
    lock.current = true; setBusy(true);
    try { await refreshSaved(); }
    finally { lock.current = false; if (valid()) setBusy(false); }
  }
  async function perform(frozen) {
    if (!valid() || lock.current || confirmed.current) return;
    lock.current = true; setBusy(true); setAttempt(frozen); setError("");
    try {
      await client.request(frozen.path, frozen.options);
      if (!valid()) return;
      confirmed.current = true;
      await refreshSaved();
    } catch (e) {
      if (valid()) setError(`${e.message} Changes are frozen because this save was not confirmed. ${frozen.options.method === "POST" ? "Retry sends exactly the same request, or close and refresh before reopening." : "Close and refresh the catalog, then reopen this definition. Do not overwrite a newer version."}`);
    } finally { lock.current = false; if (valid()) setBusy(false); }
  }
  function submit(event) {
    event.preventDefault();
    if (!valid() || lock.current || attempt || !draft) return;
    const { version, key, label, description, order, archived } = draft;
    const data = { label: label.trim(), description: description || "", order: Number(order), archived: Boolean(archived) };
    if (!version) data.key = key;
    else data.version = version;
    if (tab === "stages") { Object.assign(data, { probability: draft.outcome === "won" ? 100 : draft.outcome === "lost" ? 0 : Number(draft.probability), color: draft.color }); if (!version) data.outcome = draft.outcome; }
    else { if (!version) data.type = draft.type; data.choices = draft.type === "single-select" ? draft.choices.split("\n").map(x => x.trim()).filter(Boolean) : []; }
    const path = `/customization/${tab === "stages" ? "stages" : `fields/${kind}`}${version ? `/${encodeURIComponent(key)}` : ""}`;
    perform({ path, options: { method: version ? "PATCH" : "POST", body: { workspace_token: workspaceToken, data, ...(!version ? { idempotency_key: crypto.randomUUID() } : {}) } } });
  }
  const input = (key, title, type = "text", options) => h("label", { key }, h("span", null, title), options ? h("select", { value: draft[key], disabled: busy || !!attempt || (Boolean(draft.version) && ["type", "outcome"].includes(key)), onChange: e => change(key, e.target.value) }, options.map(value => h("option", { key: value, value }, value.replaceAll("_", " ")))) : h(key === "description" || key === "choices" ? "textarea" : "input", { value: draft[key] ?? "", type, required: ["key", "label", "order", "probability"].includes(key), disabled: busy || !!attempt || (key === "key" && !!draft.version) || (key === "probability" && draft.outcome !== "open"), min: type === "number" ? 0 : undefined, max: key === "probability" ? 100 : undefined, maxLength: key === "key" ? (tab === "stages" ? 20 : 64) : key === "label" ? 120 : key === "description" ? 2000 : undefined, pattern: key === "key" ? "[a-z][a-z0-9_]*" : undefined, onChange: e => change(key, e.target.value) }));
  return h(Drawer, { title: "Customize CRM", subtitle: "One pipeline. Stable internal keys keep records linked when labels change.", busy: busy && valid(), cancel: () => { if (!busy || !valid()) { live.current = false; cancel(); } }, returnFocus },
    h("div", { className: "hc-editor-body" },
      h("nav", { className: "hc-tabs", "aria-label": "Customization sections" }, ["stages", "fields"].map(value => h("button", { type: "button", key: value, "aria-current": tab === value ? "page" : undefined, disabled: busy || !!attempt, onClick: () => { if (valid()) { setTab(value); setDraft(null); setError(""); } } }, value === "stages" ? "Deal stages" : "Custom fields"))),
      tab === "fields" && h("label", null, "Record type", h("select", { value: kind, disabled: busy || !!attempt, onChange: e => { if (valid()) { setKind(e.target.value); setDraft(null); } } }, ["contacts", "deals", "tasks"].map(value => h("option", { key: value, value }, value)))),
      h("p", { className: "hc-muted" }, tab === "stages" ? "Deal stage is separate from contact type. Outcome cannot change. Won is 100%; lost is 0%. Stages used by records cannot be archived." : "All custom fields are optional. Internal key and type cannot change. Archive hides a field from forms and preserves stored values. Existing select choices cannot be removed."),
      !draft && h("div", { className: "hc-list" }, records.length ? records.map(item => h("button", { type: "button", key: item.key, className: "hc-list-item", onClick: () => choose({ ...item, choices: (item.choices || []).join("\n") }) }, `${item.label}${item.archived ? " · Archived" : ""}`, h("small", null, ` ${item.key} · ${item.outcome || item.type} · Version ${item.version}`))) : h("p", null, "No custom fields yet. Add an optional field for this record type.")),
      !draft && h("button", { type: "button", onClick: () => choose({ key: "", label: "", description: "", order: records.length, probability: 10, outcome: "open", color: "#4779ce", type: "text", choices: "", archived: false }) }, tab === "stages" ? "Add stage" : "Add field"),
      draft && h("form", { onSubmit: submit, "aria-label": "Definition editor" }, h("div", { className: "hc-fields" }, input("label", "Label"), input("key", "Internal key"), input("description", "Description"), input("order", "Display order", "number"),
        ...(tab === "stages" ? [input("outcome", "Outcome (permanent)", "text", ["open", "won", "lost"]), input("probability", "Probability (%)", "number"), input("color", "Stage color", "color")] : [input("type", "Field type (permanent)", "text", ["text", "number", "boolean", "date", "single-select"]), draft.type === "single-select" && input("choices", "Choices (one per line)")]),
        !!draft.version && h("label", null, h("span", null, "Archived"), h("input", { type: "checkbox", checked: draft.archived, disabled: busy || !!attempt, onChange: e => change("archived", e.target.checked) }))),
        h("p", { className: "hc-muted" }, "Internal keys use lowercase letters, numbers and underscores, beginning with a letter. Existing keys and field types are permanent."),
        h("div", { className: "hc-actions" }, h("button", { type: "submit", disabled: busy || !!attempt, className: "hc-primary" }, busy ? "Saving…" : "Save definition"), h("button", { type: "button", disabled: busy || !!attempt, onClick: () => choose(null) }, "Cancel edit"))),
      error && h("p", { role: "alert", className: "hc-notice" }, error),
      savedPendingRefresh && !busy && h("button", { type: "button", onClick: retryRefresh }, "Refresh saved catalog"),
      !savedPendingRefresh && attempt?.options.method === "POST" && !busy && error && h("button", { type: "button", onClick: () => perform(attempt) }, "Retry exact save")));
}
