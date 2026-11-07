"""Generate a reviewed path-only brand component without a network/font runtime."""
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET
root = Path(__file__).resolve().parents[1]
svg = ET.fromstring((root / 'assets/brand/hermescrm-wordmark.svg').read_text())
paths = [node.attrib['d'] for node in svg if node.tag == '{http://www.w3.org/2000/svg}path']
if len(paths) != len(svg) or not paths:
    raise SystemExit('Only reviewed SVG paths are accepted')
body = '''export function Wordmark() {
  return h("svg", { className: "hc-wordmark-svg", viewBox: %s, width: 180, height: 24,
    fill: "currentColor", role: "img", "aria-label": "HermesCRM", focusable: false },
    %s);
}''' % (json.dumps(svg.attrib['viewBox']), ',\n    '.join('h("path", { d: %s })' % json.dumps(d) for d in paths))
p = root / 'desktop/plugin.js'
s = p.read_text()
start, end = '// BEGIN GENERATED WORDMARK\n', '// END GENERATED WORDMARK\n'
region = start + body + '\n' + end
if start in s:
    if s.count(start) != 1 or s.count(end) != 1:
        raise SystemExit('Ambiguous brand markers')
    pre, tail = s.split(start)
    _, after = tail.split(end)
    result = pre + region + after
else:
    result = s.replace('const CSS = `', region + '\nconst CSS = `', 1)
if '--check' in sys.argv:
    if s != result:
        raise SystemExit('Wordmark not synchronized')
else:
    p.write_text(result)
if (root / 'hermes_crm/static/hermescrm-wordmark.svg').read_bytes() != (root / 'assets/brand/hermescrm-wordmark.svg').read_bytes():
    raise SystemExit('Standalone brand asset differs')
