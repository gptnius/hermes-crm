"""Inline report review into Hermes' single-module runtime; --check in CI."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
source = (root / 'desktop/report-review.js').read_text()
header = 'import { createElement as h, useEffect, useRef, useState } from "react";\n'
if not source.startswith(header):
    raise SystemExit('Unexpected report review import')
start = '// BEGIN GENERATED REPORT REVIEW PANEL\n'
end = '// END GENERATED REPORT REVIEW PANEL\n'
region = start + source[len(header):].lstrip('\n').rstrip() + '\n' + end
path = root / 'desktop/plugin.js'
current = path.read_text()
if start in current:
    prefix, tail = current.split(start, 1)
    _, suffix = tail.split(end, 1)
    result = prefix + region + suffix
else:
    result = current.rstrip() + '\n\n' + region
if '--check' in sys.argv:
    if result != current:
        raise SystemExit('Run scripts/build_report_review_panel.py')
else:
    path.write_text(result)
