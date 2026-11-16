const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const C = require('../coreografia/logic.js');
const root = path.join(__dirname, '..');

test('guessVersion riconosce le quattro tracce dal nome', () => {
  assert.equal(C.guessVersion('01 Exótica (Salsa Remix s1 conteggio – con intro).m4a'), 's1c');
  assert.equal(C.guessVersion('02 Exotica s2 senza intro.wav'), 's2');
  assert.equal(C.guessVersion('remix-s1.mp3'), 's1');
  assert.equal(C.guessVersion('ballo conteggio senza intro.m4a'), 's2c');
  assert.equal(C.guessVersion('con intro.flac'), 's1');
  assert.equal(C.guessVersion('music s12.mp3'), null);
  assert.equal(C.guessVersion('appunti.txt'), null);
  assert.equal(C.guessVersion(''), null);
});

test('parseState accetta il salvataggio attuale senza segnalarlo come danneggiato', () => {
  const saved = {
    active: 's2',
    moves: { '1': 'passo base', '-2': 'intro' },
    speed: 0.8,
    follow: false,
    autoplay: true,
    versions: {
      s1: { ...C.DEF.s1 },
      s1c: { ...C.DEF.s1c },
      s2: { ...C.DEF.s2, base1: 0.05 },
      s2c: { ...C.DEF.s2c },
    },
  };
  const S = C.parseState(JSON.stringify(saved));
  assert.equal(S.corrupt, false);
  assert.equal(S.active, 's2');
  assert.equal(S.moves['1'], 'passo base');
  assert.equal(S.speed, 0.8);
  assert.equal(S.follow, false);
  assert.equal(S.versions.s2.base1, 0.05);
  assert.equal(S.versions.s1.bpm, 130);
});

test('parseState recupera JSON illeggibile e campi del tipo sbagliato', () => {
  assert.equal(C.parseState('{').corrupt, true);
  assert.equal(C.parseState('null').corrupt, true);
  assert.equal(C.parseState('[]').corrupt, true);
  assert.deepEqual(C.parseState(null).moves, {});
  assert.equal(C.parseState(null).corrupt, false);

  const S = C.parseState({
    active: 'nope',
    speed: 99,
    follow: 'sì',
    moves: { '1': '<img src=x onerror=alert(1)>', bad: { x: 1 }, '2': 5 },
    versions: { s1: 'nope', s2: { bpm: 'lento', name: '  ok  ', base1: -4 } },
  });
  assert.equal(S.corrupt, true);
  assert.equal(S.active, 's1');
  assert.equal(S.speed, 1);
  assert.equal(S.follow, true);
  assert.equal(S.moves['1'], '<img src=x onerror=alert(1)>');
  assert.equal(S.moves['2'], undefined);
  assert.equal(S.moves.bad, undefined);
  assert.equal(S.versions.s1.bpm, 130);
  assert.equal(S.versions.s1.name, C.DEF.s1.name);
  assert.equal(S.versions.s2.name, 'ok');
  assert.equal(S.versions.s2.bpm, 130);
  assert.equal(S.versions.s2.base1, 0);
});

test('parseState migra le schede vecchie e taglia le mosse enormi', () => {
  const S = C.parseState({ active: 'b', moves: { '4': 'x'.repeat(C.MOVE_MAX + 50) } });
  assert.equal(S.active, 's2');
  assert.equal(S.moves['4'].length, C.MOVE_MAX);
  assert.equal(S.corrupt, true);
});

test('parseImport rifiuta la spazzatura e non tiene HTML come struttura', () => {
  assert.throws(() => C.parseImport(null));
  assert.throws(() => C.parseImport([]));
  assert.throws(() => C.parseImport({ moves: null }));
  assert.throws(() => C.parseImport({ moves: ['passo'] }));
  const out = C.parseImport({
    moves: { '3': 'giro', 'x': '<script>alert(1)</script>', '8': '  ' },
    versions: { s2: { bpm: 4000, introBases: 0, name: 's2 · prova' } },
  });
  assert.deepEqual(out.moves, { '3': 'giro' });
  assert.equal(out.versions.s2.bpm, 220);
  assert.equal(out.versions.s2.introBases, 0);
  assert.equal(out.versions.s2.name, 's2 · prova');
  assert.equal(Object.keys(C.parseImport({ moves: {} }).moves).length, 0);
});

test('la griglia e la tolleranza di 8 ms tengono la base giusta sul confine', () => {
  const v = C.DEF.s1;
  const layout = C.buildLayout(v);
  const ns = layout.rows.flatMap(r => r.bases.map(b => b.n));
  assert.equal(ns[0], -2);
  assert.equal(ns[1], -1);
  assert.ok(ns.includes(1) && ns.includes(33) && ns.includes(34));
  assert.equal(layout.rows.at(-1).bases.at(-1).bars, 1);
  assert.equal(new Set(ns).size, ns.length);

  const noIntro = C.buildLayout(C.DEF.s2);
  assert.equal(noIntro.rows[0].bases[0].n, 1);
  assert.ok(!noIntro.rows.flatMap(r => r.bases).some(b => b.n < 0));

  const b1 = v.base1;
  assert.equal(Math.floor(C.relOf(v, b1)), 0);
  assert.equal(Math.floor(C.relOf(v, b1 - 0.007)), 0);
  assert.equal(Math.floor(C.relOf(v, b1 - 0.009)), -1);
  assert.equal(Math.floor(C.relOf(v, 0)), -2);
  assert.equal(C.fmtT(0), '0:00.0');
  assert.equal(C.fmtT(61), '1:01.0');
  assert.equal(C.fmtT(Number.NaN), '0:00.0');
  assert.equal(C.minus(-2), '−2');
});

test('i file audio vuoti, enormi o non audio vengono rifiutati prima di leggerli', () => {
  assert.equal(C.audioRejection({ name: 'a.wav', type: 'audio/wav', size: 10 }), '');
  assert.match(C.audioRejection({ name: 'a.txt', type: 'text/plain', size: 10 }), /non sembra/);
  assert.match(C.audioRejection({ name: 'a.mp3', type: '', size: 0 }), /vuoto/);
  assert.match(C.audioRejection({ name: 'a.wav', type: 'audio/wav', size: C.AUDIO_MAX + 1 }), /troppo grande/);
});

test('CNAME, niente audio tracciato, niente sink HTML nel codice della pagina', () => {
  assert.equal(fs.readFileSync(path.join(root, 'CNAME'), 'utf8'), 'musicremix.byluke.org\n');
  assert.equal(fs.existsSync(path.join(root, '.nojekyll')), true);
  const tracked = execFileSync('git', ['ls-files'], { cwd: root, encoding: 'utf8' });
  assert.doesNotMatch(tracked, /\.(m4a|wav|mp3|flac|aiff?|caf)$/im);
  for (const rel of ['coreografia/index.html', 'coreografia/app.js', 'coreografia/logic.js', 'index.html', '404.html']) {
    const src = fs.readFileSync(path.join(root, rel), 'utf8');
    assert.doesNotMatch(src, /innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\s*\(/);
    assert.doesNotMatch(src, /\/MusicRemix\//);
  }
  const page = fs.readFileSync(path.join(root, 'coreografia/index.html'), 'utf8');
  assert.match(page, /script-src 'self'/);
  assert.match(page, /src="logic\.js"/);
  assert.match(page, /src="app\.js"/);
  assert.doesNotMatch(page, /<script(?![^>]*\bsrc=)/);
  const landing = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  assert.match(landing, /script-src 'none'|default-src 'none'/);
  assert.match(landing, /rel="noopener noreferrer"/);
  assert.doesNotMatch(landing, /<script/);
});
