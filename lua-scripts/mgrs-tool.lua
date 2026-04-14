-- TNS|MGRS Tool|TNE
-- Military Grid Reference System coordinate tool
-- Converts GPS lat/lon to MGRS, DD, DMS formats
-- Distance/bearing to saved waypoint, touch to save

local M = {}

-- Color definitions (TAK military palette)
local CLR_GREEN    = nil
local CLR_DKGREEN  = nil
local CLR_AMBER    = nil
local CLR_RED      = nil
local CLR_BG       = nil
local CLR_GRAY     = nil
local CLR_WHITE    = nil
local CLR_CYAN     = nil

-- Screen dimensions
local W = 720
local H = 1280

-- State
local savedLat = 0
local savedLon = 0
local savedAlt = 0
local hasSaved = false
local displayMode = 1  -- 1=MGRS, 2=DD, 3=DMS
local NUM_MODES = 3
local statusMsg = ""
local statusTimer = 0

-- WGS84 constants
local a = 6378137.0
local f = 1 / 298.257223563
local e2 = 2 * f - f * f
local e = math.sqrt(e2)
local e_prime2 = e2 / (1 - e2)
local k0 = 0.9996

-- UTM band letters
local BAND_LETTERS = "CDEFGHJKLMNPQRSTUVWX"

---------------------------------------------------------------------------
-- UTM / MGRS Conversion
---------------------------------------------------------------------------

local function getUTMZone(lon)
  return math.floor((lon + 180) / 6) + 1
end

local function getBandLetter(lat)
  if lat < -80 or lat > 84 then return "Z" end
  local idx = math.floor((lat + 80) / 8) + 1
  idx = math.max(1, math.min(#BAND_LETTERS, idx))
  return BAND_LETTERS:sub(idx, idx)
end

-- Transverse Mercator projection (lat/lon -> UTM easting/northing)
local function latLonToUTM(lat, lon)
  local zone = getUTMZone(lon)
  local band = getBandLetter(lat)

  local latRad = math.rad(lat)
  local lonRad = math.rad(lon)

  local lonOrigin = (zone - 1) * 6 - 180 + 3
  local lonOriginRad = math.rad(lonOrigin)
  local dLon = lonRad - lonOriginRad

  local sinLat = math.sin(latRad)
  local cosLat = math.cos(latRad)
  local tanLat = math.tan(latRad)

  local N = a / math.sqrt(1 - e2 * sinLat * sinLat)
  local T = tanLat * tanLat
  local C_coeff = e_prime2 * cosLat * cosLat
  local A = dLon * cosLat

  -- Meridional arc
  local M_arc = a * (
    (1 - e2/4 - 3*e2*e2/64 - 5*e2*e2*e2/256) * latRad
    - (3*e2/8 + 3*e2*e2/32 + 45*e2*e2*e2/1024) * math.sin(2*latRad)
    + (15*e2*e2/256 + 45*e2*e2*e2/1024) * math.sin(4*latRad)
    - (35*e2*e2*e2/3072) * math.sin(6*latRad)
  )

  local easting = k0 * N * (
    A + (1-T+C_coeff) * A*A*A / 6
    + (5 - 18*T + T*T + 72*C_coeff - 58*e_prime2) * A*A*A*A*A / 120
  ) + 500000.0

  local northing = k0 * (
    M_arc + N * tanLat * (
      A*A / 2
      + (5 - T + 9*C_coeff + 4*C_coeff*C_coeff) * A*A*A*A / 24
      + (61 - 58*T + T*T + 600*C_coeff - 330*e_prime2) * A*A*A*A*A*A / 720
    )
  )

  if lat < 0 then
    northing = northing + 10000000.0
  end

  return zone, band, easting, northing
end

-- 100km grid square letters for MGRS
local function get100kLetters(zone, easting, northing)
  local setNum = ((zone - 1) % 6)

  -- Column letter (easting)
  local colLetters = {
    "ABCDEFGH",
    "JKLMNPQR",
    "STUVWXYZ",
    "ABCDEFGH",
    "JKLMNPQR",
    "STUVWXYZ"
  }
  local colSet = colLetters[setNum + 1]
  local e100k = math.floor(easting / 100000)
  local colIdx = ((e100k - 1) % 8) + 1
  colIdx = math.max(1, math.min(#colSet, colIdx))
  local colLetter = colSet:sub(colIdx, colIdx)

  -- Row letter (northing)
  local rowLettersEven = "FGHJKLMNPQRSTUVABCDE"
  local rowLettersOdd  = "ABCDEFGHJKLMNPQRSTUV"
  local rowSet = (setNum % 2 == 0) and rowLettersOdd or rowLettersEven
  local n100k = math.floor(northing % 2000000 / 100000)
  local rowIdx = (n100k % 20) + 1
  rowIdx = math.max(1, math.min(#rowSet, rowIdx))
  local rowLetter = rowSet:sub(rowIdx, rowIdx)

  return colLetter .. rowLetter
end

local function toMGRS(lat, lon)
  if lat == 0 and lon == 0 then return "NO FIX", "", "", 0, 0 end
  local zone, band, easting, northing = latLonToUTM(lat, lon)
  local sq = get100kLetters(zone, easting, northing)
  local e5 = math.floor(easting % 100000)
  local n5 = math.floor(northing % 100000)
  local mgrs = string.format("%02d%s %s %05d %05d", zone, band, sq, e5, n5)
  return mgrs, zone, band, easting, northing
end

---------------------------------------------------------------------------
-- Coordinate Format Converters
---------------------------------------------------------------------------

local function toDD(lat, lon)
  if lat == 0 and lon == 0 then return "NO GPS FIX" end
  local latDir = lat >= 0 and "N" or "S"
  local lonDir = lon >= 0 and "E" or "W"
  return string.format("%s %.6f  %s %.6f", latDir, math.abs(lat), lonDir, math.abs(lon))
end

local function toDMS(lat, lon)
  if lat == 0 and lon == 0 then return "NO GPS FIX" end
  local function convert(deg)
    local d = math.floor(math.abs(deg))
    local mf = (math.abs(deg) - d) * 60
    local m = math.floor(mf)
    local s = (mf - m) * 60
    return d, m, s
  end
  local latD, latM, latS = convert(lat)
  local lonD, lonM, lonS = convert(lon)
  local latDir = lat >= 0 and "N" or "S"
  local lonDir = lon >= 0 and "E" or "W"
  return string.format("%s %02d %02d %05.2f  %s %03d %02d %05.2f",
    latDir, latD, latM, latS, lonDir, lonD, lonM, lonS)
end

---------------------------------------------------------------------------
-- Distance & Bearing
---------------------------------------------------------------------------

local function haversine(lat1, lon1, lat2, lon2)
  local R = 6371000
  local dLat = math.rad(lat2 - lat1)
  local dLon = math.rad(lon2 - lon1)
  local a_h = math.sin(dLat/2)^2 + math.cos(math.rad(lat1)) * math.cos(math.rad(lat2)) * math.sin(dLon/2)^2
  local c = 2 * math.atan2(math.sqrt(a_h), math.sqrt(1 - a_h))
  return R * c
end

local function bearing(lat1, lon1, lat2, lon2)
  local dLon = math.rad(lon2 - lon1)
  local y = math.sin(dLon) * math.cos(math.rad(lat2))
  local x = math.cos(math.rad(lat1)) * math.sin(math.rad(lat2)) -
            math.sin(math.rad(lat1)) * math.cos(math.rad(lat2)) * math.cos(dLon)
  local brg = math.deg(math.atan2(y, x))
  return (brg + 360) % 360
end

---------------------------------------------------------------------------
-- Drawing Helpers
---------------------------------------------------------------------------

local function drawSeparator(y)
  lcd.drawLine(15, y, W - 15, y, SOLID, CLR_DKGREEN)
end

local function drawField(x, y, label, value, valClr)
  lcd.drawText(x, y, label, SMLSIZE + CLR_DKGREEN)
  lcd.drawText(x + 120, y, value, SMLSIZE + (valClr or CLR_GREEN))
end

local function drawCornerBrackets(x1, y1, x2, y2, len)
  lcd.drawLine(x1, y1, x1 + len, y1, SOLID, CLR_DKGREEN)
  lcd.drawLine(x1, y1, x1, y1 + len, SOLID, CLR_DKGREEN)
  lcd.drawLine(x2 - len, y1, x2, y1, SOLID, CLR_DKGREEN)
  lcd.drawLine(x2, y1, x2, y1 + len, SOLID, CLR_DKGREEN)
  lcd.drawLine(x1, y2 - len, x1, y2, SOLID, CLR_DKGREEN)
  lcd.drawLine(x1, y2, x1 + len, y2, SOLID, CLR_DKGREEN)
  lcd.drawLine(x2, y2 - len, x2, y2, SOLID, CLR_DKGREEN)
  lcd.drawLine(x2 - len, y2, x2, y2, SOLID, CLR_DKGREEN)
end

---------------------------------------------------------------------------
-- Main Draw Functions
---------------------------------------------------------------------------

local function drawHeader()
  lcd.drawFilledRectangle(0, 0, W, 50, CLR_BG)
  lcd.drawText(10, 5, "MGRS COORDINATE TOOL", MIDSIZE + CLR_GREEN)
  lcd.drawText(W - 100, 5, "UNCLASS", SMLSIZE + CLR_DKGREEN)

  local dt = getRtcTime and getRtcTime() or nil
  local timeStr
  if dt then
    timeStr = string.format("%02d:%02d:%02dZ", dt.hour or 0, dt.min or 0, dt.sec or 0)
  else
    local secs = math.floor(getTime() / 100)
    timeStr = string.format("T+%05d", secs)
  end
  lcd.drawText(W - 100, 28, timeStr, SMLSIZE + CLR_GREEN)

  drawSeparator(50)
end

local function drawCoordinates(lat, lon, alt)
  local y = 65

  -- Mode selector tabs
  local modes = {"MGRS", "DD", "DMS"}
  local tabW = 100
  for i, name in ipairs(modes) do
    local tx = 15 + (i - 1) * (tabW + 10)
    if i == displayMode then
      lcd.drawFilledRectangle(tx, y, tabW, 28, CLR_DKGREEN)
      lcd.drawText(tx + 10, y + 5, name, SMLSIZE + CLR_BG)
    else
      lcd.drawRectangle(tx, y, tabW, 28, CLR_DKGREEN)
      lcd.drawText(tx + 10, y + 5, name, SMLSIZE + CLR_DKGREEN)
    end
  end

  y = y + 45

  -- Primary coordinate display
  lcd.drawFilledRectangle(10, y, W - 20, 55, lcd.RGB(0x05, 0x15, 0x05))
  drawCornerBrackets(10, y, W - 10, y + 55, 12)

  if displayMode == 1 then
    local mgrs = toMGRS(lat, lon)
    lcd.drawText(25, y + 8, mgrs, DBLSIZE + CLR_GREEN)
  elseif displayMode == 2 then
    local dd = toDD(lat, lon)
    lcd.drawText(25, y + 15, dd, MIDSIZE + CLR_GREEN)
  elseif displayMode == 3 then
    local dms = toDMS(lat, lon)
    lcd.drawText(25, y + 15, dms, MIDSIZE + CLR_GREEN)
  end

  y = y + 70
  drawSeparator(y)
  y = y + 10

  local zone, band, easting, northing
  if lat ~= 0 or lon ~= 0 then
    zone, band, easting, northing = latLonToUTM(lat, lon)
  end

  drawField(15, y, "LAT:", string.format("%.6f", lat), CLR_GREEN)
  y = y + 22
  drawField(15, y, "LON:", string.format("%.6f", lon), CLR_GREEN)
  y = y + 22
  drawField(15, y, "ALT:", string.format("%.1f m  (%.0f ft)", alt, alt * 3.28084), CLR_GREEN)
  y = y + 22

  if zone then
    drawField(15, y, "UTM ZONE:", string.format("%02d%s", zone, band), CLR_AMBER)
    y = y + 22
    drawField(15, y, "EASTING:", string.format("%.1f m", easting), CLR_GREEN)
    y = y + 22
    drawField(15, y, "NORTHING:", string.format("%.1f m", northing), CLR_GREEN)
    y = y + 22
  end

  local sats = getValue("Sats") or getValue("Tmp2") or 0
  local satClr = CLR_GREEN
  if sats < 6 then satClr = CLR_RED
  elseif sats < 10 then satClr = CLR_AMBER end
  drawField(15, y, "SATS:", tostring(math.floor(sats)), satClr)

  return y + 30
end

local function drawWaypoint(y, lat, lon)
  drawSeparator(y)
  y = y + 10

  lcd.drawText(15, y, "WAYPOINT", MIDSIZE + CLR_AMBER)

  -- Save button
  local btnX = W - 200
  local btnW = 180
  local btnH = 36
  lcd.drawFilledRectangle(btnX, y - 2, btnW, btnH, CLR_DKGREEN)
  lcd.drawText(btnX + 15, y + 6, "SAVE POSITION", SMLSIZE + CLR_BG)

  y = y + 45

  if hasSaved then
    local wptMgrs = toMGRS(savedLat, savedLon)
    lcd.drawText(15, y, "WPT: " .. wptMgrs, SMLSIZE + CLR_AMBER)
    y = y + 22
    lcd.drawText(15, y, string.format("WPT ALT: %.0f m", savedAlt), SMLSIZE + CLR_AMBER)
    y = y + 28

    if (lat ~= 0 or lon ~= 0) and (savedLat ~= 0 or savedLon ~= 0) then
      local dist = haversine(lat, lon, savedLat, savedLon)
      local brg = bearing(lat, lon, savedLat, savedLon)

      local distStr
      if dist > 1000 then
        distStr = string.format("%.2f km", dist / 1000)
      else
        distStr = string.format("%.0f m", dist)
      end

      lcd.drawFilledRectangle(10, y, W - 20, 60, lcd.RGB(0x10, 0x10, 0x00))
      drawCornerBrackets(10, y, W - 10, y + 60, 10)
      lcd.drawText(25, y + 5, "DIST: " .. distStr, MIDSIZE + CLR_AMBER)
      lcd.drawText(25, y + 30, string.format("BRG:  %03.0f MAG", brg), MIDSIZE + CLR_AMBER)
      y = y + 70

      -- Bearing arrow
      local cx = W / 2
      local cy = y + 50
      local r = 35
      lcd.drawCircle(cx, cy, r, CLR_DKGREEN)
      local rad = math.rad(brg)
      local ax = cx + math.sin(rad) * r
      local ay = cy - math.cos(rad) * r
      lcd.drawLine(cx, cy, math.floor(ax), math.floor(ay), SOLID, CLR_AMBER)
      lcd.drawText(cx - 5, cy - r - 18, "N", SMLSIZE + CLR_RED)
      y = cy + r + 20
    end
  else
    lcd.drawText(15, y, "No waypoint saved", SMLSIZE + CLR_GRAY)
    lcd.drawText(15, y + 18, "Touch SAVE POSITION to mark", SMLSIZE + CLR_GRAY)
    y = y + 50
  end

  return y
end

local function drawStatusBar()
  local by = H - 45
  lcd.drawFilledRectangle(0, by, W, 45, CLR_BG)
  lcd.drawLine(0, by, W, by, SOLID, CLR_DKGREEN)

  if statusTimer > 0 and statusMsg ~= "" then
    lcd.drawText(15, by + 12, statusMsg, SMLSIZE + CLR_AMBER)
    statusTimer = statusTimer - 1
  else
    lcd.drawText(15, by + 12, "TAP tabs to switch | TAP save to mark waypoint", SMLSIZE + CLR_GRAY)
  end

  lcd.drawText(W - 120, by + 12, "2xTAP EXIT", SMLSIZE + CLR_DKGREEN)
end

---------------------------------------------------------------------------
-- INIT
---------------------------------------------------------------------------

function M.init()
  CLR_GREEN   = lcd.RGB(0x00, 0xFF, 0x00)
  CLR_DKGREEN = lcd.RGB(0x00, 0x88, 0x00)
  CLR_AMBER   = lcd.RGB(0xFF, 0xAA, 0x00)
  CLR_RED     = lcd.RGB(0xFF, 0x00, 0x00)
  CLR_BG      = lcd.RGB(0x0A, 0x0A, 0x0A)
  CLR_GRAY    = lcd.RGB(0x44, 0x44, 0x44)
  CLR_WHITE   = lcd.RGB(0xFF, 0xFF, 0xFF)
  CLR_CYAN    = lcd.RGB(0x00, 0xCC, 0xCC)
end

---------------------------------------------------------------------------
-- RUN
---------------------------------------------------------------------------

function M.run(event, touchState)
  lcd.clear(CLR_BG)

  -- Get GPS data
  local lat = getValue("gps-lat") or 0
  local lon = getValue("gps-lon") or 0
  local alt = getValue("Alt") or getValue("GAlt") or 0

  -- Handle touch events
  if event == EVT_TOUCH_TAP and touchState then
    local tx, ty = touchState.x, touchState.y

    -- Mode tab switching (y 65-93)
    if ty >= 65 and ty <= 93 then
      for i = 1, NUM_MODES do
        local tabX = 15 + (i - 1) * 110
        if tx >= tabX and tx <= tabX + 100 then
          displayMode = i
          local names = {"MGRS", "DD", "DMS"}
          statusMsg = "Mode: " .. names[i]
          statusTimer = 30
        end
      end
    end

    -- Save button (top-right area of waypoint section)
    if tx >= (W - 200) and tx <= W and ty >= 360 and ty <= 410 then
      if lat ~= 0 or lon ~= 0 then
        savedLat = lat
        savedLon = lon
        savedAlt = alt
        hasSaved = true
        statusMsg = "WAYPOINT SAVED"
        statusTimer = 50
      else
        statusMsg = "NO GPS FIX - CANNOT SAVE"
        statusTimer = 50
      end
    end

    -- Double-tap top-left to exit
    if tx < 60 and ty < 60 then
      return 1
    end
  end

  -- Draw all sections
  drawHeader()
  local nextY = drawCoordinates(lat, lon, alt)
  drawWaypoint(nextY, lat, lon)
  drawStatusBar()

  -- HUD corner brackets for overall frame
  drawCornerBrackets(5, 55, W - 5, H - 50, 25)

  return 0
end

return M
