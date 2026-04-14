-- TNS|Flight Log|TNE
local LOG_FILE = "/storage/emulated/0/AX12LUA/flight_log.json"
local LCD_W, LCD_H = 480, 320
local STATE = { screen="main", flights={}, current=nil, scroll=0, today="" }

-- Colors (dark theme)
local C_BG = lcd.RGB(20, 20, 25)
local C_CARD = lcd.RGB(35, 35, 42)
local C_TEXT = lcd.RGB(220, 220, 230)
local C_DIM = lcd.RGB(130, 130, 145)
local C_ACC = lcd.RGB(60, 180, 120)
local C_WARN = lcd.RGB(220, 80, 70)
local C_BTN = lcd.RGB(50, 100, 200)
local C_BTN2 = lcd.RGB(80, 60, 160)

local function getToday()
  local d = os.date("*t")
  return string.format("%04d-%02d-%02d", d.year, d.month, d.day)
end

local function getTime()
  return os.date("%H:%M:%S")
end

local function getSeconds()
  return os.clock()
end

local function loadLog()
  local f = io.open(LOG_FILE, "r")
  if not f then return {} end
  local raw = f:read("*a")
  f:close()
  if not raw or #raw == 0 then return {} end
  local all = {}
  for entry in raw:gmatch("{(.-)}") do
    local fl = {}
    fl.date = entry:match('"date":"(.-)"')
    fl.start = entry:match('"start":"(.-)"')
    fl.duration = tonumber(entry:match('"duration":(%d+)'))
    fl.model = entry:match('"model":"(.-)"')
    fl.vStart = tonumber(entry:match('"vStart":([%d%.]+)'))
    fl.vEnd = tonumber(entry:match('"vEnd":([%d%.]+)'))
    fl.maxAlt = tonumber(entry:match('"maxAlt":([%d%.]+)'))
    fl.maxSpd = tonumber(entry:match('"maxSpd":([%d%.]+)'))
    fl.maxDist = tonumber(entry:match('"maxDist":([%d%.]+)'))
    if fl.date then all[#all+1] = fl end
  end
  return all
end

local function saveLog(flights)
  local f = io.open(LOG_FILE, "w")
  if not f then return end
  f:write("[\n")
  for i, fl in ipairs(flights) do
    f:write(string.format(
      '{"date":"%s","start":"%s","duration":%d,"model":"%s","vStart":%.1f,"vEnd":%.1f,"maxAlt":%.1f,"maxSpd":%.1f,"maxDist":%.1f}',
      fl.date or "", fl.start or "", fl.duration or 0, fl.model or "Unknown",
      fl.vStart or 0, fl.vEnd or 0, fl.maxAlt or 0, fl.maxSpd or 0, fl.maxDist or 0))
    if i < #flights then f:write(",\n") else f:write("\n") end
  end
  f:write("]\n")
  f:close()
end

local function todayFlights(flights)
  local today = getToday()
  local out = {}
  for _, fl in ipairs(flights) do
    if fl.date == today then out[#out+1] = fl end
  end
  return out
end

local function fmtDuration(sec)
  local m = math.floor(sec / 60)
  local s = sec % 60
  return string.format("%d:%02d", m, s)
end

local function drawBtn(x, y, w, h, text, color)
  lcd.drawFilledRectangle(x, y, w, h, color)
  local tw = #text * 7
  lcd.drawText(x + (w - tw) / 2, y + (h - 16) / 2, text, C_TEXT)
end

local function inBox(tx, ty, x, y, w, h)
  return tx >= x and tx <= x + w and ty >= y and ty <= y + h
end

local function drawMain()
  lcd.drawFilledRectangle(0, 0, LCD_W, LCD_H, C_BG)
  lcd.drawText(160, 10, "FLIGHT LOG", C_ACC + BOLD)
  local tfl = todayFlights(STATE.flights)
  lcd.drawText(20, 40, "Today: " .. getToday(), C_DIM)
  lcd.drawText(20, 60, "Flights: " .. #tfl, C_TEXT)
  if STATE.current then
    local elapsed = math.floor(getSeconds() - STATE.current.startSec)
    lcd.drawFilledRectangle(15, 85, 450, 50, C_CARD)
    lcd.drawText(25, 90, "RECORDING - " .. STATE.current.model, C_WARN)
    lcd.drawText(25, 110, "Duration: " .. fmtDuration(elapsed), C_TEXT)
    local v = getValue("VFAS") or 0
    if v > 0 then
      lcd.drawText(250, 110, string.format("Batt: %.1fV", v), C_TEXT)
    end
    local alt = getValue("Alt") or 0
    if alt > STATE.current.maxAlt then STATE.current.maxAlt = alt end
    local spd = getValue("GSpd") or 0
    if spd > STATE.current.maxSpd then STATE.current.maxSpd = spd end
    local dist = getValue("Dist") or 0
    if dist > STATE.current.maxDist then STATE.current.maxDist = dist end
    drawBtn(20, 145, 200, 45, "END FLIGHT", C_WARN)
  else
    drawBtn(20, 100, 200, 50, "NEW FLIGHT", C_ACC)
  end
  drawBtn(20, 210, 200, 50, "VIEW LOG", C_BTN)
  drawBtn(260, 210, 200, 50, "STATS", C_BTN2)
end

local function drawLog()
  lcd.drawFilledRectangle(0, 0, LCD_W, LCD_H, C_BG)
  lcd.drawText(150, 10, "TODAYS FLIGHTS", C_ACC + BOLD)
  drawBtn(380, 5, 90, 30, "BACK", C_CARD)
  local tfl = todayFlights(STATE.flights)
  if #tfl == 0 then
    lcd.drawText(150, 140, "No flights today", C_DIM)
    return
  end
  local y = 45
  local startIdx = STATE.scroll + 1
  local endIdx = math.min(#tfl, STATE.scroll + 5)
  for i = startIdx, endIdx do
    local fl = tfl[i]
    lcd.drawFilledRectangle(15, y, 450, 48, C_CARD)
    lcd.drawText(25, y + 4, string.format("#%d  %s  %s", i, fl.start or "??:??", fl.model or ""), C_TEXT)
    local vUsed = (fl.vStart or 0) - (fl.vEnd or 0)
    lcd.drawText(25, y + 24, string.format("Dur: %s  Batt: -%.1fV  Alt: %.0fm  Spd: %.0f",
      fmtDuration(fl.duration or 0), vUsed, fl.maxAlt or 0, fl.maxSpd or 0), C_DIM)
    y = y + 54
  end
  if endIdx < #tfl then
    lcd.drawText(200, y + 5, "v more v", C_DIM)
  end
  if STATE.scroll > 0 then
    lcd.drawText(200, 35, "^ more ^", C_DIM)
  end
end

local function drawStats()
  lcd.drawFilledRectangle(0, 0, LCD_W, LCD_H, C_BG)
  lcd.drawText(180, 10, "STATISTICS", C_ACC + BOLD)
  drawBtn(380, 5, 90, 30, "BACK", C_CARD)
  local tfl = todayFlights(STATE.flights)
  local totalTime = 0
  local totalV = 0
  for _, fl in ipairs(tfl) do
    totalTime = totalTime + (fl.duration or 0)
    totalV = totalV + ((fl.vStart or 0) - (fl.vEnd or 0))
  end
  local avg = #tfl > 0 and math.floor(totalTime / #tfl) or 0
  local y = 60
  lcd.drawFilledRectangle(15, y, 450, 200, C_CARD)
  y = y + 15
  lcd.drawText(30, y, "Total Flights Today:", C_DIM)
  lcd.drawText(280, y, tostring(#tfl), C_TEXT)
  y = y + 30
  lcd.drawText(30, y, "Total Flight Time:", C_DIM)
  lcd.drawText(280, y, fmtDuration(totalTime), C_TEXT)
  y = y + 30
  lcd.drawText(30, y, "Average Duration:", C_DIM)
  lcd.drawText(280, y, fmtDuration(avg), C_TEXT)
  y = y + 30
  lcd.drawText(30, y, "Total Batt Used:", C_DIM)
  lcd.drawText(280, y, string.format("%.1fV", totalV), C_TEXT)
  y = y + 30
  lcd.drawText(30, y, "All-Time Flights:", C_DIM)
  lcd.drawText(280, y, tostring(#STATE.flights), C_TEXT)
  y = y + 30
end

local function init()
  STATE.flights = loadLog()
  STATE.today = getToday()
  STATE.screen = "main"
end

local function run(event, touchState)
  if STATE.screen == "main" then
    drawMain()
  elseif STATE.screen == "log" then
    drawLog()
  elseif STATE.screen == "stats" then
    drawStats()
  end

  if touchState and touchState.event == EVT_TOUCH_TAP then
    local tx, ty = touchState.x, touchState.y
    if STATE.screen == "main" then
      if STATE.current == nil and inBox(tx, ty, 20, 100, 200, 50) then
        local mname = model.getInfo().name or "Unknown"
        local v = getValue("VFAS") or 0
        STATE.current = {
          startTime = getTime(), startSec = getSeconds(),
          model = mname, vStart = v > 0 and v or 0,
          maxAlt = 0, maxSpd = 0, maxDist = 0
        }
      elseif STATE.current and inBox(tx, ty, 20, 145, 200, 45) then
        local elapsed = math.floor(getSeconds() - STATE.current.startSec)
        local vEnd = getValue("VFAS") or 0
        local fl = {
          date = getToday(), start = STATE.current.startTime,
          duration = elapsed, model = STATE.current.model,
          vStart = STATE.current.vStart, vEnd = vEnd > 0 and vEnd or 0,
          maxAlt = STATE.current.maxAlt, maxSpd = STATE.current.maxSpd,
          maxDist = STATE.current.maxDist
        }
        STATE.flights[#STATE.flights + 1] = fl
        saveLog(STATE.flights)
        STATE.current = nil
      elseif inBox(tx, ty, 20, 210, 200, 50) then
        STATE.screen = "log"; STATE.scroll = 0
      elseif inBox(tx, ty, 260, 210, 200, 50) then
        STATE.screen = "stats"
      end
    elseif STATE.screen == "log" then
      if inBox(tx, ty, 380, 5, 90, 30) then
        STATE.screen = "main"
      end
      local tfl = todayFlights(STATE.flights)
      if ty > 270 and STATE.scroll + 5 < #tfl then
        STATE.scroll = STATE.scroll + 1
      elseif ty < 45 and STATE.scroll > 0 then
        STATE.scroll = STATE.scroll - 1
      end
    elseif STATE.screen == "stats" then
      if inBox(tx, ty, 380, 5, 90, 30) then
        STATE.screen = "main"
      end
    end
  end

  return 0
end

return { init=init, run=run }
