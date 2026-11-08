"""Inline the reviewed relationships component for Hermes's single-module runtime loader.

The source module is used directly by its React tests. Runtime plugins may only
import react and @hermes/plugin-sdk, so no relative import can be shipped.
Run with --check in verification; no JavaScript is evaluated by this script.
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
source = (root / 'desktop/relationships.js').read_text()
header = 'import { createElement as h, useEffect, useRef, useState } from "react";\n'
if not source.startswith(header):
    raise SystemExit('Unexpected relationships source import; review before changing the bundle')
start = '// BEGIN GENERATED RELATIONSHIPS PANEL\n'
end = '// END GENERATED RELATIONSHIPS PANEL\n'
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
        raise SystemExit('Relationship component is not synchronized; run scripts/build_relationship_panel.py')
else:
    path.write_text(result)
