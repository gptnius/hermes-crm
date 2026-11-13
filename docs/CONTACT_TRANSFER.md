# Contact CSV import and export

The first portability increment is contact-first and create-only. It does not
connect another CRM, update existing contacts, create deals/tasks, schedule work
or send messages. Ordinary CSV files are plaintext. Protected notes, encryption
keys, host files and internal receipts are not selectable CSV columns.

## Import: map, preview, then approve

Open **Contact CSV** from Contacts in the native pane. Choose a UTF-8 CSV file,
then explicitly preview its columns. Selecting a file alone does not import
records. Map each source header to one supported contact field or explicitly
ignore it. A name column is required; mapping the same target twice is rejected.

Core targets are name, email, company, title, Contact type (the stable `lifecycle`
key) and ordinary Notes. Existing active contact custom fields use
`custom.<stable_key>`. This does not create field definitions. Create and review
any needed definitions in Customize before importing.

For a simple file, the header can be:

```csv
name,email,company,title,lifecycle
```

Contact type accepts `lead`, `customer` or `partner`; it is not a deal stage.
Other products' IDs, stages, separate first/last-name columns, owner models and
relationship formats are not automatically converted. Combine or transform
unsupported source fields deliberately before import, or explicitly ignore them
in the preview. This is not a full HubSpot/Salesforce migration tool.

Preview shows normalized values, validation errors, duplicate candidates and
ignored columns before any contact is created. Core values use the same
validation/whitespace normalization as ordinary contact creation. Custom values
use the existing type rules: finite numbers, true/false booleans, YYYY-MM-DD
dates and configured single-select choices. Blank custom cells are unset, not
zero or false. Archived fields cannot be imported until restored.

Duplicate detection compares nonempty email case-insensitively and also checks
name plus company when both are present, normalizing whitespace/case. It checks
both existing contacts and earlier valid rows in the file. These are candidates,
not proof that two people are the same. The first increment does not merge,
overwrite or force-create candidates. Review them and resolve genuinely distinct
people explicitly rather than assuming the matching rule is an identity system.

Choose valid rows and review the confirmation before importing. A duplicate
policy can skip candidates or reject the selected batch. Invalid selected rows
are rejected. Unselected/invalid rows are not silently converted or partially
saved. A changed contact population or field catalog invalidates the preview;
preview again before committing.

Accepted rows, custom values, audit entries and the batch receipt commit in one
transaction. A database failure rolls the accepted batch back. The receipt
stores identifiers/counts/outcomes, not a second copy of the CSV or every field
value. Existing ordinary create receipts and records retain their established
behavior. No background importer or resumable partial-write queue is introduced.

## Lost responses and privacy

A lost response or generic server error can follow a successful commit. Do not
start another batch to resolve uncertainty. Use **Check original receipt** for the
original batch ID. A missing receipt is not proof that nothing happened.
Read-only checks do not replay or duplicate a batch. Exact retries, where used
by the service, are bound to the original data and approval.

The native drawer holds the selected CSV and preview in memory while reviewing.
Close or change view/profile to clear the working content; no raw CSV is saved
in browser storage or server receipts. This is application-state cleanup, not
secure memory erasure. Imported ordinary record values and audit entries remain
ordinary CRM data and may be included in later selected exports or encrypted
content snapshots. Do not import passwords, keys or other secrets into ordinary
fields. See [the protection inventory](PROTECTION.md).

## Export: choose scope and columns

The contact export starts with the current Contacts filters: text, Stage,
Contact type, company, email presence and follow-up state. Stage filters use
linked deals and count each matching contact once. They do not convert deal
stages into a contact property or export complete opportunity records.

Choose the columns deliberately. Defaults contain only the core identity and
Contact type columns. Ordinary Notes and custom values require explicit
selection. Archived custom values remain exportable so retirement does not
silently lose stored information. Protected-note content is never part of this
CSV path, even when its keys are configured.

Export uses one consistent database snapshot and returns the complete matching
set within its stated bound, not just the currently visible page or legacy
500-record list. If a limit is exceeded, narrow the filters/columns; the service
rejects the export instead of silently truncating it. Header names are stable
field keys rather than mutable display labels.

Select **Prepare CSV export**, then explicitly download the prepared file.
Hermes's supported file-download binding stays associated with the originating
connection/profile. The native Save dialog and its result belong to Hermes;
finishing the request is not proof that the file was saved. Cancellation leaves
the prepared plaintext artifact in the profile's private CSV export folder.
Treat both the prepared and downloaded copies according to your data-retention
and device-access policy. No automatic deletion or third-party upload occurs.

An operation reservation and content fingerprint preserve the original artifact
across uncertain responses. **Check original receipt** only inspects that original
receipt/file. Missing or altered files are not silently recreated from newer
records under the same operation identity.

## Spreadsheet-safe text is not byte-identical data

CSV quoting by itself does not prevent formula execution in spreadsheets.
Exports prefix potentially executable leading characters, leading
whitespace/control characters and literal leading apostrophes with an
apostrophe. The result reports how many cells were escaped. This reduces a
common spreadsheet-formula risk; it is not a guarantee for every spreadsheet
program or subsequent transformation. A spreadsheet may remove a text prefix
when saving, so reopening a re-saved file can change how a cell is interpreted.
Delimiter conversion and quote handling can also change boundaries. Do not
assume the original protection survives save/reopen, copy/paste or re-export;
review transformed files before opening them again as active spreadsheet data.

The first increment has no raw unescaped export mode. Import preserves leading
apostrophes verbatim and does not guess whether a file came from this exporter.
Inspect and deliberately remove export escapes before re-importing where
appropriate. This visible tradeoff avoids silently changing unrelated imported
values. No CSV formula is evaluated by the importer. The automated tests verify CSV
writer/parser boundaries and visible transformations, not execution in Excel,
LibreOffice or every spreadsheet import/save workflow. See
[OWASP CSV Injection](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/07-Injection/21-CSV_Injection/)
for the broader risk and why no sanitization strategy is universal.

## Current bounds and remaining work

- UTF-8 comma-separated CSV; a leading UTF-8 BOM and quoted embedded newlines
  are supported. Invalid encoding, malformed/duplicate/blank headers, inconsistent
  row widths and NUL bytes are rejected rather than repaired silently.
- At most 2 MiB of imported UTF-8 content, 1,000 contact rows and 106 columns.
- At most 10,000 exported contacts and 4 MiB of generated CSV. Duplicate checking
  is bounded to 100,000 existing contacts; larger workspaces are rejected.
- At most 20 retained CSV artifacts and 64 MiB in the private CSV export folder.
  Manual cleanup does not remove the operation receipts; the same operation ID
  will not capture a replacement snapshot after cleanup.
- Contact-only native UI. No standalone or agent bulk-transfer tools, xlsx,
  delimiter/encoding auto-detection, relationship imports, updates, automatic
  merge, arbitrary transformations or external CRM sync.
- Generated CSV is a portability file, not a complete backup/restore format.
  It does not preserve IDs, full history, assignments, deal/task relationships,
  custom-field definitions or protected content.

Future work includes reviewed update/merge mappings, relationship-aware deals
and tasks, larger/resumable batches, clearer format interchange, retention
controls and restoration drills. External CRM linking remains deferred in the
[current roadmap](ROADMAP.md). Tests and remaining physical
native-file-dialog checks are recorded in [verification](VERIFICATION.md).
