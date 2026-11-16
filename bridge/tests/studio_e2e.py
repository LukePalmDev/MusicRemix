"""End-to-end test of the ardour-studio MCP server through a real MCP stdio client."""
import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

VENV = os.path.expanduser("~/.local/share/musicremix/venv-studio")
ASSET = os.path.expanduser("~/Music/MusicRemix/assets/test/test_tone_A440.wav")

def short(x, n=700):
    s = json.dumps(x, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"

async def main():
    p = StdioServerParameters(command=f"{VENV}/bin/python", args=["-m", "ardour_studio_mcp.server"])
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("tools:", [t.name for t in (await s.list_tools()).tools])
            steps = [
                ("bridge_status", {}),
                ("set_tempo", {"bpm": 130}),
                ("set_meter", {"beats_per_bar": 4, "note_value": 4}),
                ("import_audio", {"file_path": ASSET, "track_name": "Test Import", "new_track": True, "bar": 3, "beat": 1}),
                ("save_version", {"note": "connection test"}),
                ("project_overview", {}),
                ("export_wav", {"name": "e2e-test", "start_bar": 1, "end_bar": 6, "tail_seconds": 1}),
            ]
            for name, args in steps:
                res = await s.call_tool(name, args)
                data = res.structuredContent if res.structuredContent is not None else [getattr(c, "text", c) for c in res.content]
                print(f"\n== {name} {args}\n   isError={res.isError}\n   {short(data, 1600 if name in ('project_overview','export_wav') else 500)}")

asyncio.run(main())
