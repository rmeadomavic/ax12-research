-- TNS|AX12 Dashboard|TNE
---- #########################################################################
---- #                                                                       #
---- # AX12 Dashboard -- Community Showcase Script                           #
---- # Real-time gimbals, switches, battery, and ELRS link display           #
---- #                                                                       #
---- # RadioMaster AX12 | github.com/rmeadomavic/ax12-research               #
---- #                                                                       #
---- #########################################################################

---------------------------------------------------------------------------
-- State
---------------------------------------------------------------------------

local startTime = 0
local isColor = false

-- Color palette (populated in init when lcd.RGB is available)
local C = {}

-- Layout metrics (computed from LCD_W / LCD_H in init)
local titleH, rowH, margin, gap
local barW, barH
local col2X

---------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------

local function clamp(v, lo, hi)
  return (v < lo) and lo or (v > hi) and hi or v
end

local function switchLabel(v)
  if v == nil then return "N/A"
  elseif v < -100 then return "DN"
  elseif v > 100 then return "UP"
  else return "MID" end
end

-- EdgeTX returns tx-voltage in varying units across builds
local function fmtVolts(v)
  if v > 100 then return string.format("%.2fV", v / 100) end
  if v > 20  then return string.format("%.1fV", v / 10) end
  return string.format("%.1fV", v)
end

---------------------------------------------------------------------------
-- Color-LCD drawing functions
---------------------------------------------------------------------------

local function drawTitle()
  local elapsed = math.floor((getTime() - startTime) / 100)
  local mm = math.floor(elapsed / 60)
  local ss = elapsed % 60

  lcd.setColor(CUSTOM_COLOR, C.titleBg)
  lcd.drawFilledRectangle(0, 0, LCD_W, titleH, CUSTOM_COLOR)

  local ty = math.floor((titleH - rowH) / 2)
  lcd.setColor(CUSTOM_COLOR, C.titleFg)
  lcd.drawText(margin, ty, "AX12 Dashboard", BOLD + CUSTOM_COLOR)
  lcd.drawText(LCD_W - margin, ty,
    string.format("%02d:%02d", mm, ss), RIGHT + BOLD + CUSTOM_COLOR)
end

local function drawSection(x, y, label, w)
  lcd.setColor(CUSTOM_COLOR, C.section)
  lcd.drawText(x, y, label, BOLD + CUSTOM_COLOR)
  lcd.drawLine(x, y + rowH, x + w, y + rowH, SOLID, FORCE)
  return y + rowH + gap
end

local function drawBar(x, y, label, val)
  -- Label
  lcd.setColor(CUSTOM_COLOR, C.text)
  lcd.drawText(x, y, label, CUSTOM_COLOR)

  local bx = x + 34

  -- Bar background
  lcd.setColor(CUSTOM_COLOR, C.barBg)
  lcd.drawFilledRectangle(bx, y, barW, barH, CUSTOM_COLOR)

  if val ~= nil then
    -- Fill from center toward current value
    local cx = math.floor(barW / 2)
    local px = math.floor(clamp(val, -1024, 1024) / 1024 * cx)

    lcd.setColor(CUSTOM_COLOR, C.barFill)
    if px >= 0 then
      lcd.drawFilledRectangle(bx + cx, y + 1,
        math.max(px, 1), barH - 2, CUSTOM_COLOR)
    else
      lcd.drawFilledRectangle(bx + cx + px, y + 1,
        math.max(-px, 1), barH - 2, CUSTOM_COLOR)
    end

    -- Center tick mark
    lcd.setColor(CUSTOM_COLOR, C.centerTick)
    lcd.drawLine(bx + cx, y, bx + cx, y + barH - 1, SOLID, FORCE)

    -- Numeric readout
    lcd.setColor(CUSTOM_COLOR, C.text)
    lcd.drawText(bx + barW + 5, y, tostring(val), CUSTOM_COLOR)
  else
    lcd.setColor(CUSTOM_COLOR, C.dim)
    lcd.drawText(bx + barW + 5, y, "N/A", CUSTOM_COLOR)
  end

  -- Border
  lcd.setColor(CUSTOM_COLOR, C.border)
  lcd.drawRectangle(bx, y, barW, barH, CUSTOM_COLOR)
end

local function drawSwitch(x, y, name, val)
  -- Switch name
  lcd.setColor(CUSTOM_COLOR, C.text)
  lcd.drawText(x, y, name .. ":", CUSTOM_COLOR)

  -- Color-coded status
  local color
  if val == nil then     color = C.dim
  elseif val < -100 then color = C.bad
  elseif val > 100 then  color = C.good
  else                   color = C.warn
  end

  lcd.setColor(CUSTOM_COLOR, color)
  lcd.drawFilledRectangle(x + 26, y + 2, 8, rowH - 4, CUSTOM_COLOR)
  lcd.drawText(x + 38, y, switchLabel(val), BOLD + CUSTOM_COLOR)
end

local function drawSensor(x, y, label, source, unit)
  lcd.setColor(CUSTOM_COLOR, C.text)
  lcd.drawText(x, y, label .. ": ", CUSTOM_COLOR)
  local lw = (lcd.sizeText and lcd.sizeText(label .. ": ")) or (#label * 8 + 16)

  local val = getValue(source)
  if val ~= nil and val ~= 0 then
    lcd.setColor(CUSTOM_COLOR, C.good)
    lcd.drawText(x + lw, y, tostring(val) .. " " .. unit, CUSTOM_COLOR)
  else
    lcd.setColor(CUSTOM_COLOR, C.dim)
    lcd.drawText(x + lw, y, "N/A", CUSTOM_COLOR)
  end
end

---------------------------------------------------------------------------
-- Main frame renderers
---------------------------------------------------------------------------

local function runColor(event)
  lcd.clear()

  -- Dark background fill
  lcd.setColor(CUSTOM_COLOR, C.bg)
  lcd.drawFilledRectangle(0, 0, LCD_W, LCD_H, CUSTOM_COLOR)

  -- Accent border
  lcd.setColor(CUSTOM_COLOR, C.accent)
  lcd.drawRectangle(0, 0, LCD_W, LCD_H, CUSTOM_COLOR)

  -- Title bar
  drawTitle()

  -- ===== Left column: Gimbals + Battery =====
  local lx = margin
  local colW = col2X - lx - gap
  local y = drawSection(lx, titleH + gap, "GIMBALS", colW)

  local sticks = {{"Ail", "ail"}, {"Ele", "ele"}, {"Thr", "thr"}, {"Rud", "rud"}}
  for _, s in ipairs(sticks) do
    drawBar(lx, y, s[1], getValue(s[2]))
    y = y + barH + gap
  end

  y = y + gap
  y = drawSection(lx, y, "BATTERY", colW)

  local txV = getValue("tx-voltage")
  if txV ~= nil and txV ~= 0 then
    lcd.setColor(CUSTOM_COLOR, C.text)
    lcd.drawText(lx, y, fmtVolts(txV), MIDSIZE + CUSTOM_COLOR)
  else
    lcd.setColor(CUSTOM_COLOR, C.dim)
    lcd.drawText(lx, y, "N/A", MIDSIZE + CUSTOM_COLOR)
  end

  -- ===== Right column: Switches + Link =====
  local rx = col2X
  local rColW = LCD_W - rx - margin
  y = drawSection(rx, titleH + gap, "SWITCHES", rColW)

  local swNames = {"SA", "SB", "SC", "SD"}
  local swSrcs  = {"sa", "sb", "sc", "sd"}
  for i = 1, 4 do
    drawSwitch(rx, y, swNames[i], getValue(swSrcs[i]))
    y = y + rowH + 4
  end

  y = y + gap
  y = drawSection(rx, y, "ELRS LINK", rColW)

  drawSensor(rx, y, "LQ", "RQly", "%")
  y = y + rowH + 4
  drawSensor(rx, y, "RSSI", "1RSS", "dBm")
  y = y + rowH + 4
  drawSensor(rx, y, "TXpwr", "TPWR", "mW")

  return 0
end

local function runBW(event)
  lcd.clear()
  lcd.drawText(0, 0, "AX12 Dashboard", INVERS)

  local y = 10
  local sticks = {{"A","ail"}, {"E","ele"}, {"T","thr"}, {"R","rud"}}
  for _, s in ipairs(sticks) do
    local v = getValue(s[2])
    lcd.drawText(0, y, s[1] .. ":" .. tostring(v or 0))
    y = y + 9
  end

  y = 10
  local sws = {"sa", "sb", "sc", "sd"}
  for _, sw in ipairs(sws) do
    lcd.drawText(LCD_W - 50, y,
      string.upper(sw) .. ":" .. switchLabel(getValue(sw)))
    y = y + 9
  end

  return 0
end

---------------------------------------------------------------------------
-- Init
---------------------------------------------------------------------------

local function init()
  startTime = getTime()
  isColor = (lcd.RGB ~= nil)

  if isColor then
    -- Dark theme color palette
    C.bg        = lcd.RGB(0x1a, 0x1a, 0x2e) -- navy background
    C.titleBg   = lcd.RGB(0x2d, 0x6b, 0x2d) -- forest green title
    C.titleFg   = lcd.RGB(0xff, 0xff, 0xff) -- white title text
    C.section   = lcd.RGB(0xff, 0xb3, 0x00) -- amber section headers
    C.text      = lcd.RGB(0xe0, 0xe0, 0xe0) -- light grey body text
    C.dim       = lcd.RGB(0x55, 0x55, 0x55) -- dim grey for N/A
    C.barBg     = lcd.RGB(0x30, 0x30, 0x40) -- dark bar background
    C.barFill   = lcd.RGB(0x4c, 0xaf, 0x50) -- green bar fill
    C.border    = lcd.RGB(0x60, 0x60, 0x70) -- bar border
    C.centerTick= lcd.RGB(0xff, 0xff, 0xff) -- white center tick
    C.good      = lcd.RGB(0x4c, 0xaf, 0x50) -- green (UP / good signal)
    C.warn      = lcd.RGB(0xff, 0xb3, 0x00) -- amber (MID)
    C.bad       = lcd.RGB(0xf4, 0x43, 0x36) -- red (DN / weak signal)
    C.accent    = lcd.RGB(0x43, 0x61, 0xaa) -- blue accent border

    -- Derive text height from the font engine
    local _, th
    if lcd.sizeText then
      _, th = lcd.sizeText("Ag")
    end
    rowH = th or 20

    -- Layout metrics
    margin  = 6
    gap     = 6
    titleH  = rowH + 10
    barH    = rowH
    col2X   = math.floor(LCD_W * 0.55)
    barW    = col2X - margin - 34 - gap - 5
  else
    -- Minimal B&W layout
    rowH    = 8
    margin  = 1
    gap     = 2
    titleH  = 10
    barH    = 8
    col2X   = math.floor(LCD_W / 2)
    barW    = 40
  end
end

---------------------------------------------------------------------------
-- Main entry
---------------------------------------------------------------------------

local function run(event, touchState)
  -- event is nil when LCD access is revoked; don't draw
  if event == nil then return 0 end

  -- Back / exit
  if event == EVT_VIRTUAL_EXIT then return 1 end

  if isColor then
    return runColor(event)
  else
    return runBW(event)
  end
end

return { init=init, run=run }
