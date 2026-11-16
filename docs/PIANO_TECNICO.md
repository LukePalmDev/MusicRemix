# Piano tecnico — Ardour controllato da Claude Code

Stato al 2026-10-13 (aggiornato: Ardour ora compilato dai sorgenti, arrangiamento salsa v2 generato). Ogni voce "✅" è stata verificata con un test reale su Ardour 9.8.186
(build Free/Demo arm64 ufficiale, firmata da Paul Davis, notarizzata Apple).

## 1. Ambiente

| Voce | Stato |
|---|---|
| Mac mini M4, macOS 27.0, arm64, 8 GB RAM, 34 GB liberi | ok |
| Homebrew 7.0.7, Node, git | presenti |
| Python di sistema 3.9 (troppo vecchio per MCP) → `uv` 0.13 + Python 3.12 gestito | installato |
| `~/Documents` sincronizzato su iCloud con "Ottimizza spazio" | dati spostati in `~/Music/MusicRemix` |
| Firewall macOS attivo, regola Ardour9 = "blocca in entrata" (2026-10-12) | ok: LAN bloccata, 127.0.0.1 funziona |

## 2. Componenti valutati

| Componente | Esito |
|---|---|
| **Ardour 9.8** | Installato. Lua scripting completo, OSC, e un **server MCP HTTP nativo** (95 tool). |
| **raibid-entertainment/ardour-mcp** (ultimo commit 2025-11-20, "Alpha") | **Non funzionante**: `tools/list` → "Method not found"; ogni chiamata finisce nell'ultimo handler (bug di registrazione con l'SDK MCP low-level). Inoltre usa indirizzi OSC che Ardour non implementa (`/add_audio_track`, `/add_midi_track`, `/set_tempo`, `/set_time_signature`, `/transport_pause`, `/set_punch_in/out`, `/strip/automation_mode`): anche se riparato, creare tracce e cambiare tempo non funzionerebbe. Tenuto in `vendor/` solo come riferimento. |
| OSC di Ardour | Bidirezionale ✅, ma senza creazione tracce, tempo, plugin, note MIDI, import, export. |
| MCP HTTP nativo | Principale canale di controllo ✅ |
| Ponte Lua (sviluppato) + server `ardour-studio` | Copre le lacune del nativo ✅ |

## 3. Matrice dei test (Fase 2)

| Funzione | Strumento | Esito |
|---|---|---|
| Creare traccia audio | nativo `tracks_add` | ✅ |
| Creare traccia MIDI | nativo `tracks_add` | ✅ |
| Rinominare | nativo `track_rename` (`newName`) | ✅ |
| Tempo 130 BPM, metro 4/4 | `set_tempo`, `set_meter` (Lua) | ✅ riletto dalla tempo map |
| Importare audio | `import_audio` (Lua) | ✅ su nuova traccia a battuta 3, durata conservata |
| Strumento virtuale | nativo `plugin_add_by_unique_id` (General MIDI Synth) | ✅ udibile nell'export |
| Note MIDI | nativo `midi_note_import_json_to_new_region_bbt` | ✅ 22/22 note; ⚠ crea regione vuota se la validazione fallisce |
| Modificare regioni audio | nativo `region_set_gain_db`, `region_move_to_bbt`, `region_split` | ✅ verificato al campione |
| Volume | nativo `track_set_fader_db`, anche via OSC `/strip/gain` | ✅ |
| Panorama | `set_pan` (−100…+100) | ✅ misurato su L/R; ⚠ nativo invertito (0 = destra) |
| Effetti | nativo `plugin_add_by_unique_id` (ACE Reverb) | ✅ |
| Salvare | nativo `session_save`, `save_version` (snapshot + backup) | ✅ |
| Esportare WAV | `export_wav` (Ardour SimpleExport) + analisi | ✅ 48 kHz/16 bit, contenuto verificato per battuta |
| Comunicazione bidirezionale | MCP nativo (HTTP), ponte Lua (file), OSC (UDP 3819↔8000) | ✅ tutte e tre |

## 4. Limiti noti e rischi

1. **Risolto il 2026-10-12/13**: Ardour 9.8 compilato dai sorgenti (`~/Builds/ardour-install`), quindi
   nessun limite demo. Regressione ripetuta sulla build: e2e ardour-studio ok, OSC ok, export con audio ok.
   Storico, versione Demo: dopo 10 min di motore audio attivo l'uscita va in silenzio (poi 5 min,
   2,5 min, … minimo 1 min) finché non si riavvia o si conferma il dialogo (da codice
   sorgente). Test reale: un export fatto 11 minuti dopo l'avvio conteneva ancora audio
   regolare, quindi l'impatto sugli export non è confermato; resta da osservare in uso. Opzioni: (a) restare in demo e riavviare Ardour prima di ogni export;
   (b) versione completa pagata dall'utente; (c) compilare Ardour dai sorgenti (GPL, gratuito,
   lungo e senza firma Apple).
2. **Sicurezza**: il server MCP nativo e l'OSC ascoltano su tutte le interfacce, senza
   autenticazione. Mitigazione: firewall macOS → Ardour9 "blocca connessioni in entrata"
   (il traffico locale 127.0.0.1 continua a funzionare).
3. Il server MCP nativo è "Experimental": verificare sempre i risultati (`project_overview`).
4. Suoni: per ora General MIDI Synth (gratuito, qualità media). Per un risultato salsa credibile
   servono campioni migliori (es. SoundFont SF2 liberi con ACE Fluid Synth) → Fase 3.

## 5. Stato Fase 3–6 (2026-10-13)

- Fase 4 fatta: stem calibrati, analisi (130 BPM esatti, La minore, clave 3-2), vedi `docs/ANALISI_EXOTICA.md`.
  Nessun time-stretch necessario: l'originale è già a 130 BPM.
- Fase 3 fatta (prima versione): `salsa_render` genera 9 parti MIDI per sezione; sessione v010, export
  `exports/Exotica salsa v2 *.wav`.
- Fase 6: controlli di sincronia, armonia, picchi, loudness eseguiti; da aggiungere al server come tool.

## 6. Prossimi passi

- **Fase 3**: strumenti di arrangiamento di alto livello (pattern clave 2-3/3-2, conga tumbao,
  campana, guiro/maracas, tumbao del basso, montuno del piano, fiati) che scrivono MIDI in
  Ardour rispettando sezioni e armonia; caricamento SoundFont; send/bus di riverbero; marker
  di sezione.
- **Fase 4**: file `.m4a` acquistato su iTunes Store (AAC 256 kbps, senza DRM) → conversione
  locale con `afconvert` → separazione locale delle sorgenti (Demucs, open source, su CPU/MPS)
  → analisi di tempo, tonalità e accordi → time-stretch della voce a 130 BPM in Ardour.
- **Fase 6**: estendere `analyze_audio` con stima BPM/beat-grid e allineamento.
