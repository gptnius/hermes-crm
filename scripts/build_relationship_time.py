"""Embed shared date/time helpers before generating the native panel."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
source = (root / 'shared/relationship-time.js').read_text().rstrip()
start, end = '// BEGIN GENERATED RELATIONSHIP TIME\n', '// END GENERATED RELATIONSHIP TIME\n'
region = start + source + '\n' + end
for name in ['desktop/relationships.js', 'hermes_crm/static/app.js']:
    path = root / name
    current = path.read_text()
    if start in current:
        prefix, tail = current.split(start, 1)
        _, suffix = tail.split(end, 1)
        result = prefix + region + suffix
    else:
        first, rest = current.split('\n', 1)
        result = first + '\n' + region + rest
    if '--check' in sys.argv:
        if result != current:
            raise SystemExit(f'{name}: run scripts/build_relationship_time.py')
    else:
        path.write_text(result)
