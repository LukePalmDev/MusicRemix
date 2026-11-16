#!/usr/bin/env python3
"""Run a Lua snippet inside the running Ardour GUI via the Claude bridge.

Usage:  lua_call.py 'return Session:name()'
        lua_call.py -f script.lua [--timeout 60]
Prints the JSON response.
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

BRIDGE_DIR = Path.home() / ".ardour-claude-bridge"


def call(code: str, timeout: float = 30.0) -> dict:
    req_id = uuid.uuid4().hex
    req = BRIDGE_DIR / "request.lua"
    resp = BRIDGE_DIR / "response.json"
    if resp.exists():
        resp.unlink()
    tmp = BRIDGE_DIR / "request.tmp"
    tmp.write_text(f"-- id:{req_id}\n{code}\n")
    os.replace(tmp, req)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if resp.exists():
            data = json.loads(resp.read_text())
            if data.get("id") == req_id:
                resp.unlink()
                return data
        time.sleep(0.02)
    if req.exists():
        req.unlink()
    raise TimeoutError(f"no response from Ardour bridge within {timeout}s (is Ardour running?)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?")
    ap.add_argument("-f", "--file")
    ap.add_argument("--timeout", type=float, default=30.0)
    a = ap.parse_args()
    code = Path(a.file).read_text() if a.file else a.code
    if not code:
        ap.error("no code given")
    print(json.dumps(call(code, a.timeout), indent=2))
