// Static design-contract checks, not a browser/layout or assistive-technology audit.
// Run: node tests/standalone_workbench.cjs
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = path.join(__dirname, '../hermes_crm/static');
const css = fs.readFileSync(path.join(base,'app.css'),'utf8');
const html = fs.readFileSync(path.join(base,'index.html'),'utf8');
const js = fs.readFileSync(path.join(base,'app.js'),'utf8');
for (const token of ['#f5f7fa','#ffffff','#18191b','#5f636b','#d8dfe8','#8c929b','#1f4dff','#eaf0fe', '#101216','#181b21','#f2f4f8','#d6dce5','#343b46','#697586','#365deb','#8faaff','#243254']) assert(css.includes(token), token);
for (const feature of ['prefers-color-scheme: dark','forced-colors: active','prefers-reduced-motion: reduce','pointer: coarse',':focus-visible','[hidden]','nav a.active::after']) assert(css.includes(feature), feature);
assert(!/backdrop-filter|linear-gradient|box-shadow|opacity:\s*0\./.test(css));
assert(!html.includes('brandmark'));
assert(html.includes('class="wordmark"'));
assert(html.includes('name="color-scheme" content="light dark"'));
assert.equal((html.match(/data-page=/g)||[]).length,5);
assert(js.includes('submit.setAttribute("aria-busy", "true")'));
assert(js.includes('submit.removeAttribute("aria-busy")'));
assert(!js.includes('stroke="#e6e8e7"'));
function luminance(hex) {
  const c = hex.replace('#','').match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);
  return c[0]*.2126+c[1]*.7152+c[2]*.0722;
}
function contrast(a,b) { const x=luminance(a),y=luminance(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); }
for (const [foreground, backgrounds] of [
  ['#18191b',['#ffffff','#f5f7fa','#eaf0fe']], ['#5f636b',['#ffffff','#f5f7fa','#eaf0fe']],
  ['#f2f4f8',['#181b21','#101216','#243254']], ['#d6dce5',['#181b21','#101216','#243254']],
  ['#1f4dff',['#ffffff','#f5f7fa','#eaf0fe']], ['#8faaff',['#181b21','#101216','#243254']],
  ['#ffffff',['#1f4dff','#365deb']], ['#b42318',['#fff0ee']], ['#ffb4ab',['#402329']],
  ['#17633d',['#e8f4ed']], ['#91e4b9',['#1c372c']], ['#854000',['#fff3e3']], ['#ffd18a',['#3e301d']],
]) for (const bg of backgrounds) assert(contrast(foreground,bg)>=4.5, `${foreground} on ${bg} contrast ${contrast(foreground,bg).toFixed(2)}`);
console.log('PASS: Workbench palette, bright dark metadata, contrast pairs ≥4.5, flat geometry, all route tabs, focus/touch/forced-color/reduced-motion contracts');
