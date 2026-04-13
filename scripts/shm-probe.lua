-- TNS|ShmVar Probe|TNE
---- #########################################################################
---- #                                                                       #
---- # ShmVar Probe -- Enumerate getShmVar / setShmVar shared memory IPC     #
---- # RadioMaster AX12 reverse engineering                                  #
---- # github.com/rmeadomavic/ax12-research                                  #
---- #                                                                       #
---- #########################################################################

local OUTFILE = "/sdcard/AX12LUA/shm-probe-results.txt"
local results = {}
local done = false

local function log(s)
  results[#results+1] = s
end

local function safeGet(arg)
  local ok, val = pcall(getShmVar, arg)
  if ok then
    return val, type(val)
  else
    return nil, "error: " .. tostring(val)
  end
end

local function safeSet(arg, val)
  local ok, ret = pcall(setShmVar, arg, val)
  if ok then
    return ret, type(ret)
  else
    return nil, "error: " .. tostring(ret)
  end
end

local function probeIntIndices()
  log("==== getShmVar(index) -- integer indices 0..255 ====")
  local found = 0
  for i = 0, 255 do
    local val, vtype = safeGet(i)
    if val ~= nil then
      log(string.format("  [%3d] = %s  (%s)", i, tostring(val), vtype))
      found = found + 1
    elseif vtype ~= "nil" and string.find(vtype, "error") then
      log(string.format("  [%3d] ERROR: %s", i, vtype))
    end
  end
  log(string.format("  => %d non-nil values found in 0..255", found))
  log("")
end

local function probeNegativeIndices()
  log("==== getShmVar(index) -- negative indices -1..-32 ====")
  for i = -1, -32, -1 do
    local val, vtype = safeGet(i)
    if val ~= nil or (vtype ~= "nil" and string.find(vtype, "error")) then
      log(string.format("  [%d] = %s  (%s)", i, tostring(val), vtype))
    end
  end
  log("")
end

local function probeLargeIndices()
  log("==== getShmVar(index) -- large indices 256..1024 (step 16) ====")
  for i = 256, 1024, 16 do
    local val, vtype = safeGet(i)
    if val ~= nil or (vtype ~= "nil" and string.find(vtype, "error")) then
      log(string.format("  [%d] = %s  (%s)", i, tostring(val), vtype))
    end
  end
  log("")
end

local function probeStringKeys()
  log("==== getShmVar(string) -- common key names ====")
  local keys = {
    -- Channel names
    "ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "ch7", "ch8",
    "ch9", "ch10", "ch11", "ch12", "ch13", "ch14", "ch15", "ch16",
    "CH1", "CH2", "CH3", "CH4",
    "channel1", "channel2", "channel3", "channel4",
    -- Stick names
    "ail", "ele", "thr", "rud",
    "aileron", "elevator", "throttle", "rudder",
    "roll", "pitch", "yaw",
    "gimbal1", "gimbal2", "gimbal3", "gimbal4",
    -- Switch names
    "sa", "sb", "sc", "sd", "se", "sf", "sg", "sh",
    "SA", "SB", "SC", "SD", "SE", "SF", "SG", "SH",
    "switch_a", "switch_b", "switch_c", "switch_d",
    -- Telemetry
    "rssi", "RSSI", "rqly", "RQly", "1RSS",
    "linkq", "LinkQ", "lq", "LQ",
    "tpwr", "TPWR", "txpower",
    "snr", "SNR",
    -- Battery
    "battery", "voltage", "tx-voltage", "txvoltage",
    "current", "mah", "capacity",
    "batt", "vbat", "Vbat",
    -- GPS / nav
    "gps", "GPS", "latitude", "longitude", "lat", "lon",
    "altitude", "alt", "Altitude", "Alt",
    "speed", "Speed", "heading", "Heading",
    "satellites", "sats", "hdop",
    -- Flight state
    "armed", "mode", "flightmode",
    "failsafe", "connected", "linkup",
    -- Model
    "model", "modelName", "modelId",
    -- Timer
    "timer1", "timer2", "timer3",
    -- System
    "time", "uptime", "freeMemory",
    -- RadioMaster specific guesses
    "hdmi", "map", "mission", "waypoint", "task",
    "gimbalAngle", "gimbalPitch", "gimbalYaw",
    "usbvcp", "serialPort",
    -- EdgeTX source names
    "Rud", "Ele", "Thr", "Ail",
    "S1", "S2", "LS", "RS",
    "TrmR", "TrmE", "TrmT", "TrmA",
  }

  local found = 0
  for _, key in ipairs(keys) do
    local val, vtype = safeGet(key)
    if val ~= nil then
      log(string.format("  %-20s = %s  (%s)", key, tostring(val), vtype))
      found = found + 1
    elseif vtype ~= "nil" and string.find(vtype, "error") then
      log(string.format("  %-20s ERROR: %s", key, vtype))
    end
  end
  log(string.format("  => %d non-nil values for string keys", found))
  log("")
end

local function probeSetShmVar()
  log("==== setShmVar probe -- test write/readback ====")
  local testIdx = 200
  local testVal = 42

  log(string.format("  Before: getShmVar(%d) = %s", testIdx, tostring(safeGet(testIdx))))

  local setRet, setType = safeSet(testIdx, testVal)
  log(string.format("  setShmVar(%d, %d) returned: %s (%s)", testIdx, testVal, tostring(setRet), setType))

  local readback, rbType = safeGet(testIdx)
  log(string.format("  After:  getShmVar(%d) = %s (%s)", testIdx, tostring(readback), rbType))

  if readback == testVal then
    log("  => Write/readback CONFIRMED: ShmVar is read-write!")
  elseif readback ~= nil then
    log("  => Write returned different value: written " .. testVal .. ", read " .. tostring(readback))
  else
    log("  => Readback is nil -- setShmVar may not persist, or index is invalid")
  end

  -- Try string key write
  local setRet2, setType2 = safeSet("test_probe", 99)
  log(string.format("  setShmVar('test_probe', 99) returned: %s (%s)", tostring(setRet2), setType2))
  local rb2, rb2t = safeGet("test_probe")
  log(string.format("  getShmVar('test_probe') = %s (%s)", tostring(rb2), rb2t))
  log("")
end

local function probeFunctionSignature()
  log("==== Function signature probes ====")

  -- Test with no args
  local ok1, r1 = pcall(getShmVar)
  log(string.format("  getShmVar()         => ok=%s  val=%s", tostring(ok1), tostring(r1)))

  -- Test with two args
  local ok2, r2 = pcall(getShmVar, 0, 1)
  log(string.format("  getShmVar(0, 1)     => ok=%s  val=%s", tostring(ok2), tostring(r2)))

  -- Test with boolean
  local ok3, r3 = pcall(getShmVar, true)
  log(string.format("  getShmVar(true)     => ok=%s  val=%s", tostring(ok3), tostring(r3)))

  -- Test with table
  local ok4, r4 = pcall(getShmVar, {})
  log(string.format("  getShmVar({})       => ok=%s  val=%s", tostring(ok4), tostring(r4)))

  -- Check if function exists at all
  log(string.format("  type(getShmVar)     = %s", type(getShmVar)))
  log(string.format("  type(setShmVar)     = %s", type(setShmVar)))
  log("")
end

local function writeResults()
  local f = io.open(OUTFILE, "w")
  if f then
    f:write("-- ShmVar Probe Results\n")
    f:write("-- AX12 RadioMaster shared memory IPC investigation\n")
    f:write("-- github.com/rmeadomavic/ax12-research\n")
    f:write("-- Total lines: " .. #results .. "\n\n")
    for _, line in ipairs(results) do
      f:write(line .. "\n")
    end
    f:close()
    return true
  end
  return false
end

---------------------------------------------------------------------------
-- Init / Run
---------------------------------------------------------------------------

local function init()
  probeFunctionSignature()
  probeIntIndices()
  probeNegativeIndices()
  probeLargeIndices()
  probeStringKeys()
  probeSetShmVar()
  writeResults()
  done = true
end

local function run(event, touchState)
  lcd.clear()

  if done then
    lcd.drawText(10, 10, "ShmVar Probe Complete", BOLD)
    lcd.drawText(10, 40, "Logged " .. #results .. " lines")
    lcd.drawText(10, 70, "Results: /sdcard/AX12LUA/")
    lcd.drawText(10, 90, "  shm-probe-results.txt")
    lcd.drawText(10, 130, "Press EXIT to close", SMLSIZE)
  else
    lcd.drawText(10, 10, "Running probes...", BOLD)
  end

  if event == EVT_EXIT_BREAK or event == EVT_VIRTUAL_EXIT then
    return 2
  end
  return 0
end

return { init=init, run=run }
