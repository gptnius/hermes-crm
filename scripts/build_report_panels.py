"""Deterministically inline local React panels for Hermes's single-module loader.

No JavaScript is evaluated. Native plugin imports remain limited to the two
host-provided modules. Source modules remain directly testable.
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
path = root / 'desktop/plugin.js'
current = path.read_text()
result = current
for filename, label in [('reports.js', 'FLEXIBLE REPORTS'), ('contact-log.js', 'CONTACT LOG')]:
    source = (root / 'desktop' / filename).read_text()
    first, source = source.split('\n', 1)
    if first not in ('import { createElement as h, useEffect, useRef, useState } from "react";',
                     "import { createElement as h, useEffect, useRef, useState } from 'react';"):
        raise SystemExit('Unexpected panel import: ' + filename)
    if any(line.startswith('import ') for line in source.splitlines()):
        raise SystemExit('Additional imports must be reviewed: ' + filename)
    start, end = '// BEGIN GENERATED ' + label + ' PANEL\n', '// END GENERATED ' + label + ' PANEL\n'
    region = start + source.strip() + '\n' + end
    if start in result:
        if result.count(start) != 1 or result.count(end) != 1:
            raise SystemExit('Ambiguous panel markers')
        prefix, tail = result.split(start, 1)
        _, suffix = tail.split(end, 1)
        result = prefix + region + suffix
    else:
        result = result.rstrip() + '\n\n' + region
if '--check' in sys.argv:
    if result != current:
        raise SystemExit('Panels are not synchronized; run scripts/build_report_panels.py')
else:
    path.write_text(result)
