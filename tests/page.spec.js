const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

function wav(seconds = 2, sr = 8000) {
  const n = Math.floor(sr * seconds);
  const buf = Buffer.alloc(44 + n * 2);
  buf.write('RIFF', 0);
  buf.writeUInt32LE(36 + n * 2, 4);
  buf.write('WAVE', 8);
  buf.write('fmt ', 12);
  buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20);
  buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(sr, 24);
  buf.writeUInt32LE(sr * 2, 28);
  buf.writeUInt16LE(2, 32);
  buf.writeUInt16LE(16, 34);
  buf.write('data', 36);
  buf.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) {
    const s = Math.sin((2 * Math.PI * 220 * i) / sr) * 0.2;
    buf.writeInt16LE((s * 32767) | 0, 44 + i * 2);
  }
  return buf;
}

const move = (page, n) => page.getByRole('textbox', { name: `Mossa della base ${n}`, exact: true });
const baseCell = (page, n) => page.locator(`.base[data-n="${n}"]`);

function watch(page) {
  const problems = [];
  page.on('pageerror', err => problems.push(String(err)));
  page.on('console', msg => {
    if (msg.type() === 'error') problems.push(msg.text());
  });
  return problems;
}

async function openApp(page) {
  const problems = watch(page);
  await page.goto('/coreografia/');
  await expect(page.locator('#score .base').first()).toBeVisible();
  return problems;
}

test('la pagina iniziale presenta il sito e apre la coreografia', async ({ page }) => {
  const problems = watch(page);
  await page.goto('/');
  await expect(page).toHaveTitle(/Coreografia salsa/);
  await expect(page.locator('meta[name="description"]')).toHaveAttribute('content', /audio/);
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute('content', /\/og\.png$/);
  const ext = page.locator('a[target="_blank"]');
  await expect(ext).toHaveAttribute('rel', /noopener/);
  await page.getByRole('link', { name: 'Apri la coreografia' }).click();
  await expect(page).toHaveURL(/\/coreografia\/?$/);
  await expect(page.locator('#score .num').first()).toBeVisible();
  expect(problems).toEqual([]);
});

test('senza audio la pagina è usabile e i salti spiegano cosa manca', async ({ page }) => {
  const problems = await openApp(page);
  await expect(page.locator('#audioState')).toHaveText('Nessun audio');
  await expect(page.locator('#verSel option')).toHaveCount(4);
  await expect(baseCell(page, -2)).toBeVisible();
  await expect(page.locator('#bPlay')).toBeDisabled();
  await page.locator('h1').click();
  await page.keyboard.press('Space');
  await expect(page.locator('#toast.show')).toContainText('Carica prima il file audio');
  await baseCell(page, 1).click({ position: { x: 8, y: 20 } });
  await expect(page.locator('#toast.show')).toContainText('Carica prima il file audio');
  await expect(page.locator('#panel')).toHaveAttribute('open', '');
  expect(problems).toEqual([]);
});

test('si scrive una mossa, si ricarica, e un localStorage rotto non butta giù la pagina', async ({ page }) => {
  const problems = await openApp(page);
  const box = move(page, 1);
  await box.fill('passo base -> giro');
  await box.blur();
  await expect(box).toHaveValue('passo base → giro');
  await expect(page.locator('#sideList [data-n="1"] .t')).toHaveText('passo base → giro');
  await expect(page.locator('#sideCount')).toHaveText(/1 \/ /);
  await page.waitForFunction(() => (localStorage.getItem('exotica-coreografia-v1') || '').includes('passo base'));
  await page.reload();
  await expect(move(page, 1)).toHaveValue('passo base → giro');

  // pagehide riscrive lo stato buono: il valore avariato va messo dopo, prima degli script.
  await page.addInitScript(() => {
    const poison = sessionStorage.getItem('exotica-test-poison');
    if (poison != null) {
      localStorage.setItem('exotica-coreografia-v1', poison);
      sessionStorage.removeItem('exotica-test-poison');
    }
  });
  await page.evaluate(() => sessionStorage.setItem('exotica-test-poison', '{'));
  await page.reload();
  await expect(page.locator('#toast.show')).toContainText('danneggiati');
  await expect(baseCell(page, 1)).toBeVisible();
  await expect(move(page, 1)).toHaveValue('');

  await page.evaluate(() => sessionStorage.setItem('exotica-test-poison', JSON.stringify({
    moves: { '5': '<img src=x onerror=alert(1)>' },
    versions: { s1: { bpm: 'no' } },
    speed: 3,
  })));
  await page.reload();
  await expect(move(page, 5)).toHaveValue('<img src=x onerror=alert(1)>');
  await expect(page.locator('img')).toHaveCount(0);
  await expect(page.locator('#fBpm')).toHaveValue('130');
  expect(problems).toEqual([]);
});

test('export, import, annullamento e file json non valido', async ({ page }) => {
  const problems = await openApp(page);
  await move(page, 2).fill('abre');
  await page.locator('#panel > summary').click();
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Salva su file' }).click(),
  ]);
  const saved = path.join(test.info().outputDir, download.suggestedFilename());
  await download.saveAs(saved);
  const json = JSON.parse(fs.readFileSync(saved, 'utf8'));
  assertMove(json, '2', 'abre');

  page.once('dialog', d => d.accept());
  await page.locator('#fJson').setInputFiles({
    name: 'mosse.json',
    mimeType: 'application/json',
    buffer: Buffer.from('\uFEFF' + JSON.stringify({ moves: { '6': 'coppia' } })),
  });
  await expect(move(page, 6)).toHaveValue('coppia');
  await expect(move(page, 2)).toHaveValue('');

  page.once('dialog', async d => {
    expect(d.message()).toContain('non contiene mosse');
    await d.dismiss();
  });
  await move(page, 6).fill('coppia');
  await page.locator('#fJson').setInputFiles({
    name: 'vuoto.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ moves: {} })),
  });
  await expect(move(page, 6)).toHaveValue('coppia');

  await page.locator('#fJson').setInputFiles({
    name: 'note.txt',
    mimeType: 'application/json',
    buffer: Buffer.from('non è json'),
  });
  await expect(page.locator('#toast.show')).toContainText('File non valido');
  await page.locator('#fJson').setInputFiles({
    name: 'grosso.json',
    mimeType: 'application/json',
    buffer: Buffer.alloc(1024 * 1024 + 10, 0x61),
  });
  await expect(page.locator('#toast.show')).toContainText('troppo grande');
  expect(problems).toEqual([]);
});

function assertMove(json, key, value) {
  if (!json.moves || json.moves[key] !== value) throw new Error('export senza la mossa attesa');
}

test('audio locale: play, scorciatoie, versione, file rifiutati, allineamento', async ({ page }) => {
  const problems = await openApp(page);
  await page.locator('#fFile').setInputFiles({ name: 'vuoto.mp3', mimeType: 'audio/mpeg', buffer: Buffer.alloc(0) });
  await expect(page.locator('#toast.show')).toContainText('vuoto');

  await page.locator('#fFile').setInputFiles({ name: 'appunti.wav', mimeType: 'audio/wav', buffer: Buffer.from('non-wav') });
  await expect(page.locator('#toast.show')).toContainText('Non riesco ad aprire');
  await expect(page.locator('#audioState')).toHaveText('File non apribile');

  await page.locator('#fFile').setInputFiles({ name: 'nota.wav', mimeType: 'audio/wav', buffer: wav(8) });
  await expect(page.locator('#audioName')).toHaveText('nota.wav');
  await page.waitForTimeout(250);
  await expect(page.locator('#audioState')).toHaveText('Audio:');
  await expect(page.locator('#bPlay')).toBeEnabled();
  await page.locator('#bPlay').click();
  await expect(page.locator('#player')).toHaveClass(/playing/);
  await page.waitForFunction(() => document.querySelector('audio').currentTime > 0.05);
  const before = await page.evaluate(() => window.__coreo.now());
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(t => window.__coreo.now() > t + 1, before);
  await page.keyboard.press('Space');
  await expect(page.locator('#player')).not.toHaveClass(/playing/);
  await page.keyboard.press('Home');
  await expect(page.locator('#player')).toHaveClass(/playing/);
  await page.locator('#bStop').click();

  await page.locator('#speed').selectOption('0.5');
  await expect.poll(() => page.evaluate(() => document.querySelector('audio').playbackRate)).toBe(0.5);
  await page.locator('#loopCtl button[data-loop="base"]').click();
  await expect(page.locator('#loopCtl button[data-loop="base"]')).toHaveAttribute('aria-pressed', 'true');

  await page.locator('#verSel').selectOption('s2');
  await expect(page.locator('#fIntro')).toHaveValue('0');
  await expect(baseCell(page, -2)).toHaveCount(0);
  await page.locator('#verSel').selectOption('s1');
  await expect(page.locator('#audioName')).toHaveText('nota.wav');

  await page.locator('#panel > summary').click();
  await page.locator('#bAuto').click();
  await expect(page.locator('#toast.show')).toContainText(/Griglia|Ritmo|analizzare/);
  await page.locator('#bUnload').click();
  await expect(page.locator('#audioState')).toHaveText('Nessun audio');
  await page.waitForTimeout(400);
  await expect(page.locator('#audioState')).toHaveText('Nessun audio');
  expect(problems.filter(p => !/decodeAudioData|NotSupportedError/.test(p))).toEqual([]);
});

test('trascinare un file e una parola lunghissima non rompono il layout, neanche su mobile', async ({ page }) => {
  const problems = await openApp(page);
  const clip = wav(1);
  await page.evaluate(async b64 => {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], '01 s1.wav', { type: 'audio/wav' }));
    dt.items.add(new File([bytes], '02 s2 conteggio.wav', { type: 'audio/wav' }));
    document.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
  }, clip.toString('base64'));
  await expect(page.locator('#toast.show')).toContainText('Assegnati');

  const word = 'supercalifragilistico'.repeat(20);
  await move(page, 1).fill(word);
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(await overflow()).toBeLessThanOrEqual(1);

  await page.setViewportSize({ width: 320, height: 700 });
  expect(await overflow()).toBeLessThanOrEqual(1);
  await page.locator('#bMore').click();
  await expect(page.locator('#bLoad')).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await overflow()).toBeLessThanOrEqual(1);
  await page.setViewportSize({ width: 1280, height: 800 });
  expect(problems).toEqual([]);
});

test('copia, cancella e ripristino dei valori predefiniti', async ({ page, context }) => {
  const problems = await openApp(page);
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await move(page, 3).fill('dile que no');
  await page.locator('#panel > summary').click();
  await page.getByRole('button', { name: 'Copia come testo' }).click();
  await expect(page.locator('#toast.show')).toContainText(/Copiato|Non riesco a copiare/);
  page.once('dialog', d => d.accept());
  await page.getByRole('button', { name: 'Cancella tutte' }).click();
  await expect(move(page, 3)).toHaveValue('');
  await page.locator('#fIntro').fill('0');
  await page.locator('#fIntro').dispatchEvent('change');
  await expect(baseCell(page, -2)).toHaveCount(0);
  await page.getByRole('button', { name: 'Valori predefiniti' }).click();
  await expect(page.locator('#fIntro')).toHaveValue('2');
  await expect(baseCell(page, -2)).toBeVisible();
  expect(problems).toEqual([]);
});
