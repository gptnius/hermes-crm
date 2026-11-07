"use strict";
const $ = (s) => document.querySelector(s),
  esc = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
let stages = ["lead", "qualified", "proposal", "negotiation", "won", "lost"];
let catalog = { stages: [], fields: {} };
function adoptCatalog(meta) {
  if (!meta?.catalog || !Array.isArray(meta.catalog.stages)) return;
  catalog = meta.catalog;
  stages = catalog.stages.filter(s => !s.archived).map(s => s.key);
}
const stageLabel = key => catalog.stages.find(s => s.key === key)?.label || label(key);
const stageColor = (key, index) => {
  const color = catalog.stages.find(s => s.key === key)?.color;
  return /^#[0-9a-fA-F]{6}$/.test(color || "") ? color : ["#427f77", "#447fa6", "#8264ac", "#b88736", "#397a4c", "#b05d65"][index % 6];
};
function stageBadge(key) {
  return `<span class="badge ${esc(key)}">${esc(stageLabel(key))}</span>`;
}
function customFieldDetails(kind, record) {
  const values = record.custom_fields || {};
  const fields = (catalog.fields[kind] || []).filter(f => Object.hasOwn(values, f.key));
  if (!fields.length) return "";
  return `<section><h3>Custom fields</h3><dl class="detail-meta">${fields.map(f => `<div><dt>${esc(f.label)}${f.archived ? " (archived)" : ""}</dt><dd>${esc(typeof values[f.key] === "boolean" ? (values[f.key] ? "Yes" : "No") : values[f.key])}</dd></div>`).join("")}</dl><p class="subtitle">Edit custom fields in Hermes Desktop.</p></section>`;
}
const label = (s) =>
  String(s || "")
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
const money = (v) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format((Number(v) || 0) / 100);
const date = (v) =>
  v
    ? new Date(v.length === 10 ? v + "T12:00:00" : v).toLocaleDateString(
        undefined,
        { month: "short", day: "numeric", year: "numeric" },
      )
    : "No date";
const initials = (s) =>
  (s || "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((x) => x[0])
    .join("")
    .toUpperCase();
const state = {
  page: "overview",
  contacts: [],
  deals: [],
  tasks: [],
  query: "",
  stage: "",
  taskFilter: "open",
  filters: {},
  offset: 0,
  total: 0,
  report: "",
  render: 0,
};
let toastTimer,
  searchTimer,
  modalOpener,
  modalEpoch = 0;
async function api(path, method = "GET", body, key) {
  const r = await fetch("/api/" + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CRM-Actor": "ui",
      ...(key ? { "Idempotency-Key": key } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  let data;
  try {
    data = await r.json();
  } catch {
    throw new Error(
      "The server returned an unreadable response. Please try again.",
    );
  }
  if (!r.ok) throw new Error(data.error || "Request failed. Please try again.");
  return data;
}
const list = (data) => (Array.isArray(data) ? data : []);
function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 4000);
}
function empty(message) {
  return `<div class="empty">${esc(message)}</div>`;
}
function badge(value) {
  return `<span class="badge ${esc(value)}">${esc(label(value))}</span>`;
}
function head(title, subtitle, actions = "") {
  return `<div class="page-head"><div><h1>${title}</h1><div class="subtitle">${subtitle}</div></div><div class="buttons">${actions}</div></div>`;
}
function createButton(type) {
  return `<button class="button primary" data-action="new-${type}"><span aria-hidden="true">＋</span> Add ${type}</button>`;
}
function contactTable(rows) {
  return rows.length
    ? `<div class="table-scroll" role="region" aria-label="Contacts table" tabindex="0"><table><thead><tr><th scope="col">Name</th><th scope="col">Company</th><th scope="col">Contact type</th><th scope="col">Linked deal stages</th><th scope="col">Added</th></tr></thead><tbody>${rows.map((c) => `<tr><td><div class="person"><span class="avatar" aria-hidden="true">${esc(initials(c.name))}</span><div><button class="name-button" data-action="contact" data-id="${esc(c.id)}">${esc(c.name)}</button><small>${esc(c.email || "No email added")}</small></div></div></td><td>${esc(c.company || "—")}</td><td>${badge(c.lifecycle)}</td><td>${Array.isArray(c.deal_stages) ? (c.deal_stages.map(stageBadge).join(" ") || "Unassigned") : "See contact details"}</td><td>${date(c.created_at)}</td></tr>`).join("")}</tbody></table></div>`
    : empty("No matching contacts. Change filters or add a contact.");
}
function taskRows(rows) {
  return rows.length
    ? rows
        .map((t) => {
          const overdue =
            t.status !== "done" && t.due_at && new Date(t.due_at) < new Date();
          return `<div class="task-row"><button class="check" aria-pressed="${t.status === "done"}" data-action="toggle-task" data-id="${esc(t.id)}" aria-label="${t.status === "done" ? "Reopen" : "Complete"} ${esc(t.title)}">${t.status === "done" ? "✓" : ""}</button><div class="task-copy"><button data-action="task" data-id="${esc(t.id)}">${esc(t.title)}</button><div class="task-meta">${esc(t.contact_name || "Workspace task")}${t.priority === "high" ? " · High priority" : ""}</div></div><span class="due ${overdue ? "overdue" : ""}">${t.status === "done" ? "Done" : (overdue ? "Overdue · " : "") + date(t.due_at)}</span></div>`;
        })
        .join("")
    : empty("All clear. No tasks to show.");
}
function activityRows(rows) {
  return rows.length
    ? rows
        .map(
          (a) =>
            `<div class="activity-row"><span class="activity-icon" aria-hidden="true">${String(a.entity_type || "").includes("task") ? "✓" : "↗"}</span><div class="activity-copy">${esc(a.summary || a.description || [label(a.entity_type), label(a.action), a.entity_name].filter(Boolean).join(" · ") || "Workspace updated")}<small>${esc(a.actor || "Workspace")} · ${date(a.created_at)}</small></div></div>`,
        )
        .join("")
    : empty("Activity will appear as your workspace changes.");
}
function dealCards(rows) {
  return rows
    .map(
      (d) =>
        `<button class="deal-card" data-action="deal" data-id="${esc(d.id)}"><strong>${esc(d.title)}</strong><small>${esc(d.contact_name || "No contact linked")}</small><div class="amount">${money(d.value)}</div><div class="deal-bottom"><span>${date(d.close_date)}</span><span>${Number(d.probability) || 0}% likely</span></div></button>`,
    )
    .join("");
}
let pendingReport = false;
function queryString(params) {
  const pairs = Object.entries(params).filter(([,v]) => v !== undefined && v !== null && v !== "");
  return pairs.length ? "?" + pairs.map(([k,v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v)).join("&") : "";
}
function dollarCents(value) {
  if (value === undefined || value === "") return undefined;
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) throw new Error("Enter a nonnegative USD amount with at most two decimal places.");
  const [whole, fraction = ""] = String(value).split(".");
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2,"0"));
  if (!Number.isSafeInteger(cents) || cents > 2000000000) throw new Error("The value is too large.");
  return cents;
}
function filterSelect(key, title, values) {
  return `<label class="filter-label">${esc(title)}<select data-filter="${key}" aria-label="${esc(title)}">${values.map(([v,t]) => `<option value="${esc(v)}" ${state.filters[key] === v ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>`;
}
function filterInput(key, title, type = "text") {
  return `<label class="filter-label">${esc(title)}<input data-filter="${key}" type="${type}" ${type === "number" ? 'min="0" step="0.01"' : ""} aria-label="${esc(title)}" value="${esc(state.filters[key] || "")}"></label>`;
}
function preserveSelection(rows, id, name, type) {
  return !id || rows.some(r => String(r.id) === String(id)) ? rows : [...rows, {id, name: name || `Current ${type} (${id})`, title: name || `Current ${type} (${id})`}];
}
function openReport(filters, title) {
  closeModal(false); clearTimeout(searchTimer); state.render++;
  state.filters = filters; state.query = ""; state.stage = ""; state.offset = 0; state.report = title;
  if (location.hash === "#contacts") { state.page = "contacts"; render(); }
  else { pendingReport = true; location.hash = "contacts"; }
}
function stageChart(rows) {
  const data = [...new Set([...stages, ...rows.map(r => r.stage)])].map(stage => ({stage, value: 0, count: 0, contact_count: 0, ...rows.find(r => r.stage === stage)}));
  const total = data.reduce((n,s) => n + Number(s.value || 0),0);
  let offset = 0;
  const details = s => `${stageLabel(s.stage)}: ${money(s.value)} USD · ${total ? (s.value / total * 100).toFixed(1) : "0.0"}% · ${Number(s.count)} deals · ${Number(s.contact_count)} distinct contacts`;
  const segments = data.map((s,i) => {
    const percent = total ? s.value / total * 100 : 0;
    const circle = percent > 0 ? `<circle class="donut-segment" cx="60" cy="60" r="45" pathLength="100" fill="none" stroke="${stageColor(s.stage, i)}" stroke-width="22" stroke-dasharray="${percent} ${100-percent}" stroke-dashoffset="${-offset}" transform="rotate(-90 60 60)" role="button" tabindex="0" aria-label="${esc(details(s))}" data-action="stage" data-stage="${esc(s.stage)}"><title>${esc(details(s))}</title></circle>` : "";
    offset += percent; return circle;
  }).join("");
  return `<div class="stage-chart"><svg viewBox="0 0 120 120" aria-label="Deal value by stage, including Won and Lost"><circle cx="60" cy="60" r="45" fill="none" class="donut-track" stroke-width="22"/>${segments}</svg><p><strong>${money(total)}</strong> total deal value</p>${total ? "" : '<p class="subtitle">No deal value to chart. Stage reports remain available below.</p>'}<div class="stage-summaries">${data.map((s,i) => `<button class="stage-summary" data-action="stage" data-stage="${esc(s.stage)}" title="${esc(details(s))}"><span class="stage-dot" style="background:${stageColor(s.stage, i)}" aria-hidden="true"></span>${esc(details(s))}</button>`).join("")}</div></div>`;
}
async function render() {
  // Only the latest render may publish markup or replace record caches.
  const token = ++state.render;
  const root = $("#content");
  root.innerHTML = '<div class="loading" role="status">Loading your workspace…</div>';
  $("#crumb").textContent = label(state.page);
  document.querySelectorAll("nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.page === state.page);
    if (a.dataset.page === state.page) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  try {
    const meta = await api("meta");
    if (token !== state.render) return;
    adoptCatalog(meta);
    let html = "";
    if (state.page === "overview") {
      const [o, contacts] = await Promise.all([
        api("overview"),
        api("contacts"),
      ]);
      if (token !== state.render) return;
      state.contacts = list(contacts);
      state.tasks = list(o.tasks);
      $("#profile").textContent = o.profile || "default";
      const ps = list(o.stages);
      html =
        head(
          "A clearer view of what’s next.",
          "Your pipeline, people, and priorities in one place.",
          `<button class="button" data-action="new-task">＋ Add task</button>${createButton("contact")}`,
        ) +
        `<div class="stats">${[
          [
            "Pipeline value",
            money(o.pipeline_value),
            "Open opportunities across your pipeline",
            "↗",
          ],
          ["Open deals", o.open_deals, "Relationships moving forward", "▤"],
          [
            "Total contacts",
            o.contacts,
            "People at the heart of your business",
            "◎",
          ],
          [
            "Won revenue",
            money(o.won_value),
            "Closed-won opportunity value",
            "✓",
          ],
        ]
          .map(
            ([t, v, f, i]) =>
              `<div class="stat"><div class="stat-label">${t}<span class="stat-symbol" aria-hidden="true">${i}</span></div><div class="stat-value">${esc(v)}</div><div class="stat-foot">${f}</div></div>`,
          )
          .join(
            "",
          )}</div><div class="grid"><section class="card"><div class="card-head"><div><h2>Sales pipeline</h2><div class="subtitle">Deal value by stage, including Won and Lost.</div></div><a class="text-link" href="#deals">View deals ↗</a></div>${stageChart(ps)}<div class="attention-reports"><h3>Lead attention</h3><button class="button" data-action="attention" data-followup="missing">${Number(o.lead_attention?.no_open_followup || 0)} leads with no open follow-up</button><button class="button" data-action="attention" data-followup="overdue">${Number(o.lead_attention?.overdue_followup || 0)} leads with overdue follow-ups</button><p class="subtitle">Based on stored tasks, not agent execution.</p></div></section><section class="card"><div class="card-head"><div><h2>Your next steps</h2><div class="subtitle">${o.open_tasks} open tasks · ${o.overdue_tasks} overdue</div></div><a href="#tasks" class="text-link">View all ↗</a></div>${taskRows(state.tasks.filter((t) => t.status !== "done").slice(0, 4))}</section></div><div class="grid"><section class="card"><div class="card-head"><div><h2>People in your orbit</h2><div class="subtitle">Every great opportunity starts with a connection.</div></div><a href="#contacts" class="text-link">All contacts ↗</a></div>${contactTable(state.contacts.slice(0, 5))}</section><section class="card"><div class="card-head"><h2>Recent activity</h2><a href="#activity" class="text-link">View all ↗</a></div>${activityRows(list(o.activity).slice(0, 5))}</section></div>`;
    } else if (state.page === "contacts") {
      const result = await api("reports/contacts" + queryString({q: state.query, ...state.filters, limit: 50, offset: state.offset}));
      if (token !== state.render) return;
      state.contacts = list(result.items);
      state.total = Number(result.total) || 0;
      html = head("Contacts", esc(state.report || "Filter contacts and their linked deal stages."), createButton("contact")) +
        `<section class="card"><div class="toolbar filters"><input class="search" id="search" type="search" aria-label="Search contacts" placeholder="Search names, companies, or emails…" value="${esc(state.query)}">${filterSelect("stage", "Stage", [["", "All stages"], ...catalog.stages.map(s => [s.key, s.label + (s.archived ? " (archived)" : "")]), ...(catalog.stages.length ? [] : stages.map(s => [s,stageLabel(s)])), ["unassigned","Unassigned"]])}${filterSelect("contact_type","Contact type",[["","All contact types"],["lead","Lead"],["customer","Customer"],["partner","Partner"]])}${filterInput("company","Company")}${filterSelect("email","Email",[["","Any email"],["present","Email present"],["missing","Email missing"]])}${filterSelect("followup","Follow-up",[["","Any follow-up"],["missing","No open follow-up"],["overdue","Overdue follow-up"],["upcoming","Upcoming follow-up"]])}<button class="button" data-action="clear-filters">Clear filters</button></div><p class="subtitle report-count">${state.total} matching contacts · ${state.total ? state.offset + 1 : 0}–${Math.min(state.offset + state.contacts.length,state.total)} shown</p>${contactTable(state.contacts)}<div class="pagination"><button class="button" data-action="previous" ${state.offset === 0 ? "disabled" : ""}>Previous</button><button class="button" data-action="next" ${state.offset + 50 >= state.total ? "disabled" : ""}>Next</button></div></section>`;
    } else if (state.page === "deals") {
      const deals = await api("deals" + queryString({q: state.query, stage: state.stage, company: state.filters.company, min_value: dollarCents(state.filters.min_value), max_value: dollarCents(state.filters.max_value)}));
      if (token !== state.render) return;
      state.deals = list(deals);
      html =
        head(
          "Deals",
          "Turn promising conversations into lasting partnerships.",
          createButton("deal"),
        ) +
        `<div class="toolbar board-toolbar"><input class="search" id="search" type="search" aria-label="Search deals" placeholder="Search opportunities…" value="${esc(state.query)}"><select id="stage-filter" aria-label="Filter by stage"><option value="">All stages</option>${stages.map((s) => `<option value="${esc(s)}" ${state.stage === s ? "selected" : ""}>${esc(stageLabel(s))}</option>`).join("")}</select>${filterInput("company","Company")}${filterInput("min_value","Minimum value (USD)","number")}${filterInput("max_value","Maximum value (USD)","number")}</div><p class="subtitle">Showing up to 500 matching deals.</p><div class="board${state.stage ? " filtered" : ""}" role="region" aria-label="Deal stages" tabindex="0">${(state.stage
          ? [state.stage]
          : stages
        )
          .map((s) => {
            const ds = state.deals.filter((d) => d.stage === s);
            return `<section class="column"><div class="column-head"><span>${esc(stageLabel(s))}</span><span class="badge ${esc(s)}">${ds.length}</span></div><div class="column-total">${money(ds.reduce((n, d) => n + d.value, 0))} total value</div>${dealCards(ds) || empty("No deals at this stage.")}</section>`;
          })
          .join("")}</div>`;
    } else if (state.page === "tasks") {
      // Filter on the server before its result limit, so completed history cannot hide open work.
      const tasks = await api("tasks" + queryString({q: state.query, status: state.taskFilter, priority: state.filters.priority, due: state.filters.due}));
      if (token !== state.render) return;
      state.tasks = list(tasks);
      const rows = state.tasks.filter(
        (t) => !state.taskFilter || t.status === state.taskFilter,
      );
      html =
        head(
          "Tasks",
          "Make the next move. Keep every follow-up on track.",
          createButton("task"),
        ) +
        `<section class="card"><div class="toolbar filters"><input class="search" id="search" type="search" aria-label="Search tasks" placeholder="Search tasks…" value="${esc(state.query)}">${filterSelect("priority","Priority",[["","All priorities"],["normal","Normal"],["high","High"]])}${filterSelect("due","Due",[["","Any due date"],["overdue","Overdue open tasks"],["upcoming","Upcoming open tasks"]])}<h2>${rows.length} ${state.taskFilter || "total"} tasks (up to 500)</h2><select id="task-filter" aria-label="Task status">${[
          ["open", "Open tasks"],
          ["done", "Completed"],
          ["", "All tasks"],
        ]
          .map(
            ([v, t]) =>
              `<option value="${v}" ${state.taskFilter === v ? "selected" : ""}>${t}</option>`,
          )
          .join("")}</select></div>${taskRows(rows)}</section>`;
    } else {
      const rows = list(await api("activity"));
      html =
        head("Activity", "A shared history for your team and your agents.") +
        `<section class="card"><div class="card-head"><h2>Workspace timeline</h2><span class="subtitle">${rows.length} events</span></div>${activityRows(rows)}</section>`;
    }
    if (token === state.render) root.innerHTML = html;
  } catch (e) {
    if (token === state.render)
      root.innerHTML = `<div class="error" role="alert">${esc(e.message)}</div><div class="error-actions"><button class="button" data-action="retry">Try again</button><button class="button" data-action="reset-current-filters">Reset filters</button></div>`;
  }
}
function route() {
  // Navigation invalidates both visible dialogs and pending modal fetches.
  closeModal(false);
  clearTimeout(searchTimer);
  const raw = location.hash.slice(1) || "overview";
  state.page = ["overview", "contacts", "deals", "tasks", "activity"].includes(
    raw,
  )
    ? raw
    : "overview";
  state.query = "";
  if (!pendingReport) { state.filters = {}; state.offset = 0; state.report = ""; state.stage = ""; }
  pendingReport = false;
  render();
}
function showModal(html) {
  modalEpoch++;
  modalOpener = document.activeElement;
  $("#modal-body").innerHTML = html;
  if (!$("#modal").open) $("#modal").showModal();
  const focus = $(
    "#modal input:not([type=hidden]),#modal select,#modal textarea",
  );
  if (focus) focus.focus();
}
function modalHead(title) {
  return `<div class="modal-head"><h2 id="dialog-title">${esc(title)}</h2><button class="close" data-action="close" aria-label="Close dialog">×</button></div>`;
}
function closeModal(restoreFocus = true) {
  const wasOpen = $("#modal").open;
  $("#modal").close();
  modalEpoch++;
  if (restoreFocus && wasOpen && modalOpener && document.contains(modalOpener))
    modalOpener.focus();
}
function field(name, title, value = "", type = "text", extra = "") {
  return `<label class="field">${title}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
}
function select(name, title, values, value, required = false) {
  return `<label class="field">${title}<select name="${name}" ${required ? "required" : ""}>${values
    .map((v) => {
      const [id, text] = Array.isArray(v) ? v : [v, label(v)];
      return `<option value="${esc(id)}" ${String(id) === String(value) ? "selected" : ""}>${esc(text)}</option>`;
    })
    .join("")}</select></label>`;
}
function localTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function taskDuePayload(value, record) {
  // An unchanged minute-level control must not round an existing scheduled time.
  return record?.due_at && value === localTime(record.due_at)
    ? record.due_at
    : new Date(value).toISOString();
}
async function openForm(type, record = {}) {
  // A newer dialog, navigation, or cancellation wins over late network results.
  const requestEpoch = ++modalEpoch;
  try {
    const meta = await api("meta");
    if (requestEpoch !== modalEpoch) return;
    adoptCatalog(meta);
    let contacts = [],
      deals = [];
    if (type !== "contact") {
      [contacts, deals] = await Promise.all([
        api("contacts"),
        type === "task" ? api("deals") : Promise.resolve([]),
      ]);
      contacts = list(contacts);
      deals = list(deals);
      contacts = preserveSelection(contacts, record.contact_id, record.contact_name, "contact");
      deals = preserveSelection(deals, record.deal_id, record.deal_title, "deal");
    }
    if (requestEpoch !== modalEpoch) return;
    let fields = "";
    if (type === "contact") {
      fields =
        field(
          "name",
          "Full name *",
          record.name,
          "text",
          'required maxlength="160"',
        ) +
        `<div class="form-row">${field("email", "Email", record.email, "email")}${field("company", "Company", record.company)}</div>` +
        `<div class="form-row">${field("title", "Job title", record.title)}${select("lifecycle", "Contact type", ["lead", "customer", "partner"], record.lifecycle || "lead")}</div>`;
    }
    if (type === "deal") {
      fields =
        field(
          "title",
          "Deal name *",
          record.title,
          "text",
          'required maxlength="200"',
        ) +
        select(
          "contact_id",
          "Contact *",
          [["", "Select a contact"], ...contacts.map((c) => [c.id, c.name])],
          record.contact_id,
          true,
        ) +
        `<div class="form-row">${field("value", "Value (USD) *", record.value == null ? "" : (record.value / 100).toFixed(2), "number", 'required min="0" step="0.01"')}${select("stage", "Stage", stages.map(s => [s, stageLabel(s)]), record.stage || "lead")}</div><div class="form-row">${field("probability", "Probability (%) *", record.probability ?? catalog.stages.find(s => s.key === "lead")?.probability ?? 10, "number", 'required min="0" max="100" step="1"')}${field("close_date", "Expected close date", record.close_date, "date")}</div>`;
    }
    if (type === "task") {
      fields =
        field(
          "title",
          "Task name *",
          record.title,
          "text",
          'required maxlength="200"',
        ) +
        `<div class="form-row">${select("contact_id", "Contact (optional)", [["", "No contact"], ...contacts.map((c) => [c.id, c.name])], record.contact_id || "")}${select("deal_id", "Deal (optional)", [["", "No deal"], ...deals.map((d) => [d.id, d.title])], record.deal_id || "")}</div><div class="form-row">${field("due_at", "Due date & time (your timezone) *", localTime(record.due_at), "datetime-local", "required")}${select("priority", "Priority", ["normal", "high"], record.priority || "normal")}</div>` +
        (record.id
          ? select("status", "Status", ["open", "done"], record.status)
          : "");
    }
    fields += customFieldDetails(type + "s", record);
    fields += `<label class="field">Notes<textarea name="notes" maxlength="10000">${esc(record.notes || "")}</textarea></label>`;
    showModal(
      modalHead((record.id ? "Edit " : "Add ") + type) +
        `<form id="record-form"><div class="form-body"><div id="form-error" class="error" role="alert" hidden></div>${fields}</div><div class="form-actions"><button type="button" class="button" data-action="close">Cancel</button><button type="submit" class="button primary">${record.id ? "Save changes" : "Create " + type}</button></div></form>`,
    );
    const epoch = modalEpoch;
    const createKey = crypto.randomUUID();
    $("#record-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.currentTarget;
      if (f.dataset.saving) return;
      const submit = f.querySelector("[type=submit]");
      if (!f.reportValidity()) return;
      const data = Object.fromEntries(new FormData(f));
      if (type === "deal") {
        data.value = Math.round(Number(data.value) * 100);
        data.contact_id = String(data.contact_id);
        data.probability = Number(data.probability);
        data.currency = "USD";
      }
      if (type === "task") {
        data.contact_id = data.contact_id || null;
        data.deal_id = data.deal_id || null;
        data.due_at = taskDuePayload(data.due_at, record);
        data.status = data.status || "open";
      }
      if (record.id) data.version = record.version;
      f.dataset.saving = "true";
      submit.disabled = true;
      submit.setAttribute("aria-busy", "true");
      submit.textContent = "Saving…";
      const error = f.querySelector("#form-error");
      error.hidden = true;
      try {
        await api(
          type + "s" + (record.id ? "/" + record.id : ""),
          record.id ? "PATCH" : "POST",
          data,
          record.id ? undefined : createKey,
        );
        if (modalEpoch === epoch) closeModal();
        toast(label(type) + (record.id ? " updated" : " created"));
        await render();
      } catch (err) {
        error.textContent = err.message;
        error.hidden = false;
        submit.disabled = false;
        submit.removeAttribute("aria-busy");
        submit.textContent = record.id ? "Save changes" : "Create " + type;
        delete f.dataset.saving;
        error.scrollIntoView({ block: "nearest" });
      }
    });
  } catch (e) {
    if (requestEpoch === modalEpoch) toast(e.message);
  }
}
async function contactDetail(id) {
  const requestEpoch = ++modalEpoch;
  try {
    const [result, meta] = await Promise.all([api("contacts/" + id), api("meta")]);
    if (requestEpoch !== modalEpoch) return;
    adoptCatalog(meta);
    const c = result.contact;
    showModal(
      modalHead(c.name) +
        `<div class="detail-body"><div class="person"><span class="avatar">${esc(initials(c.name))}</span><div>${esc(c.title || "Contact")}${c.company ? " at " + esc(c.company) : ""}<div>${badge(c.lifecycle)}</div></div></div><dl class="detail-meta"><div><dt>Email</dt><dd>${esc(c.email || "Not added")}</dd></div><div><dt>Created</dt><dd>${date(c.created_at)}</dd></div></dl>${c.notes ? `<div class="notes">${esc(c.notes)}</div>` : ""}${customFieldDetails("contacts", c)}<h3>Deals</h3>${dealCards(list(result.deals)) || empty("No linked deals.")}<h3>Tasks</h3>${taskRows(list(result.tasks))}<h3>Activity</h3>${activityRows(list(result.activity).slice(0, 8))}</div><div class="form-actions"><button class="button" data-action="close">Close</button><button class="button primary" id="edit-contact">Edit contact</button></div>`,
    ); // Fresh detail records replace cached versions before later edits.
    state.deals = mergeRecords(state.deals, list(result.deals));
    state.tasks = mergeRecords(state.tasks, list(result.tasks));
    $("#edit-contact").onclick = () => openForm("contact", c);
  } catch (e) {
    if (requestEpoch === modalEpoch) toast(e.message);
  }
}
function mergeRecords(cached, fresh) {
  const records = new Map(cached.map((record) => [record.id, record]));
  fresh.forEach((record) => records.set(record.id, record));
  return [...records.values()];
}
async function toggleTask(id, button) {
  const epoch = modalEpoch;
  const task = state.tasks.find((t) => String(t.id) === String(id));
  if (!task) return;
  button.disabled = true;
  try {
    await api("tasks/" + id, "PATCH", {
      status: task.status === "done" ? "open" : "done",
      version: task.version,
    });
    if (modalEpoch === epoch && $("#modal").open) closeModal();
    toast(task.status === "done" ? "Task reopened" : "Task completed");
    await render();
  } catch (e) {
    button.disabled = false;
    toast(e.message);
  }
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-action]");
  if (!b) return;
  const a = b.dataset.action;
  if (a.startsWith("new-")) openForm(a.slice(4));
  if (a === "close") closeModal();
  if (a === "retry") render();
  if (a === "reset-current-filters") { closeModal(false); clearTimeout(searchTimer); state.filters = {}; state.query = ""; state.stage = ""; state.offset = 0; state.report = ""; render(); }
  if (a === "contact") contactDetail(b.dataset.id);
  if (a === "deal") {
    const d = state.deals.find((x) => String(x.id) === b.dataset.id);
    if (d) openForm("deal", d);
  }
  if (a === "task") {
    const t = state.tasks.find((x) => String(x.id) === b.dataset.id);
    if (t) openForm("task", t);
  }
  if (a === "toggle-task") toggleTask(b.dataset.id, b);
  if (a === "stage") openReport({stage: b.dataset.stage}, `${stageLabel(b.dataset.stage)} stage: contacts linked to matching deals`);
  if (a === "attention") openReport({contact_type: "lead", followup: b.dataset.followup}, b.dataset.followup === "missing" ? "Leads with no open follow-up" : "Leads with overdue follow-ups");
  if (a === "clear-filters") openReport({}, "");
  if (a === "previous" || a === "next") { closeModal(false); state.offset = Math.max(0,state.offset + (a === "next" ? 50 : -50)); render(); }

});
document.addEventListener("input", (e) => {
  if (e.target.id !== "search") return;
  closeModal(false);
  state.render++;
  state.offset = 0;
  state.report = "";
  state.query = e.target.value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const pos = e.target.selectionStart;
    const page = state.page;
    const query = state.query;
    await render();
    const input = $("#search");
    if (input && state.page === page && state.query === query) {
      input.focus();
      try {
        input.setSelectionRange(pos, pos);
      } catch {}
    }
  }, 350);
});
document.addEventListener("change", (e) => {
  if (e.target.dataset.filter) {
    closeModal(false); clearTimeout(searchTimer); state.offset = 0; state.report = "";
    state.filters[e.target.dataset.filter] = e.target.value; render();
  }
  if (e.target.id === "stage-filter") {
    closeModal(false); clearTimeout(searchTimer);
    state.stage = e.target.value;
    render();
  }
  if (e.target.id === "task-filter") {
    closeModal(false); clearTimeout(searchTimer);
    state.taskFilter = e.target.value;
    render();
  }
});
$("#modal").addEventListener("cancel", () => {
  modalEpoch++;
});
// Escape also cancels a dialog request before its modal has opened.
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#modal").open) modalEpoch++;
  if ((e.key === "Enter" || e.key === " ") && e.target?.classList?.contains("donut-segment")) { e.preventDefault(); openReport({stage:e.target.dataset.stage}, `${stageLabel(e.target.dataset.stage)} stage: contacts linked to matching deals`); }
});
window.addEventListener("hashchange", route);
async function initialize() {
  try {
    const meta = await api("meta");
    adoptCatalog(meta);
    $("#profile").textContent = meta.profile || "default";
    document
      .querySelectorAll(".workspace-name")
      .forEach(
        (n) => (n.textContent = "CRM workspace"),
      );
    document
      .querySelectorAll(".workspace-description")
      .forEach(
        (n) =>
          (n.textContent = "Local-first CRM"),
      );
    $(".demo-label").hidden = !meta.demo;
  } catch (e) {
    toast("Workspace metadata is unavailable. " + e.message);
  }
  route();
}
initialize();
