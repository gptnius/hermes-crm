// Shared, dependency-free wall-time conversion. Never use the host's implicit zone.
function relZone(zone) {
  if (typeof zone !== 'string' || !zone.trim() || /^[+-]/.test(zone)) throw new Error('Choose a valid IANA timezone, such as America/New_York or UTC.');
  try { return new Intl.DateTimeFormat('en-US', {timeZone: zone}).resolvedOptions().timeZone; }
  catch { throw new Error('Choose a valid IANA timezone, such as America/New_York or UTC.'); }
}
function relWall(instant, zone) {
  relZone(zone);
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone: zone, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23'}).formatToParts(new Date(instant));
  const p = Object.fromEntries(parts.map(p => [p.type,p.value]));
  return `${p.year.padStart(4,'0')}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}
function relInstant(value) {
  const text = String(value || '').trim();
  const m = /^(\d{4}-\d\d-\d\d)T(\d\d):(\d\d)(?::(\d\d)(?:\.(\d{1,6}))?)?(Z|[+-](\d\d):(\d\d))$/.exec(text);
  if (!m || +m[2]>23 || +m[3]>59 || +(m[4]||0)>59 || +(m[7]||0)>23 || +(m[8]||0)>59 || !Number.isFinite(Date.parse(text))) throw new Error('Enter a valid date and time with an explicit offset.');
  const date = new Date(m[1]+'T00:00:00Z');
  if (date.toISOString().slice(0,10)!==m[1]) throw new Error('Enter a valid calendar date.');
  return text;
}
function relMicros(value) {
  relInstant(value);
  return BigInt(Math.floor(Date.parse(value)/1000))*1000000n + BigInt((value.match(/\.(\d+)/)?.[1] || '').padEnd(6,'0'));
}
function relCandidates(wall, zone) {
  relZone(zone);
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?$/.test(wall)) throw new Error('Enter both a date and a time.');
  const normalized = wall.length === 16 ? wall+':00' : wall;
  relInstant(normalized+'Z');
  // Restrict interactive editing to a tested modern timezone-data range.
  const year = +wall.slice(0,4);
  if (year < 1900 || year > 2100) throw new Error('Choose a year from 1900 through 2100.');
  const base = Date.parse(normalized+'Z'), offsets = new Set();
  // Obtain offsets around the target day, including both sides of DST and date-line shifts.
  for (let hour=-48; hour<=48; hour+=3) {
    const time = base+hour*3600000;
    offsets.add(Date.parse(relWall(time,zone)+'Z')-time);
  }
  return [...offsets].map(offset=>base-offset).filter(time=>relWall(time,zone)===normalized).sort((a,b)=>a-b).map(time=>new Date(time).toISOString());
}
function relUnchanged(wall, zone, original, originalZone, choice = '') {
  return !choice && !!original && zone===originalZone && relWall(original,zone)===(wall.length===16 ? wall+':00' : wall);
}
function relEditorCandidates(wall, zone, original = '', originalZone = zone, choice = '') {
  // Existing precise instants may predate or exceed the interactive editing range.
  // They are already unambiguous and must not block unrelated record edits.
  if ((+wall.slice(0,4)<1900 || +wall.slice(0,4)>2100) && relUnchanged(wall,zone,original,originalZone,choice)) return [];
  return relCandidates(wall,zone);
}
function relResolve(wall, zone, original = '', originalZone = zone, choice = '') {
  relZone(zone);
  // Preserve exact offset, seconds and microseconds even if the control normalized :00.
  if (relUnchanged(wall,zone,original,originalZone,choice)) return relInstant(original);
  const candidates=relCandidates(wall,zone);
  if (!candidates.length) throw new Error('This local time does not exist in this timezone. Choose another time.');
  if (candidates.length>1 && !candidates.includes(choice)) throw new Error('This local time occurs twice. Choose the intended occurrence.');
  return candidates.length===1 ? candidates[0] : choice;
}
function relReadable(value, zone = 'UTC') {
  if (!value) return 'Not recorded';
  try { relInstant(value); relZone(zone); return new Intl.DateTimeFormat('en', {timeZone:zone, year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit',timeZoneName:'short'}).format(new Date(value)); }
  catch { return String(value); }
}
