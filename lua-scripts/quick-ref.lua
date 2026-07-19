-- TNS|Quick Ref|TNE
-- AX12 Quick Reference Card
-- Table of contents for all installed scripts and tools

local scripts = {
  {cat="TACTICAL",name="Meshtastic Link",desc="LoRa mesh comms via paired node",
   detail="Pair a Meshtastic device via BT/USB.\nSend/receive text and position.\nWorks offline, no cell needed."},
  {cat="TACTICAL",name="ATAK Bridge",desc="Feed telemetry to ATAK CursorOnTarget",
   detail="Streams CoT data to ATAK clients.\nRequires network or mesh link.\nUse with TAK Server or multicast."},
  {cat="TACTICAL",name="Network Position",desc="Network/WiFi location (no satellite fix)",
   detail="No GPS antenna: acquires zero sats.\nYGPS shows sats-in-view, blank SNR.\nPosition is network/WiFi-derived only."},
  {cat="FPV/RACING",name="ELRS Config",desc="ExpressLRS TX module settings",
   detail="Configure packet rate and power.\nBind to receivers.\nUpdate firmware OTA."},
  {cat="FPV/RACING",name="Lap Timer",desc="Race lap timer with audio cues",
   detail="Counts laps via RSSI trigger.\nAudio tone on each lap.\nDisplays best/avg/last times."},
  {cat="FPV/RACING",name="VTX Control",desc="SmartAudio/IRC Tramp channel",
   detail="Change VTX channel and power.\nUses SmartAudio or Tramp protocol.\nNo goggles menu needed."},
  {cat="GENERAL",name="Quick Ref",desc="This script - all available tools",
   detail="Scrollable list of all scripts.\nTouch any entry for details.\nCategories: TAC/FPV/GEN/DEV."},
  {cat="GENERAL",name="Battery Calc",desc="LiPo voltage and cell checker",
   detail="Input total voltage for per-cell.\nShows charge state percentage.\nWarns on low/high cells."},
  {cat="GENERAL",name="Timer Suite",desc="Count-up, count-down, flight timer",
   detail="Multiple simultaneous timers.\nHaptic alerts at thresholds.\nPersists across restarts."},
  {cat="GENERAL",name="Model Notes",desc="Per-model notes and checklists",
   detail="Attach notes to each model slot.\nPre-flight checklists.\nMaintenance reminders."},
  {cat="DEVELOPMENT",name="UMBUS Monitor",desc="Serial UMBUS protocol sniffer",
   detail="Displays raw UMBUS frames.\nDecodes gimbal/switch packets.\nUse for protocol research."},
  {cat="DEVELOPMENT",name="Input Test",desc="Gimbal/switch/touch input tester",
   detail="Shows all input axes live.\nTouch coordinates displayed.\nUseful for calibration checks."},
  {cat="DEVELOPMENT",name="Lua Sandbox",desc="Interactive Lua REPL on LCD",
   detail="Type and execute Lua snippets.\nSee return values on screen.\nTest API calls quickly."},
}

local pytools = {
  "umbus_decode.py  - Decode UMBUS serial frames",
  "gimbal_map.py    - Map gimbal axes to channels",
  "elrs_passthru.py - ELRS serial passthrough",
  "model_export.py  - Export model configs as JSON",
  "doom-demo.sh     - Launch DOOM in Termux",
}

local tips = {
  "GPS: Start YGPS app to enable positioning",
  "USB Gamepad: Plug into PC for simulator use",
  "DOOM: Run scripts/doom-demo.sh from Termux",
  "Meshtastic: Open the app and pair a LoRa node",
  "HDMI: Plug Mini HDMI cable to mirror screen",
  "<AX12-IP> is the radio's Tailscale/LAN address",
  "SSH: Tailscale at <AX12-IP> port 8022",
  "Root: Magisk grants su for system-level access",
  "Termux: Full Linux env - Python/Node tools",
  "ELRS: Long-press bind btn for WiFi update",
  "Backup: adb pull /storage/emulated/0/AX12LUA",
}

-- Dark theme colors
local BG      = lcd.RGB(20, 20, 25)
local FG      = lcd.RGB(220, 220, 220)
local ACCENT  = lcd.RGB(0, 180, 255)
local C_TAC   = lcd.RGB(255, 80, 80)
local C_FPV   = lcd.RGB(255, 200, 0)
local C_GEN   = lcd.RGB(100, 220, 100)
local C_DEV   = lcd.RGB(180, 120, 255)
local DIM     = lcd.RGB(120, 120, 130)
local DIV     = lcd.RGB(50, 50, 60)
local TIPCLR  = lcd.RGB(255, 220, 80)
local BOXBG   = lcd.RGB(30, 30, 40)

local scroll, selected = 0, nil
local LINE_H, HDR_H = 18, 28
local maxScroll = 0
local tipIdx, lastTip = 1, 0

local function catColor(c)
  if c == "TACTICAL" then return C_TAC end
  if c == "FPV/RACING" then return C_FPV end
  if c == "GENERAL" then return C_GEN end
  if c == "DEVELOPMENT" then return C_DEV end
  return FG
end

local function catTag(c)
  if c == "TACTICAL" then return "TAC" end
  if c == "FPV/RACING" then return "FPV" end
  if c == "GENERAL" then return "GEN" end
  if c == "DEVELOPMENT" then return "DEV" end
  return "---"
end

local function init()
  lastTip = getTime()
  local rows = #scripts + #pytools + 8
  local w, h = lcd.getWindowSize()
  maxScroll = rows * LINE_H - (h - HDR_H - 24)
  if maxScroll < 0 then maxScroll = 0 end
end

local function run(event, touchState)
  local w, h = lcd.getWindowSize()
  lcd.clear(BG)

  -- Touch handling
  if touchState then
    if touchState.swipeUp then
      scroll = math.min(scroll + 60, maxScroll)
    end
    if touchState.swipeDown then
      scroll = math.max(scroll - 60, 0)
    end
    if touchState.tapCount and touchState.tapCount > 0 then
      local row, si = 0, 0
      local lastCat = ""
      local idx = math.floor((touchState.y - HDR_H + scroll) / LINE_H)
      for i, s in ipairs(scripts) do
        if s.cat ~= lastCat then
          if row == idx then si = 0; break end
          row = row + 1
          lastCat = s.cat
        end
        if row == idx then si = i; break end
        row = row + 1
      end
      if si >= 1 and si <= #scripts then
        selected = (selected == si) and nil or si
      else
        selected = nil
      end
    end
  end

  -- Encoder / button navigation
  if event == EVT_ROT_RIGHT or event == EVT_PLUS_FIRST then
    scroll = math.min(scroll + LINE_H, maxScroll)
  elseif event == EVT_ROT_LEFT or event == EVT_MINUS_FIRST then
    scroll = math.max(scroll - LINE_H, 0)
  elseif event == EVT_EXIT_BREAK then
    if selected then selected = nil else return 1 end
  end

  -- Header
  lcd.color(ACCENT)
  lcd.font(FONT_STD)
  lcd.drawText(4, 4, "AX12 QUICK REFERENCE")
  lcd.color(DIM)
  lcd.font(FONT_XS)
  lcd.drawText(w - 76, 8, #scripts .. " scripts")
  lcd.color(DIV)
  lcd.drawLine(0, HDR_H - 2, w, HDR_H - 2)

  -- Detail overlay
  if selected and scripts[selected] then
    local s = scripts[selected]
    local bx, by, bw, bh = 8, HDR_H + 6, w - 16, 68
    lcd.color(BOXBG)
    lcd.drawFilledRectangle(bx, by, bw, bh)
    lcd.color(DIV)
    lcd.drawRectangle(bx, by, bw, bh)
    lcd.color(catColor(s.cat))
    lcd.font(FONT_STD)
    lcd.drawText(bx + 6, by + 3, s.name)
    lcd.color(FG)
    lcd.font(FONT_XS)
    local dy = 0
    for line in s.detail:gmatch("[^\n]+") do
      lcd.drawText(bx + 6, by + 20 + dy, line)
      dy = dy + 14
    end
    lcd.color(DIM)
    lcd.drawText(bx + 6, by + bh - 14, "tap/EXIT to close")
    return 0
  end

  -- Scrollable script list
  local y = HDR_H - scroll
  local lastCat = ""
  lcd.font(FONT_XS)

  for i, s in ipairs(scripts) do
    if s.cat ~= lastCat then
      lastCat = s.cat
      if y > -LINE_H and y < h - 22 then
        lcd.color(catColor(s.cat))
        lcd.drawText(4, y + 2, "-- " .. s.cat .. " --")
      end
      y = y + LINE_H
    end
    if y > -LINE_H and y < h - 22 then
      lcd.color(catColor(s.cat))
      lcd.drawText(4, y + 2, catTag(s.cat))
      lcd.color(FG)
      lcd.drawText(32, y + 2, s.name)
      lcd.color(DIM)
      lcd.drawText(136, y + 2, s.desc)
    end
    y = y + LINE_H
  end

  -- Python/shell tools
  y = y + 4
  if y > -LINE_H and y < h - 22 then
    lcd.color(ACCENT)
    lcd.drawText(4, y + 2, "-- TERMINAL TOOLS (run from Termux) --")
  end
  y = y + LINE_H
  for _, t in ipairs(pytools) do
    if y > -LINE_H and y < h - 22 then
      lcd.color(DIM)
      lcd.drawText(8, y + 2, "> " .. t)
    end
    y = y + LINE_H
  end

  -- Tip of the day (cycles every ~5s at 100 ticks/sec)
  local now = getTime()
  if now - lastTip > 500 then
    tipIdx = (tipIdx % #tips) + 1
    lastTip = now
  end
  lcd.color(DIV)
  lcd.drawLine(0, h - 20, w, h - 20)
  lcd.color(TIPCLR)
  lcd.font(FONT_XS)
  lcd.drawText(4, h - 16, "TIP: " .. tips[tipIdx])

  return 0
end

return { init = init, run = run }
