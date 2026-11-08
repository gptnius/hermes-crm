const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('shared/relationship-time.js','utf8'), ctx=vm.createContext({Intl,Date});vm.runInContext(source,ctx);
const run=s=>vm.runInContext(s,ctx), json=s=>JSON.parse(JSON.stringify(run(s)));
for(const [wall,zone,expected] of [
 ['2026-11-12T10:00','America/New_York','2026-11-12T15:00:00.000Z'],
 ['2026-01-01T00:00','Asia/Kathmandu','2025-12-31T18:15:00.000Z'],
 ['2026-07-01T10:00','Australia/Adelaide','2026-07-01T00:30:00.000Z'],
 ['1900-01-01T00:00','UTC','1900-01-01T00:00:00.000Z'],
 ['2100-12-31T23:59:59','UTC','2100-12-31T23:59:59.000Z']]) assert.equal(run(`relResolve('${wall}','${zone}')`),expected);
assert.deepEqual(json("relCandidates('2026-03-08T02:30','America/New_York')"),[]);
assert.throws(()=>run("relResolve('2026-03-08T02:30','America/New_York')"),/does not exist/);
const fold=json("relCandidates('2026-11-01T01:30','America/New_York')");assert.deepEqual(fold,['2026-11-01T05:30:00.000Z','2026-11-01T06:30:00.000Z']);
assert.throws(()=>run("relResolve('2026-11-01T01:30','America/New_York')"),/occurs twice/);
assert.equal(run(`relResolve('2026-11-01T01:30','America/New_York','','America/New_York','${fold[1]}')`),fold[1]);
assert.equal(run(`relResolve('2026-11-01T01:30','America/New_York','2026-11-01T01:30:00.123456-04:00','America/New_York','${fold[1]}')`),fold[1]);
const exact='2026-10-01T12:30:59.123456-04:00';ctx.exact=exact;
assert.equal(run("relResolve('2026-10-01T12:30:59','America/New_York',exact,'America/New_York')"),exact);
assert.equal(run("relResolve('2026-10-01T12:30:59','UTC',exact,'America/New_York')"),'2026-10-01T12:30:59.000Z');
assert.equal(run("relResolve('2026-01-01T00:00','UTC','2026-01-01T00:00:00.000001Z','UTC')"),'2026-01-01T00:00:00.000001Z');
assert.equal(run("relMicros('2026-01-01T00:00:00.000002Z')-relMicros('2026-01-01T00:00:00.000001Z')"),1n);
for(const wall of ['','2026-02-29T12:00','2026-04-31T12:00','2026-01-01T24:00','2026-01-01T12:60','2026-01-01T12:00:60','0099-01-01T12:00','1899-12-31T23:59','2101-01-01T00:00']) assert.throws(()=>run(`relResolve('${wall}','UTC')`),wall);
for(const zone of ['','No/Zone','+01:00'])assert.throws(()=>run(`relResolve('2026-01-01T12:00','${zone}')`));
for(const instant of ['2026-01-01T12:00:00+24:00','2026-01-01T12:00:00+01:60','2026-01-01T12:00:00.1234567Z'])assert.throws(()=>run(`relInstant('${instant}')`));
assert.equal(run("relInstant('0099-02-28T12:00:00Z')"),'0099-02-28T12:00:00Z');
// Half-hour DST and a whole skipped date must also be explicit, not normalized.
assert.equal(json("relCandidates('2026-04-05T01:45','Australia/Lord_Howe')").length,2);
assert.equal(json("relCandidates('2026-10-04T02:15','Australia/Lord_Howe')").length,0);
assert.equal(json("relCandidates('2011-12-30T12:00','Pacific/Apia')").length,0);
for (const file of ['desktop/relationships.js','hermes_crm/static/app.js']) {
 const target=fs.readFileSync(file,'utf8');assert(target.includes('// BEGIN GENERATED RELATIONSHIP TIME\n'+source.trimEnd()+'\n// END GENERATED RELATIONSHIP TIME'));
}
console.log('PASS shared time helpers: DST gaps/folds, half/quarter-hour offsets, date-line gap, exact fractions, changed zone, malformed/boundary inputs and generated parity.');
for(const year of ['0099','1899','2101','9998']) {
 const original=`${year}-01-01T12:00:00.123456Z`;
 ctx.outsideOriginal=original; ctx.outsideWall=`${year}-01-01T12:00`;
 assert.deepEqual(json("relEditorCandidates(outsideWall,'UTC',outsideOriginal,'UTC')"),[]);
 assert.equal(run("relResolve(outsideWall,'UTC',outsideOriginal,'UTC')"),original);
 assert.throws(()=>run("relResolve(outsideWall,'America/New_York',outsideOriginal,'UTC')"),/1900 through 2100/);
 assert.throws(()=>run("relResolve(outsideWall+'01','UTC',outsideOriginal,'UTC')"));
}
