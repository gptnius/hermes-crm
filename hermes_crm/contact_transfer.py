"""Bounded, create-only contact CSV transfer. No jobs, providers or protected data.

Imports reuse the existing transactional idempotency store, with a versioned
namespace and minimal receipts. Raw CSV and field values are never stored there.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import uuid
import unicodedata
from collections import defaultdict
from pydantic import ValidationError
from sqlalchemy import inspect, select
from .domain import CRMError, ContactInput, contacts, idempotency, settings, now

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000
MAX_EXPORT_ROWS = 10000
MAX_EXPORT_BYTES = 4 * 1024 * 1024
MAX_WORKSPACE_CONTACTS = 100000
CORE = ('name', 'email', 'company', 'title', 'lifecycle', 'notes')
DEFAULT_COLUMNS = list(CORE[:-1])
PREFIX = 'contact-csv:v1:'
LIMITS = dict(import_bytes=MAX_BYTES, import_rows=MAX_ROWS, export_rows=MAX_EXPORT_ROWS, export_bytes=MAX_EXPORT_BYTES)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def batch_key(batch_id):
    try:
        if str(uuid.UUID(batch_id)) != batch_id: raise ValueError()
    except Exception: raise CRMError('Invalid batch identifier') from None
    return PREFIX + batch_id


def _normal(value):
    return ' '.join(value.split()).casefold()


def safe_cell(value):
    """Prefix dangerous strings AND literal leading apostrophes, reversibly.

    Untrusted leading whitespace/control characters are escaped too. CSV quoting
    alone does not prevent spreadsheet formula interpretation.
    """
    if value and (value[0] in "'=+-@" or value[0].isspace() or unicodedata.category(value[0])[0] in ('C', 'Z')):
        return "'" + value, True
    return value, False


def parse_csv(csv_text):
    if not isinstance(csv_text, str): raise CRMError('CSV must be UTF-8 text')
    try: raw = csv_text.encode('utf-8')
    except UnicodeError: raise CRMError('CSV must be valid UTF-8 text') from None
    if len(raw) > MAX_BYTES: raise CRMError('CSV exceeds the 2 MiB import limit', 413)
    if '\x00' in csv_text: raise CRMError('CSV must not contain NUL bytes')
    # Enforce RFC-style quote placement in addition to csv.reader's closing-
    # quote checks. Python's reader alone accepts quotes in unquoted cells.
    text_value = csv_text[1:] if csv_text.startswith('\ufeff') else csv_text
    quoted, after_quote, at_start = False, False, True
    i = 0
    while i < len(text_value):
        char = text_value[i]
        if quoted:
            if char == '"':
                if i + 1 < len(text_value) and text_value[i + 1] == '"': i += 1
                else: quoted, after_quote = False, True
        elif after_quote:
            if char not in ',\r\n': raise CRMError('Malformed CSV quoting')
            after_quote, at_start = False, True
        elif char == '"':
            if not at_start: raise CRMError('Malformed CSV quoting')
            quoted, at_start = True, False
        elif char in ',\r\n': at_start = True
        else: at_start = False
        i += 1
    if quoted: raise CRMError('Malformed CSV quoting')
    try:
        reader = csv.reader(io.StringIO(text_value, newline=''), strict=True)
        headers = next(reader)
        if not headers or len(headers) > 106 or any(not h or h != h.strip() or len(h) > 160 for h in headers) or len(set(headers)) != len(headers):
            raise CRMError('CSV requires unique nonempty headers without surrounding whitespace (maximum 106)')
        rows = []
        for number, row in enumerate(reader, 2):
            if len(rows) >= MAX_ROWS: raise CRMError('CSV exceeds the 1000-row import limit', 413)
            if len(row) != len(headers): raise CRMError(f'CSV row {number} has {len(row)} cells; expected {len(headers)}')
            rows.append((number, row))
        if not rows: raise CRMError('CSV contains no contact rows')
        return headers, rows
    except (csv.Error, StopIteration): raise CRMError('Malformed or empty CSV') from None


class ContactTransfer:
    def __init__(self, crm): self.crm = crm

    def _scope(self, conn):
        token = conn.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar()
        # SQLAlchemy may mutate schema_translate_map with its '_none' bookkeeping
        # key. Bind only the resolved schema, never that mixed-key dictionary or
        # connection credentials (which may rotate without moving the workspace).
        schema = (self.crm.engine.get_execution_options().get('schema_translate_map') or {}).get(None)
        return digest(['contact-transfer-scope-v1', self.crm.profile, token, self.crm.backend, schema])

    def _receipt(self, conn, raw, batch_id):
        try:
            result = json.loads(raw)
            if (set(result) != {'receipt_version', 'scope', 'batch_id', 'digest', 'status', 'created', 'skipped', 'excluded', 'counts'}
                or type(result['receipt_version']) is not int or result['receipt_version'] != 1 or result['scope'] != self._scope(conn)
                or result['batch_id'] != batch_id or result['status'] != 'completed'
                or not isinstance(result['digest'], str) or len(result['digest']) != 64): raise ValueError()
            for group in ('created', 'skipped', 'excluded'):
                if not isinstance(result[group], list) or len(result[group]) > MAX_ROWS: raise ValueError()
                for item in result[group]:
                    if not isinstance(item, dict) or set(item) != ({'row_number', 'id'} if group == 'created' else {'row_number', 'reason'}): raise ValueError()
                    if type(item['row_number']) is not int or not 2 <= item['row_number'] <= MAX_ROWS + 1: raise ValueError()
                    if group == 'created': batch_key(item['id'])
                    elif item['reason'] not in ('duplicate', 'invalid', 'not_selected'): raise ValueError()
            numbers = [r['row_number'] for group in ('created', 'skipped', 'excluded') for r in result[group]]
            if not isinstance(result['counts'], dict) or any(type(v) is not int for v in result['counts'].values()): raise ValueError()
            if len(numbers) != len(set(numbers)) or result['counts'] != {group: len(result[group]) for group in ('created', 'skipped', 'excluded')}: raise ValueError()
            return result
        except Exception:
            raise CRMError('Incompatible contact import receipt; the batch identifier cannot be reused', 409) from None

    def _storage(self, conn):
        # Refuse partial/incompatible legacy receipt storage rather than create a
        # parallel store, overwrite it, or silently fall back to another backend.
        inspector = inspect(conn)
        schema = self.crm.engine.get_execution_options().get('schema_translate_map', {}).get(None)
        if not inspector.has_table(idempotency.name, schema=schema): raise CRMError('Contact transfer receipt storage is unavailable', 503)
        actual = {c['name']: c for c in inspector.get_columns(idempotency.name, schema=schema)}
        if set(actual) != set(idempotency.c.keys()): raise CRMError('Incompatible contact transfer receipt storage', 503)
        for column in idempotency.c:
            item = actual[column.name]
            if (item['type']._type_affinity is not column.type._type_affinity or
                getattr(item['type'], 'length', None) != getattr(column.type, 'length', None) or item['nullable'] != column.nullable):
                raise CRMError('Incompatible contact transfer receipt storage', 503)
        if set(inspector.get_pk_constraint(idempotency.name, schema=schema)['constrained_columns']) != {'key'}:
            raise CRMError('Incompatible contact transfer receipt primary key', 503)

    def _catalog(self, conn):
        fields = self.crm.catalog(conn)['fields']['contacts']
        columns = [dict(key=k, label='Contact type' if k == 'lifecycle' else k.title(), type='text', archived=False) for k in CORE]
        columns += [dict(f, key='custom.' + f['key']) for f in fields]
        return dict(columns=columns, default_columns=DEFAULT_COLUMNS, limits=LIMITS,
                    spreadsheet_safe_description="Dangerous leading characters and literal leading apostrophes receive one apostrophe. Import preserves apostrophes; existing contact validation trims core-field whitespace. Remove an export escape deliberately before importing if needed.")

    def catalog(self):
        with self.crm._read_connection() as conn:
            self._storage(conn)
            return self._catalog(conn)

    def _preview(self, conn, csv_text, mapping=None, spreadsheet_safe=False):
        if spreadsheet_safe is not False: raise CRMError('Import preserves apostrophes; safe-export decoding is not supported')
        self._storage(conn)
        headers, raw_rows = parse_csv(csv_text)
        catalog = self._catalog(conn)
        definitions = {f['key']: f for f in catalog['columns'] if not f['archived']}
        if mapping is None:
            return dict(headers=headers, suggested_mapping={h: h if h in definitions else None for h in headers}, needs_mapping=True,
                        rows=[], ignored_columns=[], counts=dict(ready=0, duplicate=0, invalid=0), limits=LIMITS)
        if not isinstance(mapping, dict) or set(mapping) != set(headers): raise CRMError('Map or explicitly ignore every CSV header')
        targets = [v for v in mapping.values() if v is not None]
        if any(not isinstance(v, str) or v not in definitions for v in targets): raise CRMError('Mapping contains an unknown or archived contact field')
        if len(set(targets)) != len(targets): raise CRMError('Each contact field may be mapped only once')
        if 'name' not in targets: raise CRMError('Map a contact name column')
        existing = [dict(r) for r in conn.execute(select(contacts.c.id, contacts.c.name, contacts.c.company, contacts.c.email, contacts.c.version)
                                               .order_by(contacts.c.id).limit(MAX_WORKSPACE_CONTACTS + 1)).mappings()]
        if len(existing) > MAX_WORKSPACE_CONTACTS: raise CRMError('Workspace exceeds the supported duplicate-check limit', 413)
        emails, names = defaultdict(list), defaultdict(list)
        def index(value, ref):
            email = value.get('email', '').strip().casefold()
            if email: emails[email].append(dict(ref, reason='email'))
            name, company = _normal(value.get('name', '')), _normal(value.get('company', ''))
            if name and company: names[(name, company)].append(dict(ref, reason='name_company'))
        for value in existing: index(value, dict(source='workspace', id=value['id']))
        results = []
        for number, cells in raw_rows:
            values, custom, errors = {}, {}, []
            for header, cell in zip(headers, cells):
                target = mapping[header]
                if target is None: continue
                if target.startswith('custom.'):
                    field = definitions[target]
                    value = cell
                    if cell == '': value = None
                    elif field['type'] == 'boolean':
                        if cell.strip().casefold() not in ('true', 'false'): errors.append(f'{target}: use true or false')
                        else: value = cell.strip().casefold() == 'true'
                    elif field['type'] == 'number':
                        try:
                            parsed = float(cell)
                            if not math.isfinite(parsed): raise ValueError()
                            value = parsed
                        except ValueError: errors.append(f'{target}: use a finite number')
                    custom[target[7:]] = value
                else: values[target] = cell
            try:
                values = ContactInput.model_validate(values).model_dump()
                custom = self.crm._validate_custom(conn, 'contacts', custom)
            except ValidationError as error:
                errors.extend(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors(include_input=False))
            except CRMError as error: errors.append(error.message)
            duplicates = []
            if not errors:
                email = values['email'].strip().casefold()
                duplicates.extend(emails.get(email, []) if email else [])
                duplicates.extend(names.get((_normal(values['name']), _normal(values['company'])), []) if values['company'] else [])
                # Deduplicate references when both email and name/company match.
                seen = set()
                duplicates = [d for d in duplicates if not ((key := (d['source'], d.get('id'), d.get('row_number'))) in seen or seen.add(key))]
                index(values, dict(source='file', row_number=number))
            duplicate_count = len(duplicates)
            results.append(dict(row_number=number, status='invalid' if errors else 'duplicate' if duplicates else 'ready',
                                values=dict(values, custom_fields=custom), errors=errors, duplicates=duplicates[:20], duplicate_count=duplicate_count))
        request_digest = digest([csv_text, mapping, spreadsheet_safe])
        fingerprint = digest([self._scope(conn), request_digest, catalog['columns'], existing])
        return dict(headers=headers, needs_mapping=False, ignored_columns=[h for h in headers if mapping[h] is None],
                    rows=results, counts={s: sum(r['status'] == s for r in results) for s in ('ready', 'duplicate', 'invalid')},
                    digest=request_digest, fingerprint=fingerprint, limits=LIMITS)

    def preview(self, csv_text, mapping=None, spreadsheet_safe=False):
        with self.crm._read_connection() as conn: return self._preview(conn, csv_text, mapping, spreadsheet_safe)

    def receipt(self, batch_id):
        key = batch_key(batch_id)
        with self.crm._read_connection() as conn:
            self._storage(conn)
            raw = conn.execute(select(idempotency.c.response).where(idempotency.c.key == key)).scalar()
            return self._receipt(conn, raw, batch_id) if raw else dict(batch_id=batch_id, status='not_found')

    def commit(self, *, csv_text, mapping, batch_id, expected_fingerprint, approved_rows, duplicate_policy='skip', spreadsheet_safe=False):
        key = batch_key(batch_id)
        if duplicate_policy not in ('skip', 'reject'): raise CRMError('Choose duplicate skip or reject')
        if not isinstance(approved_rows, list) or not approved_rows or len(approved_rows) > MAX_ROWS or any(type(n) is not int or n < 2 for n in approved_rows) or len(set(approved_rows)) != len(approved_rows):
            raise CRMError('Choose distinct valid CSV row numbers to import')
        if not isinstance(expected_fingerprint, str) or len(expected_fingerprint) != 64: raise CRMError('A current preview fingerprint is required', 409)
        # Digest binds the exact original approval, not just CSV contents.
        request_digest = digest([csv_text, mapping, spreadsheet_safe, sorted(approved_rows), duplicate_policy, expected_fingerprint])
        with self.crm.engine.begin() as conn:
            self.crm._catalog_lock(conn)
            self._storage(conn)
            previous = conn.execute(select(idempotency).where(idempotency.c.key == key)).mappings().first()
            if previous:
                receipt = self._receipt(conn, previous['response'], batch_id)
                if previous['digest'] != request_digest: raise CRMError('Batch identifier is already used for a different approval', 409)
                return receipt
            preview = self._preview(conn, csv_text, mapping, spreadsheet_safe)
            if preview.get('fingerprint') != expected_fingerprint: raise CRMError('Contacts or field definitions changed. Preview again before importing.', 409)
            rows = {r['row_number']: r for r in preview['rows']}
            if set(approved_rows) - rows.keys(): raise CRMError('Approval contains unknown rows')
            selected = [rows[n] for n in sorted(approved_rows)]
            if any(r['status'] == 'invalid' for r in selected): raise CRMError('Invalid rows cannot be approved')
            if duplicate_policy == 'reject' and any(r['status'] == 'duplicate' for r in selected): raise CRMError('Approved rows include duplicates; none were imported', 409)
            created, skipped = [], []
            for row in selected:
                if row['status'] == 'duplicate':
                    skipped.append(dict(row_number=row['row_number'], reason='duplicate'))
                    continue
                values = dict(row['values'])
                custom = values.pop('custom_fields')
                record = self.crm._insert_created(conn, 'contacts', values, custom, 'contact-csv-import')
                created.append(dict(row_number=row['row_number'], id=record['id']))
            excluded = [dict(row_number=r['row_number'], reason='invalid' if r['status'] == 'invalid' else 'not_selected')
                        for r in preview['rows'] if r['row_number'] not in approved_rows]
            result = dict(receipt_version=1, scope=self._scope(conn), batch_id=batch_id, digest=preview['digest'], status='completed',
                          created=created, skipped=skipped, excluded=excluded,
                          counts=dict(created=len(created), skipped=len(skipped), excluded=len(excluded)))
            conn.execute(idempotency.insert().values(key=key, digest=request_digest, response=json.dumps(result)))
            return result

    def validate_export(self, conn, columns=None, filters=None):
        columns = list(DEFAULT_COLUMNS) if columns is None else columns
        filters = {} if filters is None else filters
        if not isinstance(filters, dict) or set(filters) - {'q', 'stage', 'contact_type', 'company', 'email', 'followup'}: raise CRMError('Invalid contact export filters')
        if not isinstance(columns, list) or not columns or any(not isinstance(c, str) for c in columns) or len(set(columns)) != len(columns): raise CRMError('Choose distinct export columns')
        self._storage(conn)
        allowed = {f['key'] for f in self._catalog(conn)['columns']}
        if set(columns) - allowed: raise CRMError('Unknown or protected export column')
        predicates = self.crm._contact_predicates(**filters, timestamp=now(), conn=conn)
        return list(columns), dict(filters), predicates

    def export(self, columns=None, filters=None):
        with self.crm._read_connection() as conn:
            columns, filters, predicates = self.validate_export(conn, columns, filters)
            # Retrieve selected core values; custom dictionaries are read only
            # when at least one custom field is selected. Protected notes are never
            # read, even when ordinary notes/custom columns are requested.
            selected_core = [contacts.c[c] for c in columns if not c.startswith('custom.')]
            rows = conn.execute(select(contacts.c.id, *selected_core).where(*predicates)
                                .order_by(contacts.c.created_at.desc(), contacts.c.id.asc()).limit(MAX_EXPORT_ROWS + 1)).mappings().all()
            if len(rows) > MAX_EXPORT_ROWS: raise CRMError('Export exceeds 10000 contacts; narrow the filters', 413)
            output = io.StringIO(newline='')
            writer = csv.writer(output, lineterminator='\r\n')
            writer.writerow(columns)
            escaped = 0
            for row in rows:
                custom = self.crm._custom_values(conn, 'contacts', row['id']) if any(c.startswith('custom.') for c in columns) else {}
                cells = []
                for column in columns:
                    value = custom.get(column[7:]) if column.startswith('custom.') else row[column]
                    value = '' if value is None else ('true' if value else 'false') if type(value) is bool else str(value)
                    cell, changed = safe_cell(value)
                    cells.append(cell)
                    escaped += int(changed)
                writer.writerow(cells)
                if output.tell() > MAX_EXPORT_BYTES: raise CRMError('Export exceeds 4 MiB; narrow the filters or columns', 413)
            csv_text = output.getvalue()
            if len(csv_text.encode()) > MAX_EXPORT_BYTES: raise CRMError('Export exceeds 4 MiB; narrow the filters or columns', 413)
            return dict(csv_text=csv_text, filename='hermes-contacts.csv', row_count=len(rows), columns=columns,
                        spreadsheet_safe=True, escaped_cells=escaped)
