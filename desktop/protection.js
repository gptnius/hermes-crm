import { createElement as h, useEffect, useRef, useState } from "react";

// Locks contain no plaintext. Unknown operations cannot be replaced or replayed
// from this UI, including after a drawer remount. Closing clears local text.
const protectionLocks = new WeakMap();
const protectionListeners = new WeakMap();
export function protectionMetadata(value) {
  return value && Number.isSafeInteger(value.record_version) && value.record_version >= 1 &&
    Number.isSafeInteger(value.note_version) && value.note_version >= 0 && typeof value.has_note === 'boolean';
}
export function createProtectionSession(client, workspaceToken, record, isCurrent = () => true, captureDownload, operationStore) {
  let alive = true, rejected = null;
  const locks = operationStore || protectionLocks.get(client) || new Map(); protectionLocks.set(client, locks);
  const scope = `${workspaceToken}|${record ? `${record.kind}|${record.id}` : 'export'}`;
  const listeners = protectionListeners.get(locks) || new Set(); protectionListeners.set(locks, listeners);
  const notify = () => { for (const listener of listeners) listener(scope); };
  const remove = () => { locks.delete(scope); notify(); };
  const put = operation => { locks.set(scope, operation); notify(); };
  const unknown = operation => { operation.state = 'unknown'; notify(); };
  const current = () => alive && client.current() && isCurrent();
  const base = record ? `/protection/notes/${record.kind}/${encodeURIComponent(record.id)}` : '/protection/export';
  const query = new URLSearchParams({ workspace_token: workspaceToken });
  const artifact = (result, download) => {
    if (!result || typeof result.export_id !== 'string' || typeof result.stored_path !== 'string' || !result.stored_path || typeof result.suggested_name !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,180}$/.test(result.suggested_name) || typeof download !== 'function') throw new Error('Invalid export response');
    return { name: result.suggested_name, async download() {
      if (!current()) return false;
      await download(result.stored_path, result.suggested_name);
      return current();
    } };
  };
  const api = {
    current, close() { alive = false; }, pending: () => locks.get(scope) || rejected,
    subscribe(listener) {
      const scoped = changed => { if (changed === scope && current()) listener(); };
      listeners.add(scoped);
      return () => listeners.delete(scoped);
    },
    async load() {
      if (!current()) return null;
      const status = await client.request(`/protection/status?${query}`);
      if (!current()) return null;
      if (!status || typeof status.notes_enabled !== 'boolean' || typeof status.backup_enabled !== 'boolean') throw new Error('Protection unavailable.');
      let metadata = null;
      if (record && status.notes_enabled) {
        metadata = await client.request(`${base}?${query}`);
        if (!current()) return null;
        if (!protectionMetadata(metadata)) throw new Error('Protection unavailable.');
      }
      return { status, metadata };
    },
    async checkSave() {
      const operation = locks.get(scope);
      if (!record || !current() || operation?.state !== 'unknown') return null;
      const result = await client.request(`${base}/operations/${encodeURIComponent(operation.operation_id)}?${query}`);
      if (!current()) return null;
      if (result?.operation_id !== operation.operation_id || result?.state !== 'committed' || !protectionMetadata(result)) return null;
      if (locks.get(scope) === operation) remove();
      return { record_version: result.record_version, note_version: result.note_version, has_note: result.has_note };
    },
    async reveal() {
      if (!current() || locks.has(scope) || rejected) return null;
      const result = await client.request(`${base}/reveal`, { method: 'POST', body: { workspace_token: workspaceToken } });
      if (!current()) return null;
      if (!protectionMetadata(result) || typeof result.plaintext !== 'string' || result.plaintext.length > 16000) throw new Error('Protected note unavailable.');
      return result;
    },
    async save(metadata, plaintext) {
      if (!current() || locks.has(scope) || rejected) return null;
      if (!record || !protectionMetadata(metadata) || typeof plaintext !== 'string' || plaintext.length > 16000) throw new Error('Invalid protected note.');
      const operation = { operation_id: crypto.randomUUID(), state: 'pending', expected_record_version: metadata.record_version, expected_note_version: metadata.note_version };
      put(operation);
      try {
        const result = await client.request(base, { method: 'PUT', body: {
          workspace_token: workspaceToken, operation_id: operation.operation_id,
          expected_record_version: operation.expected_record_version, expected_note_version: operation.expected_note_version, plaintext,
        } });
        if (!current()) { unknown(operation); return null; }
        if (!protectionMetadata(result)) throw new Error('Invalid response');
        remove();
        return result;
      } catch (error) {
        // A 5xx may arrive after commit (including proxy errors). Preserve the
        // operation identity and require a scoped receipt instead of replay.
        if ([400, 403, 404, 409, 413, 422].includes(error?.status)) {
          remove(); rejected = { state: 'rejected' };
          throw new Error(error.status === 409 ? 'This record or note changed. Close and reopen before editing.' : 'Protected note was not saved. Check protection configuration and reopen.');
        }
        unknown(operation);
        throw new Error('Save outcome unknown. Do not repeat this save. Use Check save outcome to inspect the original receipt.');
      }
    },
    async checkExport() {
      const operation = locks.get(scope);
      if (record || !current() || operation?.state !== 'unknown') return null;
      const result = await client.request(`/protection/export/operations/${encodeURIComponent(operation.operation_id)}?${query}`);
      if (!current()) return null;
      if (result?.operation_id !== operation.operation_id || result?.state !== 'committed') return null;
      // Reuse the download binding captured before the original write, including
      // across remounts. Receipt lookup is read-only and never makes a snapshot.
      const prepared = artifact(result, operation.download);
      if (locks.get(scope) === operation) remove();
      return prepared;
    },
    async prepareExport() {
      if (!current() || locks.has(scope) || rejected) return null;
      if (typeof captureDownload !== 'function') throw new Error('Update Hermes Desktop to download encrypted exports.');
      // A capture failure occurs before dispatch and must not create an unknown
      // write lock. There is no await or profile-changing work before REST.
      const download = captureDownload();
      if (typeof download !== 'function') throw new Error('Download unavailable');
      const operation = { operation_id: crypto.randomUUID(), state: 'pending', download };
      put(operation);
      try {
        const result = await client.request('/protection/export', { method: 'POST', body: { workspace_token: workspaceToken, operation_id: operation.operation_id } });
        if (!current()) { unknown(operation); return null; }
        const prepared = artifact(result, download);
        remove();
        return prepared;
      } catch (error) {
        if ([400, 403, 404, 409, 413, 422].includes(error?.status)) remove();
        else unknown(operation);
        throw new Error('Export could not be confirmed. Do not repeat an uncertain export; check the local export folder.');
      }
    },
  };
  return api;
}

export function ProtectionHelp() {
  return h('details', null, h('summary', null, 'About protected notes and exports'),
    h('p', null, 'Optional encryption covers protected notes and encrypted CRM content exports only. Ordinary Notes, record fields and existing files are not automatically encrypted or moved.'),
    h('p', null, 'Configure keys separately through the supported Hermes secret source. No keys are created here. A masked secret setting may use a plaintext .env file; masking is not encryption. Missing, unavailable or malformed keys disable the protected action.'),
    h('p', null, 'Revealed text exists temporarily in this drawer and is cleared on close, cancel or view/profile changes. This is not a promise of cryptographic memory erasure.'),
    h('p', null, 'Protected notes are bound to the exact profile and workspace. Renaming a profile or opening a fresh workspace prevents normal reveal. Retain the protected-note key and export key separately: the export key alone cannot decrypt protected-note content.'),
    h('p', null, 'Exports are encrypted CRM content snapshots, not complete Hermes backups or verified full recovery. Keys are excluded. Keep your key separately and safely; losing it can make protected data unrecoverable. No restore workflow is provided here.'));
}

export function ProtectionDrawer({ Drawer, client, workspaceToken, record = null, current, invalidated = false, captureDownload, operationStore, cancel, returnFocus }) {
  const [view, setView] = useState(null), [text, setText] = useState(''), [revealed, setRevealed] = useState(false);
  const [editing, setEditing] = useState(false), [busy, setBusy] = useState(false), [notice, setNotice] = useState('');
  const [prepared, setPrepared] = useState(null);
  const [, setOperationRevision] = useState(0);
  const latest = useRef(null); latest.current = { current, invalidated };
  const session = useRef(null), lock = useRef(false);
  useEffect(() => {
    const own = createProtectionSession(client, workspaceToken, record, () => !latest.current.invalidated && latest.current.current(), captureDownload, operationStore);
    session.current = own;
    const unsubscribe = own.subscribe(() => {
      // Other drawers may share an in-flight operation. Notify them when the
      // original request settles, even after its submitting drawer unmounts.
      if (own.pending()) { setText(''); setRevealed(false); setEditing(false); }
      setOperationRevision(value => value + 1);
    });
    own.load().then(value => { if (value) setView(value); }).catch(() => { if (own.current()) setNotice('Protection configuration could not be loaded.'); });
    return () => { unsubscribe(); own.close(); session.current = null; };
  }, [client, workspaceToken, record?.kind, record?.id]);
  useEffect(() => {
    if (invalidated || !current()) { session.current?.close(); setText(''); setRevealed(false); setEditing(false); setPrepared(null); setNotice('This view changed. Close and reopen to continue.'); }
  }, [invalidated, current()]);
  function clear() { setText(''); setRevealed(false); setEditing(false); }
  function close() { clear(); session.current?.close(); cancel(); }
  const stale = invalidated || !current() || !client.current();
  const blocked = stale || busy || !view || Boolean(session.current?.pending());
  async function run(action, readOnly = false) {
    const own = session.current;
    if (!own?.current() || lock.current || (!readOnly && own.pending())) return;
    lock.current = true; setBusy(true); setNotice('');
    try { await action(own); }
    catch (error) { if (own.current()) setNotice(error.message === 'This record or note changed. Close and reopen before editing.' || error.message.startsWith('Save outcome unknown.') || error.message.startsWith('Protected note was not saved.') ? error.message : 'Protected action could not be completed. Check configuration and reopen.'); }
    finally { lock.current = false; if (own.current()) setBusy(false); }
  }
  return h(Drawer, { title: record ? 'Protected note' : 'Encrypted CRM export', subtitle: record ? 'Separate from ordinary record Notes.' : 'Optional encrypted content snapshot.', busy: false, cancel: close, returnFocus, closeLabel: 'Close protection drawer' },
    h('div', { className: 'hc-editor-body' },
      h(ProtectionHelp),
      stale && h('p', { role: 'alert' }, 'Stale view. Writes and downloads are disabled; you can still close this drawer.'),
      !view && !notice && h('p', { role: 'status' }, 'Checking protection configuration…'),
      view && h('p', null, record ? `Protected notes: ${view.status.notes_enabled ? 'configured' : 'unavailable'}.` : `Encrypted exports: ${view.status.backup_enabled ? 'configured' : 'unavailable'}.`),
      view?.metadata && h('p', null, `Record version ${view.metadata.record_version} · Protected note version ${view.metadata.note_version} · ${view.metadata.has_note ? 'A protected note exists' : 'No protected note yet'}`),
      record && view?.status.notes_enabled && h('div', null,
        !revealed && h('button', { type: 'button', disabled: blocked, onClick: () => run(async own => {
          const result = await own.reveal();
          if (result && own.current()) { setView(old => ({ ...old, metadata: { record_version: result.record_version, note_version: result.note_version, has_note: result.has_note } })); setText(result.plaintext); setRevealed(true); }
        }) }, 'Reveal protected note'),
        revealed && !stale && !editing && h('div', null, h('p', { className: 'hc-details', 'aria-label': 'Revealed protected note' }, text || 'Empty protected note'),
          h('button', { type: 'button', disabled: blocked, onClick: () => setEditing(true) }, 'Edit protected note')),
        editing && !stale && h('label', null, 'Protected note text', h('textarea', { value: text, maxLength: 16000, disabled: blocked, onChange: event => setText(event.target.value) })),
        editing && !stale && h('button', { type: 'button', disabled: blocked, onClick: () => run(async own => {
          const result = await own.save(view.metadata, text);
          if (!result || !own.current()) return;
          clear(); setView(old => ({ ...old, metadata: result })); setNotice('Protected note saved.');
          try { const fresh = await own.load(); if (fresh) setView(fresh); }
          catch { if (own.current()) setNotice('Protected note saved, but metadata refresh failed. Close and reopen.'); }
        }) }, 'Save protected note'),
        revealed && h('button', { type: 'button', onClick: clear }, 'Cancel and hide')),
      !record && h('div', null,
        typeof captureDownload !== 'function' && h('p', null, 'Download unavailable. Update Hermes Desktop to a version with gateway file download support.'),
        h('button', { type: 'button', disabled: blocked || !view?.status.backup_enabled || typeof captureDownload !== 'function' || Boolean(prepared), onClick: () => run(async own => {
          const result = await own.prepareExport(); if (result && own.current()) { setPrepared(result); setNotice('Encrypted export prepared. A copy remains in the plugin export folder, including if the save dialog is cancelled.'); }
        }) }, 'Prepare encrypted export'),
        prepared && h('div', null, h('p', null, prepared.name), h('p', null, 'The encrypted copy remains in the plugin export folder. No automatic deletion is performed.'),
          h('button', { type: 'button', disabled: blocked, onClick: () => run(async own => {
            setNotice('Save dialog requested. Hermes Desktop reports the outcome; cancellation does not remove the prepared export.');
            await prepared.download();
            if (own.current()) setNotice('Save dialog request finished. Check the Hermes Desktop outcome; this does not confirm the file was saved. The prepared export remains available.');
          }) }, 'Download encrypted export'))),
      !record && session.current?.pending()?.state === 'unknown' && h('button', { type: 'button', disabled: stale || busy, onClick: () => run(async own => {
        const result = await own.checkExport();
        if (!own.current()) return;
        if (!result) { setNotice('No original encrypted artifact confirmed. The export remains locked; no replacement snapshot was created.'); return; }
        setPrepared(result); setNotice('Original encrypted export confirmed. Download is a separate action; a copy remains in the plugin export folder.');
      }, true) }, 'Check export outcome'),
      record && session.current?.pending()?.state === 'unknown' && h('button', { type: 'button', disabled: stale || busy, onClick: () => run(async own => {
        const result = await own.checkSave();
        if (!own.current()) return;
        if (!result) { setNotice('No committed receipt confirmed. The save remains locked; missing evidence does not prove it failed.'); return; }
        clear(); setView(old => ({ ...old, metadata: result })); setNotice('Protected note save confirmed. Text remains hidden.');
        try { const fresh = await own.load(); if (fresh) setView(fresh); }
        catch { if (own.current()) setNotice('Protected note save confirmed, but metadata refresh failed. Close and reopen.'); }
      }, true) }, 'Check save outcome'),
      view && h('button', { type: 'button', disabled: stale || busy, onClick: () => run(async own => {
        clear(); const fresh = await own.load(); if (fresh) { setView(fresh); setNotice('Protection metadata refreshed. Text remains hidden.'); }
      }, true) }, 'Refresh protection metadata'),
      session.current?.pending()?.state === 'unknown' && h('p', { role: 'alert' }, 'An earlier operation has an unknown outcome. New writes are locked in this view; no automatic retry is performed.'),
      notice && h('p', { role: 'status' }, notice)));
}
