-- TNS|BF OSD|TNE
---- #########################################################################
---- #                                                                       #
---- # BF OSD -- Betaflight-style On-Screen Display                          #
---- # Telemetry overlay for FPV / drone operations                          #
---- #                                                                       #
---- # RadioMaster AX12 | github.com/rmeadomavic/ax12-research               #
---- #                                                                       #
---- #########################################################################

---------------------------------------------------------------------------
-- State
---------------------------------------------------------------------------

local startTime = 0
local milGreen = false          -- toggle: false=FPV white, true=mil green
local hasTelem = false          -- true if any telemetry value received
local mAhUsed = 0              -- accumulated mAh consumed
local lastCurrentTime = 0       -- for mAh integration
local warnings = {}             -- active warning strings
local warnBlink = 0             -- blink counter

-- Color palettes (populated in init)
local FPV = {}   -- white-on-black FPV style
local MIL = {}   -- green-on-black military style
local C = {}     -- active palette reference

-- Layout constants (set in init from LCD_W/LCD_H)
local W, H
local margin, topBarH, botBarH
local centerX, centerY
local horizonR                  -- artificial horizon radius
local compassBarY, compassBarH
local fontSize

-- Telemetry cache (updated each frame)
local T = {
  vbat = 0,       -- total battery voltage
  cells = 0,      -- cell count
  cellV = 0,      -- per-cell voltage
  curr = 0,       -- current draw amps
  mah = 0,        -- mAh consumed (from telem or integrated)
  rssi = 0,       -- RSSI dBm
  lq = 0,         -- link quality %
  alt = 0,        -- altitude m
  spd = 0,        -- ground speed m/s
  dist = 0,       -- distance from home m
  lat = 0,        -- GPS latitude
  lon = 0,        -- GPS longitude
  hdg = 0,        -- heading degrees
  sats = 0,       -- GPS satellite count
  mode = "----",  -- flight mode string
  pitch = 0,      -- pitch degrees
  roll = 0,       -- roll degrees
  armed = false,  -- armed state
  txV = 0,        -- transmitter voltage
}

-- Battery capacity for remaining bar (mAh)
local BATT_CAPACITY = 1300

---------------------------------------------------------------------------
-- Math helpers
---------------------------------------------------------------------------

local sin = math.sin
local cos = math.cos
local rad = math.rad
local floor = math.floor
local abs = math.abs
local min = math.min
local max = math.max

local function clamp(v, lo, hi)
  return (v < lo) and lo or (v > hi) and hi or v
end

---------------------------------------------------------------------------
-- Color palette setup
---------------------------------------------------------------------------

local function buildPalettes()
  -- FPV: white/cyan on black (Betaflight classic)
  FPV.bg       = lcd.RGB(0x00, 0x00, 0x00)
  FPV.text     = lcd.RGB(0xff, 0xff, 0xff)
  FPV.dim      = lcd.RGB(0x88, 0x88, 0x88)
  FPV.accent   = lcd.RGB(0x00, 0xdd, 0xff)  -- cyan
  FPV.good     = lcd.RGB(0x00, 0xff, 0x44)
  FPV.warn     = lcd.RGB(0xff, 0xcc, 0x00)
  FPV.crit     = lcd.RGB(0xff, 0x22, 0x22)
  FPV.barBg    = lcd.RGB(0x22, 0x22, 0x22)
  FPV.barFill  = lcd.RGB(0x00, 0xdd, 0xff)
  FPV.horizon  = lcd.RGB(0xff, 0xff, 0xff)
  FPV.sky      = lcd.RGB(0x11, 0x22, 0x44)
  FPV.ground   = lcd.RGB(0x33, 0x22, 0x11)
  FPV.crosshair= lcd.RGB(0xff, 0xff, 0x00)
  FPV.compass  = lcd.RGB(0xff, 0xff, 0xff)
  FPV.warnBg   = lcd.RGB(0xaa, 0x00, 0x00)
  FPV.sim      = lcd.RGB(0xff, 0x88, 0x00)

  -- Military: green on black
  MIL.bg       = lcd.RGB(0x00, 0x00, 0x00)
  MIL.text     = lcd.RGB(0x33, 0xff, 0x33)
  MIL.dim      = lcd.RGB(0x22, 0x66, 0x22)
  MIL.accent   = lcd.RGB(0x44, 0xff, 0x44)
  MIL.good     = lcd.RGB(0x33, 0xff, 0x33)
  MIL.warn     = lcd.RGB(0xff, 0xcc, 0x00)
  MIL.crit     = lcd.RGB(0xff, 0x22, 0x22)
  MIL.barBg    = lcd.RGB(0x11, 0x22, 0x11)
  MIL.barFill  = lcd.RGB(0x33, 0xff, 0x33)
  MIL.horizon  = lcd.RGB(0x33, 0xff, 0x33)
  MIL.sky      = lcd.RGB(0x05, 0x11, 0x05)
  MIL.ground   = lcd.RGB(0x11, 0x18, 0x05)
  MIL.crosshair= lcd.RGB(0x66, 0xff, 0x66)
  MIL.compass  = lcd.RGB(0x33, 0xff, 0x33)
  MIL.warnBg   = lcd.RGB(0x66, 0x00, 0x00)
  MIL.sim      = lcd.RGB(0xff, 0x88, 0x00)
end

local function setActivePalette()
  C = milGreen and MIL or FPV
end

---------------------------------------------------------------------------
-- Telemetry reading
---------------------------------------------------------------------------

local function readTelemetry()
  hasTelem = false

  -- Battery voltage (try several ELRS/CRSF sources)
  local v = getValue("RxBt") or 0
  if v == 0 then v = getValue("VFAS") or 0 end
  if v == 0 then v = getValue("Cels") or 0 end
  if v ~= 0 then
    hasTelem = true
    T.vbat = v
    -- Auto-detect cell count
    if v > 25 then T.cells = 8
    elseif v > 21 then T.cells = 6
    elseif v > 16.8 then T.cells = 5
    elseif v > 12.6 then T.cells = 4
    elseif v > 8.4 then T.cells = 3
    elseif v > 4.2 then T.cells = 2
    else T.cells = 1 end
    T.cellV = T.vbat / T.cells
  end

  -- Current draw
  local curr = getValue("Curr") or 0
  if curr == 0 then curr = getValue("curr") or 0 end
  if curr ~= 0 then hasTelem = true; T.curr = curr end

  -- mAh consumed (from telem or integrate current)
  local mah = getValue("Fuel") or 0
  if mah == 0 then mah = getValue("mAh") or 0 end
  if mah ~= 0 then
    hasTelem = true
    T.mah = mah
    mAhUsed = mah
  else
    -- Integrate current if we have it
    local now = getTime()
    if T.curr > 0 and lastCurrentTime > 0 then
      local dt = (now - lastCurrentTime) / 360000  -- hours
      mAhUsed = mAhUsed + T.curr * dt * 1000
      T.mah = floor(mAhUsed)
    end
    lastCurrentTime = now
  end

  -- RSSI
  local rssi = getValue("1RSS") or 0
  if rssi ~= 0 then hasTelem = true; T.rssi = rssi end

  -- Link Quality
  local lq = getValue("RQly") or 0
  if lq ~= 0 then hasTelem = true; T.lq = lq end

  -- Altitude
  local alt = getValue("Alt") or 0
  if alt == 0 then alt = getValue("GAlt") or 0 end
  if alt ~= 0 then hasTelem = true; T.alt = alt end

  -- Ground speed
  local spd = getValue("GSpd") or 0
  if spd ~= 0 then hasTelem = true; T.spd = spd end

  -- Distance from home
  local dist = getValue("Dist") or 0
  if dist ~= 0 then hasTelem = true; T.dist = dist end

  -- GPS
  local lat = getValue("gps-lat") or 0
  local lon = getValue("gps-lon") or 0
  if lat ~= 0 or lon ~= 0 then
    hasTelem = true
    T.lat = lat
    T.lon = lon
  end

  -- GPS satellites
  local sats = getValue("Sats") or 0
  if sats ~= 0 then hasTelem = true; T.sats = sats end

  -- Heading
  local hdg = getValue("Hdg") or 0
  if hdg == 0 then hdg = getValue("Yaw") or 0 end
  if hdg ~= 0 then hasTelem = true end
  if hdg < 0 then hdg = hdg + 360 end
  T.hdg = hdg

  -- Flight mode
  local fm = getValue("FM") or getValue("Flgt") or nil
  if fm and fm ~= 0 and fm ~= "" then
    hasTelem = true
    if type(fm) == "number" then
      local modes = {[0]="ACRO",[1]="ANGL",[2]="HRZN",[3]="AIR",
                      [4]="STAB",[5]="ALTH",[6]="PHLD",[7]="RTH",
                      [8]="LAND",[9]="CRSE",[10]="AUTO",[11]="GUID"}
      T.mode = modes[fm] or string.format("M%d", fm)
    else
      T.mode = tostring(fm)
    end
  end

  -- Pitch / Roll (from telemetry or sticks as fallback)
  local pit = getValue("Ptch") or 0
  local rol = getValue("Roll") or 0
  if pit ~= 0 or rol ~= 0 then
    hasTelem = true
    T.pitch = pit
    T.roll = rol
  else
    local ele = getValue("ele") or 0
    local ail = getValue("ail") or 0
    T.pitch = clamp(ele / 1024 * 45, -45, 45)
    T.roll = clamp(ail / 1024 * 45, -45, 45)
  end

  -- Armed state
  local armed = getValue("armed") or 0
  T.armed = (armed ~= 0)

  -- TX voltage
  local txV = getValue("tx-voltage") or 0
  if txV > 100 then txV = txV / 100 end
  if txV > 20 then txV = txV / 10 end
  T.txV = txV

  -- Generate simulated data if no telemetry
  if not hasTelem then
    local t = getTime() / 100
    T.vbat = 14.8 + sin(t * 0.1) * 0.4
    T.cells = 4
    T.cellV = T.vbat / 4
    T.curr = 12.5 + sin(t * 0.3) * 5
    T.mah = floor(t * 8) % 1300
    T.rssi = -55 + floor(sin(t * 0.2) * 15)
    T.lq = 95 + floor(sin(t * 0.15) * 5)
    T.alt = 50 + sin(t * 0.08) * 20
    T.spd = 8 + sin(t * 0.12) * 4
    T.dist = 120 + sin(t * 0.05) * 80
    T.lat = 35.1470 + sin(t * 0.01) * 0.001
    T.lon = -79.4760 + cos(t * 0.01) * 0.001
    T.sats = 12
    T.hdg = (t * 5) % 360
    T.mode = "ACRO"
    T.pitch = sin(t * 0.4) * 15
    T.roll = sin(t * 0.3) * 20
    T.armed = true
    mAhUsed = T.mah
  end

  -- Check warnings
  warnings = {}
  if hasTelem then
    if T.cellV > 0 and T.cellV < 3.5 then
      warnings[#warnings+1] = "LOW BATT"
    end
    if T.lq > 0 and T.lq < 30 then
      warnings[#warnings+1] = "FAILSAFE"
    end
    if T.sats < 4 and T.sats > 0 then
      warnings[#warnings+1] = "GPS LOST"
    end
  end
  if not hasTelem then
    warnings[#warnings+1] = "NO TELEM"
  end
end

---------------------------------------------------------------------------
-- Drawing helpers
---------------------------------------------------------------------------

local function drawHBar(x, y, w, h, pct, colorFill, colorBg)
  pct = clamp(pct, 0, 100)
  lcd.setColor(CUSTOM_COLOR, colorBg or C.barBg)
  lcd.drawFilledRectangle(x, y, w, h, CUSTOM_COLOR)
  if pct > 0 then
    local fw = floor(w * pct / 100)
    lcd.setColor(CUSTOM_COLOR, colorFill or C.barFill)
    lcd.drawFilledRectangle(x, y, max(fw, 1), h, CUSTOM_COLOR)
  end
end

local function colorForPct(pct)
  if pct < 20 then return C.crit
  elseif pct < 40 then return C.warn
  else return C.good end
end

local function colorForCellV(v)
  if v < 3.3 then return C.crit
  elseif v < 3.5 then return C.warn
  else return C.good end
end

---------------------------------------------------------------------------
-- Drawing: Compass bar (top)
---------------------------------------------------------------------------

local function drawCompassBar()
  local y = 0
  local h = compassBarH
  local cw = W

  -- Background
  lcd.setColor(CUSTOM_COLOR, C.bg)
  lcd.drawFilledRectangle(0, y, cw, h, CUSTOM_COLOR)

  -- Separator line
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawLine(0, y + h - 1, W, y + h - 1, SOLID, FORCE)

  -- Draw compass tape
  local hdg = T.hdg
  local degsVisible = 120
  local pxPerDeg = cw / degsVisible

  local cardinals = {
    [0]="N", [45]="NE", [90]="E", [135]="SE",
    [180]="S", [225]="SW", [270]="W", [315]="NW"
  }

  for deg_off = -degsVisible/2, degsVisible/2, 1 do
    local d = floor(hdg + deg_off + 0.5) % 360
    if d < 0 then d = d + 360 end
    local px = floor(cw/2 + deg_off * pxPerDeg)

    if px >= 0 and px < cw then
      if d % 45 == 0 then
        lcd.setColor(CUSTOM_COLOR, C.compass)
        lcd.drawLine(px, y + h - 14, px, y + h - 2, SOLID, FORCE)
        local label = cardinals[d]
        if label then
          local lColor = (label == "N") and C.crit or C.compass
          lcd.setColor(CUSTOM_COLOR, lColor)
          lcd.drawText(px - (#label * 4), y + 2, label, SMLSIZE + CUSTOM_COLOR)
        end
      elseif d % 15 == 0 then
        lcd.setColor(CUSTOM_COLOR, C.dim)
        lcd.drawLine(px, y + h - 10, px, y + h - 2, SOLID, FORCE)
        lcd.drawText(px - 8, y + 2, tostring(d), SMLSIZE + CUSTOM_COLOR)
      elseif d % 5 == 0 then
        lcd.setColor(CUSTOM_COLOR, C.dim)
        lcd.drawLine(px, y + h - 6, px, y + h - 2, SOLID, FORCE)
      end
    end
  end

  -- Center heading indicator (inverted triangle)
  local cx = floor(cw/2)
  lcd.setColor(CUSTOM_COLOR, C.accent)
  lcd.drawLine(cx - 6, y, cx, y + 6, SOLID, FORCE)
  lcd.drawLine(cx + 6, y, cx, y + 6, SOLID, FORCE)
  lcd.drawLine(cx - 6, y, cx + 6, y, SOLID, FORCE)

  -- Heading readout in box
  local hdgStr = string.format("%03d", floor(hdg + 0.5) % 360)
  local boxW = 46
  local boxH = 18
  lcd.setColor(CUSTOM_COLOR, C.bg)
  lcd.drawFilledRectangle(cx - boxW/2, y + h - boxH - 1, boxW, boxH, CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.accent)
  lcd.drawRectangle(cx - boxW/2, y + h - boxH - 1, boxW, boxH, CUSTOM_COLOR)
  lcd.drawText(cx - 14, y + h - boxH + 1, hdgStr, SMLSIZE + CUSTOM_COLOR)
end

---------------------------------------------------------------------------
-- Drawing: Artificial horizon (center)
---------------------------------------------------------------------------

local function drawHorizon()
  local cx = centerX
  local cy = centerY
  local r = horizonR

  local pitchPx = T.pitch / 90 * r
  local rollRad = rad(-T.roll)

  -- Sky/ground fill
  local horizY = cy + floor(pitchPx)

  lcd.setColor(CUSTOM_COLOR, C.sky)
  if horizY > cy - r then
    lcd.drawFilledRectangle(cx - r, cy - r, r * 2,
      min(horizY - (cy - r), r * 2), CUSTOM_COLOR)
  end

  lcd.setColor(CUSTOM_COLOR, C.ground)
  if horizY < cy + r then
    local gy = max(horizY, cy - r)
    lcd.drawFilledRectangle(cx - r, gy, r * 2,
      (cy + r) - gy, CUSTOM_COLOR)
  end

  -- Horizon line (accounting for roll)
  local lineLen = r * 2
  local hx1 = cx - floor(lineLen/2 * cos(rollRad))
  local hy1 = horizY + floor(lineLen/2 * sin(rollRad))
  local hx2 = cx + floor(lineLen/2 * cos(rollRad))
  local hy2 = horizY - floor(lineLen/2 * sin(rollRad))

  lcd.setColor(CUSTOM_COLOR, C.horizon)
  lcd.drawLine(floor(hx1), floor(hy1), floor(hx2), floor(hy2), SOLID, FORCE)

  -- Pitch ladder: lines every 10 degrees
  for pd = -30, 30, 10 do
    if pd ~= 0 then
      local ladderY = cy + floor((T.pitch - pd) / 90 * r)
      local lw = (abs(pd) >= 20) and 40 or 60
      local lx1 = cx - floor(lw/2 * cos(rollRad))
      local ly1 = ladderY + floor(lw/2 * sin(rollRad))
      local lx2 = cx + floor(lw/2 * cos(rollRad))
      local ly2 = ladderY - floor(lw/2 * sin(rollRad))

      if ly1 > cy - r and ly1 < cy + r and ly2 > cy - r and ly2 < cy + r then
        lcd.setColor(CUSTOM_COLOR, C.dim)
        if pd < 0 then
          local mx = floor((lx1 + lx2) / 2)
          local my = floor((ly1 + ly2) / 2)
          lcd.drawLine(floor(lx1), floor(ly1), mx - 5, my, DOTTED, FORCE)
          lcd.drawLine(mx + 5, my, floor(lx2), floor(ly2), DOTTED, FORCE)
        else
          lcd.drawLine(floor(lx1), floor(ly1), floor(lx2), floor(ly2), SOLID, FORCE)
        end
        lcd.drawText(floor(lx2) + 4, floor(ly2) - 5,
          tostring(pd), SMLSIZE + CUSTOM_COLOR)
      end
    end
  end

  -- Crosshair / aircraft symbol
  lcd.setColor(CUSTOM_COLOR, C.crosshair)
  lcd.drawLine(cx - 40, cy, cx - 12, cy, SOLID, FORCE)
  lcd.drawLine(cx - 12, cy, cx - 12, cy + 6, SOLID, FORCE)
  lcd.drawLine(cx + 12, cy, cx + 40, cy, SOLID, FORCE)
  lcd.drawLine(cx + 12, cy, cx + 12, cy + 6, SOLID, FORCE)
  lcd.drawFilledRectangle(cx - 2, cy - 2, 5, 5, CUSTOM_COLOR)

  -- Roll indicator arc
  lcd.setColor(CUSTOM_COLOR, C.dim)
  local arcR = r + 5
  for _, mark in ipairs({-45, -30, -20, -10, 0, 10, 20, 30, 45}) do
    local a = rad(mark - 90)
    local tx = cx + floor(arcR * cos(a))
    local ty = cy - r + floor(arcR * sin(a)) - 15
    if mark == 0 then
      lcd.setColor(CUSTOM_COLOR, C.accent)
      lcd.drawLine(tx, ty - 4, tx - 3, ty + 2, SOLID, FORCE)
      lcd.drawLine(tx, ty - 4, tx + 3, ty + 2, SOLID, FORCE)
      lcd.setColor(CUSTOM_COLOR, C.dim)
    else
      lcd.drawLine(tx, ty, tx, ty + 4, SOLID, FORCE)
    end
  end

  -- Current roll pointer
  local rollA = rad(-T.roll - 90)
  local rix = cx + floor(arcR * cos(rollA))
  local riy = cy - r + floor(arcR * sin(rollA)) - 10
  lcd.setColor(CUSTOM_COLOR, C.accent)
  lcd.drawLine(rix, riy + 6, rix - 3, riy, SOLID, FORCE)
  lcd.drawLine(rix, riy + 6, rix + 3, riy, SOLID, FORCE)

  -- Border
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawRectangle(cx - r, cy - r, r * 2, r * 2, CUSTOM_COLOR)
end

---------------------------------------------------------------------------
-- Drawing: Left column (battery, current, mAh)
---------------------------------------------------------------------------

local function drawLeftColumn()
  local lx = margin
  local y = compassBarH + 8

  -- Battery voltage (large)
  local vColor = colorForCellV(T.cellV)
  lcd.setColor(CUSTOM_COLOR, vColor)
  lcd.drawText(lx, y, string.format("%.1fV", T.vbat), MIDSIZE + CUSTOM_COLOR)
  y = y + 26

  -- Cell count and per-cell voltage
  lcd.setColor(CUSTOM_COLOR, C.text)
  lcd.drawText(lx, y, string.format("%dS %.2fV/c", T.cells, T.cellV),
    SMLSIZE + CUSTOM_COLOR)
  y = y + 18

  -- Battery bar (voltage-based)
  local cellPct = clamp((T.cellV - 3.3) / (4.2 - 3.3) * 100, 0, 100)
  drawHBar(lx, y, 110, 10, cellPct, colorForCellV(T.cellV), C.barBg)
  y = y + 16

  -- Current draw
  lcd.setColor(CUSTOM_COLOR, C.text)
  lcd.drawText(lx, y, string.format("%.1fA", T.curr), MIDSIZE + CUSTOM_COLOR)
  y = y + 26

  -- mAh consumed
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(lx, y, "mAh", SMLSIZE + CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.text)
  lcd.drawText(lx + 30, y, tostring(floor(mAhUsed)), SMLSIZE + CUSTOM_COLOR)
  y = y + 16

  -- Capacity remaining bar
  local capPct = clamp((1 - mAhUsed / BATT_CAPACITY) * 100, 0, 100)
  drawHBar(lx, y, 110, 10, capPct, colorForPct(capPct), C.barBg)
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(lx + 114, y, string.format("%d%%", floor(capPct)),
    SMLSIZE + CUSTOM_COLOR)
  y = y + 18

  -- TX voltage (smaller)
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(lx, y, string.format("TX %.1fV", T.txV), SMLSIZE + CUSTOM_COLOR)
end

---------------------------------------------------------------------------
-- Drawing: Right column (RSSI/LQ, alt, speed, dist)
---------------------------------------------------------------------------

local function drawRightColumn()
  local rx = W - margin - 140
  local y = compassBarH + 8

  -- RSSI
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(rx, y, "RSSI", SMLSIZE + CUSTOM_COLOR)
  local rssiColor = C.good
  if T.rssi < -90 then rssiColor = C.crit
  elseif T.rssi < -75 then rssiColor = C.warn end
  lcd.setColor(CUSTOM_COLOR, rssiColor)
  lcd.drawText(rx + 42, y, string.format("%ddBm", T.rssi),
    SMLSIZE + CUSTOM_COLOR)
  y = y + 16

  -- LQ bar
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(rx, y, "LQ", SMLSIZE + CUSTOM_COLOR)
  local lqColor = C.good
  if T.lq < 30 then lqColor = C.crit
  elseif T.lq < 70 then lqColor = C.warn end
  lcd.setColor(CUSTOM_COLOR, lqColor)
  lcd.drawText(rx + 24, y, string.format("%d%%", T.lq), SMLSIZE + CUSTOM_COLOR)
  drawHBar(rx + 60, y + 2, 80, 8, T.lq, lqColor, C.barBg)
  y = y + 20

  -- Separator
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawLine(rx, y, rx + 140, y, DOTTED, FORCE)
  y = y + 6

  -- Altitude
  lcd.setColor(CUSTOM_COLOR, C.text)
  lcd.drawText(rx, y, string.format("ALT %.1fm", T.alt), SMLSIZE + CUSTOM_COLOR)
  y = y + 16

  -- Speed (converted to km/h)
  local spdKmh = T.spd * 3.6
  lcd.drawText(rx, y, string.format("SPD %.1fkm/h", spdKmh),
    SMLSIZE + CUSTOM_COLOR)
  y = y + 16

  -- Distance from home
  local distStr
  if T.dist >= 1000 then
    distStr = string.format("DST %.2fkm", T.dist / 1000)
  else
    distStr = string.format("DST %dm", floor(T.dist))
  end
  lcd.drawText(rx, y, distStr, SMLSIZE + CUSTOM_COLOR)
  y = y + 16

  -- Satellites
  local satColor = C.good
  if T.sats < 6 then satColor = C.crit
  elseif T.sats < 10 then satColor = C.warn end
  lcd.setColor(CUSTOM_COLOR, satColor)
  lcd.drawText(rx, y, string.format("SAT %d", T.sats), SMLSIZE + CUSTOM_COLOR)
end

---------------------------------------------------------------------------
-- Drawing: Bottom bar (flight time, mode, GPS, warnings)
---------------------------------------------------------------------------

local function drawBottomBar()
  local by = H - botBarH
  lcd.setColor(CUSTOM_COLOR, C.bg)
  lcd.drawFilledRectangle(0, by, W, botBarH, CUSTOM_COLOR)

  -- Separator line
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawLine(0, by, W, by, SOLID, FORCE)

  local y = by + 4

  -- Flight time (left)
  local elapsed = floor((getTime() - startTime) / 100)
  local mm = floor(elapsed / 60)
  local ss = elapsed % 60
  lcd.setColor(CUSTOM_COLOR, C.text)
  lcd.drawText(margin, y, string.format("%02d:%02d", mm, ss),
    MIDSIZE + CUSTOM_COLOR)

  -- Flight mode (center)
  local modeColor = C.accent
  if T.mode == "RTH" or T.mode == "LAND" then modeColor = C.warn end
  lcd.setColor(CUSTOM_COLOR, modeColor)
  lcd.drawText(floor(W/2) - 20, y, T.mode, MIDSIZE + CUSTOM_COLOR)

  -- Armed indicator
  if T.armed then
    lcd.setColor(CUSTOM_COLOR, C.crit)
    lcd.drawText(floor(W/2) + 40, y + 2, "ARMED", SMLSIZE + CUSTOM_COLOR)
  else
    lcd.setColor(CUSTOM_COLOR, C.good)
    lcd.drawText(floor(W/2) + 40, y + 2, "DSRM", SMLSIZE + CUSTOM_COLOR)
  end

  -- SIM label
  if not hasTelem then
    lcd.setColor(CUSTOM_COLOR, C.sim)
    lcd.drawText(W - margin - 40, y + 2, "SIM", BOLD + CUSTOM_COLOR)
  end

  -- GPS coordinates (bottom row, small)
  y = by + 30
  lcd.setColor(CUSTOM_COLOR, C.dim)
  if T.lat ~= 0 or T.lon ~= 0 then
    local latDir = T.lat >= 0 and "N" or "S"
    local lonDir = T.lon >= 0 and "E" or "W"
    local gpsStr = string.format("%s%.5f %s%.5f",
      latDir, abs(T.lat), lonDir, abs(T.lon))
    lcd.drawText(margin, y, gpsStr, SMLSIZE + CUSTOM_COLOR)
  else
    lcd.drawText(margin, y, "NO GPS FIX", SMLSIZE + CUSTOM_COLOR)
  end

  -- Style label (bottom right)
  lcd.setColor(CUSTOM_COLOR, C.dim)
  local styleLabel = milGreen and "MIL" or "FPV"
  lcd.drawText(W - margin - 30, y, styleLabel, SMLSIZE + CUSTOM_COLOR)
end

---------------------------------------------------------------------------
-- Drawing: Warnings overlay (center, blinking)
---------------------------------------------------------------------------

local function drawWarnings()
  if #warnings == 0 then return end

  warnBlink = warnBlink + 1
  if warnBlink % 20 < 10 then return end  -- blink off phase

  local warnY = centerY + horizonR + 15
  for i, w in ipairs(warnings) do
    local ww = #w * 10 + 16
    local wx = floor(W/2 - ww/2)
    local wy = warnY + (i - 1) * 24

    lcd.setColor(CUSTOM_COLOR, C.warnBg)
    lcd.drawFilledRectangle(wx, wy, ww, 20, CUSTOM_COLOR)
    lcd.setColor(CUSTOM_COLOR, C.crit)
    lcd.drawRectangle(wx, wy, ww, 20, CUSTOM_COLOR)
    lcd.drawText(wx + 8, wy + 2, w, SMLSIZE + BOLD + CUSTOM_COLOR)
  end
end

---------------------------------------------------------------------------
-- Init
---------------------------------------------------------------------------

local function init()
  startTime = getTime()
  lastCurrentTime = getTime()

  buildPalettes()
  setActivePalette()

  W = LCD_W
  H = LCD_H
  margin = 8
  compassBarH = 34
  botBarH = 52

  -- Horizon centered, leaving room for compass bar and bottom bar
  local usableH = H - compassBarH - botBarH
  centerX = floor(W / 2)
  centerY = compassBarH + floor(usableH / 2)
  horizonR = floor(min(W * 0.25, usableH * 0.35))
end

---------------------------------------------------------------------------
-- Run
---------------------------------------------------------------------------

local function run(event, touchState)
  if event == nil then return 0 end
  if event == EVT_VIRTUAL_EXIT then return 1 end

  -- Touch toggle: tap top-right corner to switch style
  if event == EVT_TOUCH_TAP then
    if touchState and touchState.x and touchState.y then
      if touchState.x > W - 80 and touchState.y < 50 then
        milGreen = not milGreen
        setActivePalette()
      end
    end
  end

  -- Read telemetry data
  readTelemetry()

  -- Clear screen
  lcd.clear()
  lcd.setColor(CUSTOM_COLOR, C.bg)
  lcd.drawFilledRectangle(0, 0, W, H, CUSTOM_COLOR)

  -- Draw all OSD elements (edges first, center last)
  drawCompassBar()
  drawLeftColumn()
  drawRightColumn()
  drawHorizon()
  drawBottomBar()
  drawWarnings()

  -- Style toggle hint (top-right, subtle)
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(W - margin - 36, 2,
    milGreen and "[FPV]" or "[MIL]", SMLSIZE + CUSTOM_COLOR)

  return 0
end

return { init=init, run=run }
