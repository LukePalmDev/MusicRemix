"""Salsa arrangement generator for "Exotica" (Gabry Ponte, Greg Taro) at 130 BPM, 4/4.

Musical data comes from the analysis of the original (docs/ANALISI_EXOTICA.md):
A minor (Aeolian; breaks F-G -> Am, i.e. VI-VII-i; checked against the vocal line
because the original instrumental is almost silent there), son clave 3-2 with the "3" side on odd
session bars (every section starts on an odd bar, so the clave never has to switch).
Session bar = song bar + 4 (bars 1-4 are a new salsa intro).

Every part is rendered per section as a small Standard MIDI File (program change at tick 0,
so playback started anywhere picks the right sound) and imported into Ardour as an editable
MIDI region. Nothing here touches audio: Ardour stays the single source of truth.
"""
from __future__ import annotations

import random
import struct
import unicodedata
import zlib
from dataclasses import dataclass, field
from pathlib import Path

TPQ = 960  # SMF ticks per quarter note

# ----------------------------------------------------------------------------- form & harmony

@dataclass
class Section:
    name: str
    start: int            # first session bar (1-based)
    chords: list[str]     # one chord per bar
    kind: str             # intro | verse | pre | break | chorus | ending
    stops: list[int] = field(default_factory=list)  # session bars played as clave-rhythm hits

    @property
    def bars(self) -> range:
        return range(self.start, self.start + len(self.chords))


def _rep(seq: list[str], n: int) -> list[str]:
    return (seq * n)[:max(n, 0)] if n else []


FORM: list[Section] = [
    Section("Intro salsa", 1, ["Am", "G", "Am", "G"], "intro"),
    Section("Strofa 1", 5, ["Am"] * 8, "verse"),
    Section("Pre-ritornello 1", 13, ["Am", "G", "Dm", "Em"] * 2, "pre"),
    Section("Break 1", 21, ["F", "G"], "break"),
    Section("Ritornello 1", 23, _rep(["Am", "G"], 14), "chorus"),
    Section("Strofa 2", 37, ["Am"] * 8, "verse"),
    Section("Pre-ritornello 2", 45, ["Am", "G", "Dm", "Em"] * 2, "pre"),
    Section("Break 2", 53, ["F", "G"], "break"),
    Section("Ritornello 2", 55, ["Am", "G", "Am", "G", "Am", "G", "Am", "G", "Am", "G", "Am", "G", "Am", "G"],
            "chorus", stops=[60]),
    Section("Finale", 69, ["G", "E", "Am"], "ending"),
]

PC = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def chord_pcs(ch: str) -> tuple[int, int, int]:
    """(root, third, fifth) pitch classes of a major/minor triad name like 'Am', 'G', 'E'."""
    minor = ch.endswith("m")
    root = PC[ch[:-1] if minor else ch]
    return root, (root + (3 if minor else 4)) % 12, (root + 7) % 12


def nearest(pc: int, target: int) -> int:
    """MIDI note with pitch class pc closest to target."""
    base = target - ((target - pc) % 12)
    return base if target - base <= 6 else base + 12


def clave_side(bar: int) -> int:
    """3 for the '3' side (odd session bars, 3-2 son clave), 2 for the '2' side."""
    return 3 if bar % 2 == 1 else 2


def section_by_name(name: str) -> Section:
    for s in FORM:
        if s.name.lower() == name.lower():
            return s
    raise KeyError(f"unknown section {name!r}; known: {[s.name for s in FORM]}")


def chord_at(bar: int) -> str | None:
    for s in FORM:
        if bar in s.bars:
            return s.chords[bar - s.start]
    return None


# ----------------------------------------------------------------------------- instruments

@dataclass(frozen=True)
class Part:
    track: str
    program: int      # General MIDI program (0-based)
    channel: int      # 0-based; 9 = GM percussion
    description: str


PARTS: dict[str, Part] = {
    "clave": Part("Clave", 0, 9, "son clave 3-2 (GM 75 Claves)"),
    "congas": Part("Congas", 0, 9, "tumbao: slap on 2, open tones on 4 and 4& (tumba on the 2 side)"),
    "bongo": Part("Bongó-Campana", 0, 9, "martillo on bongó in verses, campana (bongo bell) in choruses"),
    "timbales": Part("Timbales", 0, 9, "cáscara in verses, bell in choruses, fills/abanico into sections, crash on chorus downbeat"),
    "guiro": Part("Güiro", 0, 9, "long-short-short per half bar"),
    "bass": Part("Basso Tumbao", 32, 0, "anticipated tumbao on 2& and 4 (acoustic bass)"),
    "piano": Part("Piano Montuno", 0, 0, "2-bar montuno locked to the clave; light comping in verses"),
    "trumpets": Part("Trombe", 56, 0, "chorus hook (C-A-B-C | B) in thirds, punches and hits"),
    "trombones": Part("Tromboni", 57, 0, "punches on the 2 side, hits in breaks"),
}

# GM percussion keys
CLAVES, MUTE_CONGA, OPEN_CONGA, LOW_CONGA = 75, 62, 63, 64
HI_BONGO, LO_BONGO, COWBELL = 60, 61, 56
HI_TIMBALE, LO_TIMBALE, WOODBLOCK, RIDE_BELL, CRASH = 65, 66, 76, 53, 49
GUIRO_SHORT, GUIRO_LONG = 73, 74

Note = tuple[float, int, int, float]  # (beat from section start, 0-based; MIDI note; velocity; length in beats)


class _Gen:
    def __init__(self, sec: Section, seed: int):
        self.sec = sec
        self.notes: list[Note] = []
        self.rng = random.Random(seed)

    def add(self, bar: int, beat: float, note: int, vel: int, length: float = 0.1, human: int = 6):
        """bar = session bar, beat = 1-based beat inside the bar."""
        v = max(1, min(127, vel + (self.rng.randint(-human, human) if human else 0)))
        pos = (bar - self.sec.start) * 4 + (beat - 1)
        self.notes.append((pos, note, v, length))

    def is_stop(self, bar: int) -> bool:
        return self.sec.kind in ("break", "ending") or bar in self.sec.stops

    def is_last(self, bar: int) -> bool:
        return bar == self.sec.bars[-1]


def _hits(bar: int) -> list[float]:
    """Clave-rhythm hits used for breaks/stops ('bloque')."""
    return [1, 2.5, 4] if clave_side(bar) == 3 else [2, 3]


def _next_kind(sec: Section) -> str | None:
    i = FORM.index(sec)
    return FORM[i + 1].kind if i + 1 < len(FORM) else None


def _fill(g: _Gen, bar: int, start: float = 3.0, strength: int = 100):
    """Timbale abanico/fill from `start` to the end of the bar (16ths, crescendo)."""
    b = start
    i = 0
    while b < 5 - 1e-6:
        g.add(bar, b, HI_TIMBALE if i % 2 == 0 else LO_TIMBALE, int(strength * (0.6 + 0.4 * (b - start) / (5 - start))))
        b += 0.25
        i += 1


# ---- percussion

def gen_clave(g: _Gen):
    for bar in g.sec.bars:
        if g.sec.kind == "ending" and bar == g.sec.bars[-1]:
            g.add(bar, 1, CLAVES, 110)
            continue
        for b in ([1, 2.5, 4] if clave_side(bar) == 3 else [2, 3]):
            g.add(bar, b, CLAVES, 100 if g.sec.kind != "verse" else 88)


def gen_congas(g: _Gen):
    k = g.sec.kind
    scale = {"verse": 0.82, "pre": 0.92}.get(k, 1.0)
    for bar in g.sec.bars:
        if g.is_stop(bar):
            for b in _hits(bar) if not (k == "ending" and g.is_last(bar)) else [1]:
                g.add(bar, b, OPEN_CONGA, 112)
            continue
        side = clave_side(bar)
        pat = [(1, MUTE_CONGA, 50), (1.5, MUTE_CONGA, 40), (2, MUTE_CONGA, 110), (2.5, MUTE_CONGA, 42),
               (3, MUTE_CONGA, 50), (3.5, MUTE_CONGA, 42), (4, OPEN_CONGA, 105),
               (4.5, OPEN_CONGA if side == 3 else LOW_CONGA, 100)]
        if k in ("chorus", "intro") and side == 3:
            pat.append((3.5, LOW_CONGA, 70))  # extra tumba tone on the 3 side in full sections
        for b, n, v in pat:
            g.add(bar, b, n, int(v * scale))


def gen_bongo(g: _Gen):
    k = g.sec.kind
    for bar in g.sec.bars:
        if g.is_stop(bar):
            continue
        if k in ("chorus", "intro"):  # campana (bongo bell): big on 1 and 3
            for b, v in [(1, 118), (2, 82), (2.5, 58), (3, 114), (4, 82), (4.5, 58)]:
                g.add(bar, b, COWBELL, v)
        else:  # martillo
            for b, n, v in [(1, HI_BONGO, 95), (1.5, HI_BONGO, 45), (2, HI_BONGO, 62), (2.5, HI_BONGO, 50),
                            (3, HI_BONGO, 95), (3.5, HI_BONGO, 45), (4, LO_BONGO, 100), (4.5, HI_BONGO, 52)]:
                g.add(bar, b, n, int(v * (0.85 if k == "verse" else 1.0)))


def gen_timbales(g: _Gen):
    k = g.sec.kind
    nxt = _next_kind(g.sec)
    for bar in g.sec.bars:
        if g.is_stop(bar):
            if k == "ending" and g.is_last(bar):
                g.add(bar, 1, LO_TIMBALE, 120)
                g.add(bar, 1, CRASH, 115)
            else:
                for b in _hits(bar):
                    g.add(bar, b, LO_TIMBALE, 115)
            if g.is_last(bar) and nxt in ("chorus", "verse"):
                _fill(g, bar, 3.5, 112)
            continue
        if k == "chorus" and bar == g.sec.start:
            g.add(bar, 1, CRASH, 110)
        if k == "intro" and bar == g.sec.start:
            g.add(bar, 1, CRASH, 100)
        side = clave_side(bar)
        # cáscara 3-2: '3' side x.xx.x.x, '2' side x.x.xx.x (8ths)
        pat = [1, 2, 2.5, 3.5, 4.5] if side == 3 else [1, 2, 3, 3.5, 4.5]
        clave_hits = [1, 2.5, 4] if side == 3 else [2, 3]
        last_fill = g.is_last(bar) and nxt in ("break", "chorus", "verse", "ending") and k != "intro"
        for b in pat:
            if last_fill and b >= 3:
                continue
            acc = b in clave_hits or b == 1
            if k in ("chorus", "intro"):
                g.add(bar, b, RIDE_BELL, 100 if acc else 78)
            else:
                g.add(bar, b, WOODBLOCK, 88 if acc else 62)
        if k in ("chorus", "intro") and side == 2 and not last_fill:
            g.add(bar, 4, LO_TIMBALE, 92)  # golpe on 4 of the 2 side
        if last_fill:
            _fill(g, bar, 3.0, 110 if nxt in ("chorus", "break") else 90)


def gen_guiro(g: _Gen):
    k = g.sec.kind
    scale = 0.8 if k == "verse" else 1.0
    for bar in g.sec.bars:
        if g.is_stop(bar):
            continue
        for b, n, v, ln in [(1, GUIRO_LONG, 95, 0.45), (2, GUIRO_SHORT, 70, 0.1), (2.5, GUIRO_SHORT, 66, 0.1),
                            (3, GUIRO_LONG, 92, 0.45), (4, GUIRO_SHORT, 70, 0.1), (4.5, GUIRO_SHORT, 66, 0.1)]:
            g.add(bar, b, n, int(v * scale), ln)


# ---- harmony instruments

def _bass_note(pc: int) -> int:
    return nearest(pc, 38)  # around D2: range ~ G#1..G#2


def gen_bass(g: _Gen):
    sec = g.sec
    for bar in sec.bars:
        ch = sec.chords[bar - sec.start]
        r, _, f = chord_pcs(ch)
        nxt_ch = chord_at(bar + 1)
        if g.is_stop(bar):
            hits = [1] if (sec.kind == "ending" and g.is_last(bar)) else _hits(bar)
            for b in hits:
                g.add(bar, b, _bass_note(r), 112, 0.4 if not (sec.kind == "ending" and g.is_last(bar)) else 1.5, 4)
            continue
        if bar == sec.start or bar - 1 in sec.stops:
            g.add(bar, 1, _bass_note(r), 104, 1.4, 4)  # re-establish after a stop / section start
        g.add(bar, 2.5, _bass_note(f) if sec.kind != "verse" or bar % 2 else _bass_note(r), 100, 1.4, 4)
        anticip = chord_pcs(nxt_ch)[0] if nxt_ch else r
        into_hit = bar + 1 in sec.stops
        g.add(bar, 4, _bass_note(anticip), 108, 0.9 if into_hit else 2.4, 4)


def _triad_notes(ch: str, center: int) -> list[int]:
    return sorted(nearest(pc, center) for pc in chord_pcs(ch))


def gen_piano(g: _Gen):
    sec = g.sec
    k = sec.kind
    for bar in sec.bars:
        ch = sec.chords[bar - sec.start]
        r, t, f = chord_pcs(ch)
        nxt_ch = chord_at(bar + 1) or ch
        if g.is_stop(bar):
            hits = [1] if (k == "ending" and g.is_last(bar)) else _hits(bar)
            for b in hits:
                ln = 2.0 if (k == "ending" and g.is_last(bar)) else 0.35
                for n in _triad_notes(ch, 64) + [nearest(r, 57), nearest(r, 76)]:
                    g.add(bar, b, n, 108, ln, 4)
            continue
        if k == "verse":  # light comping: chord stabs on 2& and 4 (with the bass), anticipating on 4
            for b, c in [(2.5, ch), (4, nxt_ch)]:
                for n in _triad_notes(c, 62):
                    g.add(bar, b, n, 72, 0.3, 5)
            continue
        vel = 92 if k in ("chorus", "intro") else 80
        top = [nearest(pc, 74) for pc in (r, t, f, t)]           # melodic octave line (A4..D5 area)
        inner = [n for n in _triad_notes(ch, 66)]                 # chord tones in the middle
        nr, nt, nf = chord_pcs(nxt_ch)
        top_next = nearest(nr, 74)
        side = clave_side(bar)
        if side == 3:
            seq = [(1.5, "T", 0), (2, "I", 0), (2.5, "T", 1), (3, "I", 0), (3.5, "T", 2), (4, "I", 0), (4.5, "N", 0)]
        else:
            seq = [(1.5, "I", 0), (2, "T", 3), (2.5, "I", 0), (3, "T", 0), (3.5, "I", 0), (4, "T", 1), (4.5, "N", 0)]
        for b, kind, idx in seq:
            if kind == "T":
                tn = top[idx]
                for n in (tn, tn - 12):
                    g.add(bar, b, n, vel, 0.3, 5)
                mid = [x for x in inner if tn - 12 < x < tn and x % 12 != tn % 12]
                for n in mid[:1]:
                    g.add(bar, b, n, vel - 15, 0.3, 5)
            elif kind == "I":
                for n in inner[:2]:
                    g.add(bar, b, n, vel - 18, 0.25, 5)
            else:  # anticipation of the next bar's chord on 4&, held over the bar line
                for n in (top_next, top_next - 12):
                    g.add(bar, b, n, vel + 4, 0.5, 4)


HOOK = [  # (bar offset in a 2-bar cycle, beat, MIDI, length) — chorus vocal hook C-A-B-C | B, an octave up
    (0, 1.0, 72, 0.75), (0, 2.5, 69, 0.5), (0, 3.0, 71, 0.5), (0, 3.5, 72, 1.0),
    (1, 2.0, 71, 1.5),
]


def _third_below(n: int, ch: str) -> int:
    pcs = chord_pcs(ch)
    for d in range(3, 6):
        if (n - d) % 12 in pcs:
            return n - d
    return n - 3


def gen_trumpets(g: _Gen):
    sec = g.sec
    k = sec.kind
    for bar in sec.bars:
        ch = sec.chords[bar - sec.start]
        if g.is_stop(bar):
            hits = [1] if (k == "ending" and g.is_last(bar)) else _hits(bar)
            top = nearest(chord_pcs(ch)[1], 74)
            for b in hits:
                ln = 2.0 if (k == "ending" and g.is_last(bar)) else 0.3
                g.add(bar, b, top, 110, ln, 4)
                g.add(bar, b, _third_below(top, ch), 102, ln, 4)
            continue
        if k == "intro" or (k == "chorus" and bar >= sec.bars[-1] - 3):
            # hook (intro, and last 4 bars of each chorus as a mambo answer)
            off = (bar - sec.start) % 2
            for o, b, n, ln in HOOK:
                if o == off:
                    g.add(bar, b, n, 100 if k == "intro" else 84, ln, 4)
                    g.add(bar, b, _third_below(n, ch), 92 if k == "intro" else 78, ln, 4)
        elif k == "chorus" and clave_side(bar) == 2:
            top = nearest(chord_pcs(ch)[1], 74)
            for b in (2, 3):
                g.add(bar, b, top, 96, 0.25, 4)
                g.add(bar, b, _third_below(top, ch), 88, 0.25, 4)


def gen_trombones(g: _Gen):
    sec = g.sec
    k = sec.kind
    for bar in sec.bars:
        ch = sec.chords[bar - sec.start]
        r, t, f = chord_pcs(ch)
        if g.is_stop(bar):
            hits = [1] if (k == "ending" and g.is_last(bar)) else _hits(bar)
            for b in hits:
                ln = 2.0 if (k == "ending" and g.is_last(bar)) else 0.3
                g.add(bar, b, nearest(r, 52), 108, ln, 4)
                g.add(bar, b, nearest(f, 57), 100, ln, 4)
            continue
        if k in ("chorus", "intro") and clave_side(bar) == 2:
            for b in (2, 3):
                g.add(bar, b, nearest(r, 52), 92, 0.25, 4)
                g.add(bar, b, nearest(f, 57), 86, 0.25, 4)
        elif k == "pre" and bar == sec.bars[-1]:
            g.add(bar, 3, nearest(t, 55), 80, 2.0, 4)  # swell into the break


GENERATORS = {
    "clave": gen_clave, "congas": gen_congas, "bongo": gen_bongo, "timbales": gen_timbales,
    "guiro": gen_guiro, "bass": gen_bass, "piano": gen_piano, "trumpets": gen_trumpets,
    "trombones": gen_trombones,
}


def generate(part: str, sec: Section, seed: int = 0) -> list[Note]:
    g = _Gen(sec, seed=zlib.crc32(f"{part}|{sec.name}|{seed}".encode()))
    GENERATORS[part](g)
    return sorted(g.notes)


# ----------------------------------------------------------------------------- SMF writer

def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def write_smf(path: Path, notes: list[Note], program: int | None, channel: int, bars: int, bpm: float = 130.0,
              track_name: str = "") -> Path:
    """Type-0 SMF: tempo, 4/4, program change at 0, notes; end-of-track at the section end."""
    ev: list[tuple[int, int, bytes]] = []  # (tick, order, data) — note-offs (order 0) before note-ons (1)
    for pos, n, v, ln in notes:
        on = int(round(pos * TPQ))
        off = on + max(1, int(round(ln * TPQ)))
        ev.append((on, 1, bytes([0x90 | channel, n, v])))
        ev.append((off, 0, bytes([0x80 | channel, n, 0])))
    end = bars * 4 * TPQ
    meta = bytearray()
    if track_name:
        nm = track_name.encode("utf-8")
        meta += _vlq(0) + b"\xff\x03" + _vlq(len(nm)) + nm
    mpq = int(round(60_000_000 / bpm))
    meta += _vlq(0) + b"\xff\x51\x03" + mpq.to_bytes(3, "big")
    meta += _vlq(0) + b"\xff\x58\x04\x04\x02\x18\x08"
    if program is not None:
        meta += _vlq(0) + bytes([0xC0 | channel, program])
    last = 0
    body = bytearray(meta)
    for t, _, data in sorted(ev, key=lambda e: (e[0], e[1])):
        t = min(t, end)
        body += _vlq(t - last) + data
        last = t
    body += _vlq(max(0, end - last)) + b"\xff\x2f\x00"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MThd" + struct.pack(">IHHH", 6, 0, 1, TPQ) + b"MTrk" + struct.pack(">I", len(body)) + bytes(body))
    return path


def render(part: str, sec: Section, out_dir: Path, seed: int = 0) -> tuple[Path, int]:
    p = PARTS[part]
    notes = generate(part, sec, seed)
    # ASCII file names: Ardour's batch import stops at the first non-ASCII path
    fname = unicodedata.normalize("NFKD", f"{p.track} - {sec.name}.mid").encode("ascii", "ignore").decode().replace("/", "-")
    # no program change on the GM percussion channel: gmsynth would switch it to a melodic preset
    prog = None if p.channel == 9 else p.program
    return write_smf(out_dir / fname, notes, prog, p.channel, len(sec.chords), track_name=p.track), len(notes)
