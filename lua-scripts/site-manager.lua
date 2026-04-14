-- TNS|Site Manager|TNE
-- Flying site database for AX12
-- Persist sites to JSON, show distance/bearing, military green styling

local SITES_FILE = "/storage/emulated/0/AX12LUA/sites.json"

-- Colors (military green palette)
local C_BG       = lcd.RGB(20, 30, 20)
local C_HEADER   = lcd.RGB(40, 60, 35)
local C_GREEN    = lcd.RGB(80, 180, 60)
local C_DKGREEN  = lcd.RGB(50, 120, 40)
local C_TEXT     = lcd.RGB(200, 220, 190)
local C_DIM      = lcd.RGB(120, 140, 110)
local C_ACCENT   = lcd.RGB(160, 200, 80)
local C_RED      = lcd.RGB(200, 60, 60)
local C_WHITE    = lcd.RGB(240, 240, 230)
local C_BLACK    = lcd.RGB(0, 0, 0)

-- Screen dimensions
local W = LCD_W or 480
local H = LCD_H or 320

-- State
local sites = {}
local selectedIdx = 0
local scrollOffset = 0
local screen = "list"  -- list, detail, confirm_delete
local myLat = 0
local myLon = 0
local hasGPS = false

-- ============ PERSISTENCE ============

local function loadSites()
  local f = io.open(SITES_FILE, "r")
  if not f then return end
  local content = f:read("*a")
  f:close()
  if not content or content == "" then return end
  -- Simple JSON array parser for our format
  sites = {}
  for name, lat, lon, notes in content:gmatch('"name":"([^"]*)"[^}]-"lat":([%d%.%-]+)[^}]-"lon":([%d%.%-]+)[^}]-"notes":"([^"]*)"') do
    sites[#sites + 1] = {
      name = name,
      lat = tonumber(lat),
      lon = tonumber(lon),
      notes = notes:gsub("\\n", "\n")
    }
  end
end

local function saveSites()
  local f = io.open(SITES_FILE, "w")
  if not f then return end
  f:write("[\n")
  for i, s in ipairs(sites) do
    local notes_escaped = (s.notes or ""):gsub("\n", "\\n"):gsub('"', '\\"')
    f:write(string.format('  {"name":"%s","lat":%.7f,"lon":%.7f,"notes":"%s"}',
      s.name, s.lat, s.lon, notes_escaped))
    if i < #sites then f:write(",") end
    f:write("\n")
  end
  f:write("]\n")
  f:close()
end

-- ============ GPS / TELEMETRY ============

local function updateGPS()
  -- Try to get GPS from telemetry
  local gpsSource = getFieldInfo("GPS")
  if gpsSource then
    local gpsVal = getValue("GPS")
    if type(gpsVal) == "table" then
      if gpsVal.lat and gpsVal.lon and gpsVal.lat ~= 0 then
        myLat = gpsVal.lat
        myLon = gpsVal.lon
        hasGPS = true
        return
      end
    end
  end
  -- Fallback: try individual lat/lon fields
  local latField = getFieldInfo("Tmp1") -- Some setups use temp fields
  if not latField then
    -- Hardcoded fallback: Ft Bragg / default area
    myLat = 35.1390
    myLon = -79.0064
    hasGPS = false
  end
end

-- ============ MATH UTILS ============

local function toRad(d) return d * math.pi / 180 end
local function toDeg(r) return r * 180 / math.pi end

local function haversine(lat1, lon1, lat2, lon2)
  local dLat = toRad(lat2 - lat1)
  local dLon = toRad(lon2 - lon1)
  local a = math.sin(dLat/2)^2 + math.cos(toRad(lat1)) * math.cos(toRad(lat2)) * math.sin(dLon/2)^2
  local c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
  return 6371000 * c  -- meters
end

local function bearing(lat1, lon1, lat2, lon2)
  local dLon = toRad(lon2 - lon1)
  local y = math.sin(dLon) * math.cos(toRad(lat2))
  local x = math.cos(toRad(lat1)) * math.sin(toRad(lat2)) - math.sin(toRad(lat1)) * math.cos(toRad(lat2)) * math.cos(dLon)
  local brng = toDeg(math.atan2(y, x))
  return (brng + 360) % 360
end

local function bearingToCompass(b)
  local dirs = {"N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"}
  local idx = math.floor((b + 11.25) / 22.5) % 16
  return dirs[idx + 1]
end

local function formatDist(m)
  if m < 1000 then
    return string.format("%dm", m)
  elseif m < 10000 then
    return string.format("%.1fkm", m/1000)
  else
    return string.format("%.0fkm", m/1000)
  end
end

-- ============ NEAREST SITE ============

local function findNearest()
  if #sites == 0 then return nil, 0, 0 end
  local minDist = math.huge
  local nearest = nil
  local nearBearing = 0
  for _, s in ipairs(sites) do
    local d = haversine(myLat, myLon, s.lat, s.lon)
    if d < minDist then
      minDist = d
      nearest = s
      nearBearing = bearing(myLat, myLon, s.lat, s.lon)
    end
  end
  return nearest, minDist, nearBearing
end

-- ============ DRAWING ============

local function drawHeader(title)
  lcd.drawFilledRectangle(0, 0, W, 28, C_HEADER)
  lcd.drawText(W/2, 4, title, MIDSIZE + CENTER + C_WHITE)
  lcd.drawLine(0, 28, W, 28, SOLID, C_GREEN)
end

local function drawButton(x, y, w, h, label, color)
  lcd.drawFilledRectangle(x, y, w, h, color or C_DKGREEN)
  lcd.drawRectangle(x, y, w, h, C_GREEN)
  lcd.drawText(x + w/2, y + (h-12)/2, label, SMLSIZE + CENTER + C_WHITE)
end

local function drawListScreen()
  lcd.drawFilledRectangle(0, 0, W, H, C_BG)
  drawHeader("SITE MANAGER")

  -- GPS status bar
  local gpsText = hasGPS and string.format("GPS: %.4f, %.4f", myLat, myLon) or "GPS: NO FIX (fallback)"
  lcd.drawText(5, 32, gpsText, SMLSIZE + (hasGPS and C_GREEN or C_DIM))

  -- Nearest site banner
  local nearest, nDist, nBrg = findNearest()
  if nearest then
    lcd.drawFilledRectangle(0, 46, W, 20, lcd.RGB(30, 50, 30))
    local nText = string.format("NEAREST: %s  %s %s", nearest.name, formatDist(nDist), bearingToCompass(nBrg))
    lcd.drawText(5, 48, nText, SMLSIZE + C_ACCENT)
  end

  -- Site list
  local listTop = 70
  local rowH = 30
  local maxVisible = math.floor((H - listTop - 40) / rowH)

  if #sites == 0 then
    lcd.drawText(W/2, H/2 - 10, "No sites saved", MIDSIZE + CENTER + C_DIM)
    lcd.drawText(W/2, H/2 + 14, "Tap [+] to save current position", SMLSIZE + CENTER + C_DIM)
  else
    for i = 1, math.min(#sites, maxVisible) do
      local idx = i + scrollOffset
      if idx > #sites then break end
      local s = sites[idx]
      local y = listTop + (i-1) * rowH
      local dist = haversine(myLat, myLon, s.lat, s.lon)
      local brg = bearing(myLat, myLon, s.lat, s.lon)

      -- Highlight selected
      if idx == selectedIdx then
        lcd.drawFilledRectangle(0, y, W, rowH, lcd.RGB(40, 70, 40))
      end

      lcd.drawText(8, y + 2, s.name, SMLSIZE + C_WHITE)
      lcd.drawText(8, y + 15, string.format("%.4f, %.4f", s.lat, s.lon), SMLSIZE + C_DIM)
      lcd.drawText(W - 8, y + 2, formatDist(dist), SMLSIZE + RIGHT + C_ACCENT)
      lcd.drawText(W - 8, y + 15, bearingToCompass(brg), SMLSIZE + RIGHT + C_DIM)

      lcd.drawLine(0, y + rowH - 1, W, y + rowH - 1, DOTTED, C_DKGREEN)
    end
  end

  -- Bottom buttons
  local btnY = H - 34
  drawButton(5, btnY, 70, 28, "+ SAVE", C_DKGREEN)
  if selectedIdx > 0 then
    drawButton(80, btnY, 70, 28, "DETAIL", C_DKGREEN)
    drawButton(155, btnY, 70, 28, "DELETE", C_RED)
  end
end

local function drawDetailScreen()
  lcd.drawFilledRectangle(0, 0, W, H, C_BG)
  if selectedIdx < 1 or selectedIdx > #sites then
    screen = "list"
    return
  end
  local s = sites[selectedIdx]
  drawHeader(s.name)

  local y = 38
  lcd.drawText(10, y, "COORDINATES:", SMLSIZE + C_DIM)
  y = y + 16
  lcd.drawText(10, y, string.format("  Lat: %.7f", s.lat), SMLSIZE + C_TEXT)
  y = y + 16
  lcd.drawText(10, y, string.format("  Lon: %.7f", s.lon), SMLSIZE + C_TEXT)
  y = y + 24

  local dist = haversine(myLat, myLon, s.lat, s.lon)
  local brg = bearing(myLat, myLon, s.lat, s.lon)
  lcd.drawText(10, y, "DISTANCE:", SMLSIZE + C_DIM)
  y = y + 16
  lcd.drawText(10, y, string.format("  %s  bearing %03.0f (%s)", formatDist(dist), brg, bearingToCompass(brg)), SMLSIZE + C_ACCENT)
  y = y + 24

  lcd.drawText(10, y, "NOTES:", SMLSIZE + C_DIM)
  y = y + 16
  local notes = s.notes or "(none)"
  for line in notes:gmatch("[^\n]+") do
    lcd.drawText(10, y, "  " .. line, SMLSIZE + C_TEXT)
    y = y + 14
    if y > H - 50 then break end
  end

  -- Back button
  drawButton(5, H - 34, 70, 28, "< BACK", C_DKGREEN)
end

local function drawConfirmDelete()
  lcd.drawFilledRectangle(0, 0, W, H, C_BG)
  drawHeader("CONFIRM DELETE")

  if selectedIdx >= 1 and selectedIdx <= #sites then
    local s = sites[selectedIdx]
    lcd.drawText(W/2, H/2 - 30, "Delete " .. s.name .. "?", MIDSIZE + CENTER + C_WHITE)
    lcd.drawText(W/2, H/2, "This cannot be undone.", SMLSIZE + CENTER + C_DIM)
  end

  drawButton(W/2 - 90, H/2 + 30, 80, 30, "CANCEL", C_DKGREEN)
  drawButton(W/2 + 10, H/2 + 30, 80, 30, "DELETE", C_RED)
end

-- ============ TOUCH HANDLING ============

local function handleTouch(event)
  if event == nil then return end
  local tx = event.x or 0
  local ty = event.y or 0

  if screen == "list" then
    -- Bottom buttons
    local btnY = H - 34
    if ty >= btnY and ty <= btnY + 28 then
      -- SAVE button
      if tx >= 5 and tx <= 75 then
        local newName = "Site " .. (#sites + 1)
        sites[#sites + 1] = {
          name = newName,
          lat = myLat,
          lon = myLon,
          notes = "Saved " .. os.date("%Y-%m-%d %H:%M")
        }
        saveSites()
        selectedIdx = #sites
        return
      end
      -- DETAIL button
      if tx >= 80 and tx <= 150 and selectedIdx > 0 then
        screen = "detail"
        return
      end
      -- DELETE button
      if tx >= 155 and tx <= 225 and selectedIdx > 0 then
        screen = "confirm_delete"
        return
      end
    end

    -- List tap to select
    local listTop = 70
    local rowH = 30
    if ty >= listTop and ty < H - 40 then
      local tapped = math.floor((ty - listTop) / rowH) + 1 + scrollOffset
      if tapped >= 1 and tapped <= #sites then
        if selectedIdx == tapped then
          screen = "detail"
        else
          selectedIdx = tapped
        end
      end
    end

  elseif screen == "detail" then
    -- Back button
    if ty >= H - 34 and ty <= H - 6 and tx >= 5 and tx <= 75 then
      screen = "list"
    end

  elseif screen == "confirm_delete" then
    if ty >= H/2 + 30 and ty <= H/2 + 60 then
      -- Cancel
      if tx >= W/2 - 90 and tx <= W/2 - 10 then
        screen = "list"
      end
      -- Confirm delete
      if tx >= W/2 + 10 and tx <= W/2 + 90 then
        table.remove(sites, selectedIdx)
        saveSites()
        selectedIdx = 0
        screen = "list"
      end
    end
  end
end

-- ============ MAIN ============

local function init()
  loadSites()
end

local function run(event, touchState)
  updateGPS()

  -- Handle touch
  if touchState and touchState.tapCount and touchState.tapCount > 0 then
    handleTouch(touchState)
  end

  -- Draw
  if screen == "list" then
    drawListScreen()
  elseif screen == "detail" then
    drawDetailScreen()
  elseif screen == "confirm_delete" then
    drawConfirmDelete()
  end

  return 0
end

return { init=init, run=run }
