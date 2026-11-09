"""Host-selected existing connection. Construction and reads never run gws."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import time
from .domain import CRMError
from .gmail_gws import ExistingWorkspaceGwsTransport
from .gmail_incremental import IncrementalGmailReader

PINNED_VERSION = '0.22.5'


def host_selection():
    from hermes_constants import get_hermes_home
    from hermes_cli.config import load_config_readonly
    home = get_hermes_home().resolve()
    try:
        entry = (load_config_readonly() or {}).get('plugins', {}).get('entries', {}).get('hermes-crm', {})
        settings, legacy = entry.get('settings', {}), entry.get('config', {})
        enabled = settings.get('gmail_bridge_enabled', legacy.get('gmail_bridge_enabled', False))
        executable = settings.get('gmail_bridge_gws_path', legacy.get('gmail_bridge_gws_path', ''))
        if type(enabled) is not bool or not isinstance(executable, str):
            raise ValueError()
        if executable and (not Path(executable).is_absolute() or '..' in Path(executable).parts):
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        raise CRMError('Invalid Gmail bridge configuration', 503) from None
    return home, enabled, executable


class GmailBridgeRuntime:
    def __init__(self, crm, *, selection=host_selection, transport_factory=ExistingWorkspaceGwsTransport,
                 reader_factory=IncrementalGmailReader, clock=time.time):
        self._source_stamps = None
        self.crm, self.selection = crm, selection
        self.home, self.enabled, self.executable = selection()
        self.profile, self.workspace = crm.profile, crm.existing_workspace_token()
        self.transport_factory, self.reader_factory, self.clock = transport_factory, reader_factory, clock
        self.selector_fingerprint = hashlib.sha256(json.dumps([
            str(self.home), self.profile, 'explicit_existing_workspace_file',
            str(self.home / 'google_token.json'), self.executable, PINNED_VERSION
        ], separators=(',', ':')).encode()).hexdigest()

    def setup(self):
        return dict(available=self.enabled and bool(self.executable), host_enabled=self.enabled,
                    configured=bool(self.executable), cli_version=PINNED_VERSION,
                    installation_verified=False, polling='while_crm_open',
                    storage='selected_crm_backend', metadata_only=True,
                    notice='Explicit approval is required before verifying or reading the existing mailbox. Unrelated metadata may be examined in memory. No bodies, attachments or sending.')

    def host_guard(self):
        if (self.selection() != (self.home, self.enabled, self.executable) or
                self.crm.profile != self.profile or
                not self.enabled or not self.executable):
            raise CRMError('Gmail bridge context changed or unavailable', 409)
        if self._source_stamps is not None and self._stamps() != self._source_stamps:
            raise CRMError('Gmail bridge connection changed', 409)
        return True

    def _stamps(self):
        try:
            result = []
            for path in (self.executable, self.home / 'google_token.json'):
                stat = Path(path).stat()
                result.append((stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
            return tuple(result)
        except OSError:
            raise CRMError('Gmail bridge connection unavailable', 503) from None

    def guard(self):
        self.host_guard()
        if self.crm.existing_workspace_token() != self.workspace:
            raise CRMError('Gmail bridge workspace changed', 409)
        return True

    @contextmanager
    def reader(self, mailbox, *, lease_guard=lambda: True):
        def guard():
            return self.guard() is True and lease_guard() is True
        guard()
        self._source_stamps = self._stamps()
        # Only explicit provider handlers enter here. No credential bytes are opened.
        with tempfile.TemporaryDirectory(prefix='hermes-crm-gws-') as directory:
            # Canonicalize only our newly created directory: system temp paths
            # may use a symlink spelling (for example macOS /var). Supplied
            # binary and connection paths retain the transport's strict policy.
            work_root = Path(directory).resolve(strict=True)
            work_root.chmod(0o700)
            transport = self.transport_factory(executable=self.executable,
                connection_file=self.home / 'google_token.json', work_root=work_root,
                expected_mailbox=mailbox, guard=guard)
            with transport.session():
                yield self.reader_factory(transport), guard


def gmail_bridge_runtime(crm):
    return GmailBridgeRuntime(crm)
