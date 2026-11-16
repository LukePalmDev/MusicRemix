# Analisi di "Exotica" (Gabry Ponte, Greg Taro) e arrangiamento salsa

Fonte: `~/Music/MusicRemix/assets/source/01 Exótica.m4a` (iTunes, AAC 44,1 kHz, 2:01), stem
separati in locale (Mel-Band RoFormer + HTDemucs ft, calibrati in guadagno). Analisi eseguite con
librosa sugli stem; sono **stime tecniche**, non giudizi d'ascolto.

## Dati misurati

| Voce | Risultato | Come |
|---|---|---|
| Tempo | **130,0 BPM** costante (129,99 da regressione sui beat, scarto 8 ms rms) | beat tracking sullo stem batteria; 130,0 massimizza l'energia di onset rispetto a 129,9/130,1 |
| Primo beat | 0,046 s; il cambio d'accordo cade sul beat 1 → battuta 1 del brano a 0,046 s | novità cromatica per beat |
| Tonalità | **La minore** (eolio); la voce usa Do naturale (Do# ≈ 0) | Krumhansl + istogramma pitch della voce |
| Clave | **son 3-2**, lato "3" sulle battute dispari | accenti di voce, basso e synth sulla griglia a 16esimi (+0,87…+1,57 per 3-2 vs ≈0 per 2-3) |
| Durata | 66 battute (radio edit) | |

## Forma e armonia (battuta di sessione = battuta del brano + 4)

| Sessione | Brano | Sezione | Accordi (1 per battuta) | Note |
|---|---|---|---|---|
| 1–4 | — | Intro salsa (nuova) | Lam Sol Lam Sol | fiati con l'hook |
| 5–12 | 1–8 | Strofa 1 | Lam (pedale) | voce + basso nell'originale, niente batteria |
| 13–20 | 9–16 | Pre-ritornello 1 | Lam Sol Rem Mim ×2 | |
| 21–22 | 17–18 | Break 1 | Fa Sol | strumentale originale quasi muto: accordi dedotti dalla voce (La-Do-Re / Si-Sol) e dal synth residuo; Fa ≈ Rem7 ≈ Lam come punteggio (ambiguo), Sol netto |
| 23–36 | 19–32 | Ritornello 1 | (Lam Sol) ×7 | drop dell'originale |
| 37–44 | 33–40 | Strofa 2 | Lam | |
| 45–52 | 41–48 | Pre-ritornello 2 | Lam Sol Rem Mim ×2 | |
| 53–54 | 49–50 | Break 2 | Fa Sol | come Break 1 |
| 55–68 | 51–64 | Ritornello 2 | (Lam Sol) ×7, battuta 60 = stop su Sol | |
| 69–71 | 65–66 | Finale | Sol Mi Lam (colpo finale) | l'originale sfuma; cadenza salsa aggiunta |

Hook del ritornello (voce): **Do–La–Si–Do | Si** su Lam | Sol, attacchi su 1 e 2& (colpi della clave 3-2).

## Arrangiamento salsa v2 (generato da `salsa_render`)

Tutte le parti sono regioni MIDI in Ardour (General MIDI Synth), una per sezione:

- **Clave**: son 3-2 continua (1, 2&, 4 | 2, 3).
- **Congas**: tumbao (slap sul 2, aperti su 4 e 4&, tumba sul lato 2; tono extra nei ritornelli).
- **Bongó-Campana**: martillo nelle strofe/pre, campana nei ritornelli e nell'intro.
- **Timbales**: cáscara 3-2 nelle strofe, campana nei ritornelli, golpe sul 4 del lato 2, abanico/fill
  prima di break e ritornelli, piatto sul primo battere dei ritornelli.
- **Güiro**: lungo-corto-corto.
- **Basso Tumbao**: 2& e 4 con anticipo dell'accordo successivo.
- **Piano Montuno**: montuno a 2 battute agganciato alla clave (ottave + accordo, anticipo sul 4&); comping leggero nelle strofe.
- **Trombe / Tromboni**: hook in terze nell'intro e nelle ultime 4 battute dei ritornelli, punch sul lato 2,
  colpi "bloque" sul ritmo della clave in break, stop e finale.
- Tracce originali: voce attiva; synth originale attivo a −6,6 dB; batteria, basso e strumentale originali in mute
  (restano nella sessione come riferimento).

## Verifiche tecniche (v2)

- Allineamento stem: errore < 1 campione; residuo −38 dB rispetto all'originale (sotto 15 kHz, dovuto al ricampionamento).
- Griglia: tempo costante, nessuna deriva misurabile (fase 17 ms → 22 ms tra prima e seconda metà, entro la latenza di rilevamento).
- Armonia: similarità cromatica per battuta salsa vs originale 0,88 (riferimento casuale 0,64); le battute meno simili
  sono quelle dove l'originale non ha strumenti (break, finale).
- Export: true peak −1,24 dBTP, 0 campioni clippati, −17,8 LUFS integrati, correlazione stereo 0,76.

## Da valutare all'ascolto (non verificabile con i test)

Groove e "sabor", naturalezza dei suoni GM, equilibrio voce/percussioni, se il synth originale stona con la
salsa, scelta Fa vs Rem nel primo accordo dei break, finale aggiunto, loudness bassa (nessun limiter).
