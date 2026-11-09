# Public research providers and acceptance

HermesCRM stores records, sourced evidence and reviewable proposals. Hermes owns
search, extraction, browser access and the model. A CRM tool registration or a
saved research assignment does not establish that those host capabilities work.
Keep provider selection configurable; the keyless option below is not a required
provider or a global restriction on interactive agents.

## Optional keyless search on the verified host

These instructions are source-backed for Hermes commit
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. Check the installed version's own
setup interface before applying them elsewhere. No existing application installation or profile was changed
by the isolated verification recorded below.

1. Identify the intended Hermes installation and profile, not just a similarly
   named Python interpreter. Inspect the selected search provider and tool
   availability without exposing credentials. If a suitable provider already
   works, retain it.
2. DDGS is an optional search provider and does not need a Gmail/social login or
   API key. The pinned host declares `ddgs==9.16.0` as its `ddgs` extra. For a
   managed Hermes environment, use its supported package manager rather than
   raw pip. The pinned host's own missing-extra hint is:

   ```sh
   hermes pm install --extra ddgs
   ```

   Run it for the identified installation, preserve existing extras and inspect
   the proposed environment change. Coordinate if that installation is shared
   or an active runtime needs reactivation; do not silently change other profiles.
3. Select DDGS for search through the supported `hermes tools` interface or the
   version's documented configuration flow (`web.search_backend: ddgs`). This is
   an explicit operator choice, not something CRM changes at registration.
4. Reactivate/restart the affected runtime at an agreed time if needed. Verify
   the intended session actually exposes `web_search`, then run one bounded
   public query and inspect the real success/error result. A dependency installed
   into another test venv does not enable the app.

DDGS is **search-only**. `web_extract` needs its own supported provider; selecting
search plus extraction in a research assignment does not install one. Other
configured search/extraction/browser providers remain valid alternatives. A new
account grant, paid service or credential setup needs its own approval. Never
bypass a provider's access restrictions or treat a search snippet as verified
biographical or contact information.

Sources at the exact host revision:
- [Declared web-provider extras](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/pyproject.toml)
- [Supported missing-extra installation hint](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/pm/extras.py)
- [Search/extraction provider capabilities](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/hermes_cli/tools_config_providers.py)
- [Normal web tool and provider loading](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/tools/web_tools.py)

## Isolated real-provider verification, November 9, 2026

On that pinned host, the unmodified `tools.web_tools.web_search_tool` performed
normal plugin discovery, provider registration/selection, the provider subprocess
and normal `success`/`data.web` result normalization. This was not mocked discovery
or a replacement tool. A fresh disposable home and dependency venv used Python
3.14.9, DDGS 9.16.0, httpx 0.28.1, ruamel.yaml 0.18.17 and packaging 26.3.

The fixture selected DDGS for `web.backend` and `web.search_backend`, disabled
keyless rescue and enabled only `web/ddgs`, disabling unrelated bundled plugins
**only inside that disposable test configuration**. Those isolation choices are
not recommended production defaults. The child environment was an explicit
allowlist with no inherited provider tokens. A test audit guard denied path-based
file opens under existing private profile locations, apart from an independently
reviewed read-only Python standard-library code exception for the base interpreter.
This guard is not a general filesystem/network sandbox or security guarantee.

Query: `site:nousresearch.com Nous Research company`, with a three-result limit.
The real callable returned **success=true, three results in 7.14 seconds**, with
empty stderr and normal exit. Only `web/ddgs` loaded. Returned public links were:
- https://nousresearch.com/
- https://nousresearch.com/careers
- https://hermes-agent.nousresearch.com/

An earlier direct-provider query also succeeded, but is a separate, weaker test.
The initial normal-path attempts stopped before searching: first on the fixture's
over-broad standard-library read restriction, then on a missing `packaging`
dependency. The narrow read-only guard correction was independently reviewed;
packaging was installed only into the disposable venv at the host-lock version.
Neither failure is counted as successful host integration.

Disposable homes and the venv were removed; no test process remained and no
listening service was launched. No actual profile, app, credentials, CRM record,
model or provider grant was changed. This proves **isolated normal tool/provider
execution**, not intended-profile enablement, extraction, model reasoning,
complete leadership research or CRM end-to-end acceptance. The three links show
basic company relevance, not a verified executive roster.

## Complete the real workflow separately

After the intended profile's provider is verified, use its authorized model to
research one bounded public subject. Retain source URL/date and uncertainty,
leave unknown details blank, and distinguish public professional information from
private contact data. Verify actual linked records and sourced proposals through
CRM, including after reload. Do not infer every executive or email address from
a partial search. No outreach is necessary for research acceptance.

For timed work, verify the selected preset exposes the needed provider in the
scheduled context too. Check due-time execution, stored evidence/proposals and
reported blockers separately from job creation. See the [scheduled workflow](SCHEDULED_RESEARCH_UI.md)
and [release acceptance plan](RELEASE_READINESS.md). A successful synthetic
scheduler test and a separate successful provider query do not by themselves
prove a model-led scheduled research workflow.
