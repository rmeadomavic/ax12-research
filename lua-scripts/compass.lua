-- TNS|Compass|TNE
---- #########################################################################
---- #                                                                       #
---- # Compass -- Heading & Attitude Display for ICM-42607 IMU               #
---- # RadioMaster AX12 | github.com/rmeadomavic/ax12-research               #
---- #                                                                       #
---- #########################################################################

---------------------------------------------------------------------------
-- Configuration
---------------------------------------------------------------------------

local UPDATE_INTERVAL = 5    -- ticks between sensor reads (~50ms each)
local SMOOTH_ALPHA    = 0.3  -- EMA smoothing factor for heading

---------------------------------------------------------------------------
-- State
---------------------------------------------------------------------------

local C = {}           -- color palette
local heading = 0      -- current heading 0-360
local roll = 0         -- roll in degrees (-90..90)
local pitch = 0        -- pitch in degrees (-90..90)
local headingOffset = 0-- calibration offset (touch to zero)
local hasSensor = false-- whether real sensor data is available
local simAngle = 0     -- simulated heading for demo mode
local lastUpdate = 0   -- tick of last sensor read
local centerX, centerY -- compass center coordinates
local compassR         -- compass radius
local attR             -- attitude indicator radius
local margin, titleH

---------------------------------------------------------------------------
-- Math helpers
---------------------------------------------------------------------------

local sin = math.sin
local cos = math.cos
local rad = math.rad
local deg = math.deg
local floor = math.floor
local abs = math.abs
local pi = math.pi

local function clamp(v, lo, hi)
  return (v < lo) and lo or (v > hi) and hi or v
end

local function normalizeAngle(a)
  a = a % 360
  if a < 0 then a = a + 360 end
  return a
end

local function lerp(a, b, t)
  return a + (b - a) * t
end

-- Smooth angle interpolation (handles 359->1 wraparound)
local function lerpAngle(from, to, t)
  local diff = to - from
  if diff > 180 then diff = diff - 360
  elseif diff < -180 then diff = diff + 360 end
  return normalizeAngle(from + diff * t)
end

---------------------------------------------------------------------------
-- Sensor reading
---------------------------------------------------------------------------

local function readSensors()
  -- Try to read heading from various possible sources
  local h = nil

  -- Try getShmVar for IMU heading (AX12-specific shared memory)
  if getShmVar then
    local ok, val = pcall(getShmVar, "heading")
    if ok and val and type(val) == "number" and val ~= 0 then
      h = val
      hasSensor = true
    end
    if not h then
      local ok2, val2 = pcall(getShmVar, "imu_heading")
      if ok2 and val2 and type(val2) == "number" and val2 ~= 0 then
        h = val2
        hasSensor = true
      end
    end
  end

  -- Try getValue for telemetry-style heading source
  if not h then
    local val = getValue("Hdg")
    if val and val ~= 0 then
      h = val
      hasSensor = true
    end
  end
  if not h then
    local val = getValue("heading")
    if val and val ~= 0 then
      h = val
      hasSensor = true
    end
  end

  -- Read accelerometer for tilt (roll/pitch)
  local accX, accY, accZ

  if getShmVar then
    local okx, vx = pcall(getShmVar, "accel_x")
    local oky, vy = pcall(getShmVar, "accel_y")
    local okz, vz = pcall(getShmVar, "accel_z")
    if okx and vx then accX = vx end
    if oky and vy then accY = vy end
    if okz and vz then accZ = vz end
  end

  -- Derive roll/pitch from accelerometer
  if accX and accY and accZ and accZ ~= 0 then
    roll = clamp(deg(math.atan2(accY, accZ)), -90, 90)
    pitch = clamp(deg(math.atan2(-accX, math.sqrt(accY*accY + accZ*accZ))), -90, 90)
  else
    -- Try gimbal sticks as attitude proxy for demo
    local ailVal = getValue("ail")
    local eleVal = getValue("ele")
    if ailVal then roll = clamp(ailVal / 1024 * 45, -45, 45) end
    if eleVal then pitch = clamp(eleVal / 1024 * 45, -45, 45) end
  end

  -- Apply heading or fallback to simulation
  if h then
    heading = lerpAngle(heading, normalizeAngle(h - headingOffset), SMOOTH_ALPHA)
  else
    -- Simulated: use rudder stick or auto-rotate
    hasSensor = false
    local rudVal = getValue("rud")
    if rudVal and abs(rudVal) > 50 then
      simAngle = simAngle + rudVal / 1024 * 3
    else
      simAngle = simAngle + 0.2
    end
    heading = lerpAngle(heading, normalizeAngle(simAngle), SMOOTH_ALPHA)
  end
end

---------------------------------------------------------------------------
-- Drawing: Compass Rose
---------------------------------------------------------------------------

local function drawCompassRose()
  local cx, cy, r = centerX, centerY, compassR

  -- Outer ring
  lcd.setColor(CUSTOM_COLOR, C.ring)
  lcd.drawCircle(cx, cy, r)
  lcd.drawCircle(cx, cy, r - 1)

  -- Degree tick marks
  for i = 0, 359, 5 do
    local a = rad(i - heading + 270) -- 0=north=top
    local isMajor = (i % 30 == 0)
    local isCardinal = (i % 90 == 0)

    local innerR = r - (isCardinal and 20 or (isMajor and 14 or 8))
    local outerR = r - 3

    local x1 = cx + innerR * cos(a)
    local y1 = cy + innerR * sin(a)
    local x2 = cx + outerR * cos(a)
    local y2 = cy + outerR * sin(a)

    if isCardinal then
      lcd.setColor(CUSTOM_COLOR, C.cardinal)
    elseif isMajor then
      lcd.setColor(CUSTOM_COLOR, C.major)
    else
      lcd.setColor(CUSTOM_COLOR, C.minor)
    end
    lcd.drawLine(floor(x1), floor(y1), floor(x2), floor(y2), SOLID, FORCE)
  end

  -- Cardinal direction labels
  local cardinals = {
    {0, "N", C.north},
    {90, "E", C.cardinal},
    {180, "S", C.south},
    {270, "W", C.cardinal}
  }

  for _, card in ipairs(cardinals) do
    local a = rad(card[1] - heading + 270)
    local labelR = r - 30
    local lx = cx + labelR * cos(a)
    local ly = cy + labelR * sin(a)

    lcd.setColor(CUSTOM_COLOR, card[3])
    lcd.drawText(floor(lx) - 5, floor(ly) - 8, card[2], BOLD + CUSTOM_COLOR)
  end

  -- Intercardinal labels
  local intercards = {
    {45, "NE"}, {135, "SE"}, {225, "SW"}, {315, "NW"}
  }
  for _, ic in ipairs(intercards) do
    local a = rad(ic[1] - heading + 270)
    local labelR = r - 28
    local lx = cx + labelR * cos(a)
    local ly = cy + labelR * sin(a)
    lcd.setColor(CUSTOM_COLOR, C.dim)
    lcd.drawText(floor(lx) - 7, floor(ly) - 6, ic[2], SMLSIZE + CUSTOM_COLOR)
  end

  -- Fixed heading pointer (top triangle)
  lcd.setColor(CUSTOM_COLOR, C.pointer)
  local pw = 8
  lcd.drawLine(cx, cy - r - 6, cx - pw, cy - r + 6, SOLID, FORCE)
  lcd.drawLine(cx, cy - r - 6, cx + pw, cy - r + 6, SOLID, FORCE)
  lcd.drawLine(cx - pw, cy - r + 6, cx + pw, cy - r + 6, SOLID, FORCE)

  -- Center dot
  lcd.setColor(CUSTOM_COLOR, C.center)
  lcd.drawFilledRectangle(cx - 2, cy - 2, 5, 5, CUSTOM_COLOR)
end

---------------------------------------------------------------------------
-- Drawing: Heading readout
---------------------------------------------------------------------------

local function drawHeadingReadout()
  local cx = centerX
  local y = centerY + compassR + 16

  -- Heading value box
  lcd.setColor(CUSTOM_COLOR, C.boxBg)
  local boxW = 100
  local boxH = 30
  lcd.drawFilledRectangle(cx - boxW/2, y, boxW, boxH, CUSTOM_COLOR)

  lcd.setColor(CUSTOM_COLOR, C.boxBorder)
  lcd.drawRectangle(cx - boxW/2, y, boxW, boxH, CUSTOM_COLOR)

  -- Heading text
  local hdgStr = string.format("%03d", floor(heading + 0.5) % 360)
  lcd.setColor(CUSTOM_COLOR, C.headingText)
  lcd.drawText(cx - 20, y + 4, hdgStr .. "\xC2\xB0", MIDSIZE + CUSTOM_COLOR)

  -- Compass bearing label
  local bearings = {"N","NNE","NE","ENE","E","ESE","SE","SSE",
                    "S","SSW","SW","WSW","W","WNW","NW","NNW"}
  local idx = floor((heading + 11.25) / 22.5) % 16 + 1
  local bearStr = bearings[idx]

  lcd.setColor(CUSTOM_COLOR, C.bearing)
  lcd.drawText(cx - 15, y + boxH + 4, bearStr, BOLD + CUSTOM_COLOR)

  -- Sensor status
  local statusY = y + boxH + 22
  if hasSensor then
    lcd.setColor(CUSTOM_COLOR, C.good)
    lcd.drawText(cx - 30, statusY, "IMU LIVE", SMLSIZE + CUSTOM_COLOR)
  else
    lcd.setColor(CUSTOM_COLOR, C.warn)
    lcd.drawText(cx - 30, statusY, "SIMULATED", SMLSIZE + CUSTOM_COLOR)
  end
end

---------------------------------------------------------------------------
-- Drawing: Attitude Indicator (mini)
---------------------------------------------------------------------------

local function drawAttitudeIndicator()
  local ax = LCD_W - margin - attR - 5
  local ay = titleH + attR + 10
  local r = attR

  -- Background circle
  lcd.setColor(CUSTOM_COLOR, C.attBg)
  lcd.drawCircle(ax, ay, r)
  lcd.drawCircle(ax, ay, r - 1)

  -- Sky/ground split based on pitch
  local pitchOffset = clamp(pitch / 90 * r, -r + 2, r - 2)

  -- Ground half (below horizon)
  lcd.setColor(CUSTOM_COLOR, C.ground)
  lcd.drawFilledRectangle(ax - r + 2, ay + floor(pitchOffset),
    (r - 2) * 2, r - floor(pitchOffset), CUSTOM_COLOR)

  -- Horizon line (rotated by roll)
  local rollRad = rad(roll)
  local hx1 = ax - (r - 4) * cos(rollRad)
  local hy1 = ay + pitchOffset - (r - 4) * sin(rollRad)
  local hx2 = ax + (r - 4) * cos(rollRad)
  local hy2 = ay + pitchOffset + (r - 4) * sin(rollRad)

  lcd.setColor(CUSTOM_COLOR, C.horizon)
  lcd.drawLine(floor(hx1), floor(hy1), floor(hx2), floor(hy2), SOLID, FORCE)

  -- Aircraft symbol (center wings)
  lcd.setColor(CUSTOM_COLOR, C.aircraft)
  lcd.drawLine(ax - 12, ay, ax - 4, ay, SOLID, FORCE)
  lcd.drawLine(ax + 4, ay, ax + 12, ay, SOLID, FORCE)
  lcd.drawFilledRectangle(ax - 2, ay - 2, 5, 5, CUSTOM_COLOR)

  -- Roll arc indicators
  lcd.setColor(CUSTOM_COLOR, C.dim)
  for _, deg_mark in ipairs({-30, -15, 0, 15, 30}) do
    local a = rad(deg_mark + 270)
    local tx = ax + (r - 4) * cos(a)
    local ty = ay + (r - 4) * sin(a)
    lcd.drawFilledRectangle(floor(tx) - 1, floor(ty) - 1, 3, 3, CUSTOM_COLOR)
  end

  -- Labels
  lcd.setColor(CUSTOM_COLOR, C.text)
  lcd.drawText(ax - r, ay + r + 4, "ATT", SMLSIZE + CUSTOM_COLOR)

  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(ax - r, ay + r + 16,
    string.format("R%+.0f P%+.0f", roll, pitch), SMLSIZE + CUSTOM_COLOR)

  -- Border ring
  lcd.setColor(CUSTOM_COLOR, C.attBorder)
  lcd.drawCircle(ax, ay, r)
end

---------------------------------------------------------------------------
-- Drawing: Info panel
---------------------------------------------------------------------------

local function drawInfoPanel()
  local ix = margin + 5
  local iy = titleH + 10

  lcd.setColor(CUSTOM_COLOR, C.section)
  lcd.drawText(ix, iy, "COMPASS", BOLD + CUSTOM_COLOR)
  iy = iy + 20

  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(ix, iy, "ICM-42607", SMLSIZE + CUSTOM_COLOR)
  iy = iy + 14

  -- Help text
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(ix, LCD_H - 30, "TAP: zero hdg", SMLSIZE + CUSTOM_COLOR)
  lcd.drawText(ix, LCD_H - 16, "RUD: sim rotate", SMLSIZE + CUSTOM_COLOR)
end

---------------------------------------------------------------------------
-- Main run (color)
---------------------------------------------------------------------------

local function runColor(event, touchState)
  -- Read sensors at interval
  local now = getTime()
  if now - lastUpdate > UPDATE_INTERVAL then
    readSensors()
    lastUpdate = now
  end

  -- Handle touch: tap to zero heading
  if touchState and touchState.tapCount and touchState.tapCount > 0 then
    headingOffset = heading + headingOffset
    heading = 0
    simAngle = 0
  end

  -- Handle EVT for recalibrate (ENTER key)
  if event == EVT_VIRTUAL_ENTER then
    headingOffset = heading + headingOffset
    heading = 0
    simAngle = 0
  end

  -- Clear with dark background
  lcd.clear()
  lcd.setColor(CUSTOM_COLOR, C.bg)
  lcd.drawFilledRectangle(0, 0, LCD_W, LCD_H, CUSTOM_COLOR)

  -- Title bar
  lcd.setColor(CUSTOM_COLOR, C.titleBg)
  lcd.drawFilledRectangle(0, 0, LCD_W, titleH, CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.titleFg)
  lcd.drawText(margin, 2, "COMPASS", BOLD + CUSTOM_COLOR)

  local modeStr = hasSensor and "LIVE" or "SIM"
  lcd.drawText(LCD_W - margin - 40, 2, modeStr, BOLD + CUSTOM_COLOR)

  -- Draw components
  drawCompassRose()
  drawHeadingReadout()
  drawAttitudeIndicator()
  drawInfoPanel()

  return 0
end

---------------------------------------------------------------------------
-- Init
---------------------------------------------------------------------------

local function init()
  lastUpdate = getTime()

  -- Color palette - dark military/aviation theme
  C.bg         = lcd.RGB(0x0d, 0x0d, 0x14) -- near-black background
  C.titleBg    = lcd.RGB(0x1a, 0x2a, 0x1a) -- dark green title bar
  C.titleFg    = lcd.RGB(0x80, 0xff, 0x80) -- green title text
  C.ring       = lcd.RGB(0x60, 0x80, 0x60) -- compass ring
  C.cardinal   = lcd.RGB(0xcc, 0xcc, 0xcc) -- cardinal tick marks
  C.major      = lcd.RGB(0x88, 0x88, 0x88) -- 30-degree ticks
  C.minor      = lcd.RGB(0x44, 0x44, 0x44) -- 5-degree ticks
  C.north      = lcd.RGB(0xff, 0x40, 0x40) -- red north indicator
  C.south      = lcd.RGB(0x40, 0x80, 0xff) -- blue south indicator
  C.pointer    = lcd.RGB(0xff, 0x60, 0x00) -- orange heading pointer
  C.center     = lcd.RGB(0xff, 0xff, 0xff) -- white center dot
  C.boxBg      = lcd.RGB(0x1a, 0x1a, 0x2a) -- heading box background
  C.boxBorder  = lcd.RGB(0x40, 0x60, 0x40) -- heading box border
  C.headingText= lcd.RGB(0x00, 0xff, 0x80) -- green heading digits
  C.bearing    = lcd.RGB(0xff, 0xb3, 0x00) -- amber bearing label
  C.text       = lcd.RGB(0xc0, 0xc0, 0xc0) -- body text
  C.dim        = lcd.RGB(0x55, 0x55, 0x55) -- dim text
  C.section    = lcd.RGB(0xff, 0xb3, 0x00) -- section header amber
  C.good       = lcd.RGB(0x4c, 0xaf, 0x50) -- green good
  C.warn       = lcd.RGB(0xff, 0xb3, 0x00) -- amber warning
  C.attBg      = lcd.RGB(0x20, 0x30, 0x50) -- attitude sky blue-dark
  C.attBorder  = lcd.RGB(0x60, 0x80, 0x60) -- attitude ring
  C.ground     = lcd.RGB(0x3a, 0x2a, 0x1a) -- brown ground
  C.horizon    = lcd.RGB(0xff, 0xff, 0x00) -- yellow horizon line
  C.aircraft   = lcd.RGB(0xff, 0xff, 0xff) -- white aircraft symbol

  -- Layout based on screen dimensions
  margin = 6
  titleH = 22

  -- Compass centered in left 2/3 of screen, vertically centered
  centerX = floor(LCD_W * 0.45)
  centerY = floor(LCD_H * 0.48)
  compassR = floor(math.min(LCD_W * 0.35, (LCD_H - titleH - 60) * 0.42))

  -- Attitude indicator in top-right
  attR = floor(compassR * 0.35)

  -- Ensure minimum sizes
  if compassR < 50 then compassR = 50 end
  if attR < 20 then attR = 20 end
end

---------------------------------------------------------------------------
-- Main entry
---------------------------------------------------------------------------

local function run(event, touchState)
  if event == nil then return 0 end
  if event == EVT_VIRTUAL_EXIT then return 1 end
  return runColor(event, touchState)
end

return { init=init, run=run }
