"""Inline the reviewed pane-scoped Workbench stylesheet for the single-module loader."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
p = root / 'desktop/plugin.js'
current = p.read_text()
css = (root / 'desktop/design-system.css').read_text().strip()
if '`' in css or '${' in css:
    raise SystemExit('Stylesheet cannot contain JavaScript template expressions')
start, end = 'const CSS = `', '`;\n\nfunction Shell'
if current.count(start) != 1 or current.count(end) != 1:
    raise SystemExit('Ambiguous stylesheet markers')
prefix, tail = current.split(start, 1)
_, suffix = tail.split(end, 1)
result = prefix + start + '\n' + css + '\n' + end + suffix
if '--check' in sys.argv:
    if result != current:
        raise SystemExit('Stylesheet not synchronized; run scripts/build_design_system.py')
else:
    p.write_text(result)
