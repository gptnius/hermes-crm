"use strict";
// BEGIN GENERATED RELATIONSHIP TIME
// Shared, dependency-free wall-time conversion. Never use the host's implicit zone.
function relZone(zone) {
  if (typeof zone !== 'string' || !zone.trim() || /^[+-]/.test(zone)) throw new Error('Choose a valid IANA timezone, such as America/New_York or UTC.');
  try { return new Intl.DateTimeFormat('en-US', {timeZone: zone}).resolvedOptions().timeZone; }
  catch { throw new Error('Choose a valid IANA timezone, such as America/New_York or UTC.'); }
}
function relWall(instant, zone) {
  relZone(zone);
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone: zone, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23'}).formatToParts(new Date(instant));
  const p = Object.fromEntries(parts.map(p => [p.type,p.value]));
  return `${p.year.padStart(4,'0')}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}
function relInstant(value) {
  const text = String(value || '').trim();
  const m = /^(\d{4}-\d\d-\d\d)T(\d\d):(\d\d)(?::(\d\d)(?:\.(\d{1,6}))?)?(Z|[+-](\d\d):(\d\d))$/.exec(text);
  if (!m || +m[2]>23 || +m[3]>59 || +(m[4]||0)>59 || +(m[7]||0)>23 || +(m[8]||0)>59 || !Number.isFinite(Date.parse(text))) throw new Error('Enter a valid date and time with an explicit offset.');
  const date = new Date(m[1]+'T00:00:00Z');
  if (date.toISOString().slice(0,10)!==m[1]) throw new Error('Enter a valid calendar date.');
  return text;
}
function relMicros(value) {
  relInstant(value);
  return BigInt(Math.floor(Date.parse(value)/1000))*1000000n + BigInt((value.match(/\.(\d+)/)?.[1] || '').padEnd(6,'0'));
}
function relCandidates(wall, zone) {
  relZone(zone);
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?$/.test(wall)) throw new Error('Enter both a date and a time.');
  const normalized = wall.length === 16 ? wall+':00' : wall;
  relInstant(normalized+'Z');
  // Restrict interactive editing to a tested modern timezone-data range.
  const year = +wall.slice(0,4);
  if (year < 1900 || year > 2100) throw new Error('Choose a year from 1900 through 2100.');
  const base = Date.parse(normalized+'Z'), offsets = new Set();
  // Obtain offsets around the target day, including both sides of DST and date-line shifts.
  for (let hour=-48; hour<=48; hour+=3) {
    const time = base+hour*3600000;
    offsets.add(Date.parse(relWall(time,zone)+'Z')-time);
  }
  return [...offsets].map(offset=>base-offset).filter(time=>relWall(time,zone)===normalized).sort((a,b)=>a-b).map(time=>new Date(time).toISOString());
}
function relUnchanged(wall, zone, original, originalZone, choice = '') {
  return !choice && !!original && zone===originalZone && relWall(original,zone)===(wall.length===16 ? wall+':00' : wall);
}
function relEditorCandidates(wall, zone, original = '', originalZone = zone, choice = '') {
  // Existing precise instants may predate or exceed the interactive editing range.
  // They are already unambiguous and must not block unrelated record edits.
  if ((+wall.slice(0,4)<1900 || +wall.slice(0,4)>2100) && relUnchanged(wall,zone,original,originalZone,choice)) return [];
  return relCandidates(wall,zone);
}
function relResolve(wall, zone, original = '', originalZone = zone, choice = '') {
  relZone(zone);
  // Preserve exact offset, seconds and microseconds even if the control normalized :00.
  if (relUnchanged(wall,zone,original,originalZone,choice)) return relInstant(original);
  const candidates=relCandidates(wall,zone);
  if (!candidates.length) throw new Error('This local time does not exist in this timezone. Choose another time.');
  if (candidates.length>1 && !candidates.includes(choice)) throw new Error('This local time occurs twice. Choose the intended occurrence.');
  return candidates.length===1 ? candidates[0] : choice;
}
function relReadable(value, zone = 'UTC') {
  if (!value) return 'Not recorded';
  try { relInstant(value); relZone(zone); return new Intl.DateTimeFormat('en', {timeZone:zone, year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit',timeZoneName:'short'}).format(new Date(value)); }
  catch { return String(value); }
}
// END GENERATED RELATIONSHIP TIME
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
  if (meta?.workspace_token) { if (relationshipWorkspace !== meta.workspace_token) researchWorkspaceEpoch++; relationshipWorkspace = meta.workspace_token; }
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
  if (!r.ok) { const error = new Error(data.error || "Request failed. Please try again."); error.status = r.status; throw error; }
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
    ? `<div class="table-scroll" role="region" aria-label="Contacts table" tabindex="0"><table><thead><tr><th scope="col">Name</th><th scope="col">Company</th><th scope="col">Contact type</th><th scope="col">Linked deal stages</th><th scope="col">Added</th></tr></thead><tbody>${rows.map((c) => `<tr><td><div class="person"><span class="avatar" aria-hidden="true">${esc(initials(c.name))}</span><div><button class="name-button" data-action="contact" data-id="${esc(c.id)}">${esc(c.name)}</button><small>${esc(c.email || "No email added")}</small></div></div></td><td>${c.company_id ? relationshipRecordButton("companies",{id:c.company_id,name:c.company_name || "Open Company"}) : esc(c.company || "—") + (c.company ? " <small>Unlinked text</small>" : "")}</td><td>${badge(c.lifecycle)}</td><td>${Array.isArray(c.deal_stages) ? (c.deal_stages.map(stageBadge).join(" ") || "Unassigned") : "See contact details"}</td><td>${date(c.created_at)}</td></tr>`).join("")}</tbody></table></div>`
    : empty("No matching contacts. Change filters or add a contact.");
}
function taskRows(rows) {
  return rows.length
    ? rows
        .map((t) => {
          const overdue =
            t.status !== "done" && t.due_at && new Date(t.due_at) < new Date();
          return `<div class="task-row"><button class="check" aria-pressed="${t.status === "done"}" data-action="toggle-task" data-id="${esc(t.id)}" aria-label="${t.status === "done" ? "Reopen" : "Complete"} ${esc(t.title)}">${t.status === "done" ? "✓" : ""}</button><div class="task-copy"><button data-action="task" data-id="${esc(t.id)}">${esc(t.title)}</button><div class="task-meta">${esc(t.contact_name || "Workspace task")} · Human owner: ${esc(t.owner_label || "Not recorded")}${t.priority === "high" ? " · High priority" : ""}</div>${taskRelationshipContext(t)}</div><span class="due ${overdue ? "overdue" : ""}">${t.status === "done" ? "Done" : (overdue ? "Overdue · " : "") + date(t.due_at)}</span></div>`;
        })
        .join("")
    : empty("All clear. No tasks to show.");
}
function taskAssignmentLines(task) {
  const work = task.agent_work;
  const states = {
    pending: "Saved, not scheduled", scheduled: "Schedule recorded; execution unverified",
    result_reported: "Result reported; awaiting human review", bound_paused: "Bound schedule paused",
    cancelled: "Cancelled intent; schedule status not checked", superseded: "Superseded intent; schedule status not checked",
    create_unknown: "Scheduling outcome unknown", resume_unknown: "Scheduling outcome unknown", unknown: "Scheduling outcome unknown",
  };
  if (work?.status !== "available" || !Number.isSafeInteger(work.total) || work.total < 0
      || !Array.isArray(work.items) || work.items.length !== Math.min(work.total, 3)
      || !work.items.every(item => item && typeof item === "object" && !Array.isArray(item)
        && typeof item.id === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(item.id)
        && item.executor === "Hermes" && typeof item.state === "string" && Object.hasOwn(states, item.state)
        && typeof item.human_owner === "string" && item.human_owner.trim() && item.human_owner.length <= 160
        && typeof item.source_task_current === "boolean"))
    return ["Agent work: Unavailable; review in Hermes Desktop."];
  if (work.total === 0) return ["Agent work: None saved"];
  const lines = work.items.map(item =>
    `Agent executor: Hermes · Human owner (agent work): ${item.human_owner} · ${states[item.state]}${item.source_task_current === false ? " · Earlier task version" : ""}`);
  if (work.total > work.items.length) lines.push(`${work.total} saved assignments; latest ${work.items.length} shown. Open task in Hermes Desktop for full history.`);
  return lines;
}
function upcomingTasks(rows) {
  return rows.length ? `<div class="upcoming-list">${rows.map(task => {
    const overdue = task.status === "open" && new Date(task.due_at) < new Date();
    const linked = typeof task.linked_contact_id === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(task.linked_contact_id)
      && typeof task.contact_name === "string" && task.contact_name.trim();
    const contact = linked ? `<button class="name-button" data-action="contact" data-id="${esc(task.linked_contact_id)}">Contact: ${esc(task.contact_name)}</button>`
      : task.contact_id || task.deal_id ? "Contact: Unavailable" : "Contact: No linked contact";
    return `<article class="upcoming-task"><button class="name-button task-title" data-action="task" data-id="${esc(task.id)}">${esc(task.title)}</button><div class="task-meta">${contact}</div><div class="task-meta">Due ${esc(new Date(task.due_at).toLocaleString())} · ${esc(label(task.priority))} priority ${overdue ? badge("overdue") : ""}</div><div class="task-assignment">Human owner: ${esc(task.owner_label || "Not recorded")}</div>${taskAssignmentLines(task).map(line => `<div class="task-assignment">${esc(line)}</div>`).join("")}</article>`;
  }).join("")}</div>` : empty("No open tasks. Start with a contact or a task.");
}
function activityContact(a, currentContactId) {
  return a.linked_contact_id !== currentContactId && a.link_basis === "current_relationship" && typeof a.linked_contact_id === "string"
    && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(a.linked_contact_id)
    && typeof a.linked_contact_name === "string" && a.linked_contact_name.trim()
    ? `<button class="name-button" data-action="contact" data-id="${esc(a.linked_contact_id)}">Current contact: ${esc(a.linked_contact_name)}</button>` : "";
}
function contactActivity(rows, currentContactId) {
  return `<h3>Record history</h3><p class="subtitle">CRM record changes only. Sent and received emails are not synced here.</p>${activityRows(rows.slice(0, 5), currentContactId)}${rows.length > 5 ? `<details><summary>Older Record history (${rows.length - 5} available)</summary>${activityRows(rows.slice(5), currentContactId)}</details>` : ""}<p class="subtitle">Up to 100 recent CRM changes for this contact and its currently linked records; older history may not be included.</p>`;
}
function activityRows(rows, currentContactId) {
  return rows.length
    ? rows
        .map(
          (a) =>
            `<div class="activity-row"><span class="activity-icon" aria-hidden="true">${String(a.entity_type || "").includes("task") ? "✓" : "↗"}</span><div class="activity-copy">${esc(a.summary || a.description || [label(a.entity_type), label(a.action), a.entity_name].filter(Boolean).join(" · ") || "Workspace updated")}<small>${esc(a.actor || "Workspace")} · ${date(a.created_at)}</small>${activityContact(a, currentContactId)}</div></div>`,
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
          )}</div><div class="grid"><section class="card"><div class="card-head"><div><h2>Sales pipeline</h2><div class="subtitle">Deal value by stage, including Won and Lost.</div></div><a class="text-link" href="#deals">View deals ↗</a></div>${stageChart(ps)}<div class="attention-reports"><h3>Lead attention</h3><button class="button" data-action="attention" data-followup="missing">${Number(o.lead_attention?.no_open_followup || 0)} leads with no open follow-up</button><button class="button" data-action="attention" data-followup="overdue">${Number(o.lead_attention?.overdue_followup || 0)} leads with overdue follow-ups</button><p class="subtitle">Based on stored tasks, not agent execution.</p></div></section><section class="card"><div class="card-head"><div><h2>Upcoming Tasks</h2><div class="subtitle">${o.open_tasks} open tasks · ${o.overdue_tasks} overdue</div></div><a href="#tasks" class="text-link">View all ↗</a></div><div class="upcoming-context"><p class="subtitle">Earliest open tasks, including overdue.</p><details class="task-assignment"><summary>About task assignments</summary><p>Task assignees are not stored. Agent-work owners are separate. Agent work shows saved intent, not a live execution check.</p></details></div>${upcomingTasks(state.tasks)}</section></div><div class="grid"><section class="card"><div class="card-head"><div><h2>People in your orbit</h2><div class="subtitle">Every great opportunity starts with a connection.</div></div><a href="#contacts" class="text-link">All contacts ↗</a></div>${contactTable(state.contacts.slice(0, 5))}</section><section class="card"><div class="card-head"><h2>Recent Record history</h2><a href="#activity" class="text-link">View all ↗</a></div><p class="subtitle activity-disclaimer">Latest 5 CRM record changes. Contact links reflect current relationships, not historical ownership. Communications are not synced in this feed.</p>${activityRows(list(o.activity).slice(0, 5))}</section></div>`;
    } else if (state.page === "contacts") {
      const result = await api("reports/contacts" + queryString({q: state.query, ...state.filters, limit: 50, offset: state.offset}));
      if (token !== state.render) return;
      state.contacts = list(result.items);
      state.total = Number(result.total) || 0;
      html = head("Contacts", esc(state.report || "Filter contacts and their linked deal stages."), createButton("contact")) +
        `<section class="card"><div class="toolbar filters"><input class="search" id="search" type="search" aria-label="Search contacts" placeholder="Search names, companies, or emails…" value="${esc(state.query)}">${filterSelect("stage", "Stage", [["", "All stages"], ...catalog.stages.map(s => [s.key, s.label + (s.archived ? " (archived)" : "")]), ...(catalog.stages.length ? [] : stages.map(s => [s,stageLabel(s)])), ["unassigned","Unassigned"]])}${filterSelect("contact_type","Contact type",[["","All contact types"],["lead","Lead"],["customer","Customer"],["partner","Partner"]])}${filterInput("company","Legacy company text")}${filterSelect("email","Email",[["","Any email"],["present","Email present"],["missing","Email missing"]])}${filterSelect("followup","Follow-up",[["","Any follow-up"],["missing","No open follow-up"],["overdue","Overdue follow-up"],["upcoming","Upcoming follow-up"]])}<button class="button" data-action="clear-filters">Clear filters</button></div><p class="subtitle report-count">${state.total} matching contacts · ${state.total ? state.offset + 1 : 0}–${Math.min(state.offset + state.contacts.length,state.total)} shown</p>${contactTable(state.contacts)}<div class="pagination"><button class="button" data-action="previous" ${state.offset === 0 ? "disabled" : ""}>Previous</button><button class="button" data-action="next" ${state.offset + 50 >= state.total ? "disabled" : ""}>Next</button></div></section>`;
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
        `<div class="toolbar board-toolbar"><input class="search" id="search" type="search" aria-label="Search deals" placeholder="Search opportunities…" value="${esc(state.query)}"><select id="stage-filter" aria-label="Filter by stage"><option value="">All stages</option>${stages.map((s) => `<option value="${esc(s)}" ${state.stage === s ? "selected" : ""}>${esc(stageLabel(s))}</option>`).join("")}</select>${filterInput("company","Legacy company text")}${filterInput("min_value","Minimum value (USD)","number")}${filterInput("max_value","Maximum value (USD)","number")}</div><p class="subtitle">Showing up to 500 matching deals.</p><div class="board${state.stage ? " filtered" : ""}" role="region" aria-label="Deal stages" tabindex="0">${(state.stage
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
      const tasks = await api("tasks" + queryString({q: state.query, status: state.taskFilter, priority: state.filters.priority, due: state.filters.due, owner: state.filters.owner, owner_label: state.filters.owner_label}));
      if (token !== state.render) return;
      state.tasks = list(tasks);
      const rows = state.tasks.filter(
        (t) => !state.taskFilter || t.status === state.taskFilter,
      );
      html =
        head(
          "Tasks",
          "Make the next move. Keep every follow-up on track.",
          createButton("task") + '<button class="button" data-action="task-owner-policy">Task ownership policy</button>',
        ) +
        `<section class="card"><div class="toolbar filters"><input class="search" id="search" type="search" aria-label="Search tasks" placeholder="Search tasks…" value="${esc(state.query)}">${filterSelect("owner","Human owner",[["","Any owner"],["present","Owner recorded"],["missing","Owner missing"]])}${filterInput("owner_label","Exact owner")}${filterSelect("priority","Priority",[["","All priorities"],["normal","Normal"],["high","High"]])}${filterSelect("due","Due",[["","Any due date"],["overdue","Overdue open tasks"],["upcoming","Upcoming open tasks"]])}<h2>${rows.length} ${state.taskFilter || "total"} tasks (up to 500)</h2><select id="task-filter" aria-label="Task status">${[
          ["open", "Open tasks"],
          ["done", "Completed"],
          ["", "All tasks"],
        ]
          .map(
            ([v, t]) =>
              `<option value="${v}" ${state.taskFilter === v ? "selected" : ""}>${t}</option>`,
          )
          .join("")}</select></div>${taskRows(rows)}</section>`;
    } else if (["companies", "events", "activities"].includes(state.page)) {
      html = await relationshipPage();
    } else {
      const rows = list(await api("activity"));
      html =
        head("Record history", "Administrative record changes, separate from relationship Activities.") +
        `<section class="card"><div class="card-head"><h2>Workspace timeline</h2><span class="subtitle">${rows.length} changes</span></div>${activityRows(rows)}</section>`;
    }
    if (token === state.render) root.innerHTML = `<div id="relationship-notices">${relationshipNotices()}</div>` + html;
  } catch (e) {
    if (token === state.render)
      root.innerHTML = `<div id="relationship-notices">${relationshipNotices()}</div><div class="error" role="alert">${esc(e.message)}</div><div class="error-actions"><button class="button" data-action="retry">Try again</button><button class="button" data-action="reset-current-filters">Reset filters</button></div>`;
  }
}
function route() {
  // A dirty relationship editor must be explicitly dismissed before navigation.
  if (closeModal(false) === false) {
    window.history?.replaceState(null, '', '#'+state.page);
    return;
  }
  clearTimeout(searchTimer);
  const raw = location.hash.slice(1) || "overview";
  state.page = ["overview", "contacts", "deals", "tasks", "activity", "record-history", "companies", "events", "activities"].includes(
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
  const form = $('#relationship-form');
  if (form?.dataset.saving) return false;
  if (form?.dataset.dirty && !form.dataset.discard) {
    $('#relationship-discard').hidden = false;
    $('#relationship-keep').focus();
    return false;
  }
  const returnContext = form?.returnContext;
  const wasOpen = $("#modal").open;
  $("#modal").close();
  modalEpoch++;
  refreshRelationshipNotices();
  if (restoreFocus && wasOpen && modalOpener && document.contains(modalOpener))
    modalOpener.focus();
  if (restoreFocus && wasOpen && returnContext) restoreRelatedSource(returnContext);
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
async function openForm(type, record = {}, context = null) {
  // A newer dialog, navigation, or cancellation wins over late network results.
  const requestEpoch = ++modalEpoch, scope = relationshipWorkspace;
  try {
    const meta = await api("meta");
    if (requestEpoch !== modalEpoch || scope !== relationshipWorkspace || (scope && meta.workspace_token !== scope)) return;
    adoptCatalog(meta);
    if (type === "contact" && !record.id) return newContactForm(record, context);
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
    if (requestEpoch !== modalEpoch || scope !== relationshipWorkspace) return;
    if (type === "task") return taskOwnerEditor(record, contacts, deals, checkedOwnerPolicy(meta.task_owner_policy, !Object.hasOwn(meta,'task_owner_policy')));
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
    if (type === 'deal' && record.id) {
      const action=document.createElement('button'); action.type='button'; action.className='button'; action.textContent='Create Event';
      let changed=false;
      $('#record-form').addEventListener('input',()=>{changed=true; action.disabled=true; action.title='Save or cancel deal changes before creating an Event.';});
      $('#record-form').addEventListener('change',()=>{changed=true; action.disabled=true;});
      action.onclick=()=>{if(!changed) startRelatedCreate('events','deals',record);};
      $('#record-form .form-actions').prepend(action);
    }
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
  const requestEpoch = ++modalEpoch, scope = relationshipWorkspace;
  try {
    const [result, meta] = await Promise.all([api("contacts/" + id), api("meta")]);
    if (requestEpoch !== modalEpoch) return;
    adoptCatalog(meta);
    const c = result.contact;
    if (scope !== relationshipWorkspace || c?.id !== id) return;
    showModal(
      modalHead(c.name) +
        `<div class="detail-body"><div class="person"><span class="avatar">${esc(initials(c.name))}</span><div>${esc(c.title || "Contact")}${c.company ? " at " + esc(c.company) : ""}<div>${badge(c.lifecycle)}</div></div></div><dl class="detail-meta"><div><dt>Email</dt><dd>${esc(c.email || "Not added")}</dd></div><div><dt>Created</dt><dd>${date(c.created_at)}</dd></div></dl>${c.notes ? `<div class="notes">${esc(c.notes)}</div>` : ""}<section><h3>Company</h3>${c.company_id ? relationshipRecordButton("companies",{id:c.company_id,name:c.company_name || "Open linked Company"}) : `<p>Unlinked legacy company text: ${esc(c.company || "Not set")}</p>`}<button class="button" id="contact-company">Link or unlink Company</button><button class="button" id="contact-events">Events & Activities</button><button class="button" id="contact-create-event">Create Event</button></section>${customFieldDetails("contacts", c)}${contactActivity(list(result.activity), c.id)}<h3>Deals</h3>${dealCards(list(result.deals)) || empty("No linked deals.")}<h3>Tasks</h3>${taskRows(list(result.tasks))}</div><div class="form-actions"><button class="button" data-action="close">Close</button><button class="button" id="contact-research">Research</button><button class="button primary" id="edit-contact">Edit contact</button></div>`,
    ); // Fresh detail records replace cached versions before later edits.
    state.deals = mergeRecords(state.deals, list(result.deals));
    state.tasks = mergeRecords(state.tasks, list(result.tasks));
    $("#contact-company")?.addEventListener("click",()=>contactCompanyForm(c));
    $("#contact-create-event")?.addEventListener("click",()=>startRelatedCreate("events","contacts",c));
    $("#contact-events")?.addEventListener("click",()=>contactEvents(c));
    $("#edit-contact").onclick = () => openForm("contact", c);
    $("#contact-research").onclick = () => openResearch("contacts", c.id);
    return modalEpoch;
  } catch (e) {
    if (requestEpoch === modalEpoch) toast(e.message);
  }
}
async function taskDetail(id) {
  // Exact fresh task data, never a contact target or a cached edit version.
  const requestEpoch = ++modalEpoch;
  try {
    const [task, meta] = await Promise.all([api("tasks/" + encodeURIComponent(id)), api("meta")]);
    if (requestEpoch !== modalEpoch) return;
    if (task?.id !== id) throw new Error("The task could not be verified. Refresh and try again.");
    adoptCatalog(meta);
    const overdue = task.status === "open" && new Date(task.due_at) < new Date();
    showModal(modalHead(task.title) + `<div class="detail-body"><dl class="detail-meta"><div><dt>Status</dt><dd>${badge(task.status)} ${overdue ? badge("overdue") : ""}</dd></div><div><dt>Due (your timezone)</dt><dd>${esc(new Date(task.due_at).toLocaleString())}</dd></div><div><dt>Priority</dt><dd>${esc(label(task.priority))}</dd></div><div><dt>Human owner (task accountability)</dt><dd>${esc(task.owner_label || "Not recorded")}</dd></div><div><dt>Contact</dt><dd>${task.contact_id ? `<button class="name-button" data-action="contact" data-id="${esc(task.contact_id)}">Open linked contact</button>` : task.deal_id ? "Linked through deal" : "No linked contact"}</dd></div></dl>${task.notes ? `<div class="notes">${esc(task.notes)}</div>` : ""}${task.event_id ? `<section><h3>Event</h3>${relationshipRecordButton("events",{id:task.event_id,title:task.event_title || "Open linked Event"})}<button class="button" id="task-unlink-event">Unlink Event</button></section>` : ""}${taskRelationshipContext(task)}${customFieldDetails("tasks", task)}<p class="subtitle">Review any separate saved agent assignments in Hermes Desktop. A task due date does not schedule agent work.</p></div><div class="form-actions"><button class="button" data-action="close">Close</button><button class="button primary" id="edit-task">Edit task</button></div>`);
    state.tasks = mergeRecords(state.tasks, [task]);
    $("#task-unlink-event")?.addEventListener("click",()=>prepareEventUnlink(task));
    $("#edit-task").onclick = () => openForm("task", task);
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
  button.disabled = true;
  const epoch = modalEpoch, scope = relationshipWorkspace, view = state.render;
  try {
    const [task, policyValue] = await Promise.all([relationshipRead('tasks/'+encodeURIComponent(id)),relationshipRead('task-owner-policy')]);
    if (epoch !== modalEpoch || scope !== relationshipWorkspace || view !== state.render) return;
    if(task.id !== id) throw new Error('The task could not be verified. Refresh before changing its status.');
    const policy=checkedOwnerPolicy(policyValue);
    if(policy.required && !task.owner_label) {
      await openForm('task', {...task, status:task.status === 'done' ? 'open' : 'done'});
      return;
    }
    await ownerWrite('tasks/'+encodeURIComponent(id),'PATCH',{version:task.version,status:task.status === 'done' ? 'open' : 'done',owner_policy_version:policy.version},scope);
    if(epoch!==modalEpoch || scope!==relationshipWorkspace || view!==state.render) return;
    if($('#modal').open) closeModal();
    toast(task.status==='done' ? 'Task reopened' : 'Task completed'); await render();
  } catch(error) { if(epoch === modalEpoch && scope === relationshipWorkspace && view===state.render) toast(error.message); }
  finally { button.disabled = false; }
}
document.addEventListener("click", (e) => {
  void relationshipClick(e);
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
  if (a === "task-owner-policy") openTaskOwnerPolicy();
  if (a === "owner-retry") retryOwnerWrite();
  if (a === "owner-recover") recoverOwnerDraft();
  if (a === "research-recover") researchRecover();
  if (a === "research-retry") researchRecover(true);
  if (a === "task") {
    taskDetail(b.dataset.id);
  }
  if (a === "toggle-task") toggleTask(b.dataset.id, b);
  if (a === "stage") openReport({stage: b.dataset.stage}, `${stageLabel(b.dataset.stage)} stage: contacts linked to matching deals`);
  if (a === "attention") openReport({contact_type: "lead", followup: b.dataset.followup}, b.dataset.followup === "missing" ? "Leads with no open follow-up" : "Leads with overdue follow-ups");
  if (a === "clear-filters") openReport({}, "");
  if (a === "previous" || a === "next") { closeModal(false); state.offset = Math.max(0,state.offset + (a === "next" ? 50 : -50)); render(); }

});
document.addEventListener("input", (e) => {
  if(e.target.dataset?.exactSearch) exactSearch(e.target);
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
$("#modal").addEventListener("cancel", event => {
  if ($('#relationship-form')) { event.preventDefault(); closeModal(); }
  else modalEpoch++;
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
// Local relationships are exact-ID records. No external calendar or communication side effects.
let relationshipWorkspace = null;
const relationshipAttempts = new Map();
const relationshipDrafts = new Map();
// Successful receipts retain the original navigation intent, including explicit null/list context.
const relationshipReceiptContexts = new WeakMap();
function relationshipNotices() {
  return researchNotice() + ownerNotices() + (relationshipAttempts.has(relationshipWorkspace) ? '<section class="error" role="alert">A relationship write has an unknown outcome. New writes are blocked.<button class="button" data-action="relationship-retry">Retry original request</button></section>' : '') + (relationshipDrafts.has(relationshipWorkspace) ? '<section class="error" role="alert">An original creation request was rejected. Its draft is retained for correction.<button class="button" data-action="relationship-recover-draft">Review original draft</button></section>' : '');
}
function refreshRelationshipNotices() {
  // Modal completion/dismissal need not reload the list to expose retained recovery controls.
  const slot=$('#relationship-notices');
  if(slot) slot.innerHTML=relationshipNotices();
}
function relationshipPath(path, params = {}) {
  if (!relationshipWorkspace) throw new Error('Workspace identity unavailable. Refresh before continuing.');
  return path + '?' + new URLSearchParams({ ...params, workspace_token: relationshipWorkspace });
}
function relationshipRead(path, params) { return api(relationshipPath(path, params)); }
function confirmedRelationshipReceipt(path, method, body, result) {
  const version = value => Number.isSafeInteger(value) && value > 0;
  const id = value => typeof value === 'string' && value.trim().length > 0;
  const record = value => Boolean(value && id(value.id) && version(value.version));
  const atLeast = (actual, expected) => version(actual) && (!version(expected) || actual >= expected);
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  if (!result || typeof result !== 'object') return false;
  if (parts[0] === 'relationship-contacts' && parts.length === 1 && method === 'POST') {
    const contact = result.contact, link = result.company_link;
    return record(contact) && Boolean(link) && link.contact_id === contact.id && link.contact_version === contact.version &&
      Object.hasOwn(link,'company_id') && link.company_id === (body.company_id ?? null) &&
      link.company_link_basis === (body.company_id ? 'explicit' : 'unlinked');
  }
  if (parts[0] === 'contacts' && parts.length === 3 && parts[2] === 'company' && method === 'PUT')
    return result.contact_id === parts[1] && atLeast(result.contact_version, body.expected_contact_version) && Object.hasOwn(result, 'company_id') && result.company_id === body.company_id;
  if (parts[0] === 'events' && parts.length === 3 && parts[2] === 'tasks' && method === 'POST')
    return record(result.task) && (!body.data || ['owner_label','owner_source'].every(key=>!Object.hasOwn(body.data,key) || result.task[key]===body.data[key])) && result.task_id === result.task.id && record(result.event) && result.event.id === parts[1] && result.event_id === parts[1] && atLeast(result.event.version, body.expected_version);
  if (parts[0] === 'tasks' && parts[2] === 'event') {
    if (!record(result.task) || result.task_id !== parts[1] || result.task.id !== parts[1] || !atLeast(result.task.version, body.expected_task_version)) return false;
    if (parts.length === 4 && parts[3] === 'unlink' && method === 'POST')
      return result.event_id === null && Object.hasOwn(result, 'event') && ((result.event === null && result.task.version === body.expected_task_version) || (record(result.event) && result.event.id === body.event_id && atLeast(result.event.version, body.expected_version)));
    if (parts.length === 3 && method === 'PUT')
      return record(result.event) && result.event.id === body.event_id && result.event_id === body.event_id && atLeast(result.event.version, body.expected_version);
    return false;
  }
  if (!['companies', 'events'].includes(parts[0]) || !record(result)) return false;
  if (parts.length === 1) return method === 'POST' && (parts[0] !== 'events' || ['contact_id','deal_id','company_id'].every(key => Object.hasOwn(result,key) && result[key] === (body.data?.[key] ?? null)));
  return result.id === parts[1] && atLeast(result.version, body.expected_version) &&
    ((parts.length === 2 && method === 'PATCH') || (parts.length === 3 && method === 'POST' &&
      (parts[0] === 'companies' ? ['archive', 'restore'] : ['complete', 'cancel', 'reopen', 'needs-rescheduling', 'reschedule']).includes(parts[2])));
}
async function relationshipWrite(path, method, body, returnContext = null) {
  const scope = relationshipWorkspace;
  if (!scope) throw new Error('Workspace identity unavailable. Refresh before continuing.');
  if (ownerAttempts.has(scope)) throw new Error('An accountability save is unconfirmed. Retry its original unchanged save first.');
  const payload = JSON.stringify({ ...body, workspace_token: scope });
  let attempt = relationshipAttempts.get(scope);
  if (attempt && (attempt.path !== path || attempt.method !== method || attempt.payload !== payload)) throw new Error('An earlier write has an unknown outcome. Retry that original request before changing intent.');
  if (attempt?.running) throw new Error('A write is already running.');
  if (!attempt) { attempt = { path, method, payload, key: crypto.randomUUID(), returnContext }; relationshipAttempts.set(scope, attempt); }
  attempt.running = true;
  try {
    const result = await api(path, method, { ...JSON.parse(attempt.payload), idempotency_key: attempt.key });
    if (!confirmedRelationshipReceipt(attempt.path, attempt.method, JSON.parse(attempt.payload), result)) throw new Error('Unconfirmed response');
    relationshipReceiptContexts.set(result,attempt.returnContext);
    relationshipAttempts.delete(scope);
    return result;
  } catch (error) {
    if ([400, 404, 409, 422].includes(error.status)) relationshipAttempts.delete(scope);
    else error.message += ' Outcome unknown. Retry the original unchanged request; its key is retained even if you close this form.';
    throw error;
  } finally { attempt.running = false; if(scope === relationshipWorkspace) refreshRelationshipNotices(); }
}
function relationshipPager(page, action, extra = '') {
  return `<div class="form-actions"><span>${page.total} total · ${page.items.length ? page.offset + 1 : 0}–${page.offset + page.items.length} shown</span><button class="button" data-action="${action}" data-offset="${Math.max(0,page.offset-page.limit)}" ${extra} ${page.offset ? '' : 'disabled'}>Previous</button><button class="button" data-action="${action}" data-offset="${page.offset+page.limit}" ${extra} ${page.offset+page.items.length >= page.total ? 'disabled' : ''}>Next</button></div>`;
}
function relationshipRecordButton(kind, row) {
  return `<button class="name-button" data-action="${kind === 'contacts' ? 'contact' : kind === 'tasks' ? 'task' : kind === 'deals' ? 'relationship-deal' : kind === 'companies' ? 'company' : 'event'}" data-id="${esc(row.id)}">${esc(row.name || row.title || row.id)}</button>`;
}
function taskRelationshipContext(task) {
  if (!task.company_id && !task.event_id && !task.event_company_id) return '';
  const company = (id,name) => id ? relationshipRecordButton('companies',{id,name:(name || 'Company')+' · ID '+id}) : 'Not linked';
  return `<div class="task-relationship-context"><small>Current-contact Company: ${company(task.company_id,task.company_name)} · Basis: ${esc(label(task.company_link_basis || 'unlinked'))}</small><small>Explicit Event Company: ${company(task.event_company_id,task.event_company_name)} · Basis: ${esc(label(task.event_link_basis || 'unlinked'))}</small>${task.event_id ? `<small>Linked Event: ${relationshipRecordButton('events',{id:task.event_id,title:(task.event_title || 'Event')+' · ID '+task.event_id})}</small>` : ''}</div>`;
}
function eventRelatedLinks(row) {
  return `<div class="event-related-links" role="group" aria-label="Related Event records">${['contact','deal','company'].map(kind=>row[kind+'_id'] ? relationshipRecordButton(kind === 'company' ? 'companies' : kind+'s',{id:row[kind+'_id'],name:'Open '+kind}) : '').join('')}</div>`;
}
function relationshipRows(page, kind) {
  return page.items.length ? `<ul class="relationship-list">${page.items.map(row => `<li>${relationshipRecordButton(kind,row)}<small>${esc(row.domain || row.email || label(row.status || ''))}${row.archived_at ? ' · Archived' : ''}${(row.relationship_basis || row.event_link_basis || row.company_link_basis) ? ' · '+esc(label(row.relationship_basis || row.event_link_basis || row.company_link_basis)) : ''}</small><details><summary>Record details</summary><small>ID ${esc(row.id)}</small>${['starts_at','ends_at'].filter(key=>row[key]).map(key=>`<small>${esc(label(key))}: ${esc(row[key])}</small>`).join('')}</details>${kind === 'tasks' ? '<small>Human owner: '+esc(row.owner_label || 'Not recorded')+'</small>'+taskRelationshipContext(row) : ''}${row.starts_at ? `<small>${esc(relReadable(row.starts_at,row.timezone))} → ${esc(relReadable(row.ends_at,row.timezone))} · ${esc(row.timezone)}</small>` : ''}</li>`).join('')}</ul>` : empty('No matching records.');
}
async function relationshipPage() {
  const kind = state.page;
  const params = { limit: 25, offset: state.offset, q: state.query };
  if (kind === 'companies') params.include_archived = 'true';
  if (kind === 'events') for (const filter of ['status','kind']) if (state.filters[filter]) params[filter] = state.filters[filter];
  const page = await relationshipRead(kind === 'activities' ? 'relationship-activities' : kind, kind === 'activities' ? {limit:25,offset:state.offset} : params);
  let body;
  if (kind === 'activities') body = page.items.map(row => `<li>${row.record_type === 'event' ? relationshipRecordButton('events',{id:row.record_id,title:row.title}) : esc(row.title || row.summary || label(row.kind))}<small>${esc(relReadable(row.happened_at))} · ${esc(row.provenance)} · ${esc(row.timestamp_basis)} · ${esc(row.id)}</small>${row.contact_id ? relationshipRecordButton('contacts',{id:row.contact_id,name:'Open contact'}) : ''}</li>`).join('');
  return head(label(kind),kind === 'activities' ? 'Completed local Events and self-reported contact logs. Not verified communications.' : kind === 'companies' ? 'Explicit organizations and their associated records.' : 'Local appointments and calls.',kind === 'activities' ? '' : `<button class="button primary" data-action="relationship-create" data-kind="${kind}">Add ${kind === 'companies' ? 'Company' : 'Event'}</button>`) + `<section class="card">${kind !== 'activities' ? `<input class="search" id="search" type="search" aria-label="Search ${kind}" placeholder="Search ${kind}" value="${esc(state.query)}">` : ''}${kind === 'events' ? filterSelect("status","Event status",[["","All statuses"],["scheduled","Scheduled"],["needs_rescheduling","Needs rescheduling"],["completed","Completed"],["cancelled","Cancelled"]])+filterSelect("kind","Event type",[["","All types"],["appointment","Appointment"],["call","Call"]]) : ""}${kind === 'activities' ? `<ul class="relationship-list">${body || '<li>No recorded interactions.</li>'}</ul>` : relationshipRows(page,kind)}${relationshipPager(page,'relationship-page')}</section>`;
}
const eventLocalHelp = 'Local record only. Saving does not invite attendees, place calls, send reminders, schedule agent work or sync a calendar. Related records are context, not verified attendees. Notes and outcomes are ordinary plaintext.';
function relationshipForm(title, fields, submit, done, returnContext = null) {
  showModal(modalHead(title) + `<form id="relationship-form" class="detail-body"><div class="relationship-form-grid">${fields}</div><p role="alert" id="relationship-error" hidden></p><div id="relationship-discard" class="relationship-wide" role="alert" hidden><p>Discard unsaved changes?</p><button class="button" type="button" id="relationship-keep">Keep editing</button><button class="button" type="button" id="relationship-discard-confirm">Discard changes</button></div><div class="form-actions"><button class="button" type="button" data-action="close">Cancel</button><button class="button primary" type="submit">Save</button></div></form>`);
  const epoch = modalEpoch, scope = relationshipWorkspace;
  const form = $('#relationship-form');
  form.returnContext = returnContext;
  const pending=relationshipAttempts.get(scope);
  if(pending) {
    const origin=pending.returnContext;
    $('#relationship-error').hidden=false;
    $('#relationship-error').textContent='An earlier request has an unknown outcome. Save can only retry its identical original data. Its original return destination is '+(origin ? origin.kind+' record '+origin.id : 'the list (no source record)')+'. Close this form and choose Retry original request to recover it without changing intent.';
  }
  $('#relationship-keep').onclick=()=>{ $('#relationship-discard').hidden=true; form.querySelector('input,textarea,select')?.focus(); };
  $('#relationship-discard-confirm').onclick=()=>{form.dataset.discard='true';closeModal();};
  form.addEventListener('input',()=>{form.dataset.dirty='true'; updateRelationshipTimes(form);});
  form.addEventListener('change',()=>{form.dataset.dirty='true'; updateRelationshipTimes(form);});
  updateRelationshipTimes(form);
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (form.dataset.saving || !form.reportValidity()) return;
    if (scope !== relationshipWorkspace || epoch !== modalEpoch) return;
    const values = Object.fromEntries(new FormData(form));
    const controls = [...form.querySelectorAll('input,select,textarea,button')];
    form.dataset.saving = 'true'; controls.forEach(control => control.disabled = true);
    try {
      resolveRelationshipTimes(form,values);
      const result = await submit(values);
      if (scope !== relationshipWorkspace || modalEpoch !== epoch) return;
      delete form.dataset.saving; form.dataset.discard='true'; closeModal(false); const closedEpoch=modalEpoch; await render(); if (scope !== relationshipWorkspace || closedEpoch !== modalEpoch) return; if (done) await done(result,relationshipReceiptContexts.has(result) ? relationshipReceiptContexts.get(result) : returnContext);
    } catch(error) {
      if (scope === relationshipWorkspace && modalEpoch === epoch) { $('#relationship-error').hidden = false; $('#relationship-error').textContent = error.message; }
    } finally { delete form.dataset.saving; controls.forEach(control => control.disabled = false); }
  });
}
function relationshipNotes(value = '') { return `<label class="field relationship-wide">Notes<textarea name="notes" rows="4">${esc(value)}</textarea></label>`; }
function exactSelector(name, kind, value = '') {
  return `<div class="exact-selector"><label class="field">${label(kind)} exact ID (optional)<input name="${name}" value="${esc(value || '')}" maxlength="36"></label><label class="field">Find ${label(kind)}<input type="search" data-exact-search="${kind}" data-exact-name="${name}" placeholder="Search, then choose an exact record"></label><div data-exact-results="${name}" aria-live="polite"></div></div>`;
}
function relationshipTimeField(name, title, value = '', zone = 'UTC') {
  return `<div class="relationship-time" data-time-field="${name}" data-original="${esc(value)}" data-zone="${esc(zone)}">${field(name,title,value ? relWall(value,zone) : '', 'datetime-local','required step="1"')}<label class="field" data-occurrence-label hidden>Repeated time: choose an occurrence<select data-occurrence><option value="">Choose occurrence</option></select></label><small data-time-preview role="status"></small>${value ? `<details><summary>Original precise time</summary><small>${esc(value)}</small></details>` : ''}</div>`;
}
function relationshipZone(zone = 'UTC', name = '_time_zone') {
  return field(name,'Timezone for entered times',zone,'text','required placeholder="America/New_York" data-time-zone')+'<p class="subtitle">Changing the zone reinterprets the entered wall times. New or changed times must use years 1900–2100; unchanged original times are preserved. Review each preview before saving.</p>';
}
function updateRelationshipTimes(form) {
  const zone=form.querySelector('[data-time-zone]')?.value || 'UTC';
  form.querySelectorAll('[data-time-field]').forEach(container=>{
    const input=container.querySelector('input'), choice=container.querySelector('[data-occurrence]'), preview=container.querySelector('[data-time-preview]');
    let validCandidates=false;
    try {
      const candidates=relEditorCandidates(input.value,zone,container.dataset.original,container.dataset.zone,choice.value), signature=JSON.stringify([input.value,zone,candidates]);
      validCandidates=true;
      if (choice.dataset.signature!==signature) { choice.value=''; choice.innerHTML='<option value="">Choose occurrence</option>'+candidates.map((instant,index)=>`<option value="${esc(instant)}">${index ? 'Second' : 'First'} · ${esc(relReadable(instant,zone))} · ${esc(instant)}</option>`).join(''); choice.dataset.signature=signature; }
      container.querySelector('[data-occurrence-label]').hidden=candidates.length<2;
      preview.textContent=relReadable(relResolve(input.value,zone,container.dataset.original,container.dataset.zone,choice.value),zone);
    } catch(error) {
      // Invalid or cleared wall times invalidate any earlier repeated-time choice.
      if (!validCandidates) {
        choice.value=''; delete choice.dataset.signature;
        choice.innerHTML='<option value="">Choose occurrence</option>';
        container.querySelector('[data-occurrence-label]').hidden=true;
      }
      preview.textContent=error.message;
    }
  });
}
function resolveRelationshipTimes(form, values) {
  const zone=form.querySelector('[data-time-zone]')?.value || 'UTC';
  form.querySelectorAll('[data-time-field]').forEach(container=>{
    const name=container.dataset.timeField;
    values[name]=relResolve(values[name],zone,container.dataset.original,container.dataset.zone,container.querySelector('[data-occurrence]').value);
  });
  delete values._time_zone;
  if (values.outcome_happened_at && relMicros(values.outcome_happened_at)>BigInt(Date.now())*1000n) throw new Error('Claimed occurrence cannot be in the future.');
}
function eventFields(row = {}) {
  const zone=row.timezone || 'UTC';
  return `<p class="subtitle relationship-wide">${eventLocalHelp}</p>${field('title','Title',row.title || '', 'text','required maxlength="200"')}${select('kind','Type',['appointment','call'],row.kind || 'appointment',true)}${relationshipZone(zone,'timezone')}${relationshipTimeField('starts_at','Start',row.starts_at,zone)}${relationshipTimeField('ends_at','End',row.ends_at,zone)}${exactSelector('contact_id','contacts',row.contact_id)}${exactSelector('deal_id','deals',row.deal_id)}${exactSelector('company_id','companies',row.company_id)}${relationshipNotes(row.notes)}`;
}
function eventPayload(values) {
  for (const name of ['starts_at','ends_at']) relInstant(values[name]);
  if (relMicros(values.ends_at) <= relMicros(values.starts_at)) throw new Error('End must follow start.');
  relZone(values.timezone);
  for (const name of ['contact_id','deal_id','company_id']) values[name] = values[name] || null;
  return values;
}
function relationshipEditor(kind, row = {}, operation = '', initialValues = {}, returnContext = null) {
  const path = `${kind}${row.id ? '/'+encodeURIComponent(row.id) : ''}${operation ? '/'+operation : ''}`;
  relationshipForm(`${row.id ? operation === 'reschedule' ? 'Reschedule' : 'Edit' : 'Add'} ${kind === 'companies' ? 'Company' : 'Event'}`,kind === 'companies' ? field('name','Company name',row.name || '','text','required maxlength="200"')+field('domain','Domain (unverified text)',row.domain || '')+relationshipNotes(row.notes) : eventFields(row.id ? row : initialValues),values => relationshipWrite(path,operation || !row.id ? 'POST' : 'PATCH',{data:kind === 'events' ? eventPayload(values) : values,...(row.id ? {expected_version:row.version} : {})},returnContext),(result,originalContext) => openRelatedResult(kind,result.id || row.id,originalContext),returnContext);
}
async function relationshipDetail(kind,id,tab = 'contacts',offset = 0) {
  const requestEpoch = ++modalEpoch, scope = relationshipWorkspace;
  try {
    const result = await relationshipRead(`${kind}/${encodeURIComponent(id)}`);
    const row = kind === 'companies' ? result.company : result;
    if (row?.id !== id) throw new Error('The source record could not be verified. Refresh and try again.');
    const path = kind === 'companies' ? `companies/${encodeURIComponent(id)}/records/${tab}` : `events/${encodeURIComponent(id)}/tasks`;
    const page = await relationshipRead(path,{limit:25,offset});
    if (requestEpoch !== modalEpoch || scope !== relationshipWorkspace) return;
    const buttons = kind === 'companies' ? `<button class="button" data-rel-op="${row.archived_at ? 'restore' : 'archive'}">${row.archived_at ? 'Restore' : 'Archive'}</button>` : ['scheduled','needs_rescheduling'].includes(row.status) ? `<button class="button" data-rel-op="reschedule">Reschedule</button><button class="button" data-rel-op="complete">Complete (self-reported)</button><details><summary>More Event actions</summary><div class="form-actions"><button class="button" data-rel-op="cancel">Cancel Event</button>${row.status === 'scheduled' ? '<button class="button" data-rel-op="needs-rescheduling">Needs rescheduling</button>' : ''}</div></details>` : '<button class="button" data-rel-op="reopen">Reopen</button>';
    showModal(modalHead(row.name || row.title)+`<div class="detail-body"><p>${esc(row.domain || label(row.status || ''))}</p><details><summary>Record details</summary><p>ID ${esc(row.id)} · Version ${row.version}</p>${['starts_at','ends_at','outcome_happened_at','recorded_at'].filter(key=>row[key]).map(key=>`<p>${esc(label(key))}: ${esc(row[key])}</p>`).join('')}</details>${kind === 'events' ? `<p>${esc(relReadable(row.starts_at,row.timezone))} → ${esc(relReadable(row.ends_at,row.timezone))} · ${esc(row.timezone)}</p><p class="subtitle">Source: local${row.status === 'completed' ? ' · Self-reported completion, not verified attendance or a verified call' : ''}</p>${row.outcome_summary ? `<p>${esc(row.outcome_summary)}<small>Claimed: ${esc(relReadable(row.outcome_happened_at,row.timezone))} · Recorded: ${esc(relReadable(row.recorded_at,row.timezone))}</small></p>` : ''}<details><summary>About local Events</summary><p>${eventLocalHelp}</p></details>${eventRelatedLinks(row)}` : '<p class="subtitle">Current relationship rollup. Contacts use explicit Company links; deals follow their contact. Tasks can belong through their contact or linked Event. Events use their own Company link. A rename never overwrites legacy contact text.</p>'}${row.notes ? `<p class="notes">${esc(row.notes)}</p>` : ''}<div class="form-actions">${kind === 'companies' || ['scheduled','needs_rescheduling'].includes(row.status) ? '<button class="button primary" id="relationship-edit">Edit</button>' : ''}${buttons}</div>${kind === 'companies' ? `<div class="form-actions"><button class="button" id="company-activities">Relationship Activities</button>${['contacts','deals','tasks','events'].map(k=>`<button class="button" data-rel-tab="${k}" aria-pressed="${tab === k}">${label(k)} (${Number(result.counts[k] || 0)})</button>`).join('')}</div>` : '<h3>Associated tasks</h3><p class="subtitle">Task owners record human accountability. Agent assignments and execution are separate; review them in Hermes Desktop.</p><div class="form-actions"><button class="button" id="event-create-task">Create task</button><button class="button" id="event-link-task">Link existing task</button></div>'}${relationshipRows(page,kind === 'companies' ? tab : 'tasks')}${relationshipPager(page,'relationship-detail-page',`data-kind="${kind}" data-id="${esc(id)}" data-tab="${tab}"`)}</div>`);
    if (kind === 'companies') {
      const actions = document.createElement('div'); actions.className='form-actions';
      actions.innerHTML=`<button class="button" id="company-research">Research</button><button class="button" id="company-create-contact" ${row.archived_at ? 'disabled' : ''}>Create contact</button><button class="button" id="company-create-event" ${row.archived_at ? 'disabled' : ''}>Create Event</button>`;
      $('#modal-body .detail-body').prepend(actions);
      $('#company-research').onclick=()=>openResearch('companies',id,()=>relationshipDetail(kind,id,tab,offset));
      $('#company-create-contact').onclick=()=>startRelatedCreate('contacts',kind,row,{tab,offset});
      $('#company-create-event').onclick=()=>startRelatedCreate('events',kind,row,{tab,offset});
    }
    $('#company-activities')?.addEventListener('click',()=>companyActivities(row));
    $('#relationship-edit')?.addEventListener('click',()=>relationshipEditor(kind,row));
    document.querySelectorAll('[data-rel-tab]').forEach(button=>button.addEventListener('click',()=>relationshipDetail(kind,id,button.dataset.relTab)));
    document.querySelectorAll('[data-rel-op]').forEach(button=>button.addEventListener('click',()=>relationshipOperation(kind,row,button.dataset.relOp)));
    $('#event-create-task')?.addEventListener('click',()=>eventTaskForm(row));
    $('#event-link-task')?.addEventListener('click',()=>eventLinkTask(row));
    return modalEpoch;
  } catch(error) { if (requestEpoch === modalEpoch) toast(error.message); }
}
function relationshipOperation(kind,row,operation) {
  if (operation === 'reschedule') return relationshipEditor(kind,row,operation);
  const complete = operation === 'complete';
  const fields = complete ? '<p class="subtitle">You are recording your claim that this Event happened, not verified attendance.</p>'+relationshipZone(row.timezone || 'UTC')+relationshipTimeField('outcome_happened_at','Claimed occurrence',new Date().toISOString(),row.timezone || 'UTC')+field('outcome_summary','Outcome summary','','text','required maxlength="10000"') : ['archive','restore'].includes(operation) ? `<p>${label(operation)} this Company? Its existing links and history remain available.</p>` : field('reason','Reason','','text','required maxlength="2000"');
  relationshipForm(label(operation),fields, values=>relationshipWrite(`${kind}/${encodeURIComponent(row.id)}/${operation}`,'POST',{expected_version:row.version,...(complete ? {data:values} : values)}),()=>relationshipDetail(kind,row.id));
}
async function eventTaskForm(event) {
  const epoch=++modalEpoch, scope=relationshipWorkspace;
  let policy;
  try { policy=checkedOwnerPolicy(await relationshipRead('task-owner-policy')); } catch(error) { if(epoch===modalEpoch && scope===relationshipWorkspace) toast(error.message); return; }
  if(epoch!==modalEpoch || scope!==relationshipWorkspace) return;
  relationshipForm('Create Event task',ownerFields(policy,{})+field('title','Task title','','text','required')+relationshipZone(event.timezone || 'UTC')+relationshipTimeField('due_at','Due','',event.timezone || 'UTC')+select('priority','Priority',['normal','high'],'normal')+exactSelector('contact_id','contacts',event.contact_id)+exactSelector('deal_id','deals',event.deal_id)+relationshipNotes()+`<p class="subtitle">Review the exact contact and deal IDs above, prefilled from this Event. Clear either ID for no direct context. An Event-only task with no direct contact or deal does not count as a contact follow-up. Creates and links one task atomically. No agent is assigned and no research runs when you save. The explicit Event link remains independent of the selected contact and deal.</p>`,async data=>{ await verifyOwnerPolicy(policy,scope,modalEpoch); return relationshipWrite(`events/${encodeURIComponent(event.id)}/tasks`,'POST',{expected_version:event.version,data:{...ownerTaskData(data,policy),status:'open',contact_id:data.contact_id || null,deal_id:data.deal_id || null}}); },()=>relationshipDetail('events',event.id));
}
async function prepareEventUnlink(task) {
  const epoch=++modalEpoch, scope=relationshipWorkspace;
  try {
    const event=await relationshipRead('events/'+encodeURIComponent(task.event_id));
    if(epoch!==modalEpoch || scope!==relationshipWorkspace) return;
    relationshipForm('Unlink Event',`<p>Remove the link from task ${esc(task.title)} (ID ${esc(task.id)}, version ${task.version}) to Event ${esc(event.title)} (ID ${esc(event.id)}, version ${event.version})? The task remains available.</p>`,()=>relationshipWrite('tasks/'+encodeURIComponent(task.id)+'/event/unlink','POST',{event_id:event.id,expected_version:event.version,expected_task_version:task.version}),()=>taskDetail(task.id));
  } catch(error) { if(epoch===modalEpoch) toast(error.message); }
}
function eventLinkTask(event) {
  const scope = relationshipWorkspace, openingEpoch = modalEpoch;
  relationshipForm('Link exact task',exactSelector('task_id','tasks')+'<p class="subtitle">Select the exact task. Existing task context is retained. No agent work is scheduled.</p>',async values=>{
    if (!values.task_id) throw new Error('Select a task ID.');
    const task = await relationshipRead('tasks/'+encodeURIComponent(values.task_id));
    if (scope !== relationshipWorkspace || modalEpoch !== openingEpoch+1) throw new Error('This task selector is no longer current.');
    return relationshipWrite('tasks/'+encodeURIComponent(task.id)+'/event','PUT',{event_id:event.id,expected_version:event.version,expected_task_version:task.version});
  },()=>relationshipDetail('events',event.id));
}
function contactCompanyForm(contact) {
  relationshipForm('Link Company',exactSelector('company_id','companies',contact.company_id)+`<p class="subtitle">Choose an exact Company ID, or clear the ID to unlink. Legacy company text (${esc(contact.company || 'empty')}) remains unchanged. Names are never matched automatically.</p>`,values=>relationshipWrite('contacts/'+encodeURIComponent(contact.id)+'/company','PUT',{company_id:values.company_id || null,expected_contact_version:contact.version}),()=>contactDetail(contact.id));
}
// Contextual creation keeps exact source identity separate from editable values.
function recoverRelationshipDraft(scope = relationshipWorkspace) {
  const saved=relationshipDrafts.get(scope);
  if(!saved || scope !== relationshipWorkspace) return;
  if($('#modal').open && closeModal(false) === false) return;
  const body=JSON.parse(saved.attempt.payload), source=saved.attempt.returnContext;
  if(saved.attempt.path === 'relationship-contacts') {
    // The old reviewed version is intentionally not restored: review a fresh exact selection.
    newContactForm({...body.data,company_id:body.company_id},source);
  } else if(saved.attempt.path === 'events') {
    relationshipEditor('events',{},'',body.data,source);
  } else return;
  relationshipDrafts.delete(scope);
  refreshRelationshipNotices();
  $('#relationship-form').dataset.dirty='true';
  $('#relationship-error').hidden=false;
  $('#relationship-error').textContent=saved.error+' Original draft restored. Review and correct the fields before saving.'+(saved.attempt.path === 'relationship-contacts' && body.company_id ? ' Choose the exact Company again from search results to review its current version.' : '');
}
function relatedSourceContext(kind,row,extra = {}) {
  return {kind,id:row.id,scope:relationshipWorkspace,...extra};
}
async function restoreRelatedSource(source) {
  if (!source || source.scope !== relationshipWorkspace) return;
  try {
    if (source.kind === 'companies') return await relationshipDetail('companies',source.id,source.tab,source.offset);
    if (source.kind === 'contacts') return await contactDetail(source.id);
    const epoch=++modalEpoch, row=await relationshipRead('deals/'+encodeURIComponent(source.id));
    if (epoch === modalEpoch && source.scope === relationshipWorkspace && row.id === source.id) return openForm('deal',row);
  } catch(error) { if(source.scope === relationshipWorkspace) toast(error.message); }
}
async function openRelatedResult(kind,id,source) {
  if (source && source.scope !== relationshipWorkspace) return;
  const epoch = kind === 'contacts' ? await contactDetail(id) : await relationshipDetail(kind,id);
  if (!source || source.scope !== relationshipWorkspace || epoch !== modalEpoch) return;
  const back=document.createElement('button'); back.type='button'; back.className='button'; back.textContent='Back to source '+(source.kind === 'companies' ? 'Company' : source.kind.slice(0,-1));
  back.onclick=()=>restoreRelatedSource(source);
  $('#modal-body').append(back);
  if (['contacts','companies'].includes(kind)) {
    const researchButton=$(kind==='contacts'?'#contact-research':'#company-research');
    if(researchButton) researchButton.onclick=()=>openResearch(kind,id,()=>openRelatedResult(kind,id,source));
  }
}
function startRelatedCreate(kind,sourceKind,row,extra = {}) {
  if (sourceKind === 'companies' && row.archived_at) return;
  const source=relatedSourceContext(sourceKind,row,extra);
  if (kind === 'contacts') return openForm('contact',{company_id:row.id,expected_company_version:row.version},source);
  const key={companies:'company_id',contacts:'contact_id',deals:'deal_id'}[sourceKind];
  relationshipEditor('events',{},'',{[key]:row.id},source);
}
function contactCreatePayload(values,record,selected) {
  const company_id=values.company_id || null;
  const expected_company_version=company_id ? Number(selected.dataset.reviewedVersion) : null;
  if (company_id && (selected.dataset.reviewedId !== company_id || !Number.isSafeInteger(expected_company_version) || expected_company_version < 1)) throw new Error('Choose the exact Company from search results to review its current version. Search again after a stale or archived Company error.');
  const data={...values}; delete data.company_id;
  if (record.custom_fields) data.custom_fields=structuredClone(record.custom_fields);
  return {data,company_id,expected_company_version};
}
function newContactForm(record = {},source = null) {
  if (source && source.scope !== relationshipWorkspace) return;
  const fields=field('name','Full name *',record.name,'text','required maxlength="160"')+field('email','Email',record.email,'email')+field('company','Legacy company text (unlinked)',record.company)+field('title','Job title',record.title)+select('lifecycle','Contact type',['lead','customer','partner'],record.lifecycle || 'lead')+exactSelector('company_id','companies',record.company_id)+customFieldDetails('contacts',record)+relationshipNotes(record.notes);
  relationshipForm('Add contact',fields,values=>relationshipWrite('relationship-contacts','POST',contactCreatePayload(values,record,document.querySelector('[name="company_id"]')),source),(result,originalContext)=>openRelatedResult('contacts',result.contact.id,originalContext),source);
  const selected=document.querySelector('[name="company_id"]');
  selected.dataset.reviewedId=record.company_id || '';
  selected.dataset.reviewedVersion=String(record.expected_company_version || '');
  selected.addEventListener('input',()=>{delete selected.dataset.reviewedId; delete selected.dataset.reviewedVersion;});
  exactSearch(document.querySelector('[data-exact-search="companies"]'));
}

let exactSearchSequence = 0;
async function exactSearch(input,offset = 0) {
  const seq = ++exactSearchSequence, epoch = modalEpoch, scope = relationshipWorkspace, kind = input.dataset.exactSearch, name = input.dataset.exactName;
  const container = document.querySelector(`[data-exact-results="${name}"]`);
  try {
    const page = await relationshipRead(kind === 'companies' ? kind : 'relationship-selectors/'+kind,{q:input.value,limit:25,offset});
    if (seq !== exactSearchSequence || epoch !== modalEpoch || scope !== relationshipWorkspace) return;
    const rows = Array.isArray(page) ? page : page.items;
    container.innerHTML = rows.map(row=>`<button type="button" class="button" data-exact-id="${esc(row.id)}" data-exact-version="${esc(row.version || '')}">${esc(row.name || row.title)} · ${esc(row.email || row.domain || row.status || '')} · ${esc(row.id)}</button>`).join('') || 'No matches';
    container.querySelectorAll('[data-exact-id]').forEach(button=>button.addEventListener('click',()=>{ const selected=document.querySelector(`[name="${name}"]`); selected.value = button.dataset.exactId; selected.dataset.reviewedId=button.dataset.exactId; selected.dataset.reviewedVersion=button.dataset.exactVersion; const form=$('#relationship-form'); if(form) form.dataset.dirty='true'; container.textContent = 'Selected exact ID: '+button.dataset.exactId+(button.dataset.exactVersion ? ' · Reviewed version '+button.dataset.exactVersion : ''); }));
    if (!Array.isArray(page)) { const pager = document.createElement('div'); pager.innerHTML = `<button class="button" type="button" ${offset ? '' : 'disabled'}>Previous matches</button><button class="button" type="button" ${offset+rows.length>=page.total ? 'disabled' : ''}>Next matches</button>`; container.append(pager); const buttons = pager.querySelectorAll('button'); buttons[0].onclick=()=>exactSearch(input,Math.max(0,offset-25));buttons[1].onclick=()=>exactSearch(input,offset+25); }
    else container.insertAdjacentHTML('beforeend','<small>Returned matches only; enter an exact ID if not listed.</small>');
  } catch(error) { if(seq === exactSearchSequence && epoch === modalEpoch && scope === relationshipWorkspace) container.textContent = error.message; }
}
async function relationshipClick(event) {
  const button = event.target.closest('[data-action]'); if (!button) return;
  const {action,id,kind,tab} = button.dataset;
  if(action === 'relationship-retry') {
    const scope=relationshipWorkspace, epoch=modalEpoch, attempt=relationshipAttempts.get(scope);
    if(attempt) try {
      const result=await relationshipWrite(attempt.path,attempt.method,JSON.parse(attempt.payload));
      if(scope !== relationshipWorkspace || epoch !== modalEpoch) return;
      toast('Original request confirmed.'); await render();
      if(scope !== relationshipWorkspace || epoch !== modalEpoch) return;
      if(attempt.path === 'relationship-contacts') await openRelatedResult('contacts',result.contact.id,attempt.returnContext);
      else if(attempt.path === 'events') await openRelatedResult('events',result.id,attempt.returnContext);
    } catch(error) {
      const rejected=[400,404,409,422].includes(error.status);
      if(rejected && ['relationship-contacts','events'].includes(attempt.path)) {
        relationshipDrafts.set(scope,{attempt,error:error.message});
        if(scope === relationshipWorkspace) refreshRelationshipNotices();
      }
      if(scope !== relationshipWorkspace || epoch !== modalEpoch) return;
      toast(error.message);
      if(rejected) {
        await render();
        if(scope === relationshipWorkspace && epoch === modalEpoch) {
          recoverRelationshipDraft(scope);
          if(!relationshipDrafts.has(scope)) await render();
        }
      }
    }
  }
  if(action === 'relationship-recover-draft') {
    recoverRelationshipDraft();
    if(!relationshipDrafts.has(relationshipWorkspace)) render();
  }
  if(action === 'relationship-create') relationshipEditor(kind);
  if(action === 'company' || action === 'event') relationshipDetail(action === 'company' ? 'companies' : 'events',id);
  if(action === 'relationship-page') { state.offset = Number(button.dataset.offset); render(); }
  if(action === 'relationship-detail-page') relationshipDetail(kind,id,tab,Number(button.dataset.offset));
  if(action === 'relationship-deal') { const epoch=++modalEpoch; try { const row=await relationshipRead('deals/'+encodeURIComponent(id)); if(epoch===modalEpoch) openForm('deal',row); } catch(error) { if(epoch===modalEpoch) toast(error.message); } }
}

async function companyActivities(company,offset=0) {
  const epoch=++modalEpoch;
  try {
    const page=await relationshipRead('relationship-activities',{company_id:company.id,limit:25,offset});
    if(epoch!==modalEpoch) return;
    showModal(modalHead(company.name+' · Activities')+`<div class="detail-body"><p class="subtitle">Completed Events use their explicit Company. Contact logs use the currently linked contact, not historical ownership. All are self-reported.</p><ul class="relationship-list">${page.items.map(row=>`<li>${esc(row.title)}<small>${esc(relReadable(row.happened_at))} · ${esc(row.provenance)} · ${esc(row.timestamp_basis)}</small>${row.record_type==='event' ? relationshipRecordButton('events',{id:row.record_id,title:'Open Event'}) : relationshipRecordButton('contacts',{id:row.contact_id,name:'Open contact'})}</li>`).join('') || '<li>No recorded interactions.</li>'}</ul><div class="form-actions"><button class="button" id="company-activities-prev" ${offset ? '' : 'disabled'}>Previous</button><span>${page.total} total</span><button class="button" id="company-activities-next" ${offset+page.items.length>=page.total ? 'disabled' : ''}>Next</button><button class="button" id="company-activities-back">Back to Company</button></div></div>`);
    $('#company-activities-prev').onclick=()=>companyActivities(company,Math.max(0,offset-25));
    $('#company-activities-next').onclick=()=>companyActivities(company,offset+25);
    $('#company-activities-back').onclick=()=>relationshipDetail('companies',company.id);
  } catch(error) { if(epoch===modalEpoch) toast(error.message); }
}
async function contactEvents(contact, offset = 0, feed = false) {
  const epoch = ++modalEpoch;
  try {
    const page = await relationshipRead(feed ? 'relationship-activities' : 'events',{contact_id:contact.id,limit:25,offset});
    if(epoch !== modalEpoch) return;
    showModal(modalHead(contact.name + (feed ? ' · Activities' : ' · Events')) + `<div class="detail-body"><button class="button" id="contact-toggle-feed">${feed ? 'View Events' : 'View relationship Activities'}</button>${feed ? '<p class="subtitle">Self-reported interactions, not verified communications.</p><ul class="relationship-list">'+page.items.map(row=>`<li>${esc(row.title)}<small>${esc(relReadable(row.happened_at))} · ${esc(row.provenance)} · ${esc(row.timestamp_basis)}</small>${row.record_type === 'event' ? relationshipRecordButton('events',{id:row.record_id,title:'Open Event'}) : ''}</li>`).join('')+'</ul>' : relationshipRows(page,'events')}<div class="form-actions"><button class="button" id="contact-events-prev" ${offset ? '' : 'disabled'}>Previous</button><span>${page.total} total</span><button class="button" id="contact-events-next" ${offset+page.items.length>=page.total ? 'disabled' : ''}>Next</button><button class="button" id="contact-events-back">Back to contact</button></div></div>`);
    $('#contact-toggle-feed').onclick=()=>contactEvents(contact,0,!feed);
    $('#contact-events-prev').onclick=()=>contactEvents(contact,Math.max(0,offset-25),feed);
    $('#contact-events-next').onclick=()=>contactEvents(contact,offset+25,feed);
    $('#contact-events-back').onclick=()=>contactDetail(contact.id);
  } catch(error) { if(epoch === modalEpoch) toast(error.message); }
}
// Human task accountability is independent of frozen agent assignment ownership.
const ownerAttempts = new Map();
const ownerDrafts = new Map();
function checkedOwnerPolicy(value, legacyAbsent=false) {
  const p=value===undefined && legacyAbsent ? {version:0,required:false,default_owner_label:null,legacy_edit_rule:'owner_required_on_edit'} : value;
  if (!p || typeof p!=='object' || Array.isArray(p) || !Number.isSafeInteger(p.version) || p.version<0 || typeof p.required!=='boolean' ||
    !(p.default_owner_label===null || (typeof p.default_owner_label==='string' && p.default_owner_label.trim() && p.default_owner_label.length<=160)))
    throw new Error('Task ownership policy could not be verified. Refresh before saving.');
  return {...p};
}
function ownerFields(policy,record) {
  const useDefault=!record.ownerDraftReview && !record.id && !!policy.default_owner_label;
  return `<p class="subtitle">Human accountability only. This owner does not assign Hermes, change saved agent assignments or schedule work. Reviewed policy version ${policy.version}: owner ${policy.required ? 'required' : 'optional'}.</p>`+
    select('owner_choice','Owner choice', [['explicit','Enter owner explicitly'],...(policy.default_owner_label ? [['default','Use reviewed default: '+policy.default_owner_label]] : [])],useDefault ? 'default' : 'explicit')+
    field('owner_label','Human owner',record.owner_label || (useDefault ? policy.default_owner_label : ''),'text','maxlength="160"')+
    (record.id && !record.owner_label ? '<p class="subtitle">This existing task has no recorded owner. Choose an owner explicitly before editing or completing it when ownership is required. No default is applied automatically.</p>' : '');
}
function ownerTaskData(values,policy) {
  const data={...values}, choice=data.owner_choice;
  delete data.owner_choice;
  const owner=String(data.owner_label || '').trim();
  if(owner.length>160) throw new Error('Owner must be at most 160 characters.');
  if(choice==='default' && (!policy.default_owner_label || owner!==policy.default_owner_label)) throw new Error('To use the reviewed default, enter its exact label or choose explicit owner.');
  if(policy.required && !owner) throw new Error('A human owner is required. Enter an owner before saving this task.');
  data.owner_label=owner || null; data.owner_source=choice==='default' ? 'default' : 'explicit'; data.owner_policy_version=policy.version;
  return data;
}
async function verifyOwnerPolicy(policy,scope,epoch) {
  const fresh=checkedOwnerPolicy(await api('task-owner-policy?'+new URLSearchParams({workspace_token:scope})));
  if(scope!==relationshipWorkspace || epoch!==modalEpoch) throw new Error('This task draft is no longer current.');
  if(fresh.version!==policy.version || fresh.required!==policy.required || fresh.default_owner_label!==policy.default_owner_label)
    throw new Error('Ownership policy changed. Your draft has not been saved. Cancel and reopen to review the current policy and default.');
}
function ownerNotices() {
  return (ownerAttempts.has(relationshipWorkspace) ? '<section class="error" role="alert">A task or policy save has an unknown outcome. New accountability writes are blocked. <button class="button" data-action="owner-retry">Retry original unchanged save</button></section>' : '') + (ownerDrafts.has(relationshipWorkspace) ? '<section class="error" role="alert">A rejected task or policy draft is retained. <button class="button" data-action="owner-recover">Review rejected draft with current policy</button></section>' : '');
}
function sameOwnerDue(actual,expected) {
  try { return relMicros(actual)===relMicros(expected); } catch { return false; }
}
function ownerReceipt(attempt,result) {
  const body=JSON.parse(attempt.payload);
  if(attempt.path==='task-owner-policy') return !!result && result.version===body.data.version+1 && result.required===body.data.required && result.default_owner_label===body.data.default_owner_label;
  return !!result && typeof result.id==='string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(result.id) && typeof result.title==='string' && !!result.title.trim() && result.title.length<=200 && sameOwnerDue(result.due_at,result.due_at) && ['open','done'].includes(result.status) && (result.owner_label===null || typeof result.owner_label==='string' && !!result.owner_label.trim() && result.owner_label.length<=160) && (result.owner_source===null || ['explicit','default'].includes(result.owner_source)) && Number.isSafeInteger(result.version) && result.version>0 &&
    (attempt.id ? result.id===attempt.id && result.version===body.version+1 : result.version===1) &&
    ['title','status','owner_label','priority','notes','contact_id','deal_id'].every(k=>!Object.hasOwn(body,k) || result[k]===body[k]) &&
    (!Object.hasOwn(body,'due_at') || sameOwnerDue(result.due_at,body.due_at)) &&
    (!Object.hasOwn(body,'owner_source') || result.owner_source===body.owner_source);
}
async function ownerWrite(path,method,body,scope=relationshipWorkspace,retry=false,recovered=null) {
  if(!scope || scope!==relationshipWorkspace) throw new Error('Workspace changed. Reopen before saving.');
  if (relationshipAttempts.has(scope)) throw new Error('A relationship save is unconfirmed. Retry its original request first.');
  let attempt=ownerAttempts.get(scope);
  if(attempt && !retry) throw new Error('An earlier save is unconfirmed. Use Retry original unchanged save before editing again.');
  if(attempt?.running) throw new Error('A save is already running.');
  if(!attempt) { attempt={path,method,payload:JSON.stringify(body),key:crypto.randomUUID(),recovered,id:path.startsWith('tasks/') ? decodeURIComponent(path.slice(6)) : null}; ownerAttempts.set(scope,attempt); }
  attempt.running=true;
  try {
    const saved=JSON.parse(attempt.payload);
    const result=await api(attempt.path+(attempt.path==='task-owner-policy' ? '' : '?'+new URLSearchParams({workspace_token:scope})),attempt.method,attempt.path==='task-owner-policy' ? {...saved,workspace_token:scope,idempotency_key:attempt.key} : saved,attempt.key);
    if(!ownerReceipt(attempt,result)) throw new Error('Save receipt could not be verified.');
    ownerAttempts.delete(scope); if(attempt.recovered && ownerDrafts.get(scope)===attempt.recovered) ownerDrafts.delete(scope); return result;
  } catch(error) {
    if([400,404,409,422].includes(error.status)) { ownerAttempts.delete(scope); ownerDrafts.set(scope,{attempt,error:error.message}); }
    else error.message+=' Outcome unknown. Retry original unchanged save; the exact request and key are retained.';
    throw error;
  } finally { attempt.running=false; if(scope===relationshipWorkspace) refreshRelationshipNotices(); }
}
async function retryOwnerWrite() {
  const scope=relationshipWorkspace, epoch=modalEpoch, attempt=ownerAttempts.get(scope);
  if(!attempt) return;
  try {
    await ownerWrite(attempt.path,attempt.method,JSON.parse(attempt.payload),scope,true);
    if(scope!==relationshipWorkspace || epoch!==modalEpoch) return;
    toast('Original save confirmed. Reopen to review current data.'); await render();
  } catch(error) { if(scope===relationshipWorkspace && epoch===modalEpoch) toast(error.message); }
}
async function recoverOwnerDraft() {
  const scope=relationshipWorkspace, saved=ownerDrafts.get(scope);
  if(!saved || ($('#modal').open && closeModal(false)===false)) return;
  const epoch=++modalEpoch;
  try {
    if(saved.attempt.path==='task-owner-policy') {
      await openTaskOwnerPolicy(saved);
      return;
    }
    const body=JSON.parse(saved.attempt.payload);
    const [policyValue,current,contacts,deals]=await Promise.all([
      relationshipRead('task-owner-policy'),saved.attempt.id ? relationshipRead('tasks/'+encodeURIComponent(saved.attempt.id)) : Promise.resolve({}),api('contacts'),api('deals')]);
    if(scope!==relationshipWorkspace || epoch!==modalEpoch || ownerDrafts.get(scope)!==saved) return;
    if(saved.attempt.id && current.id!==saved.attempt.id) throw new Error('Current task identity could not be verified.');
    const record={...current,...body,ownerDraftReview:true};
    delete record.owner_policy_version;
    if(saved.attempt.id) { record.id=current.id; record.version=current.version; } else { delete record.version; delete record.id; }
    taskOwnerEditor(record,preserveSelection(list(contacts),record.contact_id,record.contact_name,'contact'),preserveSelection(list(deals),record.deal_id,record.deal_title,'deal'),checkedOwnerPolicy(policyValue),saved);
    $('#relationship-form').dataset.dirty='true';
    $('#relationship-error').hidden=false;
    $('#relationship-error').textContent=saved.error+' Original values restored against the current task and ownership policy. Review every field and choose an owner source before Save. Nothing has been resubmitted.';
  } catch(error) { if(scope===relationshipWorkspace && epoch===modalEpoch) toast(error.message); }
}
async function openTaskOwnerPolicy(recovered=null) {
  const scope=relationshipWorkspace, epoch=++modalEpoch;
  try {
    const policy=checkedOwnerPolicy(await relationshipRead('task-owner-policy'));
    if(scope!==relationshipWorkspace || epoch!==modalEpoch) return;
    relationshipForm('Task ownership policy',`<p>Current policy version ${policy.version}: human owner ${policy.required ? 'required' : 'optional'}. Default: ${esc(policy.default_owner_label || 'None')}.</p><p>Required ownership applies to new tasks and task-detail edits, including Complete and Reopen. Relationship-only maintenance is unchanged. Existing ownerless tasks remain unchanged until you edit them. This does not alter agent assignments or run times.</p>`+select('required','Require a human owner',[['false','Optional'],['true','Required']],String(recovered ? JSON.parse(recovered.attempt.payload).data.required : policy.required))+field('default_owner_label','Default owner for new tasks (optional)',(recovered ? JSON.parse(recovered.attempt.payload).data.default_owner_label : policy.default_owner_label) || '','text','maxlength="160"'),values=>ownerWrite('task-owner-policy','PATCH',{data:{version:policy.version,required:values.required==='true',default_owner_label:values.default_owner_label.trim() || null}},scope,false,recovered),()=>{ if(recovered && ownerDrafts.get(scope)===recovered) ownerDrafts.delete(scope); refreshRelationshipNotices(); toast('Task ownership policy saved. Existing tasks were not changed.'); });
    if(recovered && scope===relationshipWorkspace) { $('#relationship-form').dataset.dirty='true'; $('#relationship-error').hidden=false; $('#relationship-error').textContent=recovered.error+' Original policy choices restored. Review them against the current policy above, then explicitly Save. Nothing has been resubmitted.'; }
  } catch(error) { if(scope===relationshipWorkspace && epoch===modalEpoch) toast(error.message); }
}
function taskOwnerEditor(record,contacts,deals,policy,recovered=null) {
  const scope=relationshipWorkspace;
  const fields=field('title','Task name *',record.title,'text','required maxlength="200"')+ownerFields(policy,record)+
    select('contact_id','Contact (optional)',[['','No contact'],...contacts.map(c=>[c.id,c.name])],record.contact_id || '')+
    select('deal_id','Deal (optional)',[['','No deal'],...deals.map(d=>[d.id,d.title])],record.deal_id || '')+
    field('due_at','Due date & time (your timezone) *',localTime(record.due_at),'datetime-local','required')+
    select('priority','Priority',['normal','high'],record.priority || 'normal')+select('status','Status',['open','done'],record.status || 'open')+customFieldDetails('tasks',record)+relationshipNotes(record.notes);
  relationshipForm(record.id ? 'Edit task' : 'Add task',fields,async values=>{
    const epoch=modalEpoch;
    const data=ownerTaskData(values,policy);
    data.contact_id=data.contact_id || null; data.deal_id=data.deal_id || null; data.due_at=taskDuePayload(data.due_at,record);
    if(record.id) data.version=record.version;
    await verifyOwnerPolicy(policy,scope,epoch);
    return ownerWrite('tasks'+(record.id ? '/'+encodeURIComponent(record.id) : ''),record.id ? 'PATCH' : 'POST',data,scope,false,recovered);
  },result=>{ if(recovered && ownerDrafts.get(scope)===recovered) ownerDrafts.delete(scope); refreshRelationshipNotices(); return taskDetail(result.id); });
}

// Manual research is local plaintext evidence, never an instruction to fetch or execute.
const researchAttempts = new Map();
const researchDrafts = new Map();
let researchWorkspaceEpoch = 0;
let researchView = null;
function researchCurrent(ctx) { return ctx.scope === relationshipWorkspace && ctx.workspaceEpoch === researchWorkspaceEpoch && ctx.epoch === modalEpoch; }
function researchContext(kind,id,back) { return {kind,id,scope:relationshipWorkspace,workspaceEpoch:researchWorkspaceEpoch,epoch:modalEpoch,back}; }
function researchTarget(row,ctx) { return row && row.target_kind === ctx.kind && row.target_id === ctx.id; }
function researchLength(v) { return Array.from(v).length; }
function researchVersion(v) { return Number.isSafeInteger(v) && v > 0; }
function researchId(v) { return typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v); }
function researchHash(v) { return typeof v === 'string' && /^[a-f0-9]{64}$/.test(v); }
function researchNotice() {
  const a=researchAttempts.get(relationshipWorkspace);
  return a ? `<section class="error" role="alert">Research write outcome unconfirmed for ${esc(a.kind)} ${esc(a.id)}. New research writes are frozen. <button class="button" type="button" data-action="research-recover">Check original operation</button><button class="button" type="button" data-action="research-retry">Retry original unchanged request</button></section>` : '';
}
function researchReceipt(a,r) {
  if (!r || !researchTarget(r,a) || !researchVersion(r.target_version)) return false;
  const d=a.body.data, parts=a.path.split('/');
  if (parts[1]==='evidence') {
    if (!researchId(r.id) || !researchHash(r.digest) || !researchVersion(r.lifecycle_version) || typeof r.recorded_at!=='string' || typeof r.source_url!=='string' || typeof r.source_title!=='string' || typeof r.observed_at!=='string' || !(r.published_on===null || typeof r.published_on==='string') || !Number.isSafeInteger(r.claims_count) || r.claims_count<1 || !Number.isSafeInteger(r.hypotheses_count) || r.hypotheses_count<0) return false;
    if (parts.length===2) return r.target_version===d.target_version && r.lifecycle_version===1 && r.source_url===d.source_url && r.source_title===d.source_title && r.observed_at===d.observed_at && r.published_on===d.published_on && r.claims_count===d.claims.length && r.hypotheses_count===d.hypotheses.length && r.archived_at===null;
    return r.id===decodeURIComponent(parts[2]) && r.lifecycle_version===d.lifecycle_version+1 && (parts[3]==='archive' ? typeof r.archived_at==='string' : r.archived_at===null);
  }
  if(parts.length===2) return researchId(r.id) && typeof r.created_at==='string' && !!r.created_at && r.status==='pending' && r.proposal_version===1 && researchHash(r.proposal_digest) && researchHash(r.before_hash) && researchHash(r.after_hash) && r.evidence_id===d.evidence_id && r.evidence_digest===d.evidence_digest && r.evidence_lifecycle_version===d.evidence_lifecycle_version && r.target_version===d.target_version && r.addition===d.addition;
  return researchId(r.evidence_id) && researchId(r.proposal_id) && researchHash(r.evidence_digest) && researchVersion(r.evidence_lifecycle_version) && researchHash(r.before_hash) && researchHash(r.after_hash) && typeof r.actor==='string' && typeof r.recorded_at==='string' && r.proposal_id===decodeURIComponent(parts[2]) && r.proposal_digest===d.proposal_digest && r.proposal_version===d.proposal_version+1 && r.status===(parts[3]==='apply' ? 'applied' : 'dismissed') && (parts[3]!=='apply' || (r.target_version===d.target_version && r.applied_target_version===d.target_version+1 && r.before_hash===d.before_hash && r.after_hash===d.after_hash));
}
async function researchWrite(ctx,path,data) {
  if(!researchCurrent(ctx)) throw new Error('This research view is no longer current.');
  if(researchAttempts.has(ctx.scope)) throw new Error('An earlier research outcome is unknown. Check the original operation first.');
  const key=crypto.randomUUID(), a={kind:ctx.kind,id:ctx.id,path,key,body:JSON.parse(JSON.stringify({workspace_token:ctx.scope,idempotency_key:key,data})),running:true};
  researchAttempts.set(ctx.scope,a);
  try {
    const r=await api(path,'POST',a.body);
    if(!researchReceipt(a,r)) throw new Error('Unverified research receipt. Check the original operation before continuing.');
    if(researchAttempts.get(ctx.scope)===a) researchAttempts.delete(ctx.scope);
    return r;
  } catch(e) {
    if([400,404,409,422].includes(e.status) && researchAttempts.get(ctx.scope)===a) researchAttempts.delete(ctx.scope);
    throw e;
  } finally { a.running=false; refreshRelationshipNotices(); }
}
async function researchRecover(retry=false) {
  const scope=relationshipWorkspace, a=researchAttempts.get(scope), epoch=modalEpoch, generation=researchWorkspaceEpoch;
  if(!a || a.running) return;
  a.running=true;
  try {
    const result=retry ? {state:'committed',receipt:await api(a.path,'POST',a.body)} : await api('research/operations/'+encodeURIComponent(a.key)+'?'+new URLSearchParams({workspace_token:scope}));
    if(result.state==='committed' && researchReceipt(a,result.receipt)) {
      if(researchAttempts.get(scope)===a) researchAttempts.delete(scope);
      if(a.draftKey && researchDrafts.get(a.draftKey)===a.draft) researchDrafts.delete(a.draftKey);
      if(scope===relationshipWorkspace && epoch===modalEpoch && generation===researchWorkspaceEpoch) {
        toast('Original research operation confirmed. This historical receipt does not prove notes are unchanged.');
        const form=$('#relationship-form'); if(form?.researchAttemptKey===a.key) await form.researchRecovery?.(true);
      }
    } else if(scope===relationshipWorkspace && epoch===modalEpoch && generation===researchWorkspaceEpoch) toast('Outcome remains unknown. Original key and request retained; no new write was sent.');
  } catch(e) {
    if(retry && [400,404,409,422].includes(e.status) && researchAttempts.get(scope)===a) {
      researchAttempts.delete(scope);
      if(scope===relationshipWorkspace && epoch===modalEpoch && generation===researchWorkspaceEpoch) { const form=$('#relationship-form'); if(form?.researchAttemptKey===a.key) await form.researchRecovery?.(false); }
    }
    if(scope===relationshipWorkspace && epoch===modalEpoch && generation===researchWorkspaceEpoch) toast(e.message);
  }
  finally { a.running=false; refreshRelationshipNotices(); }
}
function researchShell(ctx,title,body) {
  showModal(modalHead(title)+`<div class="detail-body"><p>${esc(label(ctx.kind))} · ${esc(ctx.id)}</p><p class="subtitle">Manually supplied evidence. Claims and hypotheses are unverified plaintext. Nothing is fetched, researched, emailed or executed. Source URLs and supplied dates are not verified.</p>${researchNotice()}${body}<div class="form-actions"><button class="button" id="research-back">Back to record</button><button class="button" data-action="close">Close</button></div></div>`);
  ctx.epoch=modalEpoch; researchView=ctx;
  $('#research-back').onclick=()=>{if(researchCurrent(ctx) && closeModal(false)!==false) ctx.back();};
}
async function researchRow(ctx) {
  const result=await relationshipRead(ctx.kind+'/'+encodeURIComponent(ctx.id));
  const row=ctx.kind==='contacts' ? result.contact : result.company;
  if(!row || row.id!==ctx.id || !researchVersion(row.version)) throw new Error('Target identity or version unavailable.');
  return row;
}
function researchPageValid(page,ctx) {
  return page && Array.isArray(page.items) && Number.isSafeInteger(page.total) && page.total>=0 && Number.isSafeInteger(page.offset) && page.offset>=0 && Number.isSafeInteger(page.limit) && page.limit>0 && page.items.every(r=>researchTarget(r,ctx));
}
async function openResearch(kind,id,back=null,tab='evidence',offset=0) {
  if(!['contacts','companies'].includes(kind) || !['evidence','proposals'].includes(tab)) return;
  const priorView=$('#modal').open && researchView && researchCurrent(researchView) ? researchView : null;
  const form=$('#relationship-form');
  if($('#modal').open && (form?.dataset.saving || (form?.dataset.dirty && !form.dataset.discard)) && closeModal(false)===false) return;
  ++modalEpoch;
  const returnToRecord=back || (async()=>{await (kind==='contacts' ? contactDetail(id) : relationshipDetail(kind,id)); $(kind==='contacts'?'#contact-research':'#company-research')?.focus();});
  const ctx=researchContext(kind,id,returnToRecord);
  try {
    const [row,page]=await Promise.all([researchRow(ctx),relationshipRead('research/'+tab,{target_kind:kind,target_id:id,limit:10,offset})]);
    if(!researchCurrent(ctx)) return;
    if(!researchPageValid(page,ctx)) throw new Error('Research page identity could not be verified.');
    researchShell(ctx,row.name+' · Research',`<div class="form-actions"><button class="button" id="research-evidence">Evidence</button><button class="button" id="research-proposals">Note proposals</button><button class="button primary" id="research-add">Add manual evidence</button></div><ul class="relationship-list">${page.items.map(r=>`<li>${tab==='evidence' ? `${esc(r.source_title)}<small>${esc(r.source_url)} · ${esc(researchObservedPreview(r.observed_at))} · Raw observation timestamp: ${esc(r.observed_at)} · ${r.archived_at ? 'Archived' : 'Active'} · ${Number(r.claims_count)} claims / ${Number(r.hypotheses_count)} hypotheses · Server-derived channel: ${esc(r.recorded_actor||'Not recorded')} (not a verified person)</small>` : `${esc(r.status)}${r.stale ? ' · Stale: '+esc(r.stale_reason) : ''}<small>${esc(r.id)} · Target version ${Number(r.target_version)} · Server-derived channel: ${esc(r.created_actor||'Not recorded')} (not a verified person)</small>`}<button class="button" data-research-item="${esc(r.id)}">${tab==='evidence' ? 'Review evidence' : 'Preview proposal'}</button></li>`).join('') || '<li>No records yet.</li>'}</ul><div class="form-actions"><button class="button" id="research-prev" ${offset===0?'disabled':''}>Previous</button><span>${page.total} total</span><button class="button" id="research-next" ${offset+page.items.length>=page.total?'disabled':''}>Next</button></div>`);
    $('#research-evidence').onclick=()=>researchCurrent(ctx)&&openResearch(kind,id,ctx.back);
    $('#research-proposals').onclick=()=>researchCurrent(ctx)&&openResearch(kind,id,ctx.back,'proposals');
    $('#research-add').onclick=()=>researchEvidenceForm(ctx);
    $('#research-prev').onclick=()=>researchCurrent(ctx)&&openResearch(kind,id,ctx.back,tab,Math.max(0,offset-10));
    $('#research-next').onclick=()=>researchCurrent(ctx)&&openResearch(kind,id,ctx.back,tab,offset+10);
    document.querySelectorAll('[data-research-item]').forEach(b=>b.onclick=()=>tab==='evidence'?researchEvidence(ctx,b.dataset.researchItem):researchPreview(ctx,b.dataset.researchItem));
  } catch(e) { if(researchCurrent(ctx)) { if(priorView) priorView.epoch=modalEpoch; toast(e.message+' The previous view is retained. Try Previous or retry this page.'); } }
}
function researchDraftKey(ctx,type) { return JSON.stringify([ctx.scope,ctx.kind,ctx.id,type]); }
function researchForm(ctx,title,fields,type,submit) {
  researchShell(ctx,title,`<form id="relationship-form"><div class="relationship-form-grid">${fields}</div><p id="relationship-error" role="alert" hidden></p><div id="relationship-discard" role="alert" hidden><p>Discard unsaved changes?</p><button class="button" type="button" id="relationship-keep">Keep editing</button><button class="button" type="button" id="relationship-discard-confirm">Discard changes</button></div><div class="form-actions"><button class="button primary" type="submit">${type==='evidence'?'Save evidence':'Prepare append proposal'}</button><button class="button" type="button" id="research-refresh">Refresh target for corrected save</button></div></form>`);
  const form=$('#relationship-form'), key=researchDraftKey(ctx,type);
  form.researchRecovery=async committed=>{
    if(!researchCurrent(ctx)) return;
    form.querySelectorAll('input,textarea,button').forEach(b=>b.disabled=false);
    if(committed) { delete form.dataset.dirty; form.dataset.discard='true'; form.dataset.researchCommitted='true'; form.querySelectorAll('input,textarea,button').forEach(b=>b.disabled=!['relationship-keep','relationship-discard-confirm'].includes(b.id)); await openResearch(ctx.kind,ctx.id,ctx.back,type==='evidence'?'evidence':'proposals'); }
    else { $('#relationship-error').hidden=false; $('#relationship-error').textContent='Original request rejected. Draft retained. Refresh the target and explicitly save corrected data.'; }
  };
  const capture=()=>Object.fromEntries(new FormData(form));
  const keep=()=>{form.dataset.dirty='true';researchDrafts.set(key,capture());};
  form.addEventListener('input',keep); form.addEventListener('change',keep);
  if(researchDrafts.has(key)) form.dataset.dirty='true';
  $('#relationship-keep').onclick=()=>{$('#relationship-discard').hidden=true;form.querySelector('input,textarea')?.focus();};
  $('#relationship-discard-confirm').onclick=()=>{researchDrafts.delete(key);form.dataset.discard='true';closeModal();};
  $('#research-refresh').onclick=async()=>{
    if(!researchCurrent(ctx)||form.dataset.saving || researchAttempts.has(ctx.scope)) return;
    const button=$('#research-refresh'); button.disabled=true;
    try { const row=await researchRow(ctx); if(researchCurrent(ctx)){ctx.targetVersion=row.version;$('#relationship-error').hidden=false;$('#relationship-error').textContent='Current target version '+row.version+' loaded. Draft retained. Review it, then explicitly save a corrected request.';} }
    catch(e){if(researchCurrent(ctx)){ $('#relationship-error').hidden=false;$('#relationship-error').textContent=e.message; }} finally {button.disabled=false;}
  };
  form.addEventListener('submit',async event=>{
    event.preventDefault(); if(!researchCurrent(ctx)||form.dataset.saving||form.dataset.researchCommitted||!form.reportValidity()) return;
    const values=capture(); researchDrafts.set(key,values); form.dataset.dirty='true';form.dataset.saving='true';
    const controls=[...form.querySelectorAll('input,textarea,button')]; controls.forEach(b=>b.disabled=true);
    try { await submit(values); if(researchDrafts.get(key)===values) researchDrafts.delete(key); if(!researchCurrent(ctx))return;delete form.dataset.saving;delete form.dataset.dirty;form.dataset.discard='true';form.dataset.researchCommitted='true';await openResearch(ctx.kind,ctx.id,ctx.back,type==='evidence'?'evidence':'proposals'); }
    catch(e){if(researchCurrent(ctx)){ $('#relationship-error').hidden=false;$('#relationship-error').textContent=e.message+' Draft retained. Conflicts require refreshed review and an explicit corrected save.'; }}
    finally {delete form.dataset.saving; controls.forEach(b=>b.disabled=(!!form.dataset.researchCommitted || researchAttempts.has(ctx.scope)) && !['relationship-keep','relationship-discard-confirm'].includes(b.id)); if(researchCurrent(ctx) && researchAttempts.has(ctx.scope)){ const attempt=researchAttempts.get(ctx.scope);form.researchAttemptKey=attempt.key;if(!attempt.draftKey){attempt.draftKey=key;attempt.draft=values;} const recovery=document.createElement('div');recovery.innerHTML=researchNotice();form.append(recovery); }}
  });
}
function researchTextarea(name,title,value='',extra='') { return `<label class="field relationship-wide">${esc(title)}<textarea name="${name}" rows="4" ${extra}>${esc(value)}</textarea></label>`; }
function researchObservedPreview(value) {
  if(!value) return 'No observation time supplied. Choose current time explicitly or enter the time you observed the evidence.';
  try {
    relInstant(value);
    return 'Supplied observation: '+new Intl.DateTimeFormat('en-GB',{dateStyle:'full',timeStyle:'long',timeZone:'UTC'}).format(new Date(value))+' · Entered offset: '+value.match(/(Z|[+-]\d\d:\d\d)$/)[0]+'. This time is not verified.';
  } catch { return 'Enter a valid date and time with an explicit offset, such as 2030-01-01T12:00:00+00:00.'; }
}
async function researchEvidenceForm(ctx) {
  if(!researchCurrent(ctx))return;
  ++modalEpoch;ctx={...ctx,epoch:modalEpoch};
  try {
    const row=await researchRow(ctx); if(!researchCurrent(ctx))return;ctx.targetVersion=row.version;
    const d=researchDrafts.get(researchDraftKey(ctx,'evidence'))||{};
    researchForm(ctx,'Add manual evidence',field('question','Research question',d.question||'','text','required')+field('source_url','HTTPS source URL (not verified)',d.source_url||'','url','required')+field('source_title','Source title',d.source_title||'','text','required')+field('observed_at','Observed at (supplied, explicit offset required: Z or ±HH:MM)',d.observed_at||'','text','required maxlength="40" placeholder="2030-01-01T12:00:00+00:00"')+'<div class="relationship-wide"><button class="button" type="button" id="research-observed-now">Use current time as my observation time</button><p class="subtitle">Only use current time if you observed this evidence now. Otherwise enter the actual observation time with its UTC offset.</p><p id="research-observed-preview" aria-live="polite"></p></div>'+field('published_on','Published on (supplied, optional)',d.published_on||'','date')+researchTextarea('claims','Claims: one per line, up to 10, 2000 characters each',d.claims||'','required')+researchTextarea('hypotheses','Hypotheses: one per line, up to 10, 2000 characters each',d.hypotheses||''),'evidence',async v=>{
      const data={target_kind:ctx.kind,target_id:ctx.id,target_version:ctx.targetVersion,question:v.question,source_url:v.source_url,source_title:v.source_title,observed_at:v.observed_at,published_on:v.published_on||null,claims:v.claims.split('\n').filter(s=>s.trim()),hypotheses:v.hypotheses.split('\n').filter(s=>s.trim())};
      if(!/^https:\/\/[^\s]+$/.test(data.source_url))throw new Error('Use an HTTPS source reference. It will not be fetched.');
      if(researchLength(data.question)>1000 || researchLength(data.source_url)>2048 || researchLength(data.source_title)>200) throw new Error('Question/source URL/title exceed their 1000/2048/200 character limits.');
      if(data.claims.length<1 || data.claims.length>10 || data.hypotheses.length>10 || [...data.claims,...data.hypotheses].some(s=>researchLength(s)>2000))throw new Error('Provide 1–10 claims and at most 10 hypotheses, up to 2000 characters each.');
      relInstant(data.observed_at);
      return researchWrite(ctx,'research/evidence',data);
    });
    const observed=$('[name="observed_at"]'), form=$('#relationship-form');
    const preview=()=>{ $('#research-observed-preview').textContent=researchObservedPreview(observed.value); };
    observed.addEventListener('input',preview);
    $('#research-observed-now').onclick=()=>{
      if(!researchCurrent(ctx) || form.dataset.saving || researchAttempts.has(ctx.scope)) return;
      observed.value=new Date().toISOString(); form.dataset.dirty='true';
      researchDrafts.set(researchDraftKey(ctx,'evidence'),{...Object.fromEntries(new FormData(form)),observed_at:observed.value});
      preview(); observed.focus();
    };
    preview();
  } catch(e){if(researchCurrent(ctx))toast(e.message);}
}
async function researchEvidence(ctx,id) {
  if(!researchCurrent(ctx))return;
  ++modalEpoch;ctx={...ctx,epoch:modalEpoch};
  try {
    const r=await relationshipRead('research/evidence/'+encodeURIComponent(id)); if(!researchCurrent(ctx))return;
    if(!researchTarget(r,ctx)||r.id!==id||!Array.isArray(r.claims)||!Array.isArray(r.hypotheses))throw new Error('Evidence identity could not be verified.');
    researchShell(ctx,'Review evidence',`<h3>${esc(r.source_title)}</h3><p class="notes">${esc(r.question)}</p><p>Source reference (not verified): ${esc(r.source_url)}</p><p>${esc(researchObservedPreview(r.observed_at))} · Raw observation timestamp: ${esc(r.observed_at)} · Published (supplied): ${esc(r.published_on||'Not supplied')} · Recorded locally: ${esc(r.recorded_at)} · Server-derived channel: ${esc(r.recorded_actor||'Not recorded')} (not a verified person)</p><h3>Claims</h3><ul>${r.claims.map(s=>`<li class="notes">${esc(s)}</li>`).join('')}</ul><h3>Hypotheses</h3><ul>${r.hypotheses.map(s=>`<li class="notes">${esc(s)}</li>`).join('')}</ul><p>${r.archived_at?'Archived':'Active'} · Lifecycle version ${Number(r.lifecycle_version)}</p><div class="form-actions"><button class="button primary" id="research-prepare" ${r.archived_at?'disabled':''}>Prepare note addition</button><button class="button" id="research-lifecycle">${r.archived_at?'Restore':'Archive'} evidence</button></div>`);
    $('#research-prepare').onclick=()=>researchProposalForm(ctx,r);
    const button=$('#research-lifecycle');button.onclick=async()=>{
      if(!researchCurrent(ctx)||button.disabled)return;button.disabled=true;
      try{await researchWrite(ctx,'research/evidence/'+encodeURIComponent(id)+'/'+(r.archived_at?'restore':'archive'),{lifecycle_version:r.lifecycle_version});if(researchCurrent(ctx))await openResearch(ctx.kind,ctx.id,ctx.back);}
      catch(e){if(researchCurrent(ctx))toast(e.message);}finally{button.disabled=false;}
    };
  }catch(e){if(researchCurrent(ctx))toast(e.message);}
}
async function researchProposalForm(ctx,evidence) {
  if(!researchCurrent(ctx))return;
  ++modalEpoch;ctx={...ctx,epoch:modalEpoch};
  try {
    const row=await researchRow(ctx);if(!researchCurrent(ctx))return;ctx.targetVersion=row.version;
    const type='proposal:'+evidence.id,d=researchDrafts.get(researchDraftKey(ctx,type))||{};
    researchForm(ctx,'Prepare append proposal',`<p>Evidence ${esc(evidence.id)} · ${esc(evidence.source_title)}. Only the addition below will be appended. Review source claims and distinguish hypotheses. Full notes must remain within 10,000 characters.</p>`+researchTextarea('addition','Exact plaintext addition',d.addition||'','required'),type,v=>researchWrite(ctx,'research/proposals',{evidence_id:evidence.id,evidence_digest:evidence.digest,evidence_lifecycle_version:evidence.lifecycle_version,target_version:ctx.targetVersion,addition:v.addition}));
  }catch(e){if(researchCurrent(ctx))toast(e.message);}
}
function researchPreviewValid(r,ctx,id) {
  if(!researchTarget(r,ctx)||r.id!==id||!researchVersion(r.proposal_version)||!researchVersion(r.target_version)||!researchHash(r.proposal_digest)||!researchHash(r.before_hash)||!researchHash(r.after_hash)||typeof r.addition!=='string'||typeof r.stale!=='boolean'||!['pending','applied','dismissed'].includes(r.status))return false;
  return r.stale || r.status!=='pending' || (typeof r.current_notes==='string'&&typeof r.proposed_notes==='string'&&r.proposed_notes===r.current_notes+(r.current_notes?'\n\n':'')+r.addition&&researchLength(r.proposed_notes)<=10000);
}
async function researchPreview(ctx,id) {
  if(!researchCurrent(ctx))return;
  ++modalEpoch;ctx={...ctx,epoch:modalEpoch};
  try {
    const r=await relationshipRead('research/proposals/'+encodeURIComponent(id)+'/preview');if(!researchCurrent(ctx))return;
    if(!researchPreviewValid(r,ctx,id))throw new Error('Proposal preview could not be verified.');
    if(!r.stale && r.status==='pending') {
      const digest=async text=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(n=>n.toString(16).padStart(2,'0')).join('');
      const [before,after]=await Promise.all([digest(r.current_notes),digest(r.proposed_notes)]);
      if(!researchCurrent(ctx))return;
      if(before!==r.before_hash||after!==r.after_hash)throw new Error('Preview hashes do not match the displayed notes.');
    }
    researchShell(ctx,'Review note proposal',`<p>Action state: ${esc(r.status)} · ${r.stale?'Stale: '+esc(r.stale_reason):'Current review'} · Target version ${r.target_version}</p><p>Proposal ${esc(r.id)} · Evidence ${esc(r.evidence_id)} · Server-derived channel: ${esc(r.created_actor||'Not recorded')} (not a verified person)</p><h3>Addition</h3><div class="notes">${esc(r.addition)}</div>${!r.stale&&r.status==='pending'?`<h3>Current notes</h3><div class="notes">${esc(r.current_notes)}</div><h3>Proposed notes</h3><div class="notes">${esc(r.proposed_notes)}</div>`:''}<p class="subtitle">Applying updates ordinary notes and last edit only, not last interaction, task completion or agent execution. A historical applied receipt does not prove the current note is unchanged.</p><div class="form-actions"><button class="button primary" id="research-apply" ${r.stale||r.status!=='pending'?'disabled':''}>Apply reviewed append</button><button class="button" id="research-dismiss" ${r.status!=='pending'?'disabled':''}>Dismiss proposal</button><button class="button" id="research-repreview">Refresh preview</button></div>`);
    $('#research-repreview').onclick=()=>researchPreview(ctx,id);
    for(const action of ['apply','dismiss'])$('#research-'+action).onclick=async()=>{
      const button=$('#research-'+action);if(!researchCurrent(ctx)||button.disabled)return;
      const controls=['apply','dismiss','repreview'].map(s=>$('#research-'+s));controls.forEach(b=>b.disabled=true);
      const data={proposal_version:r.proposal_version,proposal_digest:r.proposal_digest,...(action==='apply'?{target_version:r.target_version,before_hash:r.before_hash,after_hash:r.after_hash}:{})};
      try{await researchWrite(ctx,'research/proposals/'+encodeURIComponent(id)+'/'+action,data);if(researchCurrent(ctx))await openResearch(ctx.kind,ctx.id,ctx.back,'proposals');}
      catch(e){if(researchCurrent(ctx)){toast(e.message+' Refresh the preview before any further review action.');$('#research-repreview').disabled=false;}}
    };
  }catch(e){if(researchCurrent(ctx))toast(e.message);}
}

initialize();
