-- TNS|TAK OSD|TNE
-- TAK/ATAK-inspired tactical OSD for RadioMaster AX12
-- Military HUD overlay with GPS, compass, link stats, channels

local M = {}

-- Color definitions (TAK military palette)
local CLR_GREEN    = lcd.RGB(0x00, 0xFF, 0x00)
local CLR_DKGREEN  = lcd.RGB(0x00, 0x88, 0x00)
local CLR_AMBER    = lcd.RGB(0xFF, 0xAA, 0x00)
local CLR_RED      = lcd.RGB(0xFF, 0x00, 0x00)
local CLR_BG       = lcd.RGB(0x0A, 0x0A, 0x0A)
local CLR_GRAY     = lcd.RGB(0x44, 0x44, 0x44)

-- Screen dimensions
local W = 720
local H = 1280

-- State
local startTime = 0
local missionElapsed = 0

-- MGRS conversion (simplified)
local function toMGRS(lat, lon)
  if lat == 0 and lon == 0 then return "NO FIX" end
  local zone = math.floor((lon + 180) / 6) + 1
  local band = "S"
  if lat >= 0 then band = "N" end
  local easting = math.floor(((lon - (zone * 6 - 183)) + 3) * 111320 / 100) % 100000
  local northing = math.floor((lat * 110540) % 100000)
  return string.format("%02d%s %05d %05d", zone, band, easting, northing)
end

-- Format coordinates as military style
local function fmtCoord(lat, lon)
  if lat == 0 and lon == 0 then return "NO GPS FIX" end
  local latDir = lat >= 0 and "N" or "S"
  local lonDir = lon >= 0 and "E" or "W"
  lat = math.abs(lat)
  lon = math.abs(lon)
  local latD = math.floor(lat)
  local latM = (lat - latD) * 60
  local lonD = math.floor(lon)
  local lonM = (lon - lonD) * 60
  return string.format("%s%02d*%06.3f %s%03d*%06.3f", latDir, latD, latM, lonDir, lonD, lonM)
end

-- Draw a horizontal bar gauge
local function drawBar(x, y, w, h, val, maxVal, color, label)
  local pct = math.min(1.0, math.max(0, val / maxVal))
  lcd.drawRectangle(x, y, w, h, CLR_DKGREEN)
  local fillW = math.floor((w - 2) * pct)
  if fillW > 0 then
    lcd.drawFilledRectangle(x + 1, y + 1, fillW, h - 2, color)
  end
  if label then
    lcd.drawText(x + 2, y + 1, label, SMLSIZE + CLR_GREEN)
  end
end

-- Draw compass rose
local function drawCompass(cx, cy, radius, heading)
  lcd.drawCircle(cx, cy, radius, CLR_DKGREEN)
  lcd.drawCircle(cx, cy, radius - 1, CLR_DKGREEN)

  local cardinals = {
    {0, "N"}, {90, "E"}, {180, "S"}, {270, "W"}
  }
  for _, c in ipairs(cardinals) do
    local ang = math.rad(c[1] - heading)
    local tx = cx + math.sin(ang) * (radius - 15)
    local ty = cy - math.cos(ang) * (radius - 15)
    local clr = c[2] == "N" and CLR_RED or CLR_GREEN
    lcd.drawText(tx - 4, ty - 5, c[2], MIDSIZE + clr)
  end

  -- Tick marks every 30 degrees
  for i = 0, 350, 30 do
    local ang = math.rad(i - heading)
    local x1 = cx + math.sin(ang) * (radius - 3)
    local y1 = cy - math.cos(ang) * (radius - 3)
    local x2 = cx + math.sin(ang) * (radius - 8)
    local y2 = cy - math.cos(ang) * (radius - 8)
    lcd.drawLine(x1, y1, x2, y2, SOLID, CLR_GREEN)
  end

  -- Heading indicator triangle at top
  lcd.drawLine(cx, cy - radius - 8, cx - 5, cy - radius - 2, SOLID, CLR_AMBER)
  lcd.drawLine(cx, cy - radius - 8, cx + 5, cy - radius - 2, SOLID, CLR_AMBER)
  lcd.drawLine(cx - 5, cy - radius - 2, cx + 5, cy - radius - 2, SOLID, CLR_AMBER)

  -- Center crosshair
  lcd.drawLine(cx - 5, cy, cx + 5, cy, SOLID, CLR_DKGREEN)
  lcd.drawLine(cx, cy - 5, cx, cy + 5, SOLID, CLR_DKGREEN)

  -- Heading readout
  lcd.drawText(cx - 18, cy + radius + 5, string.format("HDG %03d", heading), MIDSIZE + CLR_GREEN)
end

-- Draw top info bar
local function drawTopBar()
  lcd.drawFilledRectangle(0, 0, W, 52, CLR_BG)
  lcd.drawLine(0, 52, W, 52, SOLID, CLR_DKGREEN)

  -- GPS coordinates
  local lat = getValue("gps-lat") or 0
  local lon = getValue("gps-lon") or 0
  if lat == 0 and lon == 0 then
    lat = 35.147
    lon = -79.476
  end

  local coordStr = fmtCoord(lat, lon)
  lcd.drawText(5, 3, coordStr, SMLSIZE + CLR_GREEN)

  -- MGRS grid
  local mgrs = toMGRS(lat, lon)
  lcd.drawText(5, 18, "MGRS: " .. mgrs, SMLSIZE + CLR_DKGREEN)

  -- UTC time
  local dt = getRtcTime and getRtcTime() or nil
  local timeStr
  if dt then
    timeStr = string.format("%02d:%02d:%02dZ", dt.hour or 0, dt.min or 0, dt.sec or 0)
  else
    local secs = math.floor(getTime() / 100)
    timeStr = string.format("T+%05d", secs)
  end
  lcd.drawText(W - 90, 3, timeStr, SMLSIZE + CLR_GREEN)

  -- Classification banner
  lcd.drawText(W - 90, 18, "UNCLASS", SMLSIZE + CLR_DKGREEN)

  -- TAK marker
  lcd.drawText(5, 36, "TAK", SMLSIZE + CLR_AMBER)
  lcd.drawText(30, 36, "OSD v1.0", SMLSIZE + CLR_DKGREEN)
end

-- Draw right side panel
local function drawRightPanel()
  local px = W - 130
  local py = 70

  lcd.drawFilledRectangle(px - 5, py - 5, 135, 200, CLR_BG)
  lcd.drawRectangle(px - 5, py - 5, 135, 200, CLR_DKGREEN)

  -- RSSI
  local rssi = getRSSI and getRSSI() or 0
  local rssiClr = CLR_GREEN
  if rssi > 0 and rssi < 50 then rssiClr = CLR_RED
  elseif rssi > 0 and rssi < 70 then rssiClr = CLR_AMBER end
  lcd.drawText(px, py, "RSSI", SMLSIZE + CLR_DKGREEN)
  lcd.drawText(px + 50, py, string.format("%ddBm", -rssi), SMLSIZE + rssiClr)
  drawBar(px, py + 14, 120, 10, 100 - rssi, 100, rssiClr, nil)

  -- Link Quality
  py = py + 32
  local lq = getValue("RQly") or 0
  local lqClr = CLR_GREEN
  if lq < 50 then lqClr = CLR_RED
  elseif lq < 80 then lqClr = CLR_AMBER end
  lcd.drawText(px, py, "LQ", SMLSIZE + CLR_DKGREEN)
  lcd.drawText(px + 50, py, string.format("%d%%", lq), SMLSIZE + lqClr)
  drawBar(px, py + 14, 120, 10, lq, 100, lqClr, nil)

  -- TX Battery
  py = py + 32
  local txV = getValue("tx-voltage") or 0
  local battPct = math.floor(((txV - 6.0) / (8.4 - 6.0)) * 100)
  battPct = math.max(0, math.min(100, battPct))
  local battClr = CLR_GREEN
  if battPct < 20 then battClr = CLR_RED
  elseif battPct < 40 then battClr = CLR_AMBER end
  lcd.drawText(px, py, "BATT", SMLSIZE + CLR_DKGREEN)
  lcd.drawText(px + 50, py, string.format("%.1fV", txV), SMLSIZE + battClr)
  drawBar(px, py + 14, 120, 10, battPct, 100, battClr, nil)

  -- Flight Mode
  py = py + 32
  local fm = getValue("Flgt") or getValue("FM") or "---"
  if type(fm) == "number" then fm = tostring(fm) end
  lcd.drawText(px, py, "MODE", SMLSIZE + CLR_DKGREEN)
  lcd.drawText(px + 50, py, fm, SMLSIZE + CLR_GREEN)

  -- RF Mode
  py = py + 20
  local rfpwr = getValue("RFMD") or 0
  lcd.drawText(px, py, "RFMD", SMLSIZE + CLR_DKGREEN)
  lcd.drawText(px + 50, py, tostring(rfpwr), SMLSIZE + CLR_GREEN)
end

-- Draw bottom bar
local function drawBottomBar()
  local by = H - 80
  lcd.drawFilledRectangle(0, by, W, 80, CLR_BG)
  lcd.drawLine(0, by, W, by, SOLID, CLR_DKGREEN)

  -- Stick channels as mini bars
  local chNames = {"AIL", "ELE", "THR", "RUD"}
  local chSrcs = {"ail", "ele", "thr", "rud"}
  local barW = 80
  local barH = 12
  local startX = 10

  for i, name in ipairs(chNames) do
    local val = getValue(chSrcs[i]) or 0
    local pct = (val + 1024) / 2048 * 100
    local x = startX + (i - 1) * (barW + 15)
    local y = by + 8
    lcd.drawText(x, y, name, SMLSIZE + CLR_DKGREEN)
    drawBar(x, y + 14, barW, barH, pct, 100, CLR_GREEN, nil)
    lcd.drawText(x + barW - 30, y, string.format("%4d", val), SMLSIZE + CLR_GREEN)
  end

  -- Armed status
  local armed = getValue("armed") or 0
  local armStr = "DISARMED"
  local armClr = CLR_GREEN
  if armed ~= 0 then
    armStr = "ARMED"
    armClr = CLR_RED
  end
  lcd.drawText(startX, by + 45, armStr, MIDSIZE + armClr)

  -- Mission Elapsed Timer
  local now = getTime()
  missionElapsed = now - startTime
  local secs = math.floor(missionElapsed / 100)
  local mins = math.floor(secs / 60)
  local hrs = math.floor(mins / 60)
  secs = secs % 60
  mins = mins % 60
  local timerStr = string.format("MET %02d:%02d:%02d", hrs, mins, secs)
  lcd.drawText(W - 160, by + 45, timerStr, MIDSIZE + CLR_GREEN)
end

-- Draw decorative grid lines (TAK-style)
local function drawGrid()
  for y = 60, H - 90, 40 do
    lcd.drawLine(0, y, W, y, DOTTED, CLR_GRAY)
  end
  -- Corner brackets (HUD style)
  local m = 15
  local l = 30
  lcd.drawLine(m, 55, m + l, 55, SOLID, CLR_DKGREEN)
  lcd.drawLine(m, 55, m, 55 + l, SOLID, CLR_DKGREEN)
  lcd.drawLine(W - m - l, 55, W - m, 55, SOLID, CLR_DKGREEN)
  lcd.drawLine(W - m, 55, W - m, 55 + l, SOLID, CLR_DKGREEN)
  lcd.drawLine(m, H - 85 - l, m, H - 85, SOLID, CLR_DKGREEN)
  lcd.drawLine(m, H - 85, m + l, H - 85, SOLID, CLR_DKGREEN)
  lcd.drawLine(W - m, H - 85 - l, W - m, H - 85, SOLID, CLR_DKGREEN)
  lcd.drawLine(W - m - l, H - 85, W - m, H - 85, SOLID, CLR_DKGREEN)
end

-- INIT
function M.init()
  startTime = getTime()
end

-- RUN (called each frame)
function M.run(event, touchState)
  lcd.clear(CLR_BG)

  drawGrid()
  drawTopBar()

  -- Compass in center area
  local heading = getValue("Hdg") or getValue("Yaw") or 0
  if heading < 0 then heading = heading + 360 end
  drawCompass(W / 2 - 60, H / 2 - 40, 90, heading)

  drawRightPanel()
  drawBottomBar()

  -- Touch to exit (double tap top-left corner)
  if event == EVT_TOUCH_TAP then
    if touchState and touchState.x < 60 and touchState.y < 60 then
      return 1
    end
  end

  return 0
end

return M
