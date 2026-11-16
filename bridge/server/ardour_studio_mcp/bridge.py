"""Client for the file-based Lua bridge running inside the Ardour GUI.

See bridge/lua/claude_bridge.lua for the protocol. One request at a time.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

BRIDGE_DIR = Path(os.environ.get("ARDOUR_BRIDGE_DIR", Path.home() / ".ardour-claude-bridge"))
_lock = threading.Lock()


class BridgeError(RuntimeError):
    pass


def heartbeat() -> dict | None:
    hb = BRIDGE_DIR / "heartbeat.json"
    try:
        data = json.loads(hb.read_text())
    except (OSError, ValueError):
        return None
    data["age_seconds"] = round(time.time() - hb.stat().st_mtime, 1)
    return data


def is_alive(max_age: float = 5.0) -> bool:
    hb = heartbeat()
    return bool(hb and hb["age_seconds"] <= max_age)


def run_lua(code: str, timeout: float = 30.0) -> dict:
    """Execute Lua in Ardour; returns {"ok", "result", "output", "error"}."""
    # the GUI thread (and so the heartbeat) stalls for a few seconds after exports/imports
    grace = time.monotonic() + 20.0
    while not is_alive():
        if time.monotonic() > grace:
            raise BridgeError("Ardour bridge not responding (is Ardour running with a session open?)")
        time.sleep(0.5)
    req_id = uuid.uuid4().hex
    req = BRIDGE_DIR / "request.lua"
    resp = BRIDGE_DIR / "response.json"
    with _lock:
        resp.unlink(missing_ok=True)
        tmp = BRIDGE_DIR / "request.tmp"
        tmp.write_text(f"-- id:{req_id}\n{code}\n")
        os.replace(tmp, req)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if resp.exists():
                try:
                    data = json.loads(resp.read_text())
                except ValueError:
                    time.sleep(0.02)
                    continue
                if data.get("id") == req_id:
                    resp.unlink(missing_ok=True)
                    data.pop("id", None)
                    return data
            time.sleep(0.02)
        req.unlink(missing_ok=True)
    raise BridgeError(f"no response from Ardour within {timeout}s")


def lua_value(code: str, timeout: float = 30.0):
    """Run Lua and return its result, raising on Lua errors."""
    r = run_lua(code, timeout)
    if not r.get("ok"):
        raise BridgeError(r.get("error") or "unknown Lua error")
    return r.get("result")


def lua_str(s: str) -> str:
    """Quote a Python string as a Lua string literal."""
    return json.dumps(s, ensure_ascii=False)  # JSON string escapes are valid Lua escapes for our use
