import { createElement as h, useEffect, useRef, useState } from "react";

// Unknown writes survive remounts and can only be explicitly retried verbatim.
const reportAttempts = new WeakMap();
export function reportSession(client, workspaceToken, isCurrent = () => true, operationStore) {
  let alive = true;
  const attempts = operationStore || reportAttempts.get(client) || new Map();
  reportAttempts.set(client, attempts);
  const current = () => alive && client.current() && isCurrent();
  const query = new URLSearchParams({ workspace_token: workspaceToken });
  return {
    current, close() { alive = false; }, pending: () => attempts.get(workspaceToken),
    async read(path) { if (!current()) return null; const value = await client.request(`${path}${path.includes('?') ? '&' : '?'}${query}`); return current() ? value : null; },
    async run(definition, evaluatedAt, offset = 0) {
      if (!current()) return null;
      const value = await client.request('/analytics/run', { method: 'POST', body: { workspace_token: workspaceToken, definition, limit: 100, offset, ...(evaluatedAt ? { evaluated_at: evaluatedAt } : {}) } });
      return current() ? value : null;
    },
    async write(path, body, retry = false, method = 'POST') {
      if (!current()) return null;
      let attempt = attempts.get(workspaceToken);
      if (attempt && (!retry || attempt.state !== 'unknown')) return null;
      if (!attempt) { attempt = { path, method, bodyJSON: JSON.stringify({ ...body, workspace_token: workspaceToken, idempotency_key: crypto.randomUUID() }), state: 'running' }; attempts.set(workspaceToken, attempt); }
      attempt.state = 'running';
      try {
        const result = await client.request(attempt.path, { method: attempt.method, body: JSON.parse(attempt.bodyJSON) });
        if (!result || typeof result.id !== 'string' || !Number.isSafeInteger(result.version) || result.version < 1) throw new Error('Unconfirmed write response');
        attempts.delete(workspaceToken);
        return current() ? result : null;
      } catch (error) {
        if ([400, 404, 409, 422].includes(Number(error.status ?? error.statusCode))) {
          attempts.delete(workspaceToken);
          throw new Error('Write rejected. Refresh saved definitions, review the current version, then preview your changes again.');
        }
        attempt.state = 'unknown';
        throw new Error('Write outcome unknown or conflicted. Refresh to inspect current versions. Retry sends only the original request with the same key.');
      }
    },
  };
}
export function reportText(value) { return value == null ? 'Not set' : typeof value === 'object' ? JSON.stringify(value) : String(value); }
export function reportDefault(entity, fields) {
  return { schema_version: 1, entity, columns: fields.slice(0, 5).map(field => field.key), filter: null, sort: [], timezone: 'UTC' };
}
export function reportChartModel(result, kind) {
  const groups = result.groups || [];
  const valid = groups.every(group => typeof group.value === 'number' && Number.isFinite(group.value) && group.value >= 0);
  const total = groups.reduce((sum, group) => sum + (Number(group.value) || 0), 0);
  return { groups, total, graphical: valid && (kind !== 'donut' || (!result.truncated && total > 0)), max: Math.max(1, ...groups.map(group => Math.abs(Number(group.value) || 0))) };
}
const reportColors = ['var(--hc-link)', 'var(--hc-chart-purple, #A58AE0)', 'var(--hc-chart-teal, #43AA99)', 'var(--hc-chart-amber, #CF974B)', 'var(--hc-chart-rose, #CE7BA2)', 'var(--hc-secondary)'];
// Layout is owned by the shared Workbench stylesheet.
export const reportCSS = '';
function ReportSelect({ label, value, options, onChange, disabled }) {
  return h('label', { className: 'hc-report-field' }, label, h('select', { value, disabled, onChange: event => onChange(event.target.value) }, options.map(option => h('option', { key: option.value, value: option.value }, option.label))));
}
export function reportFilterValue(field, raw) {
  if (['integer', 'number'].includes(field?.type)) return raw === '' ? '' : Number(raw);
  if (field?.type === 'boolean') return raw === 'true' ? true : raw === 'false' ? false : raw;
  return raw;
}
export function reportDisplayValue(result, field, value) {
  const labels = result.choice_labels?.[field] || {};
  return Array.isArray(value) ? value.map(item => labels[item] || item).join(', ') : labels[value] || reportText(value);
}
function ReportFilter({ node, fields, onChange, disabled, depth = 0 }) {
  const group = node.all ? 'all' : node.any ? 'any' : null;
  if (group) return h('fieldset', { className: 'hc-report-filter', disabled },
    h('legend', null, group === 'all' ? 'ALL conditions must match' : 'ANY condition may match'),
    node[group].map((child, index) => h('div', { key: index, className: 'hc-report-condition' }, h(ReportFilter, { node: child, fields, disabled, depth: depth + 1, onChange: next => onChange({ [group]: node[group].map((old, i) => i === index ? next : old) }) }),
      h('button', { type: 'button', onClick: () => onChange({ [group]: node[group].filter((_, i) => i !== index) }) }, 'Remove condition'))),
    h('div', { className: 'hc-report-toolbar' }, h('button', { type: 'button', disabled: !fields.length, onClick: () => onChange({ [group]: [...node[group], { field: fields[0].key, op: fields[0].operators[0], value: fields[0].choices?.[0] ?? '' }] }) }, 'Add condition'),
      depth < 2 && h('button', { type: 'button', onClick: () => onChange({ [group]: [...node[group], { [group === 'all' ? 'any' : 'all']: [] }] }) }, group === 'all' ? 'Add ANY group' : 'Add ALL group')));
  const field = fields.find(item => item.key === node.field) || fields[0];
  const operators = field?.operators || ['eq'];
  const list = ['in', 'not_in', 'between', 'has_any', 'has_all', 'has_none'].includes(node.op);
  const initial = (op, selected) => ['is_null', 'is_not_null'].includes(op) ? null : op === 'is_empty' ? true : ['in', 'not_in', 'between', 'has_any', 'has_all', 'has_none'].includes(op) ? [] : (selected?.type === 'boolean' ? false : selected?.choices?.[0] ?? '');
  const convert = raw => reportFilterValue(field, raw);
  return h('div', { className: 'hc-report-toolbar' },
    h(ReportSelect, { label: 'Field', value: node.field, options: fields.map(item => ({ value: item.key, label: item.label })), disabled, onChange: value => { const selected = fields.find(item => item.key === value), op = selected.operators[0]; onChange({ field: value, op, value: initial(op, selected) }); } }),
    h(ReportSelect, { label: 'Operator', value: node.op, options: operators.map(value => ({ value, label: value.replaceAll('_', ' ') })), disabled, onChange: op => onChange({ ...node, op, value: initial(op, field) }) }),
    node.op === 'is_empty' ? h(ReportSelect, { label: 'Empty?', value: String(node.value), options: [{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }], disabled, onChange: value => onChange({ ...node, value: value === 'true' }) }) :
    !['is_null', 'is_not_null'].includes(node.op) && (field?.type === 'boolean' && !list ? h(ReportSelect, { label: 'Value', value: String(node.value), options: [{ value: 'true', label: 'True' }, { value: 'false', label: 'False' }], disabled, onChange: value => onChange({ ...node, value: value === 'true' }) }) : field?.choices && !list ? h(ReportSelect, { label: 'Value', value: node.value, options: field.choices.map(value => ({ value, label: field.choice_labels?.[value] || value })), disabled, onChange: value => onChange({ ...node, value }) }) :
      h('label', null, list ? 'Values (comma separated)' : 'Value', h('input', { disabled, type: ['integer', 'number'].includes(field?.type) && !list ? 'number' : 'text', value: Array.isArray(node.value) ? node.value.join(', ') : node.value ?? '', placeholder: ['date','datetime'].includes(field?.type) ? 'ISO date/time (UTC)' : field?.choices?.join(', ') || '', onChange: event => { const raw = event.target.value; onChange({ ...node, value: list ? raw.split(',').map(value => convert(value.trim())) : convert(raw) }); } }))),
    field?.semantic_notes && h('small', null, `${field.archived ? 'Archived field. ' : ''}${field.semantic_notes}`));
}
export function reportCleanFilter(node) {
  if (!node) return null;
  const group = node.all ? 'all' : node.any ? 'any' : null;
  if (!group) return node;
  const children = node[group].map(reportCleanFilter).filter(Boolean);
  return children.length ? { [group]: children } : null;
}
export function reportFields(catalog, entity) {
  return Object.entries(catalog?.entities?.[entity]?.fields || {}).map(([key, value]) => ({ key, ...value, label: `${value.label || key}${value.archived ? ' (archived)' : ''}` }));
}

export function reportLineModel(groups) {
  const points = [], omitted = [];
  for (const group of groups) {
    const timestamp = typeof group.key === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(group.key) ? Date.parse(`${group.key}T00:00:00Z`) : NaN;
    if (!Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== group.key || typeof group.value !== 'number' || !Number.isFinite(group.value)) omitted.push(group);
    else points.push({ group, timestamp });
  }
  points.sort((a, b) => a.timestamp - b.timestamp);
  const first = points[0]?.timestamp || 0, last = points.at(-1)?.timestamp || 0;
  const low = Math.min(0, ...points.map(point => point.group.value));
  const high = Math.max(0, ...points.map(point => point.group.value));
  return { omitted, first, last, points: points.map(point => ({ ...point, x: last === first ? 150 : 15 + (point.timestamp - first) / (last - first) * 270, y: 80 - (point.group.value - low) / (high - low || 1) * 65 })) };
}
export function reportSectorPath(start, fraction) {
  // Two arcs per edge also render a full-circle single-category distribution.
  const angle = turn => (turn * 2 * Math.PI) - Math.PI / 2;
  const point = (turn, radius) => `${70 + Math.cos(angle(turn)) * radius},${70 + Math.sin(angle(turn)) * radius}`;
  const middle = start + fraction / 2, end = start + fraction;
  return `M ${point(start, 60)} A 60 60 0 0 1 ${point(middle, 60)} A 60 60 0 0 1 ${point(end, 60)} L ${point(end, 34)} A 34 34 0 0 0 ${point(middle, 34)} A 34 34 0 0 0 ${point(start, 34)} Z`;
}
function reportChartControl(group, result, onDrill, disabled) {
  const inactive = disabled || !group.detail_definition;
  const label = `${reportDisplayValue(result, result.definition?.group_by?.field, group.key)}: ${reportText(group.value)} ${reportText(result.metric_unit || '')} (${group.count} records). View contributing records.`;
  const activate = () => { if (!inactive) onDrill(group.detail_definition, group.evaluated_at || result.evaluated_at); };
  return { role: 'button', tabIndex: inactive ? -1 : 0, 'aria-disabled': !!inactive, 'aria-label': label, className: 'hc-report-plot-control', onClick: activate, onKeyDown: event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); activate(); } } };
}

export function ReportResult({ result, kind = 'table', onDrill, disabled, onOpenRecord, onPage }) {
  if (!result) return null;
  const model = reportChartModel(result, kind);
  const temporalLine = ['day'].includes(result.definition?.group_by?.interval);
  const columns = result.definition?.columns || Object.keys(result.items?.[0] || {});
  const caption = h('p', { className: 'hc-report-muted' }, `LIVE query • evaluated ${reportText(result.evaluated_at)} • UTC • ${reportText(result.metric_unit || 'field units shown in column headings')}. Last logged contact is self-reported CRM activity, not Gmail.`, result.truncated ? ' Group limit reached: partial results, not a complete distribution.' : '');
  if (!result.groups) return h('div', { className: 'hc-report-result' }, caption, kind === 'metric' && h('button', { className: 'hc-report-metric', disabled: disabled || !result.detail_definition, onClick: () => onDrill(result.detail_definition, result.evaluated_at) }, reportText(result.metric ?? result.total)),
    h('p', null, `${result.total ?? result.items?.length ?? 0} matching records; showing ${result.items?.length ?? 0} from offset ${result.offset || 0}.`),
    onPage && h('div', { className: 'hc-report-toolbar' }, h('button', { disabled: disabled || !(result.offset > 0), onClick: () => onPage(Math.max(0, result.offset - (result.limit || 100))) }, 'Previous records'), h('button', { disabled: disabled || (result.offset || 0) + (result.items?.length || 0) >= result.total, onClick: () => onPage((result.offset || 0) + (result.limit || 100)) }, 'Next records')),
    !(result.items || []).length && h('p', { className: 'hc-report-empty', role: 'status' }, 'No matching records. Adjust the report conditions and preview again.'),
    h('div', { className: 'hc-report-scroll', role: 'region', 'aria-label': 'Report records', tabIndex: 0 }, h('table', { 'aria-label': 'Report results' }, h('thead', null, h('tr', null, columns.map(column => h('th', { key: column, scope: 'col' }, `${result.field_labels?.[column] || column}${result.units?.[column] ? ` (${result.units[column]})` : ''}`)), onOpenRecord && h('th', { scope: 'col' }, 'Actions'))),
      h('tbody', null, (result.items || []).map((item, index) => h('tr', { key: item.id || index }, columns.map(column => h('td', { key: column }, reportDisplayValue(result, column, item[column]))), onOpenRecord && item.id && h('td', null, h('button', { disabled, onClick: () => onOpenRecord(result.definition.entity, item.id) }, 'Open record'))))))));
  let cursor = 0;
  const sectors = model.groups.map(group => { const start = cursor, fraction = group.value / model.total; cursor += fraction; return { group, start, fraction }; });
  const line = reportLineModel(model.groups);
  return h('div', { className: 'hc-report-result' }, caption, h('p', null, `${result.total_groups ?? model.groups.length} groups • ${result.total ?? 0} matching records`),
    kind === 'metric' && h('button', { className: 'hc-report-metric', disabled: disabled || !result.detail_definition, onClick: () => onDrill(result.detail_definition, result.evaluated_at) }, reportText(result.metric)),
    !model.groups.length && h('p', { className: 'hc-report-empty', role: 'status' }, 'No matching groups.'),
    kind === 'donut' && model.graphical && h('svg', { viewBox: '0 0 140 140', role: 'group', 'aria-label': 'Interactive distribution. Focus a sector or use the exact-value buttons below.', className: 'hc-report-donut' }, sectors.filter(sector => sector.fraction > 0).map((sector, index) => {
      const controls = reportChartControl(sector.group, result, onDrill, disabled);
      return h('path', { key: index, d: reportSectorPath(sector.start, sector.fraction), fill: reportColors[index % reportColors.length], stroke: 'var(--hc-panel)', strokeWidth: 1, ...controls }, h('title', null, controls['aria-label']));
    })),
    kind === 'donut' && !model.graphical && h('p', null, 'Distribution chart unavailable for partial, negative, null, or all-zero values. Exact values below.'),
    kind === 'line' && !temporalLine && h('p', null, 'Line chart requires UTC day grouping. Exact categorical values below.'),
    kind === 'line' && temporalLine && h('div', null,
      h('p', { className: 'hc-report-muted' }, `Plotted ${line.points.length} of ${model.groups.length} returned buckets, ordered by UTC date with proportional day spacing. ${line.omitted.length} null/invalid-date or non-numeric buckets remain in the exact list below. Missing days are not treated as zero; connecting lines are guides, not observations.${result.truncated ? ' Truncated groups: chart covers only the returned dates.' : ''}`),
      line.points.length > 0 && h('svg', { viewBox: '0 0 300 110', role: 'group', 'aria-label': 'Interactive UTC daily trend. Focus a point for its exact value and contributing records.', className: 'hc-report-line' },
        h('polyline', { fill: 'none', stroke: 'var(--hc-link)', strokeWidth: 2, 'aria-hidden': true, points: line.points.map(point => `${point.x},${point.y}`).join(' ') }),
        line.points.map((point, index) => { const controls = reportChartControl(point.group, result, onDrill, disabled); return h('circle', { key: index, cx: point.x, cy: point.y, r: 5, fill: 'var(--hc-link)', ...controls }, h('title', null, controls['aria-label'])); }),
        h('text', { x: 15, y: 104, fontSize: 9, fill: 'currentColor' }, line.points[0].group.key),
        line.points.length > 1 && h('text', { x: 285, y: 104, textAnchor: 'end', fontSize: 9, fill: 'currentColor' }, line.points.at(-1).group.key))),
    h('ul', { className: 'hc-report-chart-list' }, model.groups.map((group, index) => h('li', { key: index }, h('button', { type: 'button', disabled: disabled || !group.detail_definition, onClick: () => onDrill(group.detail_definition, group.evaluated_at || result.evaluated_at) }, `${reportDisplayValue(result, result.definition?.group_by?.field, group.key)}: ${reportText(group.value)} (${group.count} records)`, kind === 'bar' && model.graphical && h('span', { 'aria-hidden': true, className: 'hc-report-bar', style: { width: `${Math.max(0, group.value / model.max * 100)}%` } }))))));
}
function ReportEditor({ catalog, value, onChange, disabled }) {
  const fields = reportFields(catalog, value.entity);
  const options = fields.map(field => ({ value: field.key, label: field.label }));
  const patch = next => onChange({ ...value, ...next });
  return h('fieldset', { disabled, className: 'hc-report-form' }, h('legend', null, 'Report definition'),
    h('p', { className: 'hc-report-muted' }, 'Choose the records, columns and conditions to include. Preview before saving a version.'),
    h(ReportSelect, { label: 'Records', value: value.entity, options: Object.entries(catalog.entities).map(([key, entry]) => ({ value: key, label: entry.label || key })), onChange: entity => onChange(reportDefault(entity, reportFields(catalog, entity))) }),
    h('fieldset', { className: 'hc-report-column-section' }, h('legend', null, 'Columns'), h('div', { className: 'hc-report-columns' }, fields.filter(field => field.selectable).map(field => h('label', { key: field.key }, h('input', { type: 'checkbox', checked: value.columns.includes(field.key), onChange: event => patch({ columns: event.target.checked ? [...value.columns, field.key] : value.columns.filter(key => key !== field.key) }) }), field.label)))),
    h(ReportFilter, { node: value.filter || { all: [] }, fields, disabled, onChange: filter => patch({ filter }) }),
    h('p', { className: 'hc-report-muted' }, 'Empty groups are omitted. No dashboard-wide filter is applied. Dates and day buckets use UTC.'),
    (value.sort || []).map((sort, index) => h('div', { className: 'hc-report-toolbar', key: index },
      h(ReportSelect, { label: `Sort ${index + 1}`, value: sort.field, options: options.filter(option => fields.find(field => field.key === option.value).sortable), onChange: field => patch({ sort: value.sort.map((item, i) => i === index ? { ...item, field } : item) }) }),
      h(ReportSelect, { label: 'Direction', value: sort.direction, options: [{ value: 'asc', label: 'Ascending' }, { value: 'desc', label: 'Descending' }], onChange: direction => patch({ sort: value.sort.map((item, i) => i === index ? { ...item, direction } : item) }) }),
      h('button', { type: 'button', onClick: () => patch({ sort: value.sort.filter((_, i) => i !== index) }) }, 'Remove sort'))),
    h('button', { type: 'button', disabled: value.sort.length >= 3, onClick: () => patch({ sort: [...value.sort, { field: fields.find(field => field.sortable).key, direction: 'asc' }] }) }, 'Add sort'),
    h(ReportSelect, { label: 'Group by', value: value.group_by?.field || '', options: [{ value: '', label: 'No grouping' }, ...options.filter(option => fields.find(field => field.key === option.value).groupable)], onChange: field => patch({ group_by: field ? { field, ...(['date', 'datetime'].includes(fields.find(item => item.key === field).type) ? { interval: 'day' } : {}) } : null, measure: field ? value.measure || { op: 'count' } : value.measure }) }),
    h(ReportSelect, { label: 'Measure', value: value.measure?.op || '', options: [{ value: '', label: 'Record table' }, ...catalog.measures.map(op => ({ value: op, label: op }))], onChange: op => patch({ measure: !op ? null : op === 'count' ? { op } : { op, field: fields.find(field => ['integer', 'number'].includes(field.type))?.key || '' }, ...(!op ? { group_by: null } : {}) }) }),
    value.measure && value.measure.op !== 'count' && h(ReportSelect, { label: 'Numeric field (unit shown in results)', value: value.measure.field, options: fields.filter(field => ['integer', 'number'].includes(field.type)).map(field => ({ value: field.key, label: `${field.label}${field.unit ? ` (${field.unit})` : ''}` })), onChange: field => patch({ measure: { ...value.measure, field } }) }),
    h('p', { className: 'hc-report-muted' }, 'Current linked deal stages are separate from contact type. Current won deals are not historical wins; expected close date is not an actual win date.'));
}
export function reportPreset(name) {
  const base = { schema_version: 1, entity: 'contacts', columns: ['id','name','contact_type','linked_stages','last_logged_contact_at','next_followup_at'], filter: { field: 'contact_type', op: 'eq', value: 'lead' }, sort: [{ field: 'name', direction: 'asc' }], timezone: 'UTC' };
  if (name === 'daily') return { ...base, columns: ['id','name','created_at'], sort: [], group_by: { field: 'created_at', interval: 'day' }, measure: { op: 'count' } };
  if (name === 'won') return { schema_version: 1, entity: 'deals', columns: ['id','title','contact_name','stage','value','expected_close_date'], filter: { field: 'stage_outcome', op: 'eq', value: 'won' }, sort: [], measure: { op: 'count' }, timezone: 'UTC' };
  return base;
}
const reportVisualizations = ['table', 'metric', 'bar', 'line', 'donut'].map(value => ({ value, label: value }));
export function reportCardPayload(card) { return { id: card.id, report_id: card.report_id, report_version: card.report_version, visualization: card.visualization, ...(card.title ? { title: card.title } : {}) }; }

export function FlexibleReports({ client, workspaceToken, routeKey, disabled = false, onOpenRecord, operationStore }) {
  const target = `${routeKey}|${workspaceToken}`;
  const renderToken = {}; const renderRef = useRef(renderToken); renderRef.current = renderToken;
  const latest = useRef({ target, disabled }); latest.current = { target, disabled };
  const browse = useRef({ offset: 0, includeArchived: false });
  const session = useRef(null), generation = useRef(0), lock = useRef(false);
  const [state, setState] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState(null), [preview, setPreview] = useState(null), [drill, setDrill] = useState(null), [runs, setRuns] = useState({});
  const valid = () => renderRef.current === renderToken && latest.current.target === target && !latest.current.disabled && client.current();
  async function refresh(own = session.current, page = browse.current) {
    const ticket = ++generation.current;
    const [catalog, reports, dashboard] = await Promise.all([own.read('/analytics/catalog'), own.read(`/analytics/reports?limit=50&offset=${page.offset}&include_archived=${page.includeArchived}`), own.read('/analytics/dashboard')]);
    if (!own.current() || ticket !== generation.current || !catalog || !reports || !dashboard) return;
    browse.current = page; setState({ target, catalog, reports, dashboard, page }); setRuns({});
  }
  useEffect(() => {
    const own = reportSession(client, workspaceToken, () => latest.current.target === target, operationStore); session.current = own;
    browse.current = { offset: 0, includeArchived: false };
    setState(null); setEditor(null); setPreview(null); setDrill(null); setError(''); setRuns({}); lock.current = false; setBusy(false);
    refresh(own).catch(() => { if (own.current()) setError('Could not load report catalog and saved dashboard. Refresh to try again.'); });
    return () => { own.close(); generation.current++; };
  }, [client, target, operationStore]);
  const visible = state?.target === target && client.current() ? state : null;
  const blocked = disabled || busy || !visible || !client.current();
  async function action(work) {
    if (!valid() || lock.current) return;
    lock.current = true; setBusy(true); setError(''); const own = session.current;
    try { await work(own); } catch (failure) { if (own.current()) setError(failure.message || 'Report request failed.'); }
    finally { if (own.current()) { lock.current = false; setBusy(false); } }
  }
  function edit(next) { if (!valid() || lock.current) return; generation.current++; setEditor(next); setPreview(null); setDrill(null); }
  function change(next) { if (editor !== latestEditor.current || !valid() || lock.current) return; edit(next); }
  const latestEditor = useRef(editor); latestEditor.current = editor;
  function openReport(record) { edit({ id: record.id, version: record.version, savedDefinition: JSON.stringify(record.definition), title: record.title, definition: record.definition, visualization: 'table' }); }
  function newReport(name) { edit({ title: name === 'daily' ? 'Leads created per UTC day' : name === 'won' ? 'Current closed won deals' : 'Leads and follow-ups', definition: reportPreset(name), visualization: name === 'daily' ? 'bar' : name === 'won' ? 'metric' : 'table' }); }
  async function drillDown(definition, evaluatedAt) {
    await action(async own => { const result = await own.run(definition, evaluatedAt); if (result) setDrill(result); });
  }
  async function runCard(card, offset = 0, evaluatedAt) {
    await action(async own => {
      const result = await client.request(`/analytics/reports/${encodeURIComponent(card.report_id)}/run`, { method: 'POST', body: { workspace_token: workspaceToken, expected_version: card.report_version, limit: 100, offset, ...(evaluatedAt ? { evaluated_at: evaluatedAt } : {}) } });
      if (own.current()) setRuns(old => ({ ...old, [card.id]: result }));
    });
  }
  async function setArchived(record) {
    await action(async own => {
      if (own.pending()) throw new Error('Resolve the pending write before archiving or restoring a report.');
      const operation = record.archived_at ? 'restore' : 'archive';
      const result = await own.write(`/analytics/reports/${encodeURIComponent(record.id)}/${operation}`, { expected_version: record.version });
      if (result) { if (latestEditor.current?.id === record.id) { setEditor(null); setPreview(null); } await refresh(own); }
    });
  }
  async function saveDashboard(cards) {
    if (!valid()) return;
    await action(async own => {
      if (own.pending()) throw new Error('Resolve the pending write before changing the dashboard.');
      const result = await own.write('/analytics/dashboard', { cards: cards.map(reportCardPayload), expected_version: visible.dashboard.version }, false, 'PUT');
      if (result) await refresh(own);
    });
  }
  return h('section', { className: 'hc-reports', 'aria-label': 'Custom reports and dashboard', 'aria-busy': busy },
    h('div', { className: 'hc-report-toolbar hc-report-header' }, h('h2', null, 'Your dashboard'), h('button', { className: 'hc-primary', disabled: blocked, onClick: () => newReport('leads') }, 'Build a report'),
      h('button', { disabled: disabled || busy || !client.current(), onClick: () => action(own => refresh(own)) }, 'Refresh saved definitions')),
    h('p', { className: 'hc-report-muted' }, 'Saved definitions are shared with agents. Cards pin a report version; results are live when you explicitly run them. No account access or email reads.'),
    error && h('p', { role: 'alert', className: 'hc-report-notice hc-report-error' }, error), !visible && !error && h('p', { role: 'status', className: 'hc-report-empty' }, 'Loading reports…'),
    visible && session.current?.pending() && h('div', { role: 'status', className: 'hc-report-notice' }, 'A write is unresolved. Inspect the refreshed saved list and dashboard before retrying.', h('button', { disabled: blocked || session.current.pending().state !== 'unknown', onClick: () => action(async own => { const result = await own.write('', {}, true); if (result) { setEditor(null); setPreview(null); await refresh(own); } }) }, 'Retry original write with same key')),
    visible && h('div', { className: 'hc-report-grid' }, visible.dashboard.cards.map((card, index) => h('article', { className: 'hc-report-card', key: card.id },
      h('h3', null, card.title || card.report?.title || 'Saved report'), h('p', { className: 'hc-report-muted' }, `Report version ${card.report_version} • ${card.reference_status || 'active'}`),
      h(ReportSelect, { label: 'Card visualization', value: card.visualization, options: reportVisualizations, disabled: blocked, onChange: visualization => saveDashboard(visible.dashboard.cards.map(item => item.id === card.id ? { ...item, visualization } : item)) }),
      h('div', { className: 'hc-report-toolbar' }, h('button', { className: 'hc-report-run', disabled: blocked || card.reference_status !== 'active', onClick: () => runCard(card) }, 'Run live'),
        h('button', { disabled: blocked || index === 0, onClick: () => { const cards = [...visible.dashboard.cards]; [cards[index - 1], cards[index]] = [cards[index], cards[index - 1]]; saveDashboard(cards); } }, 'Move up'),
        h('button', { disabled: blocked || index === visible.dashboard.cards.length - 1, onClick: () => { const cards = [...visible.dashboard.cards]; [cards[index + 1], cards[index]] = [cards[index], cards[index + 1]]; saveDashboard(cards); } }, 'Move down'),
        h('button', { disabled: blocked, onClick: () => saveDashboard(visible.dashboard.cards.filter(item => item.id !== card.id)) }, 'Remove card')),
      card.reference_status === 'outdated' && h('button', { disabled: blocked, onClick: () => action(async own => { const record = await own.read(`/analytics/reports/${encodeURIComponent(card.report_id)}`); if (record) { setEditor({ id: record.id, version: record.version, savedDefinition: JSON.stringify(record.definition), title: record.title, definition: record.definition, visualization: card.visualization, adoptCard: card.id }); setPreview(null); } }) }, 'Review latest version'),
      !runs[card.id] && h('p', { className: 'hc-report-empty' }, card.reference_status === 'active' ? 'Run this card to see current results.' : 'This saved version cannot run. Review its reference status above.'),
      h(ReportResult, { result: runs[card.id], kind: card.visualization, onDrill: drillDown, onPage: offset => runCard(card, offset, runs[card.id]?.evaluated_at), disabled: blocked, onOpenRecord: (entity, id) => { if (valid() && !lock.current) onOpenRecord?.(entity, id); } })))),
    visible && !visible.dashboard.cards.length && h('p', { className: 'hc-report-empty' }, 'No custom cards yet. Preview and save a report, then add it to your dashboard.'),
    visible && h('details', { className: 'hc-report-library' }, h('summary', null, `Saved reports (${visible.reports.total})`),
      h('p', { className: 'hc-report-muted' }, 'Archiving preserves the report and its versions; referenced cards cannot run until restored and reviewed. Nothing is permanently deleted.'),
      h('label', { className: 'hc-report-toolbar' }, h('input', { type: 'checkbox', 'aria-label': 'Include archived reports', checked: visible.page.includeArchived, disabled: blocked, onChange: event => { const includeArchived = event.target.checked; action(own => refresh(own, { offset: 0, includeArchived })); } }), 'Include archived reports'),
      !visible.reports.items.length && h('p', { className: 'hc-report-empty' }, 'No saved reports match this view.'),
      h('ul', { className: 'hc-report-saved-list' }, visible.reports.items.map(record => h('li', { key: record.id, className: 'hc-report-toolbar' }, h('button', { disabled: blocked || !!record.archived_at, onClick: () => openReport(record) }, `${record.title} · v${record.version}${record.archived_at ? ' · archived' : ''}`),
        h('button', { disabled: blocked || !!session.current?.pending(), 'aria-label': `${record.archived_at ? 'Restore' : 'Archive'} ${record.title}, version ${record.version}`, onClick: () => setArchived(record) }, record.archived_at ? 'Restore report' : 'Archive report')))),
      h('p', { className: 'hc-report-muted' }, `${visible.reports.items.length} reports shown from offset ${visible.page.offset}; ${visible.reports.total} matching reports.`),
      h('div', { className: 'hc-report-toolbar' }, h('button', { disabled: blocked || visible.page.offset === 0, onClick: () => action(own => refresh(own, { ...visible.page, offset: Math.max(0, visible.page.offset - 50) })) }, 'Previous saved reports'),
        h('button', { disabled: blocked || visible.page.offset + visible.reports.items.length >= visible.reports.total, onClick: () => action(own => refresh(own, { ...visible.page, offset: visible.page.offset + 50 })) }, 'Next saved reports'))),
    visible && editor && h('section', { className: 'hc-report-card hc-report-builder', 'aria-label': 'Report builder' }, h('h3', null, editor.id ? `Edit report · v${editor.version}` : 'Build a report'),
      h('div', { className: 'hc-report-toolbar' }, h('button', { disabled: blocked, onClick: () => newReport('leads') }, 'Preset: leads table'), h('button', { disabled: blocked, onClick: () => newReport('daily') }, 'Preset: leads per day'), h('button', { disabled: blocked, onClick: () => newReport('won') }, 'Preset: closed won'), h('button', { disabled: blocked, onClick: () => edit(null) }, 'Close builder')),
      h('div', { className: 'hc-report-form' }, h('label', null, 'Report title', h('input', { value: editor.title, disabled: blocked, onChange: event => change({ ...editor, title: event.target.value }) })),
        h(ReportSelect, { label: 'Visualization', value: editor.visualization, options: reportVisualizations, disabled: blocked, onChange: visualization => change({ ...editor, visualization }) }),
        h(ReportEditor, { catalog: visible.catalog, value: editor.definition, disabled: blocked, onChange: definition => change({ ...editor, definition, adoptCard: undefined }) })),
      h('div', { className: 'hc-report-toolbar' }, h('button', { className: 'hc-primary', disabled: blocked || !editor.definition.columns.length, onClick: () => action(async own => { if (latestEditor.current !== editor) return; const definition = { ...editor.definition, filter: reportCleanFilter(editor.definition.filter) }; const result = await own.run(definition); if (result && latestEditor.current === editor) setPreview({ editor, result }); }) }, 'Preview live'),
        h('button', { disabled: blocked || !preview || preview.editor !== editor || !editor.title.trim() || !!session.current?.pending(), onClick: () => action(async own => { if (latestEditor.current !== editor || preview.editor !== editor) return; const record = await own.write(editor.id ? `/analytics/reports/${encodeURIComponent(editor.id)}` : '/analytics/reports', { title: editor.title.trim(), definition: preview.result.definition, ...(editor.id ? { expected_version: editor.version } : {}) }, false, editor.id ? 'PATCH' : 'POST'); if (record) { setEditor({ ...editor, id: record.id, version: record.version, definition: record.definition, savedDefinition: JSON.stringify(record.definition) }); setPreview(null); await refresh(own); } }) }, editor.id ? 'Save new version' : 'Save report'),
        editor.id && h('button', { disabled: blocked || editor.savedDefinition !== JSON.stringify(editor.definition) || !preview || preview.editor !== editor || !!session.current?.pending(), onClick: () => { if (latestEditor.current !== editor) return; if (editor.adoptCard) saveDashboard(visible.dashboard.cards.map(card => card.id === editor.adoptCard ? { ...card, report_version: editor.version } : card)); else saveDashboard([...visible.dashboard.cards, { id: crypto.randomUUID(), report_id: editor.id, report_version: editor.version, visualization: editor.visualization, title: editor.title }]); } }, editor.adoptCard ? 'Adopt reviewed version for card' : 'Add saved version to dashboard')),
      editor.id && h('p', { className: 'hc-report-muted' }, 'Adding a card uses the saved version. Save any definition changes first. Preview again after saving.'),
      preview?.editor === editor && h(ReportResult, { result: preview.result, kind: editor.visualization, disabled: blocked, onDrill: drillDown, onPage: offset => action(async own => { const result = await own.run(preview.result.definition, preview.result.evaluated_at, offset); if (result && latestEditor.current === editor) setPreview({ editor, result }); }) })),
    drill && h('section', { className: 'hc-report-card hc-report-drill', 'aria-label': 'Contributing records' }, h('h3', null, 'Contributing records · LIVE rerun'), h('p', null, 'Same server-defined filters and evaluation instant; current records may have changed. This is not an immutable snapshot.'), h('button', { disabled: blocked, onClick: () => { if (valid()) setDrill(null); } }, 'Close contributing records'), h(ReportResult, { result: drill, kind: 'table', disabled: blocked, onDrill: drillDown, onPage: offset => action(async own => { const result = await own.run(drill.definition, drill.evaluated_at, offset); if (result) setDrill(result); }), onOpenRecord: (entity, id) => { if (valid() && !lock.current) onOpenRecord?.(entity, id); } })));
}
