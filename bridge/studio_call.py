#!/usr/bin/env python3
"""Call an ardour-studio tool directly from the shell (same code the MCP server runs).

Usage: studio_call.py <tool_name> ['<json-args>']
Run with the studio venv: ~/.local/share/musicremix/venv-studio/bin/python bridge/studio_call.py ...
"""
import json
import sys

from ardour_studio_mcp import server

if __name__ == "__main__":
    fn = getattr(server, sys.argv[1])
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(fn(**args), indent=2, ensure_ascii=False))
