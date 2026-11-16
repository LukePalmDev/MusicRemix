"""Drive raibid-entertainment/ardour-mcp through a real MCP stdio client and
check what actually changed in Ardour (via the Lua bridge)."""
import asyncio, json, subprocess, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = sys.argv[1]
def lua(code):
    out = subprocess.run(["python3", f"{ROOT}/bridge/lua_call.py", code], capture_output=True, text=True).stdout
    return json.loads(out).get("result")

STATE = '''local t = {} for r in Session:get_routes():iter() do t[#t+1] = r:name() .. "=" .. string.format("%.1f", 20*math.log(math.max(r:gain_control():get_value(),1e-9),10)) .. "dB" end
return { bpm = Temporal.TempoMap.read():quarters_per_minute_at(Temporal.timepos_t(0)), routes = t, rolling = Session:transport_rolling() }'''

async def main():
    params = StdioServerParameters(command=f"/Users/luke/.local/share/musicremix/venv-upstream/bin/ardour-mcp", args=[])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            try:
                tools = (await s.list_tools()).tools
                print("upstream tools/list:", len(tools))
            except Exception as e:
                print("upstream tools/list FAILED:", e)
            print("BEFORE:", lua(STATE))
            for name, args in [("list_tracks", {}), ("create_audio_track", {"name": "Upstream Test"}),
                               ("create_midi_track", {"name": "Upstream MIDI"}),
                               ("set_session_tempo", {"bpm": 100}), ("set_track_volume", {"track_id": 1, "volume_db": -4.0}),
                               ("transport_play", {}), ("get_transport_position", {}), ("transport_stop", {}),
                               ("save_session", {})]:
                try:
                    res = await s.call_tool(name, args)
                except Exception as e:
                    print(f"  {name}{args} -> EXCEPTION {e}"); continue
                txt = " ".join(getattr(c, "text", "") for c in res.content)[:160].replace("\n", " ")
                print(f"  {name}{args} -> isError={res.isError}: {txt}")
                await asyncio.sleep(0.6)
            print("AFTER: ", lua(STATE))

asyncio.run(main())
