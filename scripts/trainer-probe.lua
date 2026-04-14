-- TNS|Trainer Probe|TNE
---- #########################################################################
---- #                                                                       #
---- # Trainer Probe -- Investigate host/trainer mode API and state          #
---- # RadioMaster AX12 reverse engineering                                  #
---- # github.com/rmeadomavic/ax12-research                                  #
---- #                                                                       #
---- # Run this script TWICE: once with host OFF, once with host ON.         #
---- # Diff the output files to see which values change.                     #
---- #                                                                       #
---- #########################################################################

local OUTFILE = "/sdcard/AX12LUA/trainer-probe-results.txt"
local results = {}
local done = false

local function log(s)
  results[#results+1] = s
end

local function safe(fn, ...)
  local ok, val = pcall(fn, ...)
  if ok then
    return val, type(val)
  else
    return nil, "error: " .. tostring(val)
  end
end

---------------------------------------------------------------------------
-- 1. getTrainerStatus
---------------------------------------------------------------------------
local function probeTrainerStatus()
  log("==== getTrainerStatus() ====")
  if type(getTrainerStatus) == "function" then
    local val, vtype = safe(getTrainerStatus)
    log(string.format("  type = %s", vtype))
    if vtype == "table" then
      for k, v in pairs(val) do
        log(string.format("  .%-20s = %s  (%s)", tostring(k), tostring(v), type(v)))
      end
    elseif val ~= nil then
      log(string.format("  value = %s", tostring(val)))
    end
  else
    log("  getTrainerStatus is " .. type(getTrainerStatus) .. " (not available)")
  end
  log("")
end

---------------------------------------------------------------------------
-- 2. getGeneralSettings
---------------------------------------------------------------------------
local function probeGeneralSettings()
  log("==== getGeneralSettings() ====")
  if type(getGeneralSettings) == "function" then
    local val, vtype = safe(getGeneralSettings)
    log(string.format("  type = %s", vtype))
    if vtype == "table" then
      local keys = {}
      for k in pairs(val) do keys[#keys+1] = tostring(k) end
      table.sort(keys)
      for _, k in ipairs(keys) do
        local v = val[k] or val[tonumber(k)]
        log(string.format("  .%-30s = %s  (%s)", k, tostring(v), type(v)))
      end
    elseif val ~= nil then
      log(string.format("  value = %s", tostring(val)))
    end
  else
    log("  getGeneralSettings is " .. type(getGeneralSettings) .. " (not available)")
  end
  log("")
end

---------------------------------------------------------------------------
-- 3. Trainer channel sources (tr1..tr16)
---------------------------------------------------------------------------
local function probeTrainerChannels()
  log("==== Trainer channel sources (getValue) ====")
  if type(getValue) ~= "function" then
    log("  getValue not available")
    log("")
    return
  end

  -- Try "trN" naming (EdgeTX convention)
  for i = 1, 16 do
    local name = "tr" .. i
    local val, vtype = safe(getValue, name)
    if val ~= nil then
      log(string.format("  %-10s = %s  (%s)", name, tostring(val), vtype))
    end
  end

  -- Try "TRNX" naming variant
  for i = 1, 16 do
    local name = "TRN" .. i
    local val, vtype = safe(getValue, name)
    if val ~= nil then
      log(string.format("  %-10s = %s  (%s)", name, tostring(val), vtype))
    end
  end

  -- Try "Trainer" prefix
  for i = 1, 16 do
    local name = "Trainer" .. i
    local val, vtype = safe(getValue, name)
    if val ~= nil then
      log(string.format("  %-10s = %s  (%s)", name, tostring(val), vtype))
    end
  end

  log("")
end

---------------------------------------------------------------------------
-- 4. getFieldInfo for trainer-related fields
---------------------------------------------------------------------------
local function probeTrainerFields()
  log("==== getFieldInfo -- trainer-related ====")
  if type(getFieldInfo) ~= "function" then
    log("  getFieldInfo not available")
    log("")
    return
  end

  local names = {
    "trainer", "Trainer", "TRAINER",
    "host", "Host", "HOST",
    "pupil", "Pupil", "PUPIL",
    "master", "Master", "slave", "Slave",
    "trainerMode", "TrainerMode",
    "tr1", "tr2", "tr3", "tr4",
    "TRN1", "TRN2", "TRN3", "TRN4",
    "SBUS", "sbus",
    "buddy", "Buddy",
  }

  for _, name in ipairs(names) do
    local info, itype = safe(getFieldInfo, name)
    if info ~= nil then
      if itype == "table" then
        local parts = {}
        for k, v in pairs(info) do
          parts[#parts+1] = tostring(k) .. "=" .. tostring(v)
        end
        log(string.format("  %-20s => {%s}", name, table.concat(parts, ", ")))
      else
        log(string.format("  %-20s => %s (%s)", name, tostring(info), itype))
      end
    end
  end
  log("")
end

---------------------------------------------------------------------------
-- 5. ShmVar trainer-related keys
---------------------------------------------------------------------------
local function probeTrainerShmVar()
  log("==== getShmVar -- trainer-related keys ====")
  if type(getShmVar) ~= "function" then
    log("  getShmVar not available")
    log("")
    return
  end

  local keys = {
    "trainer", "Trainer", "trainerMode", "TrainerMode",
    "host", "Host", "hostMode", "HostMode",
    "pupil", "Pupil", "pupilMode",
    "master", "Master", "slave", "Slave",
    "buddy", "buddyBox",
    "sbus", "SBUS", "sbusTrainer",
    "trainerConnected", "trainerActive",
    "trainerSource", "trainerWeight",
  }

  local found = 0
  for _, key in ipairs(keys) do
    local val, vtype = safe(getShmVar, key)
    if val ~= nil then
      log(string.format("  %-25s = %s  (%s)", key, tostring(val), vtype))
      found = found + 1
    elseif vtype ~= "nil" and string.find(vtype, "error") then
      log(string.format("  %-25s ERROR: %s", key, vtype))
    end
  end
  log(string.format("  => %d non-nil values found", found))
  log("")
end

---------------------------------------------------------------------------
-- 6. CHAR_TRAINER constant
---------------------------------------------------------------------------
local function probeConstants()
  log("==== Trainer-related constants ====")
  local consts = {
    {"CHAR_TRAINER", CHAR_TRAINER},
    {"CHAR_INPUT", CHAR_INPUT},
    {"CHAR_CHANNEL", CHAR_CHANNEL},
    {"CHAR_SWITCH", CHAR_SWITCH},
    {"CHAR_STICK", CHAR_STICK},
    {"CHAR_TRIM", CHAR_TRIM},
    {"CHAR_SLIDER", CHAR_SLIDER},
    {"CHAR_POT", CHAR_POT},
  }

  for _, pair in ipairs(consts) do
    local name, val = pair[1], pair[2]
    if val ~= nil then
      if type(val) == "number" then
        log(string.format("  %-20s = %d  (0x%02X)", name, val, val))
      else
        log(string.format("  %-20s = %s  (%s)", name, tostring(val), type(val)))
      end
    else
      log(string.format("  %-20s = nil", name))
    end
  end
  log("")
end

---------------------------------------------------------------------------
-- 7. Model trainer configuration (EdgeTX-style)
---------------------------------------------------------------------------
local function probeModelTrainer()
  log("==== model.getModule / model trainer config ====")
  if type(model) ~= "table" then
    log("  model table not available")
    log("")
    return
  end

  -- Check for trainer-related model functions
  local modelFuncs = {
    "getModule", "getInfo", "getTimer",
    "getInput", "getOutput", "getMix",
    "getGlobalVariable",
  }

  for _, fname in ipairs(modelFuncs) do
    if type(model[fname]) == "function" then
      log(string.format("  model.%s = [function]", fname))
    end
  end

  -- Try model.getModule for trainer module (index 0 = internal, 1 = external, 2 = trainer?)
  if type(model.getModule) == "function" then
    for i = 0, 3 do
      local mod, mtype = safe(model.getModule, i)
      if mod ~= nil then
        log(string.format("  model.getModule(%d):", i))
        if mtype == "table" then
          for k, v in pairs(mod) do
            log(string.format("    .%-20s = %s  (%s)", tostring(k), tostring(v), type(v)))
          end
        else
          log(string.format("    = %s (%s)", tostring(mod), mtype))
        end
      end
    end
  end

  -- Try model.getInfo
  if type(model.getInfo) == "function" then
    local info, itype = safe(model.getInfo)
    if info ~= nil and itype == "table" then
      log("  model.getInfo():")
      for k, v in pairs(info) do
        log(string.format("    .%-20s = %s  (%s)", tostring(k), tostring(v), type(v)))
      end
    end
  end

  log("")
end

---------------------------------------------------------------------------
-- Write results
---------------------------------------------------------------------------
local function writeResults()
  local f = io.open(OUTFILE, "w")
  if f then
    f:write("-- Trainer Probe Results\n")
    f:write("-- AX12 RadioMaster trainer/host mode investigation\n")
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
  probeTrainerStatus()
  probeGeneralSettings()
  probeTrainerChannels()
  probeTrainerFields()
  probeTrainerShmVar()
  probeConstants()
  probeModelTrainer()
  writeResults()
  done = true
end

local function run(event, touchState)
  lcd.clear()

  if done then
    lcd.drawText(10, 10, "Trainer Probe Complete", BOLD)
    lcd.drawText(10, 40, "Logged " .. #results .. " lines")
    lcd.drawText(10, 70, "Results: /sdcard/AX12LUA/")
    lcd.drawText(10, 90, "  trainer-probe-results.txt")
    lcd.drawText(10, 120, "Run TWICE: host OFF then ON", SMLSIZE)
    lcd.drawText(10, 140, "Diff outputs to find changes", SMLSIZE)
    lcd.drawText(10, 180, "Press EXIT to close", SMLSIZE)
  else
    lcd.drawText(10, 10, "Running trainer probes...", BOLD)
  end

  if event == EVT_EXIT_BREAK or event == EVT_VIRTUAL_EXIT then
    return 2
  end
  return 0
end

return { init=init, run=run }
