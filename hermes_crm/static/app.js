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
const stages = ["lead", "qualified", "proposal", "negotiation", "won", "lost"];
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
  return `<div class="page-head"><div><div class="eyebrow">YOUR RELATIONSHIP WORKSPACE</div><h1>${title}</h1><div class="subtitle">${subtitle}</div></div><div class="buttons">${actions}</div></div>`;
}
function createButton(type) {
  return `<button class="button primary" data-action="new-${type}"><span aria-hidden="true">＋</span> Add ${type}</button>`;
}
function contactTable(rows) {
  return rows.length
    ? `<div class="table-scroll"><table><thead><tr><th scope="col">Name</th><th scope="col">Company</th><th scope="col">Lifecycle</th><th scope="col">Added</th></tr></thead><tbody>${rows.map((c) => `<tr><td><div class="person"><span class="avatar" aria-hidden="true">${esc(initials(c.name))}</span><div><button class="name-button" data-action="contact" data-id="${esc(c.id)}">${esc(c.name)}</button><small>${esc(c.email || "No email added")}</small></div></div></td><td>${esc(c.company || "—")}</td><td>${badge(c.lifecycle)}</td><td>${date(c.created_at)}</td></tr>`).join("")}</tbody></table></div>`
    : empty("No contacts found. Add a contact to get started.");
}
function taskRows(rows) {
  return rows.length
    ? rows
        .map((t) => {
          const overdue =
            t.status !== "done" && t.due_at && new Date(t.due_at) < new Date();
          return `<div class="task-row"><button class="check" data-action="toggle-task" data-id="${esc(t.id)}" aria-label="${t.status === "done" ? "Reopen" : "Complete"} ${esc(t.title)}">${t.status === "done" ? "✓" : ""}</button><div class="task-copy"><button data-action="task" data-id="${esc(t.id)}">${esc(t.title)}</button><div class="task-meta">${esc(t.contact_name || "Workspace task")}${t.priority === "high" ? " · High priority" : ""}</div></div><span class="due ${overdue ? "overdue" : ""}">${t.status === "done" ? "Done" : date(t.due_at)}</span></div>`;
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
async function render() {
  // Only the latest render may publish markup or replace record caches.
  const token = ++state.render;
  const root = $("#content");
  root.innerHTML = '<div class="loading">Loading your workspace…</div>';
  $("#crumb").textContent = label(state.page);
  document.querySelectorAll("nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.page === state.page);
    if (a.dataset.page === state.page) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  try {
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
      const ps = list(o.stages).filter((s) => s.stage !== "lost");
      const max = Math.max(...ps.map((s) => s.value), 1);
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
          )}</div><div class="grid"><section class="card"><div class="card-head"><div><h2>Sales pipeline</h2><div class="subtitle">A little momentum at every stage.</div></div><a class="text-link" href="#deals">View deals ↗</a></div><div class="pipeline">${ps.map((s) => `<div class="pipeline-row"><button data-action="stage" data-stage="${esc(s.stage)}">${label(s.stage)} ↗</button><div class="track" aria-hidden="true"><div class="bar" style="width:${Math.round((s.value / max) * 100)}%"></div></div><div class="pipeline-value">${money(s.value)}<small>${s.count} ${s.count === 1 ? "deal" : "deals"}</small></div></div>`).join("")}</div><div class="pipeline-summary"><span>Weighted pipeline <strong>${money(o.weighted_value)}</strong></span><span>${o.open_deals} open opportunities</span></div></section><section class="card"><div class="card-head"><div><h2>Your next steps</h2><div class="subtitle">${o.open_tasks} open tasks · ${o.overdue_tasks} overdue</div></div><a href="#tasks" class="text-link">View all ↗</a></div>${taskRows(state.tasks.filter((t) => t.status !== "done").slice(0, 4))}</section></div><div class="grid"><section class="card"><div class="card-head"><div><h2>People in your orbit</h2><div class="subtitle">Every great opportunity starts with a connection.</div></div><a href="#contacts" class="text-link">All contacts ↗</a></div>${contactTable(state.contacts.slice(0, 5))}</section><section class="card"><div class="card-head"><h2>Recent activity</h2><a href="#activity" class="text-link">View all ↗</a></div>${activityRows(list(o.activity).slice(0, 5))}</section></div>`;
    } else if (state.page === "contacts") {
      const contacts = await api(
        "contacts?q=" + encodeURIComponent(state.query),
      );
      if (token !== state.render) return;
      state.contacts = list(contacts);
      html =
        head(
          "Contacts",
          "Build stronger relationships, one conversation at a time.",
          createButton("contact"),
        ) +
        `<section class="card"><div class="toolbar"><input class="search" id="search" type="search" aria-label="Search contacts" placeholder="Search names, companies, or emails…" value="${esc(state.query)}"><span class="subtitle">${state.contacts.length} contacts</span></div>${contactTable(state.contacts)}</section>`;
    } else if (state.page === "deals") {
      const deals = await api(
        "deals?q=" +
          encodeURIComponent(state.query) +
          (state.stage ? "&stage=" + encodeURIComponent(state.stage) : ""),
      );
      if (token !== state.render) return;
      state.deals = list(deals);
      html =
        head(
          "Deals",
          "Turn promising conversations into lasting partnerships.",
          createButton("deal"),
        ) +
        `<div class="toolbar" style="padding:0 0 20px;border:0"><input class="search" id="search" type="search" aria-label="Search deals" placeholder="Search opportunities…" value="${esc(state.query)}"><select id="stage-filter" aria-label="Filter by stage"><option value="">All stages</option>${stages.map((s) => `<option value="${s}" ${state.stage === s ? "selected" : ""}>${label(s)}</option>`).join("")}</select></div><div class="board" ${state.stage ? 'style="grid-template-columns:minmax(240px,420px)"' : ""}>${(state.stage
          ? [state.stage]
          : stages
        )
          .map((s) => {
            const ds = state.deals.filter((d) => d.stage === s);
            return `<section class="column"><div class="column-head"><span>${label(s)}</span><span class="badge ${s}">${ds.length}</span></div><div class="column-total">${money(ds.reduce((n, d) => n + d.value, 0))} total value</div>${dealCards(ds) || empty("No deals at this stage.")}</section>`;
          })
          .join("")}</div>`;
    } else if (state.page === "tasks") {
      // Filter on the server before its result limit, so completed history cannot hide open work.
      const tasks = await api(
        "tasks" + (state.taskFilter ? "?status=" + encodeURIComponent(state.taskFilter) : ""),
      );
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
        `<section class="card"><div class="toolbar"><h2>${rows.length} ${state.taskFilter || "total"} tasks</h2><select id="task-filter" aria-label="Task status">${[
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
      root.innerHTML = `<div class="error" role="alert">${esc(e.message)}</div><button class="button" data-action="retry">Try again</button>`;
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
  if (state.page !== "deals") state.stage = "";
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
    let contacts = [],
      deals = [];
    if (type !== "contact") {
      [contacts, deals] = await Promise.all([
        api("contacts"),
        type === "task" ? api("deals") : Promise.resolve([]),
      ]);
      contacts = list(contacts);
      deals = list(deals);
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
        `<div class="form-row">${field("title", "Job title", record.title)}${select("lifecycle", "Lifecycle", ["lead", "customer", "partner"], record.lifecycle || "lead")}</div>`;
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
        `<div class="form-row">${field("value", "Value (USD) *", record.value == null ? "" : (record.value / 100).toFixed(2), "number", 'required min="0" step="0.01"')}${select("stage", "Stage", stages, record.stage || "lead")}</div><div class="form-row">${field("probability", "Probability (%) *", record.probability ?? 20, "number", 'required min="0" max="100" step="1"')}${field("close_date", "Expected close date", record.close_date, "date")}</div>`;
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
    const result = await api("contacts/" + id);
    if (requestEpoch !== modalEpoch) return;
    const c = result.contact;
    showModal(
      modalHead(c.name) +
        `<div class="detail-body"><div class="person"><span class="avatar">${esc(initials(c.name))}</span><div>${esc(c.title || "Contact")}${c.company ? " at " + esc(c.company) : ""}<div>${badge(c.lifecycle)}</div></div></div><dl class="detail-meta"><div><dt>Email</dt><dd>${esc(c.email || "Not added")}</dd></div><div><dt>Created</dt><dd>${date(c.created_at)}</dd></div></dl>${c.notes ? `<div class="notes">${esc(c.notes)}</div>` : ""}<h3>Deals</h3>${dealCards(list(result.deals)) || empty("No linked deals.")}<h3>Tasks</h3>${taskRows(list(result.tasks))}<h3>Activity</h3>${activityRows(list(result.activity).slice(0, 8))}</div><div class="form-actions"><button class="button" data-action="close">Close</button><button class="button primary" id="edit-contact">Edit contact</button></div>`,
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
  if (a === "stage") {
    state.stage = b.dataset.stage;
    if (location.hash === "#deals") {
      state.page = "deals";
      render();
    } else location.hash = "deals";
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id !== "search") return;
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
  if (e.target.id === "stage-filter") {
    state.stage = e.target.value;
    render();
  }
  if (e.target.id === "task-filter") {
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
});
window.addEventListener("hashchange", route);
async function initialize() {
  try {
    const meta = await api("meta");
    $("#profile").textContent = meta.profile || "default";
    document
      .querySelectorAll(".workspace-name")
      .forEach(
        (n) => (n.textContent = meta.demo ? "Demo workspace" : "CRM workspace"),
      );
    document
      .querySelectorAll(".workspace-description")
      .forEach(
        (n) =>
          (n.textContent = meta.demo ? "Sample data only" : "Local-first CRM"),
      );
    $(".demo-label").hidden = !meta.demo;
  } catch (e) {
    toast("Workspace metadata is unavailable. " + e.message);
  }
  route();
}
initialize();
