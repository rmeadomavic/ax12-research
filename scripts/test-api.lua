-- TNS|API Probe|TNE
---- #########################################################################
---- #                                                                       #
---- # API Probe -- Enumerate all globals available to Lua scripts           #
---- # RadioMaster AX12 reverse engineering                                  #
---- # github.com/rmeadomavic/ax12-research                                  #
---- #                                                                       #
---- #########################################################################

-- Results written to /sdcard/AX12LUA/api-probe-results.txt

local results = {}

local function probe(tbl, prefix)
  for k, v in pairs(tbl) do
    local name = prefix and (prefix .. "." .. tostring(k)) or tostring(k)
    local t = type(v)
    if t == "function" then
      results[#results+1] = name .. "  [function]"
    elseif t == "number" then
      results[#results+1] = name .. "  [number] = " .. tostring(v)
    elseif t == "string" then
      results[#results+1] = name .. "  [string] = " .. tostring(v)
    elseif t == "table" and v ~= _G and v ~= tbl and prefix == nil then
      results[#results+1] = name .. "  [table]"
      probe(v, name)
    elseif t == "boolean" then
      results[#results+1] = name .. "  [boolean] = " .. tostring(v)
    end
  end
end

local function init()
  probe(_G, nil)
  table.sort(results)
  local f = io.open("/sdcard/AX12LUA/api-probe-results.txt", "w")
  if f then
    f:write("-- Flyshark Lua API Probe Results\n")
    f:write("-- Generated at runtime by test-api.lua\n")
    f:write("-- Total symbols: " .. #results .. "\n\n")
    for _, line in ipairs(results) do
      f:write(line .. "\n")
    end
    f:close()
  end
end

local function run(event, touchState)
  lcd.clear()
  lcd.drawText(10, 10, "API Probe Complete", BOLD)
  lcd.drawText(10, 40, "Found " .. #results .. " symbols")
  lcd.drawText(10, 70, "Results: /sdcard/AX12LUA/")
  lcd.drawText(10, 90, "  api-probe-results.txt")
  lcd.drawText(10, 130, "Press EXIT to close", SMLSIZE)
  if event == EVT_EXIT_BREAK or event == EVT_VIRTUAL_EXIT then
    return 2
  end
  return 0
end

return { init=init, run=run }
