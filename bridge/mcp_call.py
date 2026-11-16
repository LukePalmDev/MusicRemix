#!/usr/bin/env python3
"""Call a tool on Ardour's native MCP HTTP server (for tests and scripting).

Usage: mcp_call.py <tool_name> ['<json-args>']
       mcp_call.py --list
"""
from __future__ import annotations

import json
import sys
import urllib.request

URL = "http://127.0.0.1:4820/mcp"


def rpc(method: str, params: dict | None = None) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def call_tool(name: str, args: dict | None = None) -> dict:
    res = rpc("tools/call", {"name": name, "arguments": args or {}})
    if "error" in res:
        return {"error": res["error"]}
    r = res["result"]
    return {"isError": r.get("isError", False), "data": r.get("structuredContent", r.get("content"))}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--list":
        for t in rpc("tools/list")["result"]["tools"]:
            print(t["name"])
        sys.exit(0)
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(call_tool(sys.argv[1], args), indent=2))
