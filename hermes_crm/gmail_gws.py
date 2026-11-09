"""Opt-in adapter for a trusted, explicitly captured Hermes Workspace connection.

No discovery, credential reads, auth, subprocess or account access on construction.
Only reviewed gws 0.22.5 behavior is supported (source cd3697e07eb520056dcf142d0c7439bbb9ba32e9).
A version string is compatibility evidence, NOT binary provenance: operators must
supply a trusted executable. Callers own enablement, approval and profile guards.
Stat fingerprints detect observable rebinding, not an atomic credential lease.
Trusted operators must not change the connection during a request.

The CLI necessarily reads the explicitly supplied credential and may refresh it
into its own temporary encrypted cache. The adapter never reads/copies credentials.
The reviewed file keyring backend skips password get/set (it constructs an Entry).
All CLI config/key/cache writes go into a disposable private directory, not Hermes.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlsplit

from .gmail_reader import GmailReadError, HEADER_NAMES, MESSAGE_FIELDS, validate_email

SUPPORTED_VERSION = '0.22.5'
VERSION_OUTPUT = b'gws 0.22.5\nThis is not an officially supported Google product.'
REVIEWED_SOURCE = 'cd3697e07eb520056dcf142d0c7439bbb9ba32e9'
LIST_FIELDS = 'messages(id,threadId),nextPageToken,resultSizeEstimate'
HISTORY_FIELDS = ('history(id,messages(id,threadId),messagesAdded(message(id,threadId)),'
                  'messagesDeleted(message(id,threadId)),labelsAdded(message(id,threadId),labelIds),'
                  'labelsRemoved(message(id,threadId),labelIds)),nextPageToken,historyId')
MAX_OUTPUT = 1_048_576


@dataclass(frozen=True)
class GwsResponse:
    status: int
    headers: dict
    body: bytes


def _fail(code):
    raise GmailReadError(code) from None


def _path(value):
    p = Path(value)
    if not p.is_absolute() or '..' in p.parts:
        _fail('gws_invalid_configuration')
    # Reject symlinks in all ancestors, including a swapped parent directory.
    for part in (p, *p.parents):
        if part.is_symlink():
            _fail('gws_invalid_configuration')
    return p


def _fingerprint(path, *, executable=False):
    try:
        p = _path(path)
        s = p.stat()
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
            _fail('gws_connection_unavailable')
        if executable:
            if s.st_mode & 0o022 or not os.access(p, os.X_OK):
                _fail('gws_invalid_configuration')
        elif s.st_uid != os.getuid() or s.st_mode & 0o077:
            _fail('gws_connection_unavailable')
        return (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_size,
                s.st_mtime_ns, s.st_ctime_ns)
    except (OSError, ValueError, TypeError):
        _fail('gws_connection_unavailable')


def _json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                _fail('gws_invalid_output')
            out[k] = v
        return out
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: _fail('gws_invalid_output'))
    except (ValueError, UnicodeError):
        _fail('gws_invalid_output')
    if not isinstance(value, dict):
        _fail('gws_invalid_output')
    return value


class ExistingWorkspaceGwsTransport:
    """Trusted service configuration only; never expose these paths to request JSON."""

    def __init__(self, *, executable, connection_file, work_root, expected_mailbox, guard):
        if os.name != 'posix' or not callable(guard):
            _fail('gws_unsupported_platform')
        self.executable = _path(executable)
        self.connection_file = _path(connection_file)
        self.work_root = _path(work_root)
        if self.connection_file.name != 'google_token.json':
            _fail('gws_invalid_configuration')
        self.expected_mailbox = validate_email(expected_mailbox)
        self.guard = guard
        self.connection_fingerprint = _fingerprint(self.connection_file)
        self.executable_fingerprint = _fingerprint(self.executable, executable=True)
        self._root_check()
        self._session_lock = threading.Lock()
        self._session = None

    def _root_check(self):
        try:
            s = _path(self.work_root).stat()
            if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
                _fail('gws_invalid_configuration')
        except OSError:
            _fail('gws_invalid_configuration')

    def _check(self):
        try:
            allowed = self.guard() is not False
        except Exception:
            allowed = False
        if not allowed:
            _fail('cancelled_or_profile_changed')
        if _fingerprint(self.connection_file) != self.connection_fingerprint:
            _fail('gws_connection_changed')
        if _fingerprint(self.executable, executable=True) != self.executable_fingerprint:
            _fail('gws_executable_changed')
        self._root_check()

    def _command(self, method, url):
        if method != 'GET' or not isinstance(url, str) or len(url) > 16384:
            _fail('gws_request_not_allowed')
        try:
            u = urlsplit(url)
            if (u.scheme != 'https' or u.netloc != 'gmail.googleapis.com' or u.fragment or
                    any(ord(c) < 33 for c in url)):
                _fail('gws_request_not_allowed')
            base = '/gmail/v1/users/' + quote(self.expected_mailbox, safe='')
            if not u.path.startswith(base + '/'):
                _fail('gws_request_not_allowed')
            path = u.path[len(base):]
            pairs = parse_qsl(u.query, keep_blank_values=True, strict_parsing=True,
                              max_num_fields=20, errors='strict')
        except (ValueError, UnicodeError):
            _fail('gws_request_not_allowed')
        params = {}
        headers = []
        for k, v in pairs:
            if k == 'metadataHeaders':
                headers.append(v)
            elif k in params:
                _fail('gws_request_not_allowed')
            else:
                params[k] = v
        if path == '/profile':
            cmd = ['getProfile']
            valid = (set(params) == {'fields'} and
                     params['fields'] in ('emailAddress', 'emailAddress,historyId') and not headers)
        elif path == '/messages':
            cmd = ['messages', 'list']
            valid = (set(params) in ({'q', 'fields', 'maxResults', 'includeSpamTrash'},
                                    {'q', 'fields', 'maxResults', 'includeSpamTrash', 'pageToken'})
                     and params.get('fields') == LIST_FIELDS and params.get('maxResults') == '100'
                     and params.get('includeSpamTrash') == 'false' and not headers
                     and self._query_allowed(params.get('q', '')))
        elif re.fullmatch(r'/messages/[A-Za-z0-9_-]{1,128}', path):
            cmd = ['messages', 'get']
            valid = (set(params) == {'format', 'fields'} and params.get('format') == 'metadata'
                     and params.get('fields') == MESSAGE_FIELDS and tuple(headers) == HEADER_NAMES)
            params['id'] = path.rsplit('/', 1)[1]
            params['metadataHeaders'] = headers
        elif path == '/history':
            cmd = ['history', 'list']
            valid = (set(params) in ({'fields', 'startHistoryId', 'maxResults'},
                                    {'fields', 'startHistoryId', 'maxResults', 'pageToken'})
                     and params.get('fields') == HISTORY_FIELDS and params.get('maxResults') == '100'
                     and re.fullmatch(r'[1-9][0-9]{0,39}', params.get('startHistoryId', ''))
                     and not headers)
        else:
            _fail('gws_request_not_allowed')
        if 'pageToken' in params and not re.fullmatch(r'[A-Za-z0-9_\-+=/]{1,4096}', params['pageToken']):
            valid = False
        if not valid:
            _fail('gws_request_not_allowed')
        if 'maxResults' in params:
            params['maxResults'] = 100
        if 'includeSpamTrash' in params:
            params['includeSpamTrash'] = False
        params['userId'] = self.expected_mailbox
        return ['gmail', 'users', *cmd, '--params', json.dumps(params, separators=(',', ':')),
                '--format', 'json', '--api-version', 'v1']

    @staticmethod
    def _query_allowed(query):
        m = re.fullmatch(r'(?:\{from:([^ ]+) to:([^ ]+) cc:([^ ]+)\} )?'
                         r'after:([0-9]{1,12}) before:([0-9]{1,12}) -in:drafts', query)
        if not m:
            return False
        if m[1] is not None:
            try:
                if not m[1] == m[2] == m[3] or validate_email(m[1]) != m[1]:
                    return False
            except GmailReadError:
                return False
        return 0 <= int(m[4]) < int(m[5]) <= 253402300800 and int(m[5]) - int(m[4]) <= 31 * 86400

    def _run(self, args, env, cwd, deadline):
        self._check()
        if time.monotonic() >= deadline:
            _fail('gws_timeout')
        process = None
        selector = selectors.DefaultSelector()
        out = bytearray()
        counts = {'out': 0, 'err': 0}
        try:
            process = subprocess.Popen([str(self.executable), *args], cwd=cwd, env=env,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, shell=False, start_new_session=True,
                                       close_fds=True)
            for stream, label in ((process.stdout, 'out'), (process.stderr, 'err')):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, label)
            while selector.get_map() or process.poll() is None:
                self._check()
                if time.monotonic() >= deadline:
                    _fail('gws_timeout')
                for key, _ in selector.select(min(.05, max(0, deadline - time.monotonic()))):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    counts[key.data] += len(chunk)
                    if counts[key.data] > MAX_OUTPUT:
                        _fail('gws_output_limit')
                    if key.data == 'out':
                        out.extend(chunk)
            self._check()
            if time.monotonic() >= deadline:
                _fail('gws_timeout')
            return process.returncode, bytes(out)
        except OSError:
            _fail('gws_execution_failed')
        finally:
            selector.close()
            if process is not None:
                # Kill the owned session even if its leader exited with inherited pipes open.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                process.stdout.close()
                process.stderr.close()

    @contextmanager
    def session(self, *, max_seconds=300):
        """Reuse ephemeral cache only within one explicitly owned bounded scan.

        Nested/concurrent contexts and calls from another thread are rejected.
        Exceptions poison and immediately remove the cache, even if the caller
        catches them inside the context. A new context always starts empty.
        The caller must use ``with``; no default persistent session is created.
        """
        if (type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
                or not 0 < max_seconds <= 300):
            _fail('gws_invalid_timeout')
        if not self._session_lock.acquire(blocking=False):
            _fail('gws_session_in_use')
        temporary = None
        try:
            self._check()
            temporary = tempfile.TemporaryDirectory(prefix='gmail-gws-', dir=self.work_root)
            cwd = Path(temporary.name)
            (cwd / '.env').write_text('', encoding='ascii')
            for name in ('home', 'config', 'cache', 'tmp'):
                (cwd / name).mkdir(mode=0o700)
            # Start empty: no ambient TOKEN, ADC, provider, proxy, loader,
            # logging or configuration variables survive.
            env = {'HOME': str(cwd / 'home'), 'XDG_CONFIG_HOME': str(cwd / 'config'),
                   'XDG_CACHE_HOME': str(cwd / 'cache'), 'TMPDIR': str(cwd / 'tmp'),
                   'GOOGLE_WORKSPACE_CLI_CONFIG_DIR': str(cwd / 'config'),
                   'GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE': str(self.connection_file),
                   'GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND': 'file', 'NO_COLOR': '1',
                   'LANG': 'C.UTF-8'}
            self._session = {'owner': threading.get_ident(), 'cwd': cwd, 'env': env,
                             'temporary': temporary, 'verified': False, 'failed': False,
                             'deadline': time.monotonic() + max_seconds}
            yield self
            self._check()
        except OSError:
            _fail('gws_execution_failed')
        finally:
            try:
                if temporary is not None:
                    temporary.cleanup()
            finally:
                self._session = None
                self._session_lock.release()

    def __call__(self, method, url, *, timeout):
        state = self._session
        if state is None:
            with self.session():
                return self(method, url, timeout=timeout)
        if state['owner'] != threading.get_ident():
            _fail('gws_session_in_use')
        if state['failed']:
            _fail('gws_session_failed')
        try:
            args = self._command(method, url)
            if type(timeout) not in (float, int) or not math.isfinite(timeout) or not 0 < timeout <= 120:
                _fail('gws_invalid_timeout')
            self._check()
            deadline = min(time.monotonic() + timeout, state['deadline'])
            if not state['verified']:
                code, output = self._run(['--version'], state['env'], state['cwd'], deadline)
                if code != 0 or output.replace(b'\r\n', b'\n') not in (VERSION_OUTPUT, VERSION_OUTPUT + b'\n'):
                    _fail('gws_unsupported_version')
                state['verified'] = True
            code, output = self._run(args, state['env'], state['cwd'], deadline)
            self._check()
            value = _json(output)
            if code == 0 and 'error' not in value:
                return GwsResponse(200, {'Content-Type': 'application/json'}, output)
            error = value.get('error')
            if code == 1 and isinstance(error, dict) and type(error.get('code')) is int:
                status = error['code']
                if 400 <= status <= 599:
                    return GwsResponse(status, {'Content-Type': 'application/json'}, b'{}')
            if code == 2:
                _fail('gws_auth_unavailable')
            _fail('gws_execution_failed')
        except BaseException:
            state['failed'] = True
            state['temporary'].cleanup()
            raise
