"""Inline the testable storage settings component for the native single-module loader."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
path = root / 'desktop/plugin.js'
current = path.read_text()
source = (root / 'desktop/storage-settings.js').read_text()
first, source = source.split('\n', 1)
assert first == 'import { createElement as h, useEffect, useRef, useState } from "react";'
assert not any(line.startswith('import ') for line in source.splitlines())
start, end = '// BEGIN GENERATED STORAGE SETTINGS PANEL\n', '// END GENERATED STORAGE SETTINGS PANEL\n'
region = start + source.strip() + '\n' + end
if start in current:
    prefix, tail = current.split(start, 1)
    _, suffix = tail.split(end, 1)
    result = prefix + region + suffix
else:
    result = current.rstrip() + '\n\n' + region
if '--check' in sys.argv:
    assert current == result, 'Run scripts/build_storage_settings_panel.py'
else:
    path.write_text(result)
