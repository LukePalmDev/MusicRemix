/* Logica pura della coreografia: niente DOM, così si può provare con node --test.
   In pagina espone window.Coreo; sotto Node, module.exports. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.Coreo = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const STRUCT = Object.freeze([
    Object.freeze({ cls: 'strofa', name: 'Strofa 1', from: 1, to: 4 }),
    Object.freeze({ cls: 'pre', name: 'Pre-ritornello 1', from: 5, to: 8 }),
    Object.freeze({ cls: 'break', name: 'Break 1', from: 9, to: 9 }),
    Object.freeze({ cls: 'rit', name: 'Ritornello 1', from: 10, to: 16 }),
    Object.freeze({ cls: 'strofa', name: 'Strofa 2', from: 17, to: 20 }),
    Object.freeze({ cls: 'pre', name: 'Pre-ritornello 2', from: 21, to: 24 }),
    Object.freeze({ cls: 'break', name: 'Break 2', from: 25, to: 25 }),
    Object.freeze({ cls: 'rit', name: 'Ritornello 2', from: 26, to: 32 }),
    Object.freeze({ cls: 'finale', name: 'Finale', from: 33, to: 33 }),
  ]);
  const COLS = 4;
  const COUNT = Object.freeze(['1', '2', '3', '4', '5', '6', '7', '8']);
  const REST = Object.freeze([false, false, false, true, false, false, false, true]);
  const KEY = 'exotica-coreografia-v1';
  const EPS = 0.008;
  const MOVE_MAX = 2000;
  const JSON_MAX = 1024 * 1024;
  const AUDIO_MAX = 250 * 1024 * 1024;
  const SPEEDS = Object.freeze([0.5, 0.6, 0.7, 0.8, 0.9, 1, 1.1]);
  const IDS = Object.freeze(['s1', 's1c', 's2', 's2c']);
  const WITH_INTRO = Object.freeze({ introBases: 2, codaBars: 1, bpm: 130, base1: 7.385 });
  const NO_INTRO = Object.freeze({ introBases: 0, codaBars: 1, bpm: 130, base1: 0.048 });
  const DEF = Object.freeze({
    s1: Object.freeze({ name: 's1 · con intro', ...WITH_INTRO }),
    s1c: Object.freeze({ name: 's1 conteggio · con intro', ...WITH_INTRO }),
    s2: Object.freeze({ name: 's2 · senza intro', ...NO_INTRO }),
    s2c: Object.freeze({ name: 's2 conteggio · senza intro', ...NO_INTRO }),
  });
  const LEGACY_ACTIVE = Object.freeze({ a: 's1', b: 's2' });
  const VERSION_FIELDS = Object.freeze([
    Object.freeze(['introBases', 0, 8, true]),
    Object.freeze(['codaBars', 0, 6, true]),
    Object.freeze(['bpm', 60, 220, false]),
    Object.freeze(['base1', 0, 3600, false]),
  ]);

  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const minus = n => n < 0 ? '−' + (-n) : String(n);

  function cleanName(s) {
    const t = String(s).replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, 30);
    return t || 'Versione';
  }
  function cleanFileName(s) {
    return String(s || 'audio').replace(/[\u0000-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim().slice(0, 180) || 'audio';
  }
  function fmtT(t) {
    if (!isFinite(t) || t < 0) t = 0;
    const d = Math.round(t * 10), m = Math.floor(d / 600), s = (d % 600) / 10;
    return m + ':' + s.toFixed(1).padStart(4, '0');
  }
  function guessVersion(name) {
    const n = String(name || '').toLowerCase(), c = /conteggio/.test(n);
    const m = n.match(/(?:^|[^a-z0-9])s([12])(?![0-9])/);
    if (m) return 's' + m[1] + (c ? 'c' : '');
    if (/senza\s*intro/.test(n)) return c ? 's2c' : 's2';
    if (/con\s*intro/.test(n)) return c ? 's1c' : 's1';
    return null;
  }
  function isAudioFile(f) {
    if (!f) return false;
    const type = String(f.type || ''), name = String(f.name || '');
    return /^audio\//.test(type) || /\.(m4a|wav|mp3|aiff?|flac|caf)$/i.test(name);
  }
  function audioRejection(f) {
    if (!f) return 'File mancante.';
    if (!isAudioFile(f)) return 'Questo non sembra un file audio.';
    if (!Number.isFinite(f.size) || f.size <= 0) return 'Il file audio è vuoto.';
    if (f.size > AUDIO_MAX) return 'Il file audio è troppo grande (massimo 250 MB).';
    return '';
  }
  function normalizeSpeed(x) {
    const n = Number(x);
    if (!Number.isFinite(n)) return null;
    for (const s of SPEEDS) if (Math.abs(s - n) < 1e-6) return s;
    return null;
  }

  function blankState() {
    const versions = {};
    for (const id of IDS) versions[id] = { ...DEF[id] };
    return { active: 's1', moves: {}, speed: 1, follow: true, autoplay: true, versions, corrupt: false };
  }

  function applyVersionFields(src, target) {
    let dropped = false;
    if (src.name != null) {
      if (typeof src.name === 'string' && src.name.trim()) target.name = cleanName(src.name);
      else dropped = true;
    }
    for (const [field, lo, hi, integer] of VERSION_FIELDS) {
      if (src[field] == null || src[field] === '') continue;
      const x = Number(src[field]);
      if (!Number.isFinite(x)) { dropped = true; continue; }
      const c = clamp(x, lo, hi);
      if (c !== x) dropped = true;
      target[field] = integer ? Math.round(c) : c;
    }
    return dropped;
  }

  /* raw: stringa di localStorage, oggetto, null. Non lancia. */
  function parseState(raw) {
    const S = blankState();
    if (raw == null || raw === '') return S;
    let o;
    try {
      o = typeof raw === 'string' ? JSON.parse(raw) : raw;
    } catch (e) {
      S.corrupt = true;
      return S;
    }
    if (!o || typeof o !== 'object' || Array.isArray(o)) {
      S.corrupt = true;
      return S;
    }
    if (IDS.includes(o.active)) S.active = o.active;
    else if (typeof o.active === 'string' && LEGACY_ACTIVE[o.active]) S.active = LEGACY_ACTIVE[o.active];
    else if (o.active != null) S.corrupt = true;

    if (o.moves == null) { /* niente mosse salvate */ }
    else if (typeof o.moves !== 'object' || Array.isArray(o.moves)) S.corrupt = true;
    else {
      for (const [k, v] of Object.entries(o.moves)) {
        if (/^-?\d+$/.test(k) && typeof v === 'string') {
          if (v.length > MOVE_MAX) S.corrupt = true;
          const t = v.slice(0, MOVE_MAX);
          if (t.trim()) S.moves[k] = t;
        } else S.corrupt = true;
      }
    }

    if (o.speed != null) {
      const sp = normalizeSpeed(o.speed);
      if (sp == null) S.corrupt = true;
      else S.speed = sp;
    }
    if (o.follow != null) {
      if (typeof o.follow === 'boolean') S.follow = o.follow;
      else S.corrupt = true;
    }
    if (o.autoplay != null) {
      if (typeof o.autoplay === 'boolean') S.autoplay = o.autoplay;
      else S.corrupt = true;
    }
    if (o.versions == null) { /* predefiniti */ }
    else if (typeof o.versions !== 'object' || Array.isArray(o.versions)) S.corrupt = true;
    else {
      for (const id of IDS) {
        const src = o.versions[id];
        if (src == null) continue;
        if (typeof src !== 'object' || Array.isArray(src)) { S.corrupt = true; continue; }
        if (applyVersionFields(src, S.versions[id])) S.corrupt = true;
      }
    }
    return S;
  }

  function parseImport(o) {
    if (!o || typeof o !== 'object' || Array.isArray(o) || !o.moves || typeof o.moves !== 'object' || Array.isArray(o.moves)) {
      throw new Error('bad');
    }
    const moves = {};
    for (const [k, v] of Object.entries(o.moves)) {
      if (/^-?\d+$/.test(k) && typeof v === 'string' && v.trim()) moves[k] = v.slice(0, MOVE_MAX);
    }
    const versions = {};
    if (o.versions != null) {
      if (typeof o.versions !== 'object' || Array.isArray(o.versions)) throw new Error('bad');
      for (const id of IDS) {
        const src = o.versions[id];
        if (src == null) continue;
        if (typeof src !== 'object' || Array.isArray(src)) throw new Error('bad');
        const t = {};
        applyVersionFields(src, t);
        versions[id] = t;
      }
    }
    return { moves, versions };
  }

  const beatDur = v => 60 / v.bpm;
  const baseDur = v => 8 * beatDur(v);
  const kOf = n => n > 0 ? n - 1 : n;
  const startOf = (v, n) => v.base1 + kOf(n) * baseDur(v);
  const relOf = (v, t) => (t + EPS - v.base1) / baseDur(v);

  const range = (a, b) => {
    const r = [];
    for (let n = a; n <= b; n++) if (n !== 0) r.push(n);
    return r;
  };

  function buildLayout(v) {
    const intro = clamp(Math.round(Number(v.introBases) || 0), 0, 8);
    const coda = clamp(Math.round(Number(v.codaBars) || 0), 0, 6);
    const secs = [];
    if (intro > 0) secs.push({ cls: 'intro', name: 'Intro', bases: range(-intro, -1).map(n => ({ n, bars: 2 })) });
    for (const s of STRUCT) secs.push({ cls: s.cls, name: s.name, bases: range(s.from, s.to).map(n => ({ n, bars: 2 })) });
    if (coda > 0) {
      const bs = [];
      let left = coda, n = 34;
      while (left > 0) {
        const b = Math.min(2, left);
        bs.push({ n: n++, bars: b });
        left -= b;
      }
      secs[secs.length - 1].bases.push(...bs);
    }
    const rows = [];
    secs.forEach(sec => {
      for (let i = 0; i < sec.bases.length; i += COLS) {
        rows.push({ sec, cont: i > 0, bases: sec.bases.slice(i, i + COLS) });
      }
    });
    return { secs, rows };
  }

  function stateForSave(S) {
    return {
      active: S.active,
      moves: S.moves,
      speed: S.speed,
      follow: S.follow,
      autoplay: S.autoplay,
      versions: S.versions,
    };
  }

  return {
    STRUCT, COLS, COUNT, REST, KEY, EPS, MOVE_MAX, JSON_MAX, AUDIO_MAX, SPEEDS, IDS, DEF,
    LEGACY_ACTIVE, VERSION_FIELDS,
    clamp, minus, cleanName, cleanFileName, fmtT, guessVersion, isAudioFile, audioRejection,
    normalizeSpeed, parseState, parseImport, beatDur, baseDur, kOf, startOf, relOf, buildLayout,
    stateForSave, blankState,
  };
});
