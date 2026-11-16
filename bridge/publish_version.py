#!/usr/bin/env python3
"""Turn the listening WAVs in ~/Music/MusicRemix/Version into Apple Music friendly files.

For each "Exotica sN.wav" it writes "Exotica sN.m4a" (Apple Lossless, same audio) with title,
artist, album, genre, BPM, track number, a generated cover (also saved as "Exotica sN cover.jpg")
and, if Version/testo.txt exists, the lyrics. The WAVs are left untouched.

Run with the venv that has Pillow + mutagen:
  ~/.local/share/musicremix/venv-sep/bin/python bridge/publish_version.py            # all WAVs
  ~/.local/share/musicremix/venv-sep/bin/python bridge/publish_version.py "Exotica s2.wav"
Per-version data come from Version/versioni.json (key = file name without "Exotica "; the order
gives the track number; "testo": false skips the lyrics, e.g. for count-guide versions):
  {"s1": {"sottotitolo": "con intro"}, "s1 conteggio": {"sottotitolo": "con intro", "testo": false}}
"""
from __future__ import annotations

import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

from mutagen.mp4 import MP4, MP4Cover
from PIL import Image, ImageDraw, ImageFilter, ImageFont

VERSION_DIR = Path.home() / "Music" / "MusicRemix" / "Version"
ARTIST = "Gabry Ponte & Greg Taro"
ALBUM = "Exótica (Salsa Remix)"
GENRE = "Salsa"
YEAR = "2026"
BPM = 130
FUTURA = "/System/Library/Fonts/Supplemental/Futura.ttc"
AVENIR = "/System/Library/Fonts/Avenir Next.ttc"


def font(path: str, style: str, size: int) -> ImageFont.FreeTypeFont:
    for i in range(20):
        try:
            f = ImageFont.truetype(path, size, index=i)
        except OSError:
            break
        if f.getname()[1].lower() == style.lower():
            return f
    return ImageFont.truetype(path, size)


def lerp(c1, c2, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


def gradient(draw, box, stops):
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0 - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                draw.line([(x0, y), (x1, y)], fill=lerp(c0, c1, (t - p0) / (p1 - p0)))
                break


def palm(draw, base, crown, w, color, fronds):
    (bx, by), (cx, cy) = base, crown
    left, right = [], []
    for i in range(41):  # slightly bowed, tapering trunk
        t = i / 40
        x = bx + (cx - bx) * t + math.sin(t * math.pi) * w * 1.6
        y = by + (cy - by) * t
        half = w * (1 - 0.45 * t) / 2
        left.append((x - half, y))
        right.append((x + half, y))
    draw.polygon(left + right[::-1], fill=color)
    for ang, length, droop in fronds:
        a = math.radians(ang)
        pts_top, pts_bot = [], []
        for i in range(61):
            t = i / 60
            x = cx + length * t * math.cos(a)
            y = cy + length * t * math.sin(a) + droop * length * t * t
            dx = length * math.cos(a)
            dy = length * math.sin(a) + 2 * droop * length * t
            n = math.hypot(dx, dy)
            nx, ny = -dy / n, dx / n
            width = length * 0.11 * math.sin(math.pi * min(1, t * 1.15)) ** 0.8
            jag = 1.0 if i % 2 else 0.35  # serrated leaflets
            pts_top.append((x + nx * width * jag, y + ny * width * jag))
            pts_bot.append((x - nx * width * jag, y - ny * width * jag))
        draw.polygon(pts_top + pts_bot[::-1], fill=color)
    draw.ellipse([cx - w * 0.9, cy - w * 0.7, cx + w * 0.9, cy + w * 0.7], fill=color)


def spaced(draw, xy_center, text, fnt, fill, spacing):
    widths = [draw.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = xy_center[0] - total / 2
    for ch, wd in zip(text, widths):
        draw.text((x, xy_center[1]), ch, font=fnt, fill=fill, anchor="lm")
        x += wd + spacing


def make_cover(label: str, subtitle: str, out: Path, size: int = 1600) -> None:
    S = size * 2  # draw at 2x, downsample for anti-aliasing
    img = Image.new("RGB", (S, S))
    d = ImageDraw.Draw(img)
    horizon = int(S * 0.64)
    gradient(d, (0, 0, S, horizon), [(0, (24, 8, 54)), (0.45, (122, 18, 92)), (0.8, (226, 64, 74)),
                                     (1, (255, 128, 60))])
    gradient(d, (0, horizon, S, S), [(0, (18, 58, 82)), (1, (5, 18, 30))])

    # striped retro sun sitting on the horizon
    r = int(S * 0.25)
    cx, cy = S // 2, horizon - int(r * 0.15)
    sun = Image.new("RGB", (2 * r, 2 * r))
    gradient(ImageDraw.Draw(sun), (0, 0, 2 * r, 2 * r), [(0, (255, 226, 110)), (1, (255, 110, 60))])
    mask = Image.new("L", (2 * r, 2 * r), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
    y, gap, step = int(r * 0.62), int(r * 0.018), 0
    while y < 2 * r:
        md.rectangle([0, y, 2 * r, y + gap], fill=0)
        step += 1
        y += int(r * 0.11) + gap
        gap = int(gap * 1.3) + 1
    glow = Image.new("L", (S, S), 0)
    ImageDraw.Draw(glow).ellipse([cx - r * 1.35, cy - r * 1.35, cx + r * 1.35, cy + r * 1.35], fill=110)
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.04))
    img.paste(Image.new("RGB", (S, S), (255, 170, 90)), (0, 0), glow)
    img.paste(sun, (cx - r, cy - r), mask)
    d = ImageDraw.Draw(img)
    gradient(d, (0, horizon, S, S), [(0, (18, 58, 82)), (1, (5, 18, 30))])

    # sun reflection on the sea
    rnd = random.Random(label)
    for i in range(8):
        yy = horizon + int(S * 0.018) + i * int(S * 0.021)
        half = r * (0.95 - i * 0.06) * (0.8 + 0.2 * rnd.random())
        if half <= 0:
            break
        d.rounded_rectangle([cx - half, yy, cx + half, yy + int(S * 0.006)], radius=int(S * 0.003),
                            fill=lerp((255, 190, 100), (60, 90, 110), i / 9))

    sil = (16, 6, 30)
    for ix, iw in ((0.10, 0.16), (0.93, 0.14)):  # small islands under the palms
        d.ellipse([S * (ix - iw / 2), horizon + S * 0.035, S * (ix + iw / 2), horizon + S * 0.075], fill=sil)
    palm(d, (int(S * 0.10), horizon + int(S * 0.05)), (int(S * 0.17), int(S * 0.38)), S * 0.028, sil,
         [(-160, S * 0.20, 0.55), (-130, S * 0.18, 0.45), (-95, S * 0.12, 0.2), (-55, S * 0.19, 0.5),
          (-20, S * 0.21, 0.65), (15, S * 0.15, 0.8), (165, S * 0.16, 0.8)])
    palm(d, (int(S * 0.93), horizon + int(S * 0.05)), (int(S * 0.85), int(S * 0.43)), S * 0.024, sil,
         [(-20, S * 0.17, 0.55), (-55, S * 0.15, 0.45), (-90, S * 0.10, 0.2), (-130, S * 0.17, 0.5),
          (-165, S * 0.19, 0.65), (165, S * 0.13, 0.8), (20, S * 0.13, 0.8)])

    cream, gold = (255, 240, 214), (255, 200, 90)
    title = font(FUTURA, "Condensed ExtraBold", int(S * 0.165))
    shadow = Image.new("L", (S, S), 0)
    ImageDraw.Draw(shadow).text((S // 2 + S * 0.006, int(S * 0.17) + S * 0.008), "EXÓTICA", font=title,
                                fill=170, anchor="mm")
    img.paste(Image.new("RGB", (S, S), (20, 4, 30)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(S * 0.006)))
    d = ImageDraw.Draw(img)
    d.text((S // 2, int(S * 0.17)), "EXÓTICA", font=title, fill=cream, anchor="mm")
    spaced(d, (S // 2, int(S * 0.285)), "SALSA REMIX", font(AVENIR, "Demi Bold", int(S * 0.05)), gold,
           S * 0.018)
    d.text((S // 2, int(S * 0.335)), ARTIST.upper(), font=font(AVENIR, "Medium", int(S * 0.024)),
           fill=(255, 225, 200), anchor="mm")

    # son clave 3-2 on a 32-step grid (two bars of 16ths)
    hits = {0, 6, 12, 20, 24}
    gx0, gx1, gy = S * 0.2, S * 0.8, S * 0.86
    for i in range(32):
        x = gx0 + (gx1 - gx0) * i / 31
        rr = S * (0.011 if i in hits else 0.0035)
        d.ellipse([x - rr, gy - rr, x + rr, gy + rr], fill=gold if i in hits else (120, 150, 170))
    d.text((S // 2, int(S * 0.905)), f"SON CLAVE 3-2  ·  {BPM} BPM", font=font(AVENIR, "Medium", int(S * 0.021)),
           fill=(150, 180, 195), anchor="mm")

    # version badge
    bf = font(AVENIR, "Bold", int(S * 0.03))
    txt = f"{label.upper()}  ·  {subtitle.upper()}" if subtitle else label.upper()
    tw = d.textlength(txt, font=bf)
    bx, by, ph = S // 2, int(S * 0.955), S * 0.022
    d.rounded_rectangle([bx - tw / 2 - ph * 1.6, by - ph * 1.25, bx + tw / 2 + ph * 1.6, by + ph * 1.25],
                        radius=int(ph * 1.25), fill=gold)
    d.text((bx, by), txt, font=bf, fill=(40, 10, 40), anchor="mm")

    noise = Image.effect_noise((S, S), 18).convert("RGB")
    img = Image.blend(img, noise, 0.035)
    img.resize((size, size), Image.LANCZOS).save(out, "JPEG", quality=92)


def publish(wav: Path, versions: dict, lyrics: str | None) -> Path:
    label = re.sub(r"^Exotica\s+", "", wav.stem)
    info = versions.get(label, {})
    if isinstance(info, str):
        info = {"sottotitolo": info}
    track = list(versions).index(label) + 1 if label in versions else 0
    subtitle = info.get("sottotitolo", "")
    if not info.get("testo", True):
        lyrics = None
    cover = wav.with_name(f"{wav.stem} cover.jpg")
    make_cover(label, subtitle, cover)
    out = wav.with_suffix(".m4a")
    tmp = out.with_name(out.stem + ".tmp.m4a")
    subprocess.run(["afconvert", "-f", "m4af", "-d", "alac", str(wav), str(tmp)], check=True)
    tags = MP4(tmp)
    name = f"Exótica (Salsa Remix {label}" + (f" – {subtitle})" if subtitle else ")")
    tags["\xa9nam"] = [name]
    tags["\xa9ART"] = [ARTIST]
    tags["aART"] = [ARTIST]
    tags["\xa9alb"] = [ALBUM]
    tags["\xa9gen"] = [GENRE]
    tags["\xa9day"] = [YEAR]
    tags["tmpo"] = [BPM]
    if track:
        tags["trkn"] = [(track, 0)]
    tags["\xa9cmt"] = [f"Remix salsa {BPM} BPM, son clave 3-2. Versione {label}"
                       + (f" ({subtitle})" if subtitle else "") + ". Uso personale."]
    tags["covr"] = [MP4Cover(cover.read_bytes(), imageformat=MP4Cover.FORMAT_JPEG)]
    if lyrics:
        tags["\xa9lyr"] = [lyrics]
    elif "\xa9lyr" in tags:
        del tags["\xa9lyr"]
    tags.save()
    tmp.replace(out)
    return out


def main(argv: list[str]) -> None:
    meta = VERSION_DIR / "versioni.json"
    versions = json.loads(meta.read_text()) if meta.exists() else {}
    lyr_file = VERSION_DIR / "testo.txt"
    lyrics = lyr_file.read_text().strip() if lyr_file.exists() else None
    wavs = [VERSION_DIR / a for a in argv] if argv else sorted(VERSION_DIR.glob("*.wav"))
    for wav in wavs:
        out = publish(wav, versions, lyrics)
        has = "\xa9lyr" in MP4(out).tags
        print(f"{out.name}: copertina ok, testo {'incluso' if has else 'assente'}")


if __name__ == "__main__":
    main(sys.argv[1:])
