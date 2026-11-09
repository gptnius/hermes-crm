import { createElement as h, useEffect, useRef, useState } from "react";

const storageConfigurations = new Set(['configured', 'missing_url', 'invalid_url', 'invalid_backend']);
const storageResults = {
  connected: 'Connection succeeded. This checks connectivity only, not CRM schema readiness, write permissions or migrations.',
  not_initialized: 'No local CRM database exists yet. The check did not create one. Open the CRM overview when you are ready to initialize it.',
  missing_url: 'PostgreSQL is selected, but no connection URL is available in this profile. Save it in Hermes plugin settings.',
  invalid_url: 'The saved PostgreSQL connection URL is not supported. Use a PostgreSQL database URL in Hermes plugin settings.',
  invalid_backend: 'Choose SQLite or PostgreSQL in Hermes plugin settings.',
  driver_missing: 'The PostgreSQL driver is unavailable in this gateway. Update or reinstall HermesCRM through the supported Hermes plugin installer, then restart the relevant gateway if needed.',
  unsupported_connection: 'This check supports a complete username/password PostgreSQL URL and a current driver, without ambient PG settings or custom authentication. Have the database operator verify custom connections; CRM runtime behavior is unchanged.',
  timeout: 'The connection check timed out. Verify this gateway can reach the configured database, then try again.',
  unavailable: 'The saved connection could not be verified. Check the database service, credentials, TLS and network access in Hermes plugin settings. No fallback was used.',
};
export function validateStorageStatus(value) {
  if (!value || !['sqlite', 'postgres', 'invalid'].includes(value.backend) ||
      !storageConfigurations.has(value.configuration) || !/^[a-f0-9]{64}$/.test(value.selection_token))
    throw new Error('Storage configuration could not be verified.');
  // Retain a narrow projection, never extra fields from a response.
  return {backend: value.backend, configuration: value.configuration, selection_token: value.selection_token};
}
export function storageSettingsHref(makeHref, profile) {
  if (typeof makeHref !== 'function' || typeof profile !== 'string' || !profile) return null;
  const href = makeHref();
  if (typeof href !== 'string' || !href.startsWith('/settings?')) return null;
  const params = new URLSearchParams(href.slice(href.indexOf('?') + 1));
  if (params.get('tab') !== 'plugins') return null;
  params.set('profile', profile);
  return '/settings?' + params;
}
export function StorageSettings({client, profile, openHostSettings, canOpenHostSettings}) {
  const [status, setStatus] = useState(null), [busy, setBusy] = useState(false), [notice, setNotice] = useState('');
  const live = useRef(false), generation = useRef(0), lock = useRef(false);
  const current = () => live.current && client.current();
  async function load() {
    if (!current() || lock.current) return;
    const ticket = ++generation.current;
    lock.current = true; setBusy(true); setNotice(''); setStatus(null);
    try {
      const value = validateStorageStatus(await client.request('/storage/status'));
      if (current() && ticket === generation.current) setStatus(value);
    } catch {
      if (current() && ticket === generation.current) setNotice('Storage configuration could not be loaded. You can still open Hermes plugin settings.');
    } finally {
      if (ticket === generation.current) {lock.current = false; if (current()) setBusy(false);}
    }
  }
  useEffect(() => {
    live.current = true; void load();
    return () => {live.current = false; generation.current++; lock.current = false;};
  }, [client]);
  async function check() {
    if (!current() || lock.current || !status) return;
    const selected = status, ticket = ++generation.current;
    lock.current = true; setBusy(true); setNotice('');
    try {
      const value = await client.request('/storage/check', {method: 'POST', body: {selection_token: selected.selection_token}});
      if (!value || value.backend !== selected.backend || value.selection_token !== selected.selection_token ||
          value.readiness_checked !== false || !Object.hasOwn(storageResults, value.result)) throw new Error('Invalid check result');
      if (current() && ticket === generation.current) setNotice(storageResults[value.result]);
    } catch {
      if (current() && ticket === generation.current) {
        setStatus(null);
        setNotice('The check could not be confirmed, or the saved selection changed. Reload storage settings before checking again.');
      }
    } finally {
      if (ticket === generation.current) {lock.current = false; if (current()) setBusy(false);}
    }
  }
  function configure() {
    if (!current()) return;
    // Invalidate any old result before handing off. This action does not save
    // config, send credentials, restart a gateway or select another connection.
    generation.current++; lock.current = false; setBusy(false); setStatus(null); setNotice('');
    try { if (openHostSettings() !== true) throw new Error('Unavailable'); }
    catch { if (current()) setNotice('Open Hermes Settings → Plugins, select this profile, then choose HermesCRM and Agent settings if shown.'); }
  }
  return h('section', {'aria-label': 'Storage', className: 'hc-card hc-settings-section hc-storage-settings'},
    h('h3', null, 'Storage'),
    h('p', {className: 'hc-muted'}, `For the active app profile: ${profile}. A chat in another profile does not change this selection.`),
    h('dl', {className: 'hc-setting-properties'}, h('div', null,
      h('dt', null, 'Saved backend'), h('dd', null, status ? status.backend === 'sqlite' ? 'SQLite · local to this gateway and profile' : status.backend === 'postgres' ? 'PostgreSQL · user-managed database' : 'Selection needs attention' : busy ? 'Reading saved selection…' : 'Unavailable'))),
    status && status.configuration !== 'configured' && h('p', {className: 'hc-notice'}, storageResults[status.configuration]),
    h('p', null, 'SQLite is the simple default with no server to manage. Choose PostgreSQL for an existing database on your computer, VPS or another host.'),
    h('div', {className: 'hc-safety-note'}, 'Changing storage does not migrate, upload, merge or delete existing records. Back up your data and handle any migration separately.'),
    h('details', {className: 'hc-evidence-disclosure'}, h('summary', null, 'Setup steps and storage boundaries'),
    h('ol', {className: 'hc-storage-steps'},
      h('li', null, 'Open Hermes plugin settings. Choose HermesCRM, then Agent settings if shown, and verify the selected profile.'),
      h('li', null, 'Choose SQLite or PostgreSQL. For PostgreSQL, save the database connection URL in the host’s masked field. Use TLS for remote databases. Masking is not encryption: Hermes may store secrets in the profile’s .env file.'),
      h('li', null, 'Save in Hermes, return here, reload the selection and check it. If a changed secret or driver is still unavailable, restart the relevant gateway with Hermes controls.')),
    h('p', null, 'SQLite files live on the Hermes gateway, which may be your computer or a VPS. PostgreSQL availability, access and backups are your responsibility; HermesCRM does not provision it.'),
    h('p', null, 'Profiles use separate storage namespaces derived from this host’s profile location. Pointing another installation at the same database does not automatically share records.')),
    h('div', {className: 'hc-actions'},
      h('button', {type: 'button', className: 'hc-primary', onClick: configure, disabled: !canOpenHostSettings}, 'Open Hermes plugin settings'),
      h('button', {type: 'button', onClick: load, disabled: busy}, 'Reload storage settings'),
      h('button', {type: 'button', onClick: check, disabled: busy || !status}, busy ? 'Working…' : 'Check saved connection')),
    !canOpenHostSettings && h('p', {className: 'hc-muted'}, 'Open Hermes Settings → Plugins manually, select this profile, then choose HermesCRM and Agent settings if shown.'),
    h('p', {className: 'hc-muted'}, 'Check uses a read-only query, not CRM initialization or migration. A successful connection is not proof the CRM is ready. Earlier CRM requests may still finish.'),
    notice && h('p', {role: 'status', className: 'hc-notice'}, notice));
}
