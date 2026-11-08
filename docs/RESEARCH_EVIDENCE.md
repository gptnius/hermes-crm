# Research evidence and reviewed note additions

Research helps retain **what a source said**, **what you infer**, and **what you
chose to add to a record** as separate things. Open a saved Company or Contact
and choose **Research**. This panel stores supplied information; it does not
browse websites, research a person automatically, send email or upload files.

## Save evidence

1. Choose **Add evidence** in native Desktop, or **Add manual evidence** in the
   standalone interface.
2. Enter one research question, one HTTPS source URL and a source title.
3. Enter the time you observed the information, including its UTC offset. It
   starts blank. **Use current time** is an explicit shortcut, appropriate only
   when you observed it now. The preview is readable UTC; the supplied offset is
   retained. Leave the publication date blank when unknown.
4. Put statements attributed to the source in **Source claims** and your own
   deductions in **Hypotheses**. The manual forms use one entry per line.
5. Save the supplied evidence. The exact record version is checked; if it
   changed, review the current record before submitting a corrected request.

A source claim is not an independently verified fact. Observation/publication
fields are supplied claims; server recording time is separate. A server-derived
channel such as Hermes, Desktop or web identifies the adapter, not a verified
person or proof that an agent visited a website.

Each packet has one source and immutable content. Corrections require a new
packet. Archive keeps the original packet; Restore makes it active again. Both
change its lifecycle version, so an older proposal review does not silently
become current again. No permanent deletion is included.

## Prepare and apply a note addition

1. Review an active evidence packet and choose **Prepare addition** or
   **Prepare note addition**.
2. Enter the exact ordinary-note addition. Keep citations and uncertainty clear.
   Preparation saves a proposal, not a change to the Company/Contact.
3. Open the proposal and inspect the exact record/version, evidence, current
   Notes, addition and proposed result. The preview is checked against saved
   hashes. It is unavailable when the target or evidence changed.
4. Choose the explicit **Apply** action only after reviewing the content, or
   **Dismiss proposal** to retain it without applying.

Application appends two newlines after nonempty existing Notes, followed by the
exact addition. It preserves accepted whitespace and Unicode and rejects a final
note above 10,000 characters. It does not truncate, overwrite unrelated text or
silently rebase a stale proposal. An archived Company cannot receive new
submissions or note applications. Contacts have no matching archive feature.

One proposal can apply once. Application, record version/update time,
administrative audit, proposal disposition and receipt commit together. Applying
changes **last edit**, not last interaction. It does not complete a task,
acknowledge a separate agent-run result, send a communication or prove research
execution. Use those workflows separately.

## Work with Hermes

The plugin adds five separate tools:

- `crm_research_evidence_submit`: save a supplied packet for a current exact
  Company/Contact.
- `crm_research_note_propose`: prepare an exact addition from existing evidence.
- `crm_research_evidence_list` and `crm_research_proposal_list`: page reduced
  metadata for an exact record.
- `crm_research_evidence_get`: explicitly read one full evidence packet.

These use separate `crm_research_read` and `crm_research_write` toolsets. Existing
frozen scheduled assignments gain none of them. There is no research apply,
archive, dismiss or private-current-note-preview agent tool. Existing separately
authorized ordinary CRUD/detail tools remain available; this is not a global
barrier against agent edits or an access-control system.

A useful interactive instruction is:

> Using only your already-authorized public research capabilities, examine this
> saved Company or Contact and the question I specify. Do not log in or contact
> anyone. Keep unknown details unknown. Store source claims and hypotheses with
> their URLs and observation times, then propose a concise cited note addition.
> Do not apply it. Report any source-access or capability limitation.

Provide the exact record reference and question. Whether the current agent can
actually browse or search depends on its existing host configuration and
permissions. This plugin does not enable those capabilities, bypass a source's
restrictions or provide a complete live-research workflow by itself. No Gmail or
social account connection is needed merely to store supplied evidence.

## Stale, unknown and historical outcomes

- **Pending** means a proposal has not been applied or dismissed. It is not an
  execution queue.
- **Stale** means the source lifecycle, record version or note hash no longer
  matches. Review current evidence and prepare a new proposal. Do not change
  version numbers by hand to force the old proposal through.
- **Applied/Dismissed** records the original disposition. Later record edits may
  make its displayed target version historical.
- **Unknown outcome** means the application has not verified the response.
  Check the original operation or explicitly retry its exact unchanged request
  with the same key. Do not create another key to repeat it.

A confirmed receipt proves that original operation committed. It does not prove
that the current note remains unchanged. Definitive rejection retains a draft
for fresh review and a deliberate corrected request; no automatic write occurs.
In-app recovery is scoped to the original authority and is not a durable
cross-device/offline draft store. Closing the app can lose unsent local drafts;
server receipts persist.

## Source and privacy limits

HTTPS syntax is not proof of a public, accurate or safe source. The application
rejects credentials, malformed URL encodings and common credential/signed-link
parameters, but heuristic checks cannot detect every secret. Never paste private
or signed links, passwords or access tokens. Ordinary query/fragment components
are retained rather than silently replacing the cited resource.

Sources are plain text, not executable instructions. No network fetch, DNS
lookup, preview or favicon request is made by this feature. Opening a source
link is an explicit separate action. It does not grant the agent permission to
read that source or its attachments.

Evidence and ordinary Notes are plaintext in the live datastore. Proposals and
proposal-creation receipts retain the addition and before/after hashes.
Application receipts retain identity, disposition and hashes. None automatically
copies the full old/new Notes. A fresh review reads those note values transiently; hashes
cannot reconstruct them after later edits. The current-note preview cannot open
protected notes. User/agent-submitted research may also remain in existing
Hermes conversation/tool logs; this feature does not erase those separate copies.

The explicit encrypted content export includes scoped evidence, proposals and
receipts. It remains neither a complete backup nor a tested restore workflow,
and does not encrypt the live datastore. Read [protection limits](PROTECTION.md).

## Bounds and future work

Packets are limited to a 1,000-character question, a 2,048-character URL, a
200-character title, at least one and at most ten source claims, at most ten
hypotheses, and 2,000 characters per entry. Total packet size is at most 32 KiB.
Unsupported control/format characters are rejected rather than silently removed.
Lists are paged and do not automatically fetch full claim or note text.

Automatic source verification, managed file attachments, research task proposals,
full agent-run review closure, email sending, web extraction and broader scheduled
permissions remain separate work. See the [implementation plan](RESEARCH_EVIDENCE_PLAN.md),
[file plan](ATTACHMENTS_PLAN.md), [agent-work roadmap](NEXT_RELEASE_PLAN.md) and
[verification](VERIFICATION.md) for their boundaries and test status.
