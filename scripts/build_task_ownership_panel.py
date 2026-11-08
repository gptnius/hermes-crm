"""Inline the reviewed task ownership component for Hermes's single-module runtime loader.

The source module is used directly by its React tests. Runtime plugins may only
import react and @hermes/plugin-sdk, so no relative import can be shipped.
Run with --check in verification; no JavaScript is evaluated by this script.
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
source = (root / 'desktop/task-ownership.js').read_text()
header = 'import { createElement as h, useEffect, useRef, useState } from "react";\n'
if not source.startswith(header):
    raise SystemExit('Unexpected task ownership source import; review before changing the bundle')
start = '// BEGIN GENERATED TASK OWNERSHIP PANEL\n'
end = '// END GENERATED TASK OWNERSHIP PANEL\n'
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
        raise SystemExit('Task ownership component is not synchronized; run scripts/build_task_ownership_panel.py')
else:
    path.write_text(result)
