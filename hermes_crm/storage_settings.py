"""Native, host-scoped storage diagnostics. Never initialize or migrate CRM data."""
import asyncio
from contextlib import suppress
from contextvars import ContextVar
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3

from fastapi import APIRouter, HTTPException, Request

from .runtime import configured_backend

router = APIRouter()
_TOKEN_KEY = secrets.token_bytes(32)
_PROBING = ContextVar('hermes_crm_storage_probe', default=False)
PROBE_TIMEOUT = 8


class _PrivateProbeLogs(logging.Filter):
    def filter(self, record):
        # Psycopg's DEBUG connection diagnostics contain hostnames. Suppress
        # only this task's probe logs, not unrelated host/database operations.
        return not _PROBING.get()


logging.getLogger('psycopg').addFilter(_PrivateProbeLogs())


def _selection():
    from hermes_constants import get_hermes_home
    home = Path(get_hermes_home())
    backend = configured_backend()
    url = ''
    if backend == 'postgres':
        from agent.secret_scope import get_secret
        url = get_secret('HERMES_CRM_DATABASE_URL') or ''
    if backend not in ('sqlite', 'postgres'):
        backend = 'invalid'
    if not isinstance(url, str):
        url = ''
    basis = json.dumps([str(home.resolve()), backend, url], separators=(',', ':'))
    token = hmac.new(_TOKEN_KEY, basis.encode(), hashlib.sha256).hexdigest()
    return backend, url, home / 'plugin-data' / 'hermes-crm' / 'data.db', token


def _configuration(backend, url):
    if backend == 'invalid':
        return 'invalid_backend'
    if backend == 'postgres' and not url:
        return 'missing_url'
    if backend == 'postgres' and not url.startswith(('postgresql://', 'postgresql+psycopg://')):
        return 'invalid_url'
    return 'configured'


def _query_guard(request):
    # The host may retain its already-resolved profile routing parameter. No
    # URL, schema, backend or filesystem destination comes from this request.
    if set(request.query_params) - {'profile'}:
        raise HTTPException(400, detail={'error': 'Unsupported storage check parameters.'})


def _read_selection():
    try:
        return _selection()
    except Exception:
        raise HTTPException(503, detail={'error': 'Storage configuration is unavailable. Open Hermes plugin settings.'}) from None


@router.get('/storage/status')
def storage_status(request: Request):
    _query_guard(request)
    backend, url, _, token = _read_selection()
    return {'backend': backend, 'configuration': _configuration(backend, url), 'selection_token': token}


def _sqlite_probe(path):
    # mode=ro neither creates a missing database nor runs host WAL setup. No
    # immutable flag: it would ignore live WAL data. SQLite may maintain its
    # own shared-memory sidecar when opening an existing WAL database.
    if not path.is_file():
        return 'not_initialized'
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchone()
        return 'connected'
    finally:
        connection.close()


class UnsupportedProbe(Exception):
    """A custom/ambient credential flow needs operator verification, not a probe."""


def _postgres_parameters(url):
    import psycopg
    # Never let this new diagnostic select ambient libpq identity/destination
    # defaults. Do not mutate the process environment shared by the host.
    if any(key.startswith('PG') for key in os.environ):
        raise UnsupportedProbe
    params = psycopg.conninfo.conninfo_to_dict(url.replace('postgresql+psycopg://', 'postgresql://', 1))
    required = {'host', 'dbname', 'user', 'password'}
    allowed = required | {'port', 'sslmode', 'sslrootcert', 'sslcrl', 'sslcrldir',
                          'channel_binding', 'application_name', 'connect_timeout', 'options'}
    if (not required.issubset(params) or any(not params[key] for key in required)
            or set(params) - allowed or ',' in params['host'] or params['host'].startswith('/')
            or '=' in params['dbname']):
        raise UnsupportedProbe
    supported = {option.keyword for option in psycopg.pq.Conninfo.get_defaults()}
    if not {b'sslcertmode', b'require_auth'}.issubset(supported):
        raise UnsupportedProbe
    # Permit only the explicit password (or a server accepting no auth), never
    # .pgpass, default client certificates, OS Kerberos/SSPI or OAuth identity.
    params.update(passfile=os.devnull, hostaddr='', sslcertmode='disable',
                  gssencmode='disable', require_auth='scram-sha-256,md5,password,none')
    params.update(connect_timeout=5,
                  options='-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=1000')
    return params


async def _postgres_roundtrip(url, holder):
    import psycopg
    connection = await psycopg.AsyncConnection.connect(
        **_postgres_parameters(url), autocommit=True, prepare_threshold=None)
    holder.append(connection)
    try:
        async with connection.cursor() as cursor:
            await cursor.execute('SELECT 1')
            if await cursor.fetchone() != (1,):
                raise ValueError('Unexpected connection check result')
    finally:
        await connection.close()


async def _postgres_probe(url):
    holder = []
    task = asyncio.create_task(_postgres_roundtrip(url, holder))
    try:
        done, _ = await asyncio.wait({task}, timeout=PROBE_TIMEOUT)
        if not done:
            raise TimeoutError
        await task
        return 'connected'
    finally:
        # Close before cancellation so psycopg does not issue a second network
        # cancellation connection and wait beyond the UI check's deadline.
        for connection in holder:
            with suppress(Exception):
                await connection.close()
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task


@router.post('/storage/check')
async def storage_check(request: Request):
    _query_guard(request)
    # Parse ourselves so rejected caller data is never reflected in validation
    # errors. The client sends only this opaque token, never credentials.
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, detail={'error': 'Reload storage settings before checking.'}) from None
    if (not isinstance(body, dict) or set(body) != {'selection_token'}
            or not isinstance(body['selection_token'], str) or not re.fullmatch('[a-f0-9]{64}', body['selection_token'])):
        raise HTTPException(400, detail={'error': 'Reload storage settings before checking.'})
    backend, url, path, token = _read_selection()
    if not hmac.compare_digest(body['selection_token'], token):
        raise HTTPException(409, detail={'error': 'Storage selection changed. Reload storage settings before checking.'})
    result = _configuration(backend, url)
    if result == 'configured':
        guard = _PROBING.set(True)
        try:
            result = await _postgres_probe(url) if backend == 'postgres' else await asyncio.to_thread(_sqlite_probe, path)
        except ImportError:
            result = 'driver_missing'
        except UnsupportedProbe:
            result = 'unsupported_connection'
        except TimeoutError:
            result = 'timeout'
        except Exception:
            result = 'unavailable'
        finally:
            _PROBING.reset(guard)
    # Settings/secret changes during an explicit check invalidate its result.
    if _read_selection()[3] != token:
        raise HTTPException(409, detail={'error': 'Storage selection changed. Reload storage settings before checking.'})
    return {'backend': backend, 'selection_token': token, 'result': result, 'readiness_checked': False}
