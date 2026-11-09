#!/usr/bin/env python3
"""Run credential-free contract checks. Not a live host/deployment certification."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_JS = {
    'native_research_contract.mjs': 'import-only shared fixture helper',
    'render_relationship_fixtures.mjs': 'render artifact generator, not assertions',
    'native_desktop_work_commands_host.mjs': 'requires separately verified Hermes source',
    'workbench_navigation_layout.cjs': 'requires separately installed Chromium/Playwright',
    'contact_detail_grid_rendered.cjs': 'requires separately installed Chromium/Playwright and browser-capable execution',
}



def disposable_postgres_url(value: str) -> str:
    """Accept only an unambiguous, deliberately narrow disposable-DB URL.

    Query parameters can override libpq's destination even when the URL's
    authority is loopback. Reject queries/fragments, escapes, whitespace and
    ambiguous authority syntax rather than forwarding them to another parser.
    This validates syntax/destination, not whether the server is disposable.
    """
    match = re.fullmatch(
        r'postgresql\+psycopg://'
        r'(?:[A-Za-z0-9_.~-]+(?::[A-Za-z0-9_.~-]+)?@)?'
        r'(?:localhost|127\.0\.0\.1|\[::1\])'
        r'(?::(?P<port>[0-9]{1,5}))?/'
        r'[A-Za-z0-9_][A-Za-z0-9_.-]*', value)
    if not match or (match.group('port') is not None
                     and not 1 <= int(match.group('port')) <= 65535):
        raise argparse.ArgumentTypeError(
            'use a disposable postgresql+psycopg loopback URL with a database '
            'name, optional simple credentials and port 1-65535; queries, '
            'fragments, escapes and whitespace are forbidden')
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('all', 'python', 'javascript', 'generated'), default='all')
    parser.add_argument('--react-root', type=Path, help='existing npm prefix with React and react-test-renderer 19.3.0')
    parser.add_argument('--postgres-url', type=disposable_postgres_url, help='explicit disposable loopback PostgreSQL URL; never inferred from environment')
    args = parser.parse_args()
    if args.suite in ('all', 'javascript') and not args.react_root:
        parser.error('--react-root is required for JavaScript fixture coverage')

    # No provider, cloud, database, host, Node/Python preload or token environment
    # is inherited. This is environment hygiene, not an OS/network sandbox.
    env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR') if key in os.environ}
    env.update(LANG='C.UTF-8', LC_ALL='C.UTF-8', TZ='UTC', CI='true',
               PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONPATH=str(ROOT),
               PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               CRM_EXECUTION_TEST_PYTHON=sys.executable, HERMES_CRM_TEST_PYTHON=sys.executable)
    if args.react_root:
        env['HERMES_CRM_REACT_TEST_ROOT'] = str(args.react_root.resolve())
    if args.postgres_url:
        env['HERMES_CRM_TEST_POSTGRES_URL'] = args.postgres_url
    commands: list[list[str]] = []
    if args.suite in ('all', 'generated'):
        commands += [[sys.executable, str(path.relative_to(ROOT)), '--check']
                     for path in sorted((ROOT / 'scripts').glob('build_*.py'))]
    if args.suite in ('all', 'python'):
        commands.append([sys.executable, '-m', 'pytest', '-q', '-ra', '-p', 'no:cacheprovider', 'tests'])
    if args.suite in ('all', 'javascript'):
        # Fail if an optional React block could otherwise silently skip.
        commands.append(['node', '-e', "const {createRequire}=require('node:module');"
                         "const r=createRequire(process.env.HERMES_CRM_REACT_TEST_ROOT+'/package.json');"
                         "for(const p of ['react','react-test-renderer']) {"
                         "if(r(p+'/package.json').version!=='19.3.0') throw Error(p+' must be 19.3.0');}"])
        for path in sorted((ROOT / 'tests').iterdir()):
            if path.suffix not in ('.mjs', '.cjs'):
                continue
            if path.name in EXCLUDED_JS:
                print(f'EXCLUDED {path.name}: {EXCLUDED_JS[path.name]}', flush=True)
                continue
            commands.append(['node', '--experimental-vm-modules', str(path.relative_to(ROOT))])

    print('Hermes source, guarded model/scheduler E2E and live Desktop are NOT covered.', flush=True)
    print('PostgreSQL: ' + ('explicit disposable server enabled' if args.postgres_url else 'not enabled; pytest reports skips'), flush=True)
    with tempfile.TemporaryDirectory(prefix='hermes-crm-ci-') as directory:
        home = Path(directory)
        env.update(HOME=directory, USERPROFILE=directory, HERMES_HOME=str(home / '.hermes'),
                   XDG_CONFIG_HOME=str(home / 'config'), XDG_CACHE_HOME=str(home / 'cache'),
                   TMPDIR=directory, TMP=directory, TEMP=directory)
        for command in commands:
            print('\n+ ' + ' '.join(command), flush=True)
            try:
                subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=600)
            except subprocess.CalledProcessError as exc:
                return exc.returncode or 1
            except subprocess.TimeoutExpired:
                print('FAILED: check exceeded 600 seconds', file=sys.stderr)
                return 1
    print(f'PASS: {len(commands)} check commands completed (exclusions/skips above remain unverified).', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
