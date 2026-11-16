# MusicRemix — Ardour controllato da Claude Code

L'utente parla italiano: rispondere in italiano. Obiettivo: produzione musicale in Ardour
guidata da linguaggio naturale; ogni modifica deve finire nella sessione Ardour (non
distruttiva, versionata). Primo progetto: "Exotica" (Gabry Ponte, Greg Taro) → salsa ballabile
in coppia, 130 BPM. Lavorare su audio commerciale solo con il file fornito dall'utente; mai
caricarlo su servizi esterni.

## Architettura (verificata il 2026-10-13, Ardour 9.8 compilato dai sorgenti, arm64)

- **Ardour in uso**: build dai sorgenti (tag 9.8, GPL, senza limiti demo) in `~/Builds/ardour-install`
  (`bin/ardour9`, sorgenti `~/Builds/ardour-9.8`, log di build `~/Builds/logs/`). La demo firmata
  `/Applications/Ardour9.app` resta solo come ripiego (`launch_ardour.sh` la usa se la build manca).

- **`ardour`** (MCP HTTP nativo di Ardour, `http://127.0.0.1:4820/mcp`): tracce, bus, plugin,
  note MIDI (`midi_note_import_json_*`), regioni, fader, mute/solo, send, marker, transport,
  undo/redo, save/snapshot. È un control surface di Ardour ("MCP HTTP Server (Experimental)"),
  attivo nella sessione.
- **`ardour-studio`** (`bridge/server`, Python): ciò che il nativo non fa — `set_tempo`,
  `set_meter`, `import_audio`, `export_wav` (+ analisi), `save_version`, `project_overview`,
  `set_pan` (−100 sx … +100 dx), `analyze_audio`, `ardour_lua` (Lua arbitrario),
  `salsa_arrangement_info` / `salsa_render` (parti salsa generate come regioni MIDI per sezione,
  vedi `bridge/server/ardour_studio_mcp/salsa.py` e `docs/ANALISI_EXOTICA.md`).
  Parla con Ardour tramite il **ponte Lua** (`bridge/lua/claude_bridge.lua`): un Action Hook
  su `LuaTimerDS` installato in `~/Library/Preferences/Ardour9/ui_scripts` da
  `bridge/install_bridge.py`; scambio file in `~/.ardour-claude-bridge/`.
- **Sicurezza di rete**: il server MCP nativo non ha autenticazione. Nella build compilata è
  patchato per ascoltare solo su `127.0.0.1:4820` (`bridge/patches-ardour-mcp-localhost.diff`,
  da riapplicare se si ricompila). La regola firewall copre solo la demo `Ardour9.app`.
- **OSC** (UDP 3819, ascolta su tutte le interfacce) è **disattivato** nella sessione dal v011;
  riattivarlo solo temporaneamente per `bridge/tests/osc_roundtrip.py`.
- `vendor/ardour-mcp` (raibid-entertainment): **non funzionante** come server MCP (tools/list →
  "Method not found"; tutti i tool finiscono nell'ultimo handler registrato). Non registrarlo.

## Insidie verificate

- `track_set_pan` nativo: 0.0 = DESTRA, 1.0 = SINISTRA. Preferire `set_pan` di ardour-studio.
- `midi_note_import_json_*`: i campi nota sono `n`, `v`, `l`, `b`, `bar` (non `note`). Una
  chiamata con errore di validazione può comunque creare una regione vuota: controllare con
  `track_get_regions` / `project_overview` e rimuoverla.
- `Editor:do_import` con `ImportToTrack` ignora la traccia passata (usa la selezione GUI):
  per questo `import_audio` importa come regione e poi la posiziona nella playlist.
- `track_rename` vuole `newName`. Lua: `Session:simple_export()`, `rg:to_audioregion():n_channels()`,
  `ControlProtocolManager.manager():activate(info, "")`; `Session:dirty()` non esiste.
- **Versione Demo** (non più in uso): dal sorgente (`audioengine.cc`, `SILENCE_AFTER_SECONDS 600`) l'uscita va in
  silenzio dopo ~10 min di motore attivo. Test reale: export a 11 min dall'avvio ancora
  corretto, quindi l'effetto sugli export non è confermato. `export_wav` segnala silenzio
  sospetto nei `warnings`; in quel caso salvare, riavviare Ardour e riesportare.
- `~/Documents` è sincronizzato su iCloud (Ottimizza spazio attivo): dati audio e sessioni stanno
  in `~/Music/MusicRemix/` (symlink `sessions/ exports/ backups/ assets/`); i venv Python in
  `~/.local/share/musicremix/` (iCloud marca come nascosti i `.pth` e Python li ignora).

- **Avvio senza dialoghi**: lo stato del motore audio è scritto a mano in
  `~/Library/Preferences/Ardour9/config` (`<AudioMIDISetup>`: CoreAudio, input "MacBook Air
  Microphone", output "MacBook Air Speakers", 48 kHz) e deve combaciare con gli `EngineHints` della
  sessione; altrimenti Ardour si ferma su un dialogo modale (es. quando le AirPods diventano il
  dispositivo predefinito). La build compilata richiede il permesso Microfono (dato il 2026-10-12).
  Ardour chiuso con kill lascia `<sessione>.pending`: spostarlo in `backups/` prima di riaprire,
  o comparirà il dialogo di recupero.
- **Deadlock**: mai aggiungere regioni a una playlist mentre si itera
  `ARDOUR.RegionFactory.regions()` (il thread GUI resta bloccato sul lock della playlist e Ardour va
  ucciso). Raccogliere prima le regioni in una tabella, poi aggiungerle.
- MIDI: niente Program Change sul canale 10 (gmsynth passerebbe le percussioni a un suono
  melodico). I nomi file da importare devono essere ASCII: `Editor:do_import` con più file si ferma
  al primo percorso con caratteri accentati. Il mute applicato via Lua è asincrono: rileggerlo
  subito restituisce il valore precedente.
- Sul sistema `find` è sostituito da `bfs` (niente `-newermt "-3 seconds"`): usare `stat -f %m`.
- Export da un punto diverso da 0: far partire l'intervallo da un multiplo di 64 campioni,
  altrimenti General MIDI Synth (blocchi interni da 64) sposta le note di frazioni di ms rispetto a
  un export da 0 (residuo −11 dB invece di −30 dB; verificato il 2026-10-13).
- Versioni da ascoltare: `~/Music/MusicRemix/Version/` (symlink `Version/`), con `LEGGIMI.txt`.
  Dopo ogni nuova `Exotica sN.wav`: aggiornare `Version/versioni.json` (sottotitolo) e lanciare
  `~/.local/share/musicremix/venv-sep/bin/python bridge/publish_version.py` → `.m4a` Apple Lossless con
  copertina generata, metadati e testo da `Version/testo.txt` (fornito dall'utente: non trascrivere
  né riprodurre noi il testo protetto da copyright).
- Conteggio per ballerini: `bridge/make_count_track.py` (TTS locale `say`, voce Alice, "uno due tre /
  cinque sei sette", l'1 sulle battute dispari) → traccia audio "Conteggio 123-567" (fader +4 dB, mutata
  nel mix normale). Versioni conteggio = voce originale mutata + conteggio attivo.
- I file audio commerciali sono limitati a 0 dBFS: con la voce originale nel mix serve il master
  a circa −6 dB per restare sotto −1 dBTP (nessun limiter in catena per ora).

## Coreografia (pagina locale, `coreografia/index.html`)

- Pagina unica, senza server né dipendenze: si apre col browser (meglio Safari per gli `.m4a` Apple
  Lossless; `.wav`/`.mp3` vanno ovunque). Pentagramma a **basi** (1 base = 8 tempi = 2 battute,
  1 2 3 · 5 6 7 ·), righe per sezione (`STRUCT`, ricavata da `docs/ANALISI_EXOTICA.md`, a capo ogni 4 basi),
  player con Parti/Stop/Da capo, salti "precedente / questa / successiva, dall'1 o dal 5", ripeti base/riga,
  velocità, casella mosse per base e colonna laterale con tutte le mosse (buchi dove vuote).
- Numerazione: la base 1 è l'inizio della canzone originale; l'intro del remix ha basi negative (−2, −1).
  Le mosse sono legate al numero di base, quindi valgono per entrambe le versioni.
- Versioni (menu a tendina in alto): `s1` con intro, `s1c` s1 conteggio con intro, `s2` senza intro, `s2c`
  s2 conteggio senza intro (le 4 tracce di "Exótica - Single" in Musica). Le mosse sono comuni a tutte; audio e
  griglia sono per versione. Si possono scegliere/trascinare anche più file insieme: la versione si riconosce dal
  nome (`s1`/`s2`, `conteggio`, `con/senza intro`).
- L'audio non sta nel progetto: lo sceglie l'utente dal browser (resta nel browser in IndexedDB, mai caricato
  altrove). La griglia parte da "inizio base 1" per versione e si corregge dal pannello (segna qui, allinea
  automaticamente, ±10 ms, ±1 tempo; il pannello mostra anche quanto audio resta dopo la base 33). Predefiniti
  MISURATI sui file veri il 2026-11-16: con intro (s1, s1c) 7,385 s; senza intro (s2, s2c) 0,048 s. Verifica:
  il conteggio dice "uno" a 0 / 3,692 / 7,383 s (8 tempi esatti); fase del ritmo 0,001 s (s1) e 0,048 s (s2);
  "Allinea automaticamente" dà ±1 ms; il colpo finale cade sul tempo 1 della base 34 (129,232 s in s1, ±1 ms).
  Sezioni confermate da `salsa.py` (battute sessione − 4); il Finale dura 3 battute: base 33 + colpo finale = base 34.
- Mosse in `localStorage` + esporta/importa JSON. Tolleranza di 8 ms (`EPS`) nel calcolo della base corrente:
  senza, un salto esatto sull'inizio di una base risultava nella base prima.
- Dove sono le tracce (verificato il 2026-11-16): sul Mac mini non ci sono `~/Music/MusicRemix`, Ardour né i
  WAV originali (solo `Documents`, sincronizzato da iCloud). Le 4 versioni sono in Musica come tracce iCloud
  ("Exótica - Single"); scaricate, stanno in `~/Music/Music/Media.localized/Music/Gabry Ponte & Greg Taro/Exótica
  (Salsa Remix)/` come `.m4a` **AAC** 256 kbps stereo 44,1 kHz (non Apple Lossless: Chrome le apre): 01 s1 con
  intro 133,08 s, 02 s2 senza intro 125,74 s, 03 s1 conteggio, 04 s2 conteggio. Prima del download la libreria
  (`~/Music/Music/Music Library.musiclibrary/Library.musicdb`, AES-ECB "BHUILuilfghuila3" + zlib dopo i primi
  102400 B) le elencava senza percorso; AppleScript sulla libreria andava in timeout. Pagina provata in Chrome
  con quei file; non in Safari.

## Pubblicazione (GitHub)

- Repository pubblico: https://github.com/LukePalmDev/MusicRemix (branch `main`). Sito (GitHub Pages dal ramo
  `main`, cartella radice): https://lukepalmdev.github.io/MusicRemix/coreografia/ — la radice reindirizza lì.
  Dopo un `git push` il sito si aggiorna in circa un minuto.
- La cartella interna di git sta fuori da iCloud: `~/.local/share/musicremix/musicremix.git` (`.git` nel progetto è
  solo un file che la indica; creato con `git init --separate-git-dir`). `gh repo create --source=.` non la riconosce:
  creare il repository senza `--source`, poi `git remote add` e `git push`.
- Identità dei commit: nome `LukePalmDev`, email riservata `218281005+LukePalmDev@users.noreply.github.com`
  (impostate solo in questo repository; la email personale non va nei commit).
- **Mai pubblicare**: audio (`*.m4a *.wav …`) e i link a `assets/ sessions/ exports/ backups/ Version/` (musica
  commerciale; regola del progetto), `vendor/` (repository di terzi con la sua `.git`), `bridge/logs/`, `.mcp.json`
  (percorsi locali). Sono tutti in `.gitignore`; controllare con `git ls-files` prima di ogni push.
- La pagina non contiene audio: lo carica chi la usa dal proprio browser (IndexedDB). Le mosse stanno nel
  `localStorage` del browser sul dominio del sito, quindi non coincidono con quelle scritte aprendo il file da disco.

## Operazioni

- Avvio: `bridge/launch_ardour.sh [sessione.ardour]` (default: Exotica Salsa Remix). Attendere
  `bridge_status` → `bridge_alive: true`. Il server `ardour` risponde solo con Ardour aperto.
- Ardour deve essere chiuso per (re)installare il ponte: `python3 bridge/install_bridge.py`.
- Test: `bridge/tests/studio_e2e.py`, `bridge/tests/osc_roundtrip.py`; CLI rapide
  `bridge/lua_call.py '<lua>'`, `bridge/mcp_call.py <tool> '<json>'`,
  `~/.local/share/musicremix/venv-studio/bin/python bridge/studio_call.py <tool> '<json>'` (tool ardour-studio).
- Dopo modifiche al server: `cd bridge/server && UV_PROJECT_ENVIRONMENT=~/.local/share/musicremix/venv-studio uv sync`.

## Flusso per ogni richiesta di modifica musicale

1. `project_overview` → identificare tracce/regioni coinvolte.
2. `save_version("prima: …")`.
3. Eseguire le modifiche (tool nativi per tracce/MIDI/mixer/plugin, ardour-studio per il resto),
   toccando solo ciò che è richiesto.
4. `save_version("…descrizione…")` → `export_wav` → riportare all'utente cosa è cambiato,
   file esportato e metriche tecniche, distinguendo controlli tecnici da giudizi artistici.
