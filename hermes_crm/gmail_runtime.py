"""Optional Gmail wiring. Hermes owns authentication; this module reads no secrets.

Constructing a runtime never discovers an account or invokes a provider. Only
explicit verify/sync handlers may call the reader. No agent tool imports it.
"""
from .domain import CRMError


def _enabled():
    from hermes_cli.config import load_config_readonly
    config = load_config_readonly() or {}
    try:
        entry = config.get('plugins', {}).get('entries', {}).get('hermes-crm', {})
        settings, legacy = entry.get('settings', {}), entry.get('config', {})
        value = settings.get('gmail_history_enabled', legacy.get('gmail_history_enabled', False))
    except (AttributeError, TypeError):
        raise CRMError('Gmail history settings are invalid. No account was accessed.', 503) from None
    if type(value) is not bool:
        raise CRMError('Gmail history must be enabled with an explicit boolean setting.', 503)
    return value


def gmail_runtime(crm):
    """Capture the host-selected profile; never accept routing from request data."""
    from hermes_constants import get_hermes_home
    home = get_hermes_home().resolve()
    workspace = crm.workspace_token()
    enabled = _enabled()

    def guard():
        if get_hermes_home().resolve() != home or crm.workspace_token() != workspace:
            raise CRMError('The Gmail workspace changed. Reopen this contact before continuing.', 409)
        if not _enabled():
            raise CRMError('Optional Gmail history is disabled. No further reads will be dispatched.', 409)

    reader = None
    if enabled:
        from .gmail_reader import GmailReader
        reader = GmailReader()
    return {'enabled': enabled, 'reader': reader, 'guard': guard}
