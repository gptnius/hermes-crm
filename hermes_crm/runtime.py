"""One per-call, profile-scoped factory shared by native tools and Desktop REST."""
import hashlib
from .domain import CRM, CRMError


def open_profile_crm(*, backend=None, profile=None):
    from plugins.plugin_storage import plugin_data_dir, plugin_db
    if profile is None:
        from hermes_constants import get_hermes_home, profile_name_for_home
        profile = profile_name_for_home(get_hermes_home()) or 'custom'
    if backend is None:
        # Match PluginContext.get_config's settings/legacy-config lookup without
        # constructing a fake tool context or retaining another profile's config.
        from hermes_cli.config import load_config_readonly
        config = load_config_readonly() or {}
        entry = config.get('plugins', {}).get('entries', {}).get('hermes-crm', {})
        settings = entry.get('settings', {})
        legacy = entry.get('config', {})
        backend = settings.get('backend', legacy.get('backend', 'sqlite'))
    data_dir = plugin_data_dir('hermes-crm')
    if backend == 'sqlite':
        return CRM(f'sqlite:///{data_dir / "data.db"}', profile=str(profile),
                   sqlite_creator=lambda: plugin_db('hermes-crm'))
    if backend == 'postgres':
        from agent.secret_scope import get_secret
        url = get_secret('HERMES_CRM_DATABASE_URL') or ''
        if not url.startswith(('postgresql://', 'postgresql+psycopg://')):
            raise CRMError('Profile PostgreSQL URL is missing or invalid; no fallback', 503)
        schema = 'crm_' + hashlib.sha256(str(data_dir.resolve()).encode()).hexdigest()[:24]
        return CRM(url.replace('postgresql://', 'postgresql+psycopg://', 1), profile=str(profile), schema=schema)
    raise CRMError('Choose plugin backend sqlite or postgres explicitly', 503)
