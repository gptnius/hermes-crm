// Source/contrast and generator contracts, not a rendered-layout certification.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
const read = name => readFile(new URL('../' + name, import.meta.url),'utf8');
const css = await read('desktop/design-system.css'), source = await read('desktop/plugin.js');
assert.ok(source.includes('const CSS = `\n' + css.trim() + '\n`;'));
assert.match(css, /:root\.dark \.hermes-crm-native/);
assert.match(css, /--hc-secondary:#D6DCE5/);
assert.doesNotMatch(css, /linear-gradient|backdrop-filter|opacity:\s*\.[0-9]/);
for (const feature of ['@container(max-width:640px)','@container(max-width:480px)','@media(pointer:coarse)','@media(forced-colors:active)','@media(prefers-reduced-motion:reduce)', ':focus-visible', '.hc-tabs button[aria-current=page]', '.hc-table-wrap', '.hc-editor-body', '.hc-transfer-body', '.hc-report-form', '.hc-contact-log-form']) assert.ok(css.includes(feature), feature);
assert.match(source, /String\(value \?\? ""\)/);
assert.match(source, /Saved evidence & technical details/);
assert.doesNotMatch(source, /dangerouslySetInnerHTML/);
assert.match(source, /"aria-label": "HermesCRM", focusable: false/);
const svg = await read('assets/brand/hermescrm-wordmark.svg');
assert.equal(svg, await read('hermes_crm/static/hermescrm-wordmark.svg'));
assert.equal(await read('assets/brand/OFL.txt'), await read('hermes_crm/static/wordmark-OFL.txt'));
assert.match(await read('assets/brand/PROVENANCE.json'), /SIL OFL 1.1/);
assert.doesNotMatch(svg, /script|foreignObject|<image|https?:\/\/(?!www\.w3\.org)/);
function lum(hex) { const c=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722; }
function ratio(a,b) { const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); }
for (const [fg,bgs] of [
 ['#18191B',['#FFFFFF','#F5F7FA','#EAF0FE']],['#5F636B',['#FFFFFF','#F5F7FA','#EAF0FE']],
 ['#F2F4F8',['#181B21','#101216','#243254']],['#D6DCE5',['#181B21','#101216','#243254']],
 ['#1F4DFF',['#FFFFFF','#F5F7FA','#EAF0FE']],['#8FAAFF',['#181B21','#101216','#243254']],
 ['#FFFFFF',['#1F4DFF','#365DEB']],['#B42318',['#FFF0EE']],['#FFB4AB',['#3D2428']],
 ['#885000',['#FFF4DE']],['#FFCD80',['#3A301F']],['#13734B',['#E8F4ED']],['#A0E4BF',['#1D362B']],
]) for(const bg of bgs) assert.ok(ratio(fg,bg)>=4.5,`${fg} on ${bg}: ${ratio(fg,bg)}`);
for(const generator of ['build_design_system.py','build_wordmark_component.py']) execFileSync(process.env.HERMES_CRM_TEST_PYTHON||'python3',['scripts/'+generator,'--check'],{cwd:new URL('..',import.meta.url)});
console.log('PASS native Workbench: scoped generator parity, both themes, bright metadata, contrast ≥4.5, keyboard/touch/forced-color/reduced-motion contracts, semantic brand and retained evidence');
