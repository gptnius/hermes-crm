// Scoped CSS/fixture contracts; actual pixel verification is a separate renderer run.
const fs=require('node:fs'),assert=require('node:assert/strict');
const native=fs.readFileSync('desktop/design-system.css','utf8');
const web=fs.readFileSync('hermes_crm/static/app.css','utf8');
const app=fs.readFileSync('hermes_crm/static/app.js','utf8');
assert.match(native,/\.hermes-crm-native \.hc-relationship-form label\{align-content:start\}/,'native form labels must not stretch selects beside tall DST guidance');
assert.match(native,/\.hermes-crm-native \.hc-relationships :is\(button,input,select\)\{min-height:44px\}/);
assert.match(web,/#relationship-discard:not\(\[hidden\]\)\{display:flex;flex-wrap:wrap;gap:12px;align-items:center\}/,'visible discard actions need wrapping and a gap without overriding hidden');
assert.match(web,/#relationship-discard>p\{flex-basis:100%;margin:0\}/);
assert.match(app,/id="relationship-discard"[^>]* hidden><p>Discard unsaved changes\?<\/p><button[^>]*id="relationship-keep"/);
assert.match(web,/#relationship-form :is\(input,select,button\)\{min-height:44px\}/);
console.log('PASS relationship layout contracts: natural-height native labels, separate wrapping discard actions, hidden state and 44px targets.');
