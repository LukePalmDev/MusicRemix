"""ardour-studio: MCP extension for Ardour 9.

Complements Ardour's built-in "MCP HTTP Server" (tracks, plugins, MIDI notes,
regions, mixer, markers, transport) with what it lacks:
  - tempo / meter changes
  - audio import onto a given track at a given bar
  - WAV export of the session or a bar range, with technical analysis
  - progressive versioning (snapshots + backups)
  - a compact project overview
  - arbitrary Lua in Ardour's GUI context (escape hatch for anything else)
  - technical audio QA (peaks, true peak, LUFS, clipping, correlation)

Everything goes through the Lua bridge running inside Ardour, so every change
lands in the live Ardour session (undoable where Ardour supports it).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import analysis, salsa
from .bridge import BridgeError, heartbeat, is_alive, lua_str, lua_value, run_lua

PROJECT_ROOT = Path(os.environ.get("MUSICREMIX_ROOT", Path.home() / "Music" / "MusicRemix"))
EXPORT_DIR = PROJECT_ROOT / "exports"
BACKUP_DIR = PROJECT_ROOT / "backups"
WAV_PRESET = "75969a1c-3133-4694-864b-a1fa50e43348"  # "WAV @ session-rate" (Ardour 9 bundled preset)

mcp = FastMCP(
    "ardour-studio",
    instructions=(
        "Extension tools for Ardour 9. Use together with the 'ardour' MCP server (Ardour's native "
        "server) which handles tracks, plugins, MIDI notes, regions, faders, pans and markers. "
        "Use this server for tempo/meter, audio import, WAV export + analysis, versioning, project "
        "overview and arbitrary Lua (ardour_lua). Bars and beats are 1-based. Before large edits call "
        "save_version; after edits export and analyze so the user can listen."
    ),
)

# Lua helpers prepended to snippets that need them.
LUA_PRELUDE = r"""
local TPB = Temporal.ticks_per_beat
local function bbt_tuple(s)
  local b = Temporal.TempoMap.read():bbt_at(Temporal.timepos_t(s))
  return b.bars, b.beats, b.ticks
end
local function bbt_str(s) local a, b, c = bbt_tuple(s) return string.format("%d|%d|%d", a, b, c) end
-- exact sample position of (bar, beat[.fraction]); bisection in musical ticks, so it is
-- correct across tempo and meter changes
local function bbt_to_sample(bar, beat)
  beat = beat or 1
  local whole = math.floor(beat)
  local ticks = math.floor((beat - whole) * TPB + 0.5)
  local tm = Temporal.TempoMap.read()
  local function less(T)
    local b = tm:bbt_at(Temporal.timepos_t.from_ticks(T))
    if b.bars ~= bar then return b.bars < bar end
    if b.beats ~= whole then return b.beats < whole end
    return b.ticks < ticks
  end
  local lo, hi = 0, TPB * 64
  while less(hi) do hi = hi * 2 end
  while lo < hi do
    local mid = (lo + hi) // 2
    if less(mid) then lo = mid + 1 else hi = mid end
  end
  return Temporal.timepos_t.from_ticks(lo):samples()
end
local function find_route(key)
  local r = Session:route_by_name(key)
  if r and not r:isnil() then return r end
  for x in Session:get_routes():iter() do
    if x:to_stateful():id():to_s() == tostring(key) then return x end
  end
  error("route not found: " .. tostring(key))
end
local function session_end_sample()
  local e = 0
  for r in Session:get_routes():iter() do
    local t = r:to_track()
    if not t:isnil() then
      for rg in t:playlist():region_list():iter() do
        local x = rg:position():samples() + rg:length():samples()
        if x > e then e = x end
      end
    end
  end
  return e
end
"""


def _num(name: str, value, lo: float, hi: float) -> float:
    """Coerce a tool argument before it is interpolated into Lua. Rejects strings and non-finite values."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number") from None
    if isinstance(value, bool) or not math.isfinite(x) or not lo <= x <= hi:
        raise ValueError(f"{name} out of range {lo}..{hi}")
    return x


def _int(name: str, value, lo: int, hi: int) -> int:
    x = _num(name, value, lo, hi)
    if x != math.floor(x):
        raise ValueError(f"{name} must be an integer")
    return int(x)


def _bool(name: str, value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value in (0, 1) and float(value) == int(value):
        return bool(value)
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise ValueError(f"{name} must be a boolean")


def _lua(body: str, timeout: float = 30.0):
    try:
        return lua_value(LUA_PRELUDE + body, timeout)
    except BridgeError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
def bridge_status() -> dict:
    """Check that Ardour is running with a session and the Lua bridge is responsive."""
    hb = heartbeat()
    alive = is_alive()
    info = {"bridge_alive": alive, "heartbeat": hb}
    if alive:
        info["engine"] = _lua("""
local e = Session:engine()
return { backend = e:current_backend_name(), running = e:running(), session = Session:name(),
         path = Session:path(), snapshot = Session:snap_name() }""")
    return info


@mcp.tool()
def ardour_lua(code: str, timeout_s: float = 30.0) -> dict:
    """Run arbitrary Lua inside Ardour's GUI (Session, Editor, ARDOUR, Temporal, ARDOUR.LuaAPI...).

    `return` a value (tables become JSON). print() output is captured. Wrap edits in
    Session:begin_reversible_command(...) / Session:commit_reversible_command(nil) so they are undoable.
    Helpers available: bbt_to_sample(bar, beat), bbt_str(sample), find_route(name_or_id), session_end_sample().
    """
    try:
        return run_lua(LUA_PRELUDE + code, timeout_s)
    except BridgeError as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def project_overview(include_regions: bool = True) -> dict:
    """Compact snapshot of the session: tempo/meter, every route (type, gain dB, pan, mute/solo,
    plugins, regions with bar positions) and markers. Use this before modifying the project."""
    return _lua(f"""
local include_regions = {str(include_regions).lower()}
local tm = Temporal.TempoMap.read()
local t0 = Temporal.timepos_t(0)
local m = tm:meter_at(t0)
local out = {{ session = Session:name(), snapshot = Session:snap_name(), sample_rate = Session:nominal_sample_rate(),
  bpm_at_start = tm:quarters_per_minute_at(t0), meter = m:divisions_per_bar() .. "/" .. m:note_value(),
  routes = {{}}, markers = {{}} }}
for r in Session:get_routes():iter() do
  local g = r:gain_control():get_value()
  local e = {{ name = r:name(), id = r:to_stateful():id():to_s(),
    gain_db = g > 0 and (20 * math.log(g, 10)) or -200, muted = r:muted(), soloed = r:soloed(), active = r:active() }}
  local pc = r:pan_azimuth_control()
  if pc and not pc:isnil() then e.pan = pc:get_value() end
  local t = r:to_track()
  if t:isnil() then e.type = r:is_master() and "master" or "bus"
  else
    e.type = t:to_midi_track():isnil() and "audio" or "midi"
    if include_regions then
      e.regions = {{}}
      for rg in t:playlist():region_list():iter() do
        local p, l = rg:position():samples(), rg:length():samples()
        e.regions[#e.regions + 1] = {{ name = rg:name(), id = rg:to_stateful():id():to_s(),
          start = bbt_str(p), ["end"] = bbt_str(p + l), start_sample = p, length_samples = l, muted = rg:muted() }}
      end
    end
  end
  e.plugins = {{}}
  local i = 0
  while true do
    local p = r:nth_plugin(i)
    if p:isnil() then break end
    e.plugins[#e.plugins + 1] = {{ index = i, name = p:display_name(), active = p:active() }}
    i = i + 1
  end
  out.routes[#out.routes + 1] = e
end
for l in Session:locations():list():iter() do
  if l:is_mark() or l:is_range_marker() or l:is_section() then
    out.markers[#out.markers + 1] = {{ name = l:name(), start = bbt_str(l:start():samples()),
      ["end"] = l:is_mark() and nil or bbt_str(l:_end():samples()) }}
  end
end
return out""")


@mcp.tool()
def set_tempo(bpm: float, bar: int = 1) -> dict:
    """Set the tempo (quarter notes per minute) from `bar` onward (bar 1 = whole song). Undoable."""
    bpm = _num("bpm", bpm, 20, 400)
    bar = _int("bar", bar, 1, 1_000_000)
    return _lua(f"""
local pos = Temporal.timepos_t({'0' if bar == 1 else f'bbt_to_sample({bar}, 1)'})
local tm = Temporal.TempoMap.write_copy()
tm:set_tempo(Temporal.Tempo({bpm}, {bpm}, 4), pos)
Session:begin_reversible_command("Claude: tempo {bpm} at bar {bar}")
Temporal.TempoMap.update(tm)
if not Session:abort_empty_reversible_command() then Session:commit_reversible_command(nil) end
local r = Temporal.TempoMap.read()
return {{ bpm_at_bar = r:quarters_per_minute_at(pos), bar = {bar} }}""")


@mcp.tool()
def set_meter(beats_per_bar: int = 4, note_value: int = 4, bar: int = 1) -> dict:
    """Set the time signature (e.g. 4/4, 2/2, 6/8) from `bar` onward. Undoable."""
    beats_per_bar = _int("beats_per_bar", beats_per_bar, 1, 256)
    note_value = _int("note_value", note_value, 1, 256)
    bar = _int("bar", bar, 1, 1_000_000)
    return _lua(f"""
local pos = Temporal.timepos_t({'0' if bar == 1 else f'bbt_to_sample({bar}, 1)'})
local tm = Temporal.TempoMap.write_copy()
tm:set_meter(Temporal.Meter({beats_per_bar}, {note_value}), pos)
Session:begin_reversible_command("Claude: meter {beats_per_bar}/{note_value} at bar {bar}")
Temporal.TempoMap.update(tm)
if not Session:abort_empty_reversible_command() then Session:commit_reversible_command(nil) end
local m = Temporal.TempoMap.read():meter_at(pos)
return {{ meter = m:divisions_per_bar() .. "/" .. m:note_value(), bar = {bar} }}""")


@mcp.tool()
def import_audio(file_path: str, track_name: str, new_track: bool = True, bar: int = 1, beat: float = 1.0,
                 offset_seconds: float = 0.0) -> dict:
    """Import an audio file (copied into the session, original untouched) and place it on a track
    at bar/beat. With new_track=True a track named `track_name` is created (channel count from file),
    otherwise the existing track `track_name` is used. `offset_seconds` shifts the region start
    relative to bar/beat (e.g. -0.046 so that a beat found 46 ms into the file lands on the bar). Undoable."""
    p = Path(file_path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    bar = _int("bar", bar, 1, 1_000_000)
    beat = _num("beat", beat, 0, 64)
    offset_seconds = _num("offset_seconds", offset_seconds, -86400, 86400)
    new_track = _bool("new_track", new_track)
    return _lua(f"""
local files = C.StringVector()
files:push_back({lua_str(str(p))})
local before = {{}}
for _, rg in ARDOUR.RegionFactory.regions():iter() do before[rg:to_stateful():id():to_s()] = true end
Editor:do_import(files, Editing.ImportDistinctFiles, Editing.ImportAsRegion, ARDOUR.SrcQuality.SrcBest,
  ARDOUR.MidiTrackNameSource.SMFTrackName, ARDOUR.MidiTempoMapDisposition.SMFTempoIgnore,
  Temporal.timepos_t(0), ARDOUR.PluginInfo(), ARDOUR.Track(), false)
local src
for _, rg in ARDOUR.RegionFactory.regions():iter() do
  if not before[rg:to_stateful():id():to_s()] and rg:whole_file() then src = rg end
end
if not src then error("import produced no region (unsupported format?)") end
local track
if {str(new_track).lower()} then
  local nch = src:to_audioregion():n_channels()
  local tl = Session:new_audio_track(nch, 2, ARDOUR.RouteGroup(), 1, {lua_str(track_name)}, -1, ARDOUR.TrackMode.Normal, true)
  track = tl:front()
else
  track = find_route({lua_str(track_name)}):to_track()
end
local pos = bbt_to_sample({bar}, {beat}) + math.floor({offset_seconds} * Session:nominal_sample_rate() + 0.5)
if pos < 0 then error("region would start before the session start") end
local pl = track:playlist()
local copy = ARDOUR.RegionFactory.clone_region(src, true, false)
Session:begin_reversible_command("Claude: import " .. {lua_str(p.name)})
pl:to_stateful():clear_changes()
pl:add_region(copy, Temporal.timepos_t(pos), 1, false)
Session:add_stateful_diff_command(pl:to_statefuldestructible())
Session:commit_reversible_command(nil)
return {{ track = track:name(), track_id = track:to_stateful():id():to_s(), region = copy:name(),
  region_id = copy:to_stateful():id():to_s(), start = bbt_str(pos), channels = src:to_audioregion():n_channels(),
  length_samples = copy:length():samples() }}""", timeout=600)


def _next_version(session_dir: Path) -> int:
    nums = [int(m.group(1)) for f in session_dir.glob("*.ardour") if (m := re.match(r"v(\d{3})", f.stem))]
    return max(nums, default=0) + 1


@mcp.tool()
def set_pan(track: str, pan: float) -> dict:
    """Set a track's pan with an unambiguous scale: -100 = hard LEFT, 0 = center, +100 = hard RIGHT.
    (Ardour's native track_set_pan uses the opposite 0..1 convention: 0.0 = right, 1.0 = left.)
    `track` is a track name or route id."""
    if not -100 <= pan <= 100:
        raise ValueError("pan must be in -100..100")
    az = (pan + 100) / 200  # Ardour azimuth: 0 = left, 1 = right (verified by export measurement)
    return _lua(f"""
local r = find_route({lua_str(track)})
local pc = r:pan_azimuth_control()
if not pc or pc:isnil() then error("route has no panner") end
pc:set_value({az}, PBD.GroupControlDisposition.NoGroup)
return {{ track = r:name(), pan = {pan}, azimuth = pc:get_value() }}""")


@mcp.tool()
def save_version(note: str) -> dict:
    """Save the session and record a progressive version: an Ardour snapshot "vNNN <note>" in the
    session folder (the working snapshot stays current) plus a timestamped copy of the session
    file in backups/. Call before and after significant edits."""
    info = _lua("""
Session:save_state("", false, false, false, false, false)
return { path = Session:path(), snap = Session:snap_name() }""")
    sdir = Path(info["path"])
    n = _next_version(sdir)
    clean = re.sub(r"[^\w\- ]+", "", note).strip()[:40] or "save"
    snap = f"v{n:03d} {clean}"
    _lua(f'Session:save_state({lua_str(snap)}, false, false, false, false, false) return true')
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = BACKUP_DIR / f"{stamp} {snap}"
    bdir.mkdir()
    for f in [sdir / f"{info['snap']}.ardour", sdir / f"{snap}.ardour"]:
        if f.exists():
            shutil.copy2(f, bdir / f.name)
    log = sdir / "VERSIONS.md"
    with log.open("a") as fh:
        fh.write(f"- {stamp} **{snap}** — {note}\n")
    return {"snapshot": snap, "session_dir": str(sdir), "backup_dir": str(bdir), "working_snapshot": info["snap"]}


@mcp.tool()
def export_wav(name: str = "", start_bar: int | None = None, end_bar: int | None = None,
               tail_seconds: float = 2.0, analyze: bool = True) -> dict:
    """Render the master bus to a WAV (session rate, via Ardour's export engine) in exports/.
    Default range: start of session to end of the last region + tail. Optional bar range
    (end_bar exclusive). Returns the file path and, if analyze=True, technical metrics."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    if start_bar is not None:
        start_bar = _int("start_bar", start_bar, 1, 1_000_000)
    if end_bar is not None:
        end_bar = _int("end_bar", end_bar, 1, 1_000_000)
    tail_seconds = _num("tail_seconds", tail_seconds, 0, 86400)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = re.sub(r"[^\w\- ]+", "", name).strip() or "mix"
    fname = f"{fname} {stamp}"
    s = "0" if start_bar is None else f"bbt_to_sample({start_bar}, 1)"
    e = "session_end_sample()" if end_bar is None else f"bbt_to_sample({end_bar}, 1)"
    res = _lua(f"""
local ex = Session:simple_export()
ex:set_preset({lua_str(WAV_PRESET)})
ex:set_name({lua_str(fname)})
ex:set_folder({lua_str(str(EXPORT_DIR))})
local s, e = {s}, {e} + math.floor({tail_seconds} * Session:nominal_sample_rate())
if e <= s then error("empty export range") end
ex:set_range(s, e)
local ok = ex:run_export()
return {{ ok = ok, start = bbt_str(s), start_sample = s, end_sample = e }}""", timeout=1800)
    if not res.get("ok"):
        raise RuntimeError(f"Ardour export failed: {res}")
    out = EXPORT_DIR / f"{fname}.wav"
    if not out.exists():
        cands = sorted(EXPORT_DIR.glob(f"{fname}*.wav"))
        if not cands:
            raise RuntimeError(f"export reported success but no file found for {fname}")
        out = cands[-1]
    res["file"] = str(out)
    if analyze:
        res["analysis"] = analysis.analyze_file(str(out))
    return res


GMSYNTH = "http://gareus.org/oss/lv2/gmsynth"


@mcp.tool()
def salsa_arrangement_info() -> dict:
    """Describe the salsa arrangement model of the current project: song form (sections with session
    bars, one chord per bar, kind), clave direction and the available parts (track names, GM sounds).
    Use it to map requests like "only the chorus" or "the congas" to sections/parts."""
    return {
        "tempo_bpm": 130, "meter": "4/4", "key": "A minor (Aeolian); breaks F-G -> Am (VI-VII-i)",
        "clave": "son 3-2; '3' side on odd session bars (1, 2&, 4), '2' side on even bars (2, 3)",
        "session_bar_offset": "session bar = original song bar + 4",
        "sections": [{"name": s.name, "bars": [s.start, s.bars[-1]], "kind": s.kind, "chords": s.chords,
                      "stops": s.stops} for s in salsa.FORM],
        "parts": {k: {"track": p.track, "gm_program": p.program, "channel": p.channel + 1, "role": p.description}
                  for k, p in salsa.PARTS.items()},
    }


@mcp.tool()
def salsa_render(parts: list[str] | None = None, sections: list[str] | None = None, seed: int = 0) -> dict:
    """(Re)generate salsa parts as editable MIDI regions in Ardour, one region per part per section.

    parts: keys from salsa_arrangement_info (default: all). sections: section names (default: all).
    Missing tracks are created (MIDI track + General MIDI Synth). Existing regions of those tracks
    that start inside the target sections are removed first (undoable), so other sections and
    other tracks are untouched. `seed` changes the velocity humanisation only.
    Call save_version before and after."""
    seed = _int("seed", seed, -2_147_483_648, 2_147_483_647)
    parts = parts or list(salsa.PARTS)
    secs = [salsa.section_by_name(n) for n in sections] if sections else list(salsa.FORM)
    bad = [p for p in parts if p not in salsa.PARTS]
    if bad:
        raise ValueError(f"unknown parts {bad}; known: {list(salsa.PARTS)}")
    mid_dir = PROJECT_ROOT / "assets" / "midi" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    jobs = []
    for part in parts:
        for sec in secs:
            f, n = salsa.render(part, sec, mid_dir, seed)
            if n:
                jobs.append((salsa.PARTS[part].track, str(f), sec.start, sec.bars[-1] + 1, n))
    tracks = sorted({salsa.PARTS[p].track for p in parts})
    lua_jobs = ",\n".join(f"{{ {lua_str(t)}, {lua_str(f)}, {a}, {b} }}" for t, f, a, b, _ in jobs)
    lua_tracks = ", ".join(lua_str(t) for t in tracks)
    lua_secs = ", ".join(f"{{ {s.start}, {s.bars[-1] + 1} }}" for s in secs)
    res = _lua(f"""
local jobs = {{ {lua_jobs} }}
local tracks = {{ {lua_tracks} }}
local ranges = {{ {lua_secs} }}
local function beat_pos(bar) return Temporal.timepos_t.from_ticks((bar - 1) * 4 * TPB) end
local created = {{}}
-- 1. tracks
for _, name in ipairs(tracks) do
  local r = Session:route_by_name(name)
  if r:isnil() then
    local tl = Session:new_midi_track(ARDOUR.ChanCount(ARDOUR.DataType("midi"), 1), ARDOUR.ChanCount(ARDOUR.DataType("audio"), 2),
      false, ARDOUR.LuaAPI.new_plugin_info({lua_str(GMSYNTH)}, ARDOUR.PluginType.LV2), nil, ARDOUR.RouteGroup(), 1, name,
      ARDOUR.PresentationInfo.max_order, ARDOUR.TrackMode.Normal, true, false)
    if tl:size() == 0 then error("could not create track " .. name) end
    created[#created + 1] = name
  end
end
-- 2. import all files as regions
local files = C.StringVector()
for _, j in ipairs(jobs) do files:push_back(j[2]) end
local before = {{}}
for _, rg in ARDOUR.RegionFactory.regions():iter() do before[rg:to_stateful():id():to_s()] = true end
Editor:do_import(files, Editing.ImportDistinctFiles, Editing.ImportAsRegion, ARDOUR.SrcQuality.SrcBest,
  ARDOUR.MidiTrackNameSource.SMFTrackName, ARDOUR.MidiTempoMapDisposition.SMFTempoIgnore,
  Temporal.timepos_t(0), ARDOUR.PluginInfo(), ARDOUR.Track(), false)
local by_name = {{}}
for _, rg in ARDOUR.RegionFactory.regions():iter() do
  if not before[rg:to_stateful():id():to_s()] and rg:whole_file() then by_name[rg:name()] = rg end
end
local function find_src(path)
  local base = path:match("([^/]+)%.mid$")
  for n, rg in pairs(by_name) do if n == base or n:sub(1, #base + 1) == base .. "-" then return rg end end
end
-- 3. replace regions per track/section, undoable
Session:begin_reversible_command("Claude: salsa_render")
local removed, placed = 0, {{}}
local touched = {{}}
for _, name in ipairs(tracks) do
  local pl = Session:route_by_name(name):to_track():playlist()
  pl:to_stateful():clear_changes()
  touched[name] = pl
  local doomed = {{}}
  for rg in pl:region_list():iter() do
    local p = rg:position():beats():to_ticks()
    for _, rr in ipairs(ranges) do
      if p >= (rr[1] - 1) * 4 * TPB and p < (rr[2] - 1) * 4 * TPB then doomed[#doomed + 1] = rg end
    end
  end
  for _, rg in ipairs(doomed) do pl:remove_region(rg) removed = removed + 1 end
end
for _, j in ipairs(jobs) do
  local src = find_src(j[2])
  if not src then error("imported region not found for " .. j[2]) end
  local copy = ARDOUR.RegionFactory.clone_region(src, true, false)
  touched[j[1]]:add_region(copy, beat_pos(j[3]), 1, false)
  placed[#placed + 1] = j[1] .. " @" .. j[3]
end
for _, pl in pairs(touched) do Session:add_stateful_diff_command(pl:to_statefuldestructible()) end
Session:commit_reversible_command(nil)
return {{ created_tracks = created, removed_regions = removed, placed = #placed }}""", timeout=900)
    res["midi_dir"] = str(mid_dir)
    res["notes_per_part"] = {p: sum(n for t, _, _, _, n in jobs if t == salsa.PARTS[p].track) for p in parts}
    res["sections"] = [s.name for s in secs]
    return res


@mcp.tool()
def analyze_audio(file_path: str) -> dict:
    """Technical analysis of an audio file: sample peak, estimated true peak, RMS, integrated LUFS,
    clipping, DC offset, stereo correlation, per-second RMS. These are technical checks only,
    not an artistic assessment."""
    return analysis.analyze_file(str(Path(file_path).expanduser()))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
