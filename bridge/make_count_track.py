#!/usr/bin/env python3
"""Build a spoken dance-count guide track ("uno, due, tre, cinque, sei, sette") on the session grid.

Salsa count over two 4/4 bars: 1 2 3 (4) | 5 6 7 (8); count 1 = first beat of every odd session bar
(the "3" side of the son clave 3-2, where every section starts). The words come from macOS `say`
(local TTS); each word's vowel onset is placed on its beat. "uno" is a little louder so the 1 is easy
to find. Constant tempo only (bar 1 at sample 0), like the Exotica session.

  ~/.local/share/musicremix/venv-sep/bin/python bridge/make_count_track.py OUT.wav \
      [--bpm 130] [--first-bar 1] [--last-bar 70] [--voice Alice] [--rate 230]
Then import OUT.wav at bar 1 with import_audio (ardour-studio).
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 48000
WORDS = {1: "uno", 2: "due", 3: "tre", 5: "cinque", 6: "sei", 7: "sette"}
GAIN_DB = {1: 2.0}


def tts(word: str, voice: str, rate: int, tmp: Path) -> tuple[np.ndarray, int]:
    f = tmp / f"{word}.wav"
    subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(f), f"--data-format=LEI16@{SR}", word],
                   check=True)
    x, sr = sf.read(f)
    assert sr == SR
    env = np.sqrt(np.convolve(x ** 2, np.ones(480) / 480, "same"))
    onset = int(np.argmax(env > 0.25 * env.max()))  # vowel onset ~ perceived beat of the syllable
    end = len(env) - int(np.argmax(env[::-1] > 0.02 * env.max()))
    x = x[:end] / np.abs(x).max()
    fade = int(0.005 * SR)
    x[-fade:] *= np.linspace(1, 0, fade)
    return x, onset


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--bpm", type=float, default=130.0)
    ap.add_argument("--first-bar", type=int, default=1)
    ap.add_argument("--last-bar", type=int, default=70)
    ap.add_argument("--voice", default="Alice")
    ap.add_argument("--rate", type=int, default=230)
    a = ap.parse_args()
    if a.first_bar % 2 == 0:
        raise SystemExit("--first-bar must be odd (count 1 = odd bars)")
    beat = SR * 60.0 / a.bpm
    with tempfile.TemporaryDirectory() as td:
        clips = {n: tts(w, a.voice, a.rate, Path(td)) for n, w in WORDS.items()}
    longest = max(len(x) - on for x, on in clips.values())
    if longest > beat:
        raise SystemExit(f"words too long for {a.bpm} BPM ({longest / SR:.2f}s > beat); raise --rate")
    total = int((a.last_bar + 1) * 4 * beat) + SR
    out = np.zeros(total)
    for bar in range(a.first_bar, a.last_bar + 1):
        for b in range(4):
            count = (0 if bar % 2 else 4) + b + 1
            if count not in clips:
                continue
            x, on = clips[count]
            pos = int(round(((bar - 1) * 4 + b) * beat)) - on
            if pos < 0:  # first word of the session: drop the part before sample 0
                x, pos = x[-pos:], 0
            out[pos:pos + len(x)] += x * 10 ** (GAIN_DB.get(count, 0.0) / 20)
    out *= 10 ** (-3 / 20) / np.abs(out).max()  # peak -3 dBFS
    sf.write(a.out, out, SR, subtype="PCM_24")
    print(f"{a.out}: battute {a.first_bar}-{a.last_bar}, {a.bpm} BPM, {len(out) / SR:.1f} s")


if __name__ == "__main__":
    main()
