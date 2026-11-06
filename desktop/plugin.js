import {
  host,
  useValue,
  gatewayActivationEpoch,
  useGatewayActivationEpoch,
  PANES_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  PALETTE_AREA,
} from "@hermes/plugin-sdk";
import { createElement as h, useState, useEffect, useRef } from "react";

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
export function routeIdentity() {
  return JSON.stringify([
    host.state.connectionId.get(),
    host.state.profile.get(),
    gatewayActivationEpoch(),
  ]);
}
export function createRouteClient(ctx, identity) {
  let alive = true;
  const current = () =>
    alive &&
    identity === routeIdentity() &&
    host.state.gateway.get() === "open";
  return {
    current,
    dispose() {
      alive = false;
    },
    activate() {
      alive = true;
    },
    async request(path, options) {
      if (!current())
        throw new Error(
          "Connection or profile changed. Reload before continuing.",
        );
      const result = await ctx.rest(path, options);
      if (!current())
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
.hermes-crm-native{height:100%;overflow:auto;container-type:inline-size;background:var(--ui-bg-editor);color:var(--ui-text-primary);font:13px/1.5 system-ui,sans-serif}
.hermes-crm-native *{box-sizing:border-box}.hermes-crm-native .hc-wrap{max-width:1500px;margin:auto;padding:28px}
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
@container(max-width:850px){.hermes-crm-native .hc-grid{grid-template-columns:1fr 1fr}.hermes-crm-native .hc-two{grid-template-columns:1fr}.hermes-crm-native .hc-wrap{padding:18px}}
@container(max-width:480px){.hermes-crm-native .hc-grid,.hermes-crm-native .hc-fields{grid-template-columns:1fr}.hermes-crm-native .hc-bar-row{grid-template-columns:85px 1fr 70px}.hermes-crm-native h1{font-size:24px}}
`;

function Shell({ children }) {
  return h(
    "section",
    { className: "hermes-crm-native", "aria-label": "Hermes CRM" },
    h("style", null, CSS),
    h("div", { className: "hc-wrap" }, children),
  );
}
export function CRMRoot({ ctx }) {
  const profile = useValue(host.state.profile);
  const connection = useValue(host.state.connectionId);
  const gateway = useValue(host.state.gateway);
  const epoch = useGatewayActivationEpoch();
  const identity = JSON.stringify([connection, profile, epoch]);
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
  // Keying the entire workspace prevents even one render of previous-profile records/forms.
  return h(Workspace, { key: identity, ctx, identity, profile, connection });
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
function Workspace({ ctx, identity, profile, connection }) {
  const clientRef = useRef(null);
  if (!clientRef.current) clientRef.current = createRouteClient(ctx, identity);
  const client = clientRef.current;
  const [page, setPage] = useState("overview");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState("open");
  const [editor, setEditor] = useState(null);
  const [detail, setDetail] = useState(null);
  const [notice, setNotice] = useState("");
  const [demoConfirm, setDemoConfirm] = useState(null);
  const [searchResult, setSearchResult] = useState(null);
  const serial = useRef(0);
  const mutationLock = useRef(false);
  const viewRequest = useRef(0);
  async function refresh() {
    const ticket = ++serial.current;
    setLoading(true);
    try {
      const snapshot = await client.request("/snapshot");
      if (client.current() && ticket === serial.current) {
        setData(snapshot);
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
    setSearchResult(null);
    if (!data || !["contacts", "pipeline", "tasks"].includes(page)) return;
    const kind = page === "pipeline" ? "deals" : page;
    const params = new URLSearchParams({
      workspace_token: data.meta.workspace_token,
    });
    if (query) params.set("q", query);
    if (kind === "deals" && stage) params.set("stage", stage);
    if (kind === "tasks" && status !== "all") params.set("status", status);
    const stop = ctx.setTimeout(async () => {
      try {
        const rows = await client.request(`/${kind}?${params}`);
        if (live && client.current())
          setSearchResult({
            key: JSON.stringify([
              page,
              query,
              stage,
              status,
              data?.meta.workspace_token,
            ]),
            rows,
          });
      } catch (e) {
        if (live && client.current()) setError(e.message);
      }
    }, 200);
    return () => {
      live = false;
      stop();
    };
  }, [page, query, stage, status, data]);
  const searchReady =
    searchResult?.key ===
    JSON.stringify([page, query, stage, status, data?.meta.workspace_token]);
  const searchRows = (kind) => (searchReady ? searchResult.rows : []);
  function navigate(next, selectedStage = "") {
    viewRequest.current++;
    setPage(next);
    setQuery("");
    setStage(selectedStage);
    setDetail(null);
    setEditor(null);
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
    try {
      const row = await client.request(
        `/${kind}/${encodeURIComponent(id)}?${new URLSearchParams({ workspace_token: workspaceToken })}`,
      );
      if (client.current() && viewTicket === viewRequest.current)
        setDetail({ kind, row, workspaceToken });
    } catch (e) {
      if (client.current() && viewTicket === viewRequest.current)
        setError(e.message);
    }
  }
  function edit(kind, row = null, workspaceToken = data.meta.workspace_token) {
    viewRequest.current++;
    setEditor({
      kind,
      row,
      key: crypto.randomUUID(),
      workspaceToken,
    });
    setDetail(null);
  }
  const visible = (rows, fields) =>
    rows.filter((row) =>
      fields.some((field) =>
        String(row[field] || "")
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    );
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
    activity: ["Activity", "A shared record of human and agent work."],
  }[page];
  const overview = data?.overview;
  const disabled = busy || loading || !data || !client.current();
  return h(
    Shell,
    null,
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
    error &&
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
        editor &&
          h(Editor, {
            key: editor.key,
            editor,
            data,
            busy: disabled,
            cancel: () => setEditor(null),
            save: (values) =>
              write(
                `/${editor.kind}${editor.row ? "/" + encodeURIComponent(editor.row.id) : ""}`,
                {
                  method: editor.row ? "PATCH" : "POST",
                  body: {
                    ...(editor.row
                      ? { data: { ...values, version: editor.row.version } }
                      : createPayload(values, editor.key)),
                    workspace_token: editor.workspaceToken,
                  },
                },
              ),
          }),
        detail &&
          detail.workspaceToken === data.meta.workspace_token &&
          h(
            "section",
            { className: "hc-editor" },
            h(
              "div",
              { className: "hc-row" },
              h("h2", null, "Record details"),
              h(
                "div",
                { className: "hc-actions" },
                button(
                  "Edit",
                  () =>
                    edit(
                      detail.kind,
                      detail.row.contact || detail.row,
                      detail.workspaceToken,
                    ),
                  { disabled },
                ),
                button("Close", () => setDetail(null)),
              ),
            ),
            h(Detail, { detail }),
          ),
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
            h(
              "div",
              { className: "hc-two" },
              h(
                "section",
                { className: "hc-card" },
                h(
                  "div",
                  { className: "hc-row" },
                  h("h2", null, "Pipeline by stage"),
                  badge(`${money(overview.won_value)} won`),
                ),
                overview.stages.map((item) =>
                  button(
                    h(
                      "div",
                      { className: "hc-bar-row" },
                      h("span", null, `${label(item.stage)} (${item.count})`),
                      h(
                        "div",
                        { className: "hc-track" },
                        h("div", {
                          className: "hc-fill",
                          style: {
                            width: `${Math.max(item.value ? 3 : 0, (item.value / Math.max(1, ...overview.stages.map((s) => s.value))) * 100)}%`,
                          },
                        }),
                      ),
                      h("span", null, money(item.value)),
                    ),
                    () => navigate("pipeline", item.stage),
                    {
                      style: {
                        width: "100%",
                        border: 0,
                        padding: 0,
                        background: "transparent",
                      },
                      key: item.stage,
                      "aria-label": `${label(item.stage)}: ${item.count} deals, ${money(item.value)}. View deals.`,
                    },
                  ),
                ),
              ),
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
                onChange: (e) => setQuery(e.target.value),
                placeholder: `Search ${page}…`,
                "aria-label": `Search ${page}`,
              }),
              page === "pipeline" &&
                h(
                  "select",
                  {
                    value: stage,
                    onChange: (e) => setStage(e.target.value),
                    "aria-label": "Deal stage",
                  },
                  h("option", { value: "" }, "All stages"),
                  STAGES.map((s) =>
                    h("option", { key: s, value: s }, label(s)),
                  ),
                ),
              page === "tasks" &&
                h(
                  "select",
                  {
                    value: status,
                    onChange: (e) => setStatus(e.target.value),
                    "aria-label": "Task status",
                  },
                  ["open", "done", "all"].map((s) =>
                    h("option", { key: s, value: s }, label(s)),
                  ),
                ),
            ),
            button(
              `+ ${page === "contacts" ? "Contact" : page === "pipeline" ? "Deal" : "Follow-up"}`,
              () => edit(page === "pipeline" ? "deals" : page),
              { className: "hc-primary", disabled },
            ),
          ),
        !searchReady &&
          ["contacts", "pipeline", "tasks"].includes(page) &&
          h("p", { role: "status" }, "Loading matching records…"),
        page === "contacts" &&
          searchReady &&
          h(
            "div",
            { className: "hc-list", style: { marginTop: 18 } },
            visible(searchRows("contacts"), ["name", "company", "email"]).length
              ? visible(searchRows("contacts"), [
                  "name",
                  "company",
                  "email",
                ]).map((c) =>
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
                      badge(c.lifecycle),
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
              const rows = visible(searchRows("deals"), [
                "title",
                "contact_name",
              ]).filter((d) => d.stage === s);
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
              visible(searchRows("tasks"), ["title", "contact_name"])
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
            !visible(searchRows("tasks"), ["title", "contact_name"]).filter(
              (t) => status === "all" || t.status === status,
            ).length &&
              h(Empty, null, "No matching follow-ups. You’re clear for now."),
          ),
        page === "activity" && h(Activity, { rows: data.activity }),
      ),
    h(
      "footer",
      { className: "hc-footer" },
      "Profile-local CRM · Desktop and agent tools share the same records · Refreshes every 30 seconds · Lists show up to 500 records. The active app profile controls this view, not a focused chat in another profile.",
    ),
  );
}

function Detail({ detail }) {
  const row = detail.row.contact || detail.row;
  return h(
    "div",
    null,
    h("h2", null, row.name || row.title),
    h("p", { className: "hc-muted" }, `ID: ${row.id} · Version ${row.version}`),
    Object.entries(row)
      .filter(
        ([key]) => !["id", "version", "name", "title", "notes"].includes(key),
      )
      .map(([key, value]) =>
        h(
          "p",
          { key },
          h("strong", null, `${label(key)}: `),
          value == null
            ? "Not set"
            : key === "value"
              ? money(value)
              : String(value),
        ),
      ),
    h("p", { className: "hc-details" }, row.notes || "No notes yet."),
    detail.kind === "contacts" &&
      h(
        "div",
        null,
        h("h3", null, "Related deals"),
        detail.row.deals.map((d) =>
          h(
            "p",
            { key: d.id },
            `${d.title} · ${money(d.value)} · ${label(d.stage)}`,
          ),
        ),
        h("h3", null, "Related follow-ups"),
        detail.row.tasks.map((t) =>
          h(
            "p",
            { key: t.id },
            `${t.title} · ${label(t.status)} · ${date(t.due_at)}`,
          ),
        ),
        h("h3", null, "Relationship activity"),
        h(Activity, { rows: detail.row.activity }),
      ),
  );
}

function Editor({ editor, data, busy, save, cancel }) {
  const { kind, row } = editor;
  const [values, setValues] = useState(() => {
    const keys =
      kind === "contacts"
        ? ["name", "email", "company", "title", "lifecycle", "notes"]
        : kind === "deals"
          ? [
              "title",
              "contact_id",
              "value",
              "stage",
              "probability",
              "close_date",
              "notes",
            ]
          : [
              "title",
              "contact_id",
              "deal_id",
              "due_at",
              "priority",
              "status",
              "notes",
            ];
    const defaults = {
      lifecycle: "lead",
      stage: "lead",
      probability: 10,
      priority: "normal",
      status: "open",
      value: 0,
    };
    return Object.fromEntries(
      keys.map((key) => [
        key,
        key === "value"
          ? String((row?.value || 0) / 100)
          : key === "due_at" && row?.due_at
            ? new Date(
                new Date(row.due_at).getTime() -
                  new Date(row.due_at).getTimezoneOffset() * 60000,
              )
                .toISOString()
                .slice(0, 16)
            : (row?.[key] ?? defaults[key] ?? ""),
      ]),
    );
  });
  const initialDueInput = useRef(values.due_at);
  const [validation, setValidation] = useState("");
  function update(key, value) {
    setValues((old) => ({
      ...old,
      [key]: value,
      ...(key === "stage"
        ? { probability: PROBABILITY[STAGES.indexOf(value)] }
        : {}),
    }));
  }
  const field = (key, title, type = "text", options = null) =>
    h(
      "label",
      { key, className: key === "notes" ? "hc-wide" : undefined },
      title,
      options
        ? h(
            "select",
            {
              value: values[key],
              onChange: (e) => update(key, e.target.value),
              required: key === "contact_id" && kind === "deals",
            },
            options.map(([value, text]) =>
              h("option", { key: value, value }, text),
            ),
          )
        : h(key === "notes" ? "textarea" : "input", {
            type: key === "notes" ? undefined : type,
            value: values[key],
            onChange: (e) => update(key, e.target.value),
            required:
              key === "name" ||
              key === "due_at" ||
              (key === "title" && kind !== "contacts"),
            autoFocus: key === (kind === "contacts" ? "name" : "title"),
            maxLength:
              key === "notes"
                ? 10000
                : key === "email"
                  ? 254
                  : key === "title"
                    ? kind === "contacts"
                      ? 160
                      : 200
                    : 160,
            min: type === "number" ? 0 : undefined,
            max:
              key === "probability"
                ? 100
                : key === "value"
                  ? 20000000
                  : undefined,
            step: key === "value" ? ".01" : type === "number" ? "1" : undefined,
          }),
    );
  async function submit(event) {
    event.preventDefault();
    setValidation("");
    const payload = { ...values };
    if (kind === "deals") {
      payload.value = Math.round(Number(payload.value) * 100);
      payload.probability = Number(payload.probability);
      payload.currency = "USD";
      payload.close_date ||= null;
    }
    if (kind === "tasks") {
      if (!payload.due_at || Number.isNaN(new Date(payload.due_at).getTime())) {
        setValidation("Choose a valid local due date and time.");
        return;
      }
      payload.due_at =
        row?.due_at && payload.due_at === initialDueInput.current
          ? row.due_at
          : new Date(payload.due_at).toISOString();
      payload.contact_id ||= null;
      payload.deal_id ||= null;
    }
    await save(payload);
  }
  const selectOptions = (items) => items.map((x) => [x, label(x)]);
  return h(
    "form",
    {
      className: "hc-editor",
      onSubmit: submit,
      "aria-label": `${row ? "Edit" : "Create"} ${kind}`,
    },
    h(
      "h2",
      null,
      `${row ? "Edit" : "New"} ${kind === "contacts" ? "contact" : kind === "deals" ? "deal" : "follow-up"}`,
    ),
    h(
      "fieldset",
      { disabled: busy, style: { border: 0, padding: 0, margin: 0 } },
      h(
        "div",
        { className: "hc-fields" },
        kind === "contacts"
          ? [
              field("name", "Full name"),
              field("email", "Email", "email"),
              field("company", "Company"),
              field("title", "Job title"),
              field(
                "lifecycle",
                "Lifecycle",
                "text",
                selectOptions(["lead", "customer", "partner"]),
              ),
            ]
          : [
              field("title", "Title"),
              field(
                "contact_id",
                kind === "deals" ? "Contact (required)" : "Contact (optional)",
                "text",
                [
                  ["", "Select a contact"],
                  ...data.contacts.map((c) => [
                    c.id,
                    `${c.name} · ${c.company || c.email || c.id.slice(0, 8)}`,
                  ]),
                ],
              ),
            ],
        kind === "deals" && [
          field("value", "Deal value (USD)", "number"),
          field("stage", "Stage", "text", selectOptions(STAGES)),
          field("probability", "Probability (%)", "number"),
          field("close_date", "Expected close", "date"),
        ],
        kind === "tasks" && [
          field("deal_id", "Deal (optional)", "text", [
            ["", "No deal"],
            ...data.deals
              .filter(
                (d) => !values.contact_id || d.contact_id === values.contact_id,
              )
              .map((d) => [d.id, d.title]),
          ]),
          field(
            "due_at",
            "Due date and time (your local timezone)",
            "datetime-local",
          ),
          field(
            "priority",
            "Priority",
            "text",
            selectOptions(["normal", "high"]),
          ),
          field("status", "Status", "text", selectOptions(["open", "done"])),
        ],
        field("notes", "Notes"),
      ),
      validation && h("p", { role: "alert" }, validation),
      h(
        "div",
        { className: "hc-actions", style: { marginTop: 18 } },
        h(
          "button",
          { type: "submit", className: "hc-primary" },
          busy ? "Saving…" : "Save record",
        ),
        button("Cancel", cancel),
      ),
    ),
  );
}

export default {
  id: "hermes-crm",
  name: "Hermes CRM",
  defaultEnabled: false,
  register(ctx) {
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
