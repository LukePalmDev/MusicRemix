-- Claude <-> Ardour Lua bridge (EditorHook, signal: LuaTimerDS = every 100 ms)
--
-- This file is the *factory chunk* of an Ardour "Action Hook". It is called
-- once with the hook arguments and returns the callback that Ardour invokes
-- on every LuaTimerDS tick, in the GUI thread, with full access to the
-- Session / Editor / ARDOUR / Temporal Lua API.
--
-- Protocol (single slot, files in BRIDGE_DIR):
--   client writes  request.tmp  -> renames to request.lua   (atomic)
--   first line of the request:  "-- id:<request-id>"
--   hook executes it, writes  response.tmp -> renames to response.json
--   response: {"id":..., "ok":bool, "result":<json>, "output":"...", "error":"..."}
--   heartbeat.json is refreshed about once per second.
--
-- BRIDGE_DIR is substituted by bridge/install_bridge.py at install time.

local BRIDGE_DIR = "@@BRIDGE_DIR@@"
local REQ  = BRIDGE_DIR .. "/request.lua"
local RESP = BRIDGE_DIR .. "/response.json"
local HB   = BRIDGE_DIR .. "/heartbeat.json"

-- ---------------------------------------------------------------- JSON
local function json_encode (v, seen)
	seen = seen or {}
	local t = type (v)
	if t == "nil" then return "null"
	elseif t == "boolean" then return v and "true" or "false"
	elseif t == "number" then
		if v ~= v or v == math.huge or v == -math.huge then return "null" end
		if math.type and math.type (v) == "integer" then return string.format ("%d", v) end
		return string.format ("%.10g", v)
	elseif t == "string" then
		return '"' .. v:gsub ('[%c"\\]', function (c)
			local map = { ['"'] = '\\"', ['\\'] = '\\\\', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }
			return map[c] or string.format ("\\u%04x", c:byte ())
		end) .. '"'
	elseif t == "table" then
		if seen[v] then return '"<cycle>"' end
		seen[v] = true
		local n = #v
		local is_array = true
		local count = 0
		for k, _ in pairs (v) do
			count = count + 1
			if math.type (k) ~= "integer" or k < 1 or k > n then is_array = false end
		end
		local parts = {}
		if is_array and (count > 0 or next (v) == nil) then
			for i = 1, n do parts[#parts + 1] = json_encode (v[i], seen) end
			seen[v] = nil
			return "[" .. table.concat (parts, ",") .. "]"
		end
		for k, val in pairs (v) do
			parts[#parts + 1] = json_encode (tostring (k), seen) .. ":" .. json_encode (val, seen)
		end
		seen[v] = nil
		return "{" .. table.concat (parts, ",") .. "}"
	else
		return json_encode (tostring (v), seen)
	end
end

local function write_atomic (path, data)
	local tmp = path .. ".tmp"
	local f = io.open (tmp, "w")
	if not f then return false end
	f:write (data)
	f:close ()
	return os.rename (tmp, path)
end

-- Persistent environment shared by all requests: snippets can keep state
-- across calls (e.g. helper functions) without touching the hook globals.
local shared_env = setmetatable ({ json_encode = json_encode, BRIDGE_DIR = BRIDGE_DIR }, { __index = _ENV })

local tick = 0

return function (signal, ref, ...)
	tick = tick + 1
	if tick % 10 == 0 then
		local sname = Session and Session:name () or nil
		write_atomic (HB, json_encode ({ alive = true, time = os.time (), session = sname,
			sample_rate = Session and Session:nominal_sample_rate () or nil }))
	end

	local f = io.open (REQ, "r")
	if not f then return end
	local code = f:read ("*a")
	f:close ()
	os.remove (REQ)

	local id = code:match ("^%-%- id:(%S+)") or "unknown"
	local out = {}
	shared_env.print = function (...)
		local p = {}
		for i = 1, select ("#", ...) do p[#p + 1] = tostring ((select (i, ...))) end
		out[#out + 1] = table.concat (p, "\t")
	end

	local resp = { id = id }
	local fn, err = load (code, "=claude_request", "t", shared_env)
	if not fn then
		resp.ok = false
		resp.error = "compile error: " .. tostring (err)
	else
		local ok, res = xpcall (fn, debug and debug.traceback or function (e) return e end)
		resp.ok = ok
		if ok then resp.result = res else resp.error = tostring (res) end
	end
	resp.output = table.concat (out, "\n")

	local okenc, payload = pcall (json_encode, resp)
	if not okenc then
		payload = json_encode ({ id = id, ok = false, error = "cannot encode result: " .. tostring (payload), output = resp.output })
	end
	write_atomic (RESP, payload)
end
