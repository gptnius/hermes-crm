"""Native Desktop REST entry point loaded by Hermes' dashboard API mount.

The host imports this file as a standalone module. Load only our own vendored
package, under a path-specific namespace, without modifying global sys.path or
accidentally importing another installed copy/version of the CRM package.
"""
import hashlib
import importlib
import importlib.util
from pathlib import Path
import sys

_package_dir = Path(__file__).resolve().parent.parent / 'hermes_crm'
_namespace = '_hermes_crm_api_' + hashlib.sha256(str(_package_dir).encode()).hexdigest()[:16]
if _namespace not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _namespace, _package_dir / '__init__.py', submodule_search_locations=[str(_package_dir)])
    if _spec is None or _spec.loader is None:
        raise ImportError('Unable to load the local CRM package')
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_namespace] = _module
    try:
        _spec.loader.exec_module(_module)
    except Exception:
        sys.modules.pop(_namespace, None)
        raise
router = importlib.import_module(f'{_namespace}.native_api').router
