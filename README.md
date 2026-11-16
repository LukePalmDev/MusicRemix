# MusicRemix · Exotica

Progetto personale: remix in versione **salsa** di *Exótica* (Gabry Ponte & Greg Taro, 130 BPM, son clave 3-2),
prodotto in Ardour guidato da Claude Code, più una **pagina per costruire una coreografia** sul brano.

## La pagina della coreografia

**https://lukepalmdev.github.io/MusicRemix/coreografia/**

- Pentagramma a **basi** (1 base = 8 tempi = 2 battute: `1 2 3 · 5 6 7 ·`), una riga per sezione del brano.
  L'intro ha le basi negative (−2, −1), così la base 1 coincide con l'inizio della canzone in tutte le versioni.
- Player con parti / stop / da capo, salti «dalla base precedente / questa / successiva, dall'1 o dal 5»,
  ripeti base o riga, velocità ridotta e un cursore che scorre sul pentagramma.
- Una casella per scrivere la mossa sotto ogni base e, a lato, l'elenco di tutte le basi una sotto l'altra
  (con i buchi dove non hai scritto nulla).
- Quattro versioni selezionabili: `s1` e `s2` (con e senza intro) e le rispettive «conteggio» (una voce conta
  «uno due tre / cinque sei sette»).

### L'audio non è incluso
La canzone è musica commerciale e **non è in questo repository né sul sito**. Per usare il player carichi tu un
tuo file audio (`.m4a`, `.wav`, `.mp3`…) dal pulsante «Carica audio…»: resta sul tuo dispositivo, viene letto solo
dal tuo browser e non viene caricato da nessuna parte. Senza audio la pagina funziona lo stesso per scrivere le mosse.
La griglia predefinita (inizio della base 1) è misurata sulle tracce originali del remix; con un altro file, o un'altra
versione dello stesso brano, regolala nel pannello «Impostazioni» (segna qui / allinea automaticamente / ±10 ms).

### Le tue mosse
Si salvano nel browser che stai usando (nessun server, nessun account). Per tenerne una copia o spostarle su un
altro dispositivo usa «Salva su file» e «Carica da file» nel pannello.

## Il resto del progetto
Non serve per usare la pagina. Descrizione completa in [`CLAUDE.md`](CLAUDE.md) e in [`docs/`](docs/).

- `bridge/`: ponte Lua + server MCP (`ardour-studio`) per pilotare Ardour, generatore delle parti salsa e script
  per pubblicare le versioni.
- `docs/ANALISI_EXOTICA.md`: analisi del brano (tempo, tonalità, clave, forma) e arrangiamento.
- `vendor/` (non incluso): clone locale di [raibid-entertainment/ardour-mcp](https://github.com/raibid-entertainment/ardour-mcp),
  usato solo come riferimento.

Nessuna licenza è indicata: tutti i diritti riservati, salvo accordi diversi.
