"""Inline scheduled research into Hermes' single-module runtime; --check in CI."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
source = (root / 'desktop/scheduled-research.js').read_text()
header = 'import { createElement as h, useEffect, useRef, useState } from "react";\n'
if not source.startswith(header):
    raise SystemExit('Unexpected scheduled research import')
start = '// BEGIN GENERATED SCHEDULED RESEARCH PANEL\n'
end = '// END GENERATED SCHEDULED RESEARCH PANEL\n'
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
        raise SystemExit('Run scripts/build_scheduled_research_panel.py')
else:
    path.write_text(result)
