#!/usr/bin/env python3
"""Install the Claude Lua bridge as a persistent Ardour 9 "Action Hook".

Ardour stores UI hooks in <config>/ui_scripts as a base64-encoded, serialized
Lua table  s = { n=name, s=source, f=factory-chunk, a=args }  (see
gtk2_ardour/luainstance.cc, LuaCallback::get_state / restore). We generate that
entry directly so no GUI clicks are needed.

Must run while Ardour is NOT running (Ardour rewrites ui_scripts on exit).

Usage: install_bridge.py [--uninstall]
"""
import base64
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ARDOUR_MAJOR = 9
CONFIG_DIR = Path.home() / "Library" / "Preferences" / f"Ardour{ARDOUR_MAJOR}"
UI_SCRIPTS = CONFIG_DIR / "ui_scripts"
BEEN_HERE = CONFIG_DIR / f".a{ARDOUR_MAJOR}"
BRIDGE_DIR = Path.home() / ".ardour-claude-bridge"
HOOK_SRC = Path(__file__).resolve().parent / "lua" / "claude_bridge.lua"

HOOK_NAME = "Claude Bridge"
HOOK_ID = "4200000001"
# LuaSignal enum (gtk2_ardour/luasignal_syms.inc.h, Ardour 9.8): 53 signals,
# LuaTimerDS has index 50. std::bitset::to_string() prints the highest bit first.
N_SIGNALS = 53
LUA_TIMER_DS = 50


def signals_bitstring() -> str:
    bits = ["0"] * N_SIGNALS
    bits[N_SIGNALS - 1 - LUA_TIMER_DS] = "1"
    return "".join(bits)


def lua_long_string(text: str) -> str:
    level = 1
    while ("]" + "=" * level + "]") in text:
        level += 1
    eq = "=" * level
    # a newline directly after the opening bracket is skipped by Lua
    return f"[{eq}[\n{text}]{eq}]"


def ardour_running() -> bool:
    r = subprocess.run(["pgrep", "-x", f"Ardour{ARDOUR_MAJOR}"], capture_output=True)
    return r.returncode == 0


def load_tree() -> ET.ElementTree:
    if UI_SCRIPTS.exists():
        return ET.parse(UI_SCRIPTS)
    return ET.ElementTree(ET.Element("UIScripts"))


def main() -> int:
    uninstall = "--uninstall" in sys.argv
    if ardour_running():
        print("ERROR: Ardour is running; quit it first (it rewrites ui_scripts on exit).")
        return 1

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    BEEN_HERE.touch(exist_ok=True)  # skip the first-run "new user" wizard

    tree = load_tree()
    root = tree.getroot()
    hooks = root.find("ActionHooks")
    if hooks is None:
        hooks = ET.SubElement(root, "ActionHooks")
    for cb in list(hooks.findall("LuaCallback")):
        if cb.get("name") == HOOK_NAME or cb.get("id") == HOOK_ID:
            hooks.remove(cb)

    if not uninstall:
        source = HOOK_SRC.read_text().replace("@@BRIDGE_DIR@@", str(BRIDGE_DIR))
        state = (
            "s = {} "
            f's["n"] = "{HOOK_NAME}" '
            f's["s"] = {lua_long_string(source)} '
            f's["f"] = {lua_long_string(source)} '
            's["a"] = {} '
        )
        cb = ET.SubElement(hooks, "LuaCallback", {
            "lua": "Lua 5.3",
            "id": HOOK_ID,
            "name": HOOK_NAME,
            "signals": signals_bitstring(),
        })
        cb.text = base64.b64encode(state.encode()).decode()

    if UI_SCRIPTS.exists():
        backup = UI_SCRIPTS.with_suffix(".bak")
        backup.write_bytes(UI_SCRIPTS.read_bytes())
    tree.write(UI_SCRIPTS, encoding="UTF-8", xml_declaration=True)
    print(("Removed" if uninstall else "Installed") + f" '{HOOK_NAME}' in {UI_SCRIPTS}")
    print(f"Bridge directory: {BRIDGE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
