(() => {
'use strict';

const C = window.Coreo;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const h = (tag, props = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') e.className = v;
    else if (k === 'style') e.style.cssText = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, '');
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};
const { clamp, minus, fmtT, guessVersion, cleanName, cleanFileName, audioRejection } = C;

let toastTimer;
function flash(msg, ms = 2800) {
  const t = $('#toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), ms);
}

let storageBroken = false;
let rawState = null;
try { rawState = localStorage.getItem(C.KEY); }
catch (e) { storageBroken = true; }
const S = C.parseState(rawState);
let saveTimer;
function persist() {
  if (storageBroken) return;
  try { localStorage.setItem(C.KEY, JSON.stringify(C.stateForSave(S))); }
  catch (e) { flash('Non riesco a salvare nel browser: usa «Salva su file».'); }
}
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(persist, 250);
}
function saveNow() {
  clearTimeout(saveTimer);
  persist();
}
addEventListener('pagehide', saveNow);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') saveNow();
});

const V = () => S.versions[S.active];
const beatDur = C.beatDur, baseDur = C.baseDur, startOf = C.startOf, relOf = C.relOf;

let dbp = null;
function db() {
  if (!dbp) {
    dbp = new Promise((res, rej) => {
      if (!window.indexedDB) return rej(new Error('IndexedDB assente'));
      const r = indexedDB.open('exotica-coreografia', 1);
      r.onupgradeneeded = () => {
        if (!r.result.objectStoreNames.contains('audio')) r.result.createObjectStore('audio');
      };
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    }).catch(err => { dbp = null; throw err; });
  }
  return dbp;
}
const tx = (mode, fn) => db().then(d => new Promise((res, rej) => {
  const t = d.transaction('audio', mode);
  const rq = fn(t.objectStore('audio'));
  t.oncomplete = () => res(rq && rq.result);
  t.onerror = t.onabort = () => rej(t.error);
}));
const dbGet = k => tx('readonly', s => s.get(k));
const dbSet = (k, v) => tx('readwrite', s => s.put(v, k));
const dbDel = k => tx('readwrite', s => s.delete(k));
const dbKeys = () => tx('readonly', s => s.getAllKeys());
let stored = new Set();

const au = $('#au');
let audioReady = false, curBlob = null, curName = '', objUrl = null, pending = null, audioFailed = false;
let srcGen = 0, navGen = 0;
let layout = null, bases = [], byK = new Map(), rowsEl = [];
let lastBase = null, lastBeatEl = null, lastBeat = -1, lastRow = null;
let kMin = 0, kMax = 0;
const loop = { mode: 'off', a: null, b: null };
const playhead = h('div', { class: 'playhead', hidden: true });

function buildLayout(v) { return C.buildLayout(v); }

function rebuild() {
  const v = V();
  layout = buildLayout(v);
  bases = []; byK = new Map(); rowsEl = [];
  lastBase = null; lastBeatEl = null; lastBeat = -1; lastRow = null;
  const score = $('#score'), list = $('#sideList');
  score.textContent = ''; list.textContent = '';
  playhead.hidden = true;

  layout.rows.forEach(row => {
    const nb = row.bases.length;
    const grid = h('div', { class: 'rowgrid', style: `grid-template-columns:repeat(${nb},minmax(0,1fr));width:${nb * 100 / C.COLS}%` });
    const rEl = h('article', { class: 'row', style: `--c:var(--c-${row.sec.cls})` },
      h('div', { class: 'row-head' },
        h('span', { class: 'tag' }, row.sec.name + (row.cont ? ' (segue)' : '')),
        h('span', { class: 'range' }, nb > 1 ? `basi ${minus(row.bases[0].n)} – ${minus(row.bases[nb - 1].n)}` : `base ${minus(row.bases[0].n)}`)),
      grid);
    rEl._grid = grid; rEl._nb = nb;
    rowsEl.push(rEl);
    row.bases.forEach((b, ci) => {
      const notes = h('div', { class: 'notes' + (b.bars < 2 ? ' end' : ''), style: b.bars < 2 ? `width:${b.bars * 50}%` : '' });
      for (let i = 0; i < b.bars * 4; i++) {
        notes.append(h('div', { class: 'beat' + (C.REST[i] ? ' rest' : '') }, h('span', { class: 'stem' }), h('span', { class: 'head' }), h('span', { class: 'cnt' }, C.COUNT[i])));
      }
      const cell = h('div', { class: 'base' + (ci === nb - 1 ? ' last' : ''), 'data-n': b.n, style: `grid-column:${ci + 1}`,
        title: `Base ${minus(b.n)}: clicca a sinistra per partire dall'1, a destra dal 5` },
        h('span', { class: 'num' }, minus(b.n)), notes);
      const mv = h('textarea', { class: 'mv', 'data-n': b.n, rows: 2, maxlength: String(C.MOVE_MAX), style: `grid-column:${ci + 1}`,
        placeholder: 'Mossa…', 'aria-label': `Mossa della base ${minus(b.n)}`, spellcheck: 'false' });
      const val = S.moves[b.n] || '';
      mv.value = val;
      if (val.trim()) mv.classList.add('filled');
      const li = h('li', { class: 'mi' + (val.trim() ? '' : ' hole'), 'data-n': b.n, style: `--c:var(--c-${row.sec.cls})` },
        h('b', {}, minus(b.n)), h('span', { class: 't' }, val.replace(/\s*\n+\s*/g, ' · ')));
      li.title = val;
      const beats = [...notes.children];
      const obj = { n: b.n, k: C.kOf(b.n), bars: b.bars, sec: row.sec, ri: rowsEl.length - 1, col: ci, cell, beats, mv, li, rEl, grid };
      bases.push(obj); byK.set(obj.k, obj);

      cell.addEventListener('click', e => {
        const r = cell.getBoundingClientRect();
        const half = (e.clientX - r.left) / r.width >= 0.5 ? 4 : 0;
        goTo(startOf(V(), b.n) + half * beatDur(V()));
      });
      li.addEventListener('click', () => {
        goTo(startOf(V(), b.n), true);
        ensureVisible(obj.rEl, true);
      });
      mv.addEventListener('input', () => {
        if (mv.value.length > C.MOVE_MAX) {
          mv.value = mv.value.slice(0, C.MOVE_MAX);
          flash('La mossa è troppo lunga: ho tenuto i primi 2000 caratteri.');
        }
        const t = mv.value;
        if (t.trim()) S.moves[b.n] = t; else delete S.moves[b.n];
        mv.classList.toggle('filled', !!t.trim());
        li.classList.toggle('hole', !t.trim());
        li.querySelector('.t').textContent = t.replace(/\s*\n+\s*/g, ' · ');
        li.title = t;
        updateCount();
        save();
      });
      mv.addEventListener('blur', () => {
        if (mv.value.includes('->')) { mv.value = mv.value.replace(/->/g, '→'); mv.dispatchEvent(new Event('input')); }
      });
      grid.append(cell, mv);
    });
    score.append(rEl);
  });

  let prevSec = null;
  bases.forEach(b => {
    if (b.sec !== prevSec) { list.append(h('li', { class: 'sec-h', style: `--c:var(--c-${b.sec.cls})` }, b.sec.name)); prevSec = b.sec; }
    list.append(b.li);
  });

  kMin = bases[0].k; kMax = bases[bases.length - 1].k;
  updateCount(); refreshSegs(); applyLoopUi(); update();
}

function updateCount() {
  const filled = bases.filter(b => (S.moves[b.n] || '').trim()).length;
  $('#sideCount').textContent = `${filled} / ${bases.length}`;
}

function updateCodaHint() {
  const el = $('#codaHint');
  if (!el) return;
  if (!audioReady || !isFinite(au.duration)) { el.textContent = ''; return; }
  const v = V(), rest = au.duration - (v.base1 + 33 * baseDur(v));
  el.textContent = rest >= 0
    ? `Con questa griglia l'audio dura ancora ${rest.toFixed(1)} s dopo la base 33 (≈ ${(rest / (4 * beatDur(v))).toFixed(1)} battute).`
    : `Attenzione: con questa griglia l'audio finisce ${(-rest).toFixed(1)} s prima della fine della base 33 (controlla l'inizio della base 1).`;
}
function refreshSegs() {
  const box = $('#segs');
  box.textContent = '';
  updateCodaHint();
  if (!audioReady || !isFinite(au.duration) || !layout) return;
  const v = V(), dur = au.duration;
  layout.secs.forEach(s => {
    const first = s.bases[0], last = s.bases[s.bases.length - 1];
    const a = startOf(v, first.n), b = startOf(v, last.n) + last.bars * 4 * beatDur(v);
    const l = clamp(a / dur, 0, 1), r = clamp(b / dur, 0, 1);
    if (r <= l) return;
    box.append(h('div', { class: 'seg', style: `left:${l * 100}%;width:${(r - l) * 100}%;--c:var(--c-${s.cls})`, title: s.name }, h('i', {}, s.name)));
  });
}

const now = () => pending !== null ? pending : (au.currentTime || 0);
const typing = () => /^(TEXTAREA|INPUT|SELECT)$/.test((document.activeElement || {}).tagName || '');

function update() {
  const v = V(), t = now();
  const rel = relOf(v, t), k = Math.floor(rel);
  const B = byK.get(k) || null;
  const bi = B ? Math.min(7, Math.floor((rel - k) * 8)) : -1;

  if (B !== lastBase) {
    if (lastBase) { lastBase.cell.classList.remove('cur'); lastBase.li.classList.remove('cur'); }
    if (B) { B.cell.classList.add('cur'); B.li.classList.add('cur'); }
    $('#rdBase').textContent = B ? minus(B.n) : '—';
    if (B) {
      const side = $('#side'), li = B.li, top = li.offsetTop, bot = top + li.offsetHeight;
      if (top < side.scrollTop + 44 || bot > side.scrollTop + side.clientHeight) side.scrollTop = Math.max(0, top - side.clientHeight / 2);
    }
    lastBase = B;
  }
  if (B && B.rEl !== lastRow) {
    if (S.follow && !typing()) ensureVisible(B.rEl, !au.paused);
    lastRow = B.rEl;
  }
  if (bi !== lastBeat || (B && B.beats[bi] !== lastBeatEl)) {
    if (lastBeatEl) lastBeatEl.classList.remove('on');
    const be = B && bi >= 0 && bi < B.beats.length ? B.beats[bi] : null;
    if (be) be.classList.add('on');
    lastBeatEl = be; lastBeat = bi;
    $$('#pips .pip').forEach((p, i) => p.classList.toggle('on', be !== null && i === bi));
  }
  if (B) {
    if (playhead.parentNode !== B.grid) B.grid.append(playhead);
    playhead.style.left = ((B.col + (rel - k)) / B.rEl._nb * 100) + '%';
    playhead.hidden = false;
  } else playhead.hidden = true;

  const dur = au.duration;
  $('#tNow').textContent = fmtT(t);
  if (isFinite(dur) && dur > 0) {
    const p = clamp(t / dur, 0, 1) * 100;
    $('#seekFill').style.width = p + '%';
    $('#seekHead').style.left = p + '%';
    $('#seek').setAttribute('aria-valuenow', String(Math.round(p)));
  }
}

function ensureVisible(el, smooth) {
  const top = $('#player').getBoundingClientRect().bottom + 10, r = el.getBoundingClientRect();
  if (r.top >= top && r.bottom <= innerHeight - 10) return;
  const avail = innerHeight - top;
  scrollTo({ top: scrollY + r.top - top - Math.max(0, (avail - r.height) / 2), behavior: smooth ? 'smooth' : 'auto' });
}

function frame() {
  const t = now();
  if (loop.mode !== 'off' && loop.b != null && t >= loop.b - 0.004) seek(loop.a);
  update();
  if (!au.paused) requestAnimationFrame(frame);
}

function needAudio() {
  flash('Carica prima il file audio di questa versione.');
  $('#panel').open = true;
}
function seek(t) {
  if (!audioReady) return;
  t = clamp(t, 0, Math.max(0, (au.duration || 0) - 0.02));
  pending = t; au.currentTime = t;
  if (loop.mode !== 'off') computeLoop(t);
  update();
}
async function play() {
  if (!audioReady) return needAudio();
  if (au.ended || now() >= au.duration - 0.05) seek(0);
  try { await au.play(); }
  catch (e) { flash('Il browser ha bloccato la riproduzione: premi di nuovo Parti.'); }
}
function stop() { au.pause(); update(); }
function fromStart() { if (!audioReady) return needAudio(); seek(0); play(); }
function goTo(t) {
  if (!audioReady) return needAudio();
  const was = !au.paused;
  seek(t);
  if (was || S.autoplay) play();
}
function jump(which, half) {
  if (!audioReady) return needAudio();
  const v = V();
  const k = clamp(Math.floor(relOf(v, now())) + which, kMin, kMax);
  goTo(v.base1 + k * baseDur(v) + (half ? 4 : 0) * beatDur(v));
}

function computeLoop(t) {
  const v = V(), k = Math.floor(relOf(v, t)), B = byK.get(k);
  if (!B) { loop.a = loop.b = null; return; }
  const endOf = x => startOf(v, x.n) + x.bars * 4 * beatDur(v);
  if (loop.mode === 'base') { loop.a = startOf(v, B.n); loop.b = endOf(B); }
  else { const rb = bases.filter(x => x.ri === B.ri); loop.a = startOf(v, rb[0].n); loop.b = endOf(rb[rb.length - 1]); }
}
function applyLoopUi() { $$('#loopCtl button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.loop === loop.mode))); }

function setSource(blob, name) {
  const gen = ++srcGen;
  au._gen = gen;
  au.pause(); audioReady = false; audioFailed = false; pending = null;
  if (objUrl) URL.revokeObjectURL(objUrl);
  curBlob = blob; curName = name ? cleanFileName(name) : '';
  if (blob) { objUrl = URL.createObjectURL(blob); au.src = objUrl; au.load(); }
  else { objUrl = null; au.removeAttribute('src'); au.load(); }
  refreshAudioUi();
  refreshSegs();
  update();
}
function refreshAudioUi() {
  const pl = $('#player');
  pl.classList.toggle('noaudio', !audioReady);
  $$('.transport .btn:not(#bMore), .jumps .btn').forEach(b => { b.disabled = !audioReady; });
  $('#audioState').textContent = audioReady ? 'Audio:' : audioFailed ? 'File non apribile' : (curBlob ? 'Caricamento…' : 'Nessun audio');
  $('#audioName').textContent = curBlob ? curName : '';
  $('#tTot').textContent = audioReady ? fmtT(au.duration) : '0:00.0';
  renderVersions();
}
function mediaCurrent() { return au._gen === srcGen; }
au.addEventListener('loadedmetadata', () => {
  if (!mediaCurrent()) return;
  audioReady = true; audioFailed = false;
  try { au.playbackRate = S.speed; } catch (e) { /* velocità non applicabile a questo file */ }
  try { au.preservesPitch = true; au.webkitPreservesPitch = true; } catch (e) { /* pitch lock assente */ }
  refreshAudioUi(); refreshSegs(); update();
});
au.addEventListener('error', () => {
  if (!mediaCurrent()) return;
  audioReady = false;
  audioFailed = !!curBlob;
  refreshAudioUi();
  if (curBlob) flash('Non riesco ad aprire questo file. Prova col .wav oppure apri la pagina in Safari (.m4a Apple Lossless).');
});
au.addEventListener('play', () => { if (!mediaCurrent()) return; $('#player').classList.add('playing'); requestAnimationFrame(frame); });
au.addEventListener('pause', () => { $('#player').classList.remove('playing'); update(); });
au.addEventListener('ended', () => { $('#player').classList.remove('playing'); update(); });
au.addEventListener('seeked', () => { pending = null; update(); });
au.addEventListener('timeupdate', () => { if (au.paused) update(); });

async function loadAudio(file, id = S.active) {
  const why = audioRejection(file);
  if (why) { flash(why); return; }
  const name = cleanFileName(file.name);
  if (id === S.active) setSource(file, name);
  try { await dbSet(id, { name, type: file.type, blob: file }); stored.add(id); renderVersions(); }
  catch (e) { flash('Audio caricato, ma il browser non lo ricorderà per la prossima volta.'); }
}
async function loadFiles(list) {
  const files = [...list];
  const audio = [];
  let rejected = '';
  for (const f of files) {
    const why = audioRejection(f);
    if (why) rejected = rejected || why;
    else audio.push(f);
  }
  if (!audio.length) return flash(rejected || 'Questo non sembra un file audio.');
  if (audio.length === 1) {
    await loadAudio(audio[0]);
    if (files.length !== 1) flash('Qualche file non era audio ed è stato ignorato.');
    return;
  }
  const done = [], skipped = [], seen = new Set();
  let first = null;
  for (const f of audio) {
    const id = guessVersion(f.name);
    if (!id || seen.has(id)) { skipped.push(cleanFileName(f.name)); continue; }
    seen.add(id); await loadAudio(f, id); done.push(S.versions[id].name); first = first || id;
  }
  if (!done.length) return flash('Non ho riconosciuto la versione dal nome. Sceglila dal menu e carica un file alla volta.');
  if (first && !curBlob) await switchVersion(first);
  const ignored = files.length === audio.length ? '' : ' Qualche file non era audio ed è stato ignorato.';
  flash((done.length ? 'Assegnati: ' + done.join(' · ') + '. ' : '') +
        (skipped.length ? 'Non riconosciuti (scegli la versione dal menu e caricali uno alla volta): ' + skipped.join(', ') : '') + ignored, 6000);
}
async function restoreAudio() {
  const gen = navGen;
  const id = S.active;
  setSource(null, '');
  try {
    const rec = await dbGet(id);
    if (gen !== navGen || id !== S.active) return;
    if (rec && rec.blob) setSource(rec.blob, rec.name || '');
  } catch (e) { /* nessun audio salvato o IndexedDB non disponibile */ }
}

function renderVersions() {
  const sel = $('#verSel');
  const prev = document.activeElement === sel;
  sel.textContent = '';
  for (const id of C.IDS) {
    const has = stored.has(id) || (id === S.active && !!curBlob);
    sel.append(h('option', { value: id }, (has ? '● ' : '○ ') + S.versions[id].name + (has ? '' : ' (nessun audio)')));
  }
  sel.value = S.active;
  if (prev) sel.focus();
  $('#vLabel').textContent = '«' + V().name + '»';
}
$('#verSel').addEventListener('change', e => switchVersion(e.target.value));
async function switchVersion(id) {
  if (!C.IDS.includes(id) || id === S.active) return;
  navGen++;
  au.pause(); loop.mode = 'off'; S.active = id; saveNow();
  rebuild(); bindPanel();
  await restoreAudio();
}

function bindPanel() {
  const v = V();
  $('#fName').value = v.name;
  $('#fIntro').value = v.introBases;
  $('#fCoda').value = v.codaBars;
  $('#fBpm').value = v.bpm;
  $('#fBase1').value = (+v.base1).toFixed(3);
  renderVersions();
}
function afterGridChange() { refreshSegs(); update(); save(); }
const num = (el, lo, hi, dflt) => { const x = parseFloat(el.value); return isFinite(x) ? clamp(x, lo, hi) : dflt; };

$('#fName').addEventListener('input', e => {
  const raw = e.target.value.replace(/[\u0000-\u001f\u007f]/g, '').slice(0, 30);
  if (raw !== e.target.value) e.target.value = raw;
  V().name = raw.trim() || 'Versione';
  renderVersions();
  save();
});
$('#fIntro').addEventListener('change', e => { V().introBases = Math.round(num(e.target, 0, 8, 0)); e.target.value = V().introBases; rebuild(); save(); });
$('#fCoda').addEventListener('change', e => { V().codaBars = Math.round(num(e.target, 0, 6, 0)); e.target.value = V().codaBars; rebuild(); save(); });
$('#fBpm').addEventListener('input', e => { const x = parseFloat(e.target.value); if (x >= 60 && x <= 220) { V().bpm = x; afterGridChange(); } });
$('#fBase1').addEventListener('input', e => {
  const x = parseFloat(e.target.value);
  if (!isFinite(x) || x < 0) return;
  V().base1 = Math.min(x, 3600);
  if (x > 3600) e.target.value = '3600.000';
  afterGridChange();
});
$$('[data-nudge]').forEach(b => b.addEventListener('click', () => {
  const v = V(), d = b.dataset.nudge;
  v.base1 = Math.max(0, +(v.base1 + (d === 'beat' ? beatDur(v) : d === '-beat' ? -beatDur(v) : parseFloat(d))).toFixed(3));
  $('#fBase1').value = v.base1.toFixed(3);
  afterGridChange();
}));
$('#bMark').addEventListener('click', () => {
  if (!audioReady) return needAudio();
  V().base1 = +now().toFixed(3);
  $('#fBase1').value = V().base1.toFixed(3);
  afterGridChange();
  flash('Base 1 segnata a ' + fmtT(V().base1) + ' s');
});
$('#bReset').addEventListener('click', () => {
  const v = V();
  Object.assign(v, C.DEF[S.active]);
  bindPanel(); rebuild(); save();
  flash('Valori predefiniti ripristinati');
});
$('#bUnload').addEventListener('click', async () => {
  try { await dbDel(S.active); } catch (e) { /* niente da togliere */ }
  stored.delete(S.active);
  setSource(null, '');
  flash('Audio rimosso da questa versione');
});

async function autoAlign() {
  if (!curBlob) return needAudio();
  const btn = $('#bAuto');
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = 'Analisi…';
  try {
    const arr = await curBlob.arrayBuffer();
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) throw new Error('no-audio-context');
    const ctx = new Ctx();
    const buf = await new Promise((res, rej) => ctx.decodeAudioData(arr.slice(0), res, rej));
    ctx.close();
    const sr = buf.sampleRate, hop = Math.max(1, Math.round(sr * 0.002)), n = Math.floor(buf.length / hop);
    if (n < 8) throw new Error('too-short');
    const c0 = buf.getChannelData(0), c1 = buf.numberOfChannels > 1 ? buf.getChannelData(1) : c0;
    const eR = new Float32Array(n), eD = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      let sr2 = 0, sd = 0; const o = i * hop;
      for (let j = 1; j < hop; j++) {
        const a = o + j, m = (c0[a] + c1[a]) * 0.5, d = (c0[a] + c1[a] - c0[a - 1] - c1[a - 1]) * 0.5;
        sr2 += m * m; sd += d * d;
      }
      eR[i] = sr2 / hop; eD[i] = sd / hop;
    }
    const smooth = x => { const y = new Float32Array(n); for (let i = 2; i < n - 2; i++) y[i] = (x[i - 2] + x[i - 1] + x[i] + x[i + 1] + x[i + 2]) / 5; return y; };
    const sR = smooth(eR), sD = smooth(eD), on = new Float32Array(n);
    for (let i = 3; i < n; i++) {
      on[i] = Math.max(0, Math.log((sR[i] + 1e-9) / (sR[i - 3] + 1e-9))) + Math.max(0, Math.log((sD[i] + 1e-12) / (sD[i - 3] + 1e-12)));
    }
    const v = V(), bt = beatDur(v), hs = hop / sr, steps = Math.round(bt / 0.001), total = buf.duration;
    let best = -1, bestPhi = 0, tot = 0;
    for (let s = 0; s < steps; s++) {
      const phi = s * 0.001; let sc = 0;
      for (let t = phi; t < total - 0.02; t += bt) {
        const idx = Math.round(t / hs);
        sc += Math.max(on[idx - 1] || 0, on[idx] || 0, on[idx + 1] || 0);
      }
      tot += sc; if (sc > best) { best = sc; bestPhi = phi; }
    }
    const conf = best / (tot / steps || 1);
    const j = Math.round((v.base1 - bestPhi) / bt), nb1 = Math.max(0, Math.min(3600, bestPhi + j * bt));
    const shift = nb1 - v.base1;
    v.base1 = +nb1.toFixed(3);
    $('#fBase1').value = v.base1.toFixed(3);
    afterGridChange();
    flash((conf < 1.15 ? 'Ritmo poco netto: controlla a orecchio. ' : '') +
      (Math.abs(shift) < 0.003 ? 'Griglia già allineata.' : `Griglia spostata di ${shift > 0 ? '+' : ''}${Math.round(shift * 1000)} ms.`) +
      ' Se i colpi forti cadono sul 2 o sul 3, sposta di 1 tempo.');
  } catch (e) {
    flash('Non riesco ad analizzare questo file (prova col .wav o apri la pagina in Safari).');
  } finally { btn.disabled = false; btn.textContent = old; }
}
$('#bAuto').addEventListener('click', autoAlign);

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h('a', { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
$('#bExport').addEventListener('click', () => {
  saveNow();
  download('coreografia-exotica.json', JSON.stringify({ app: 'exotica-coreografia', versione: 1, esportato: new Date().toISOString(), moves: S.moves, versions: S.versions }, null, 2), 'application/json');
});
$('#bImport').addEventListener('click', () => $('#fJson').click());
$('#fJson').addEventListener('change', async e => {
  const f = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!f) return;
  if (f.size > C.JSON_MAX) { flash('Questo file è troppo grande per essere una coreografia (massimo 1 MB).'); return; }
  try {
    let text = await f.text();
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
    const parsed = C.parseImport(JSON.parse(text));
    const n = Object.keys(parsed.moves).length;
    const hasVersions = Object.keys(parsed.versions).length > 0;
    const had = Object.keys(S.moves).length;
    if (!n && !had && !hasVersions) { flash('Il file non contiene mosse utilizzabili.'); return; }
    if (n) {
      if (!confirm('Sostituire le mosse attuali con quelle del file (' + n + ' basi)?')) return;
      S.moves = parsed.moves;
    } else if (had) {
      if (!confirm('Il file non contiene mosse. Cancellare le mosse attuali?')) return;
      S.moves = {};
    }
    for (const id of C.IDS) {
      const src = parsed.versions[id];
      if (!src) continue;
      Object.assign(S.versions[id], src);
    }
    saveNow(); rebuild(); bindPanel();
    flash('Mosse caricate dal file');
  } catch (err) { flash('File non valido: serve un .json salvato da questa pagina.'); }
});
$('#bCopy').addEventListener('click', async () => {
  const text = bases.map(b => `Base ${minus(b.n)}: ${(S.moves[b.n] || '').replace(/\n+/g, ' / ')}`).join('\n');
  try {
    await navigator.clipboard.writeText(text);
    flash('Copiato: una riga per base, vuota dove non c\'è la mossa');
  } catch (e) {
    const ta = h('textarea', { style: 'position:fixed;left:-9999px' });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
    ta.remove();
    flash(ok ? 'Copiato' : 'Non riesco a copiare negli appunti. Usa «Salva su file».');
  }
});
$('#bPrint').addEventListener('click', () => window.print());
$('#bClear').addEventListener('click', () => {
  if (!Object.keys(S.moves).length) return flash('Non ci sono mosse da cancellare');
  if (confirm('Cancellare tutte le mosse? Non si può annullare (salva prima su file se vuoi tenerle).')) {
    S.moves = {}; saveNow(); rebuild(); flash('Mosse cancellate');
  }
});

$('#bPlay').addEventListener('click', play);
$('#bStop').addEventListener('click', stop);
$('#bStart').addEventListener('click', fromStart);
$('#bMore').addEventListener('click', () => {
  const open = $('#player').classList.toggle('open');
  $('#bMore').setAttribute('aria-expanded', String(open));
});
$$('[data-j]').forEach(b => b.addEventListener('click', () => jump(+b.dataset.j, +b.dataset.h)));
$('#bLoad').addEventListener('click', () => $('#fFile').click());
$('#bLoad2').addEventListener('click', () => $('#fFile').click());
$('#fFile').addEventListener('change', e => { const fs = [...e.target.files]; e.target.value = ''; if (fs.length) loadFiles(fs); });
$('#speed').addEventListener('change', e => {
  const sp = C.normalizeSpeed(e.target.value) || 1;
  S.speed = sp; e.target.value = String(sp);
  try { au.playbackRate = S.speed; } catch (err) { /* il file non è ancora pronto */ }
  save();
});
$('#optPlay').addEventListener('change', e => { S.autoplay = e.target.checked; save(); });
$('#optFollow').addEventListener('change', e => { S.follow = e.target.checked; save(); });
$$('#loopCtl button').forEach(b => b.addEventListener('click', () => {
  loop.mode = b.dataset.loop;
  applyLoopUi();
  if (loop.mode !== 'off') { if (audioReady) computeLoop(now()); }
  else loop.a = loop.b = null;
}));

const seekEl = $('#seek');
let seekWarned = false;
const seekFromEvent = e => {
  const r = seekEl.getBoundingClientRect();
  if (!r.width) return;
  if (audioReady) seek(clamp((e.clientX - r.left) / r.width, 0, 1) * au.duration);
  else if (!seekWarned) { seekWarned = true; needAudio(); }
};
seekEl.addEventListener('pointerdown', e => {
  seekWarned = false;
  try { seekEl.setPointerCapture(e.pointerId); } catch (err) { /* pointer capture non disponibile */ }
  seekFromEvent(e);
});
seekEl.addEventListener('pointermove', e => { if (e.buttons) seekFromEvent(e); });
seekEl.addEventListener('keydown', e => {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
  e.preventDefault(); e.stopPropagation();
  if (!audioReady) return needAudio();
  seek(now() + (e.key === 'ArrowLeft' ? -2 : 2));
});

document.addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const tag = (e.target.tagName || '');
  if (/^(TEXTAREA|INPUT|SELECT)$/.test(tag)) return;
  if (e.code === 'Space') { if (tag === 'BUTTON' || tag === 'SUMMARY') return; e.preventDefault(); au.paused ? play() : stop(); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); jump(-1, e.shiftKey); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); jump(1, e.shiftKey); }
  else if (e.key === 'r' || e.key === 'R') { e.preventDefault(); jump(0, e.shiftKey); }
  else if (e.key === 'Home') { e.preventDefault(); fromStart(); }
});

addEventListener('dragover', e => { if ([...(e.dataTransfer?.types || [])].includes('Files')) { e.preventDefault(); } });
addEventListener('drop', e => {
  const fs = e.dataTransfer?.files;
  if (!fs || !fs.length) return;
  e.preventDefault();
  loadFiles(fs);
});

const setPh = () => document.documentElement.style.setProperty('--ph', $('#player').offsetHeight + 'px');
if (window.ResizeObserver) new ResizeObserver(setPh).observe($('#player'));
addEventListener('resize', setPh);

(function init() {
  $('#pips').append(...C.COUNT.map((c, i) => h('span', { class: 'pip' + (C.REST[i] ? ' rest' : '') }, c)));
  $('#speed').value = String(S.speed);
  $('#optPlay').checked = S.autoplay;
  $('#optFollow').checked = S.follow;
  rebuild(); bindPanel(); setPh();
  if (storageBroken) flash('Non riesco a leggere i dati di questo browser. Puoi comunque scrivere le mosse e salvarle su file.', 5000);
  else if (S.corrupt) {
    flash('I dati salvati in questo browser erano danneggiati. Ho tenuto le mosse valide e ripristinato il resto. Se hai un file esportato, caricalo da «Carica da file».', 6500);
    saveNow();
  }
  dbKeys().then(k => { stored = new Set(k); renderVersions(); }).catch(() => {});
  restoreAudio();
  window.__coreo = {
    S, seek, play, stop, jump, goTo, update, now: () => now(),
    get bases() { return bases; }, get layout() { return layout; }, autoAlign, saveNow,
  };
})();
})();
