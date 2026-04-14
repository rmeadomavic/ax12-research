-- TNS|Servo Test|TNE
-- Servo/Motor Output Tester for ArduPilot/Betaflight/INAV
-- Displays 8 output channels with visual servo arc indicators

local LCD_W, LCD_H = LCD_W or 480, LCD_H or 272
local sel = 1
local channels = {}
local armed = false

-- Military green palette
local C_BG       = lcd.RGB(20, 28, 20)
local C_PANEL    = lcd.RGB(30, 42, 30)
local C_BORDER   = lcd.RGB(60, 80, 60)
local C_TEXT     = lcd.RGB(180, 200, 170)
local C_DIM      = lcd.RGB(80, 100, 75)
local C_WHITE    = lcd.RGB(230, 240, 220)
local C_RED      = lcd.RGB(200, 50, 40)
local C_GREEN    = lcd.RGB(50, 180, 60)
local C_YELLOW   = lcd.RGB(200, 190, 50)
local C_SEL      = lcd.RGB(70, 110, 70)
local C_NEEDLE   = lcd.RGB(255, 200, 50)
local C_CENTER   = lcd.RGB(200, 210, 190)
local C_ARMED_BG = lcd.RGB(120, 30, 25)

-- Channel labels for common mappings
local CH_LABELS = {
  "A/Ail", "E/Ele", "T/Thr", "R/Rud",
  "CH5", "CH6", "CH7", "CH8"
}

local function init()
  for i = 1, 8 do
    channels[i] = { pwm = 1500, name = CH_LABELS[i] }
  end
end

-- Map PWM 1000-2000 to angle 0-pi
local function pwmToAngle(pwm)
  local p = math.max(1000, math.min(2000, pwm))
  return ((p - 1000) / 1000) * math.pi
end

-- Map PWM to percentage -100 to +100
local function pwmToPct(pwm)
  return math.floor(((pwm - 1500) / 500) * 100 + 0.5)
end

-- Draw a small servo arc (grid view)
local function drawMiniArc(cx, cy, r, pwm, selected)
  local steps = 12
  for i = 1, steps do
    local a = math.pi - (i / steps) * math.pi
    local pa = math.pi - ((i - 1) / steps) * math.pi
    local x0 = cx + math.floor(r * math.cos(pa))
    local y0 = cy - math.floor(r * math.sin(pa))
    local x1 = cx + math.floor(r * math.cos(a))
    local y1 = cy - math.floor(r * math.sin(a))
    local segColor = (i <= 2 or i >= steps - 1) and C_RED or C_GREEN
    lcd.drawLine(x0, y0, x1, y1, SOLID, segColor)
  end
  -- Center tick
  lcd.drawLine(cx, cy - r + 2, cx, cy - r + 5, SOLID, C_CENTER)
  -- Needle
  local angle = math.pi - pwmToAngle(pwm)
  local nx = cx + math.floor((r - 3) * math.cos(angle))
  local ny = cy - math.floor((r - 3) * math.sin(angle))
  lcd.drawLine(cx, cy, nx, ny, SOLID, selected and C_NEEDLE or C_WHITE)
  -- Pivot dot
  lcd.drawFilledRectangle(cx - 1, cy - 1, 3, 3, C_WHITE)
end

-- Draw the large detailed arc (selected channel)
local function drawDetailArc(cx, cy, r, pwm)
  local steps = 36
  for i = 1, steps do
    local a = math.pi - (i / steps) * math.pi
    local pa = math.pi - ((i - 1) / steps) * math.pi
    local x0 = cx + math.floor(r * math.cos(pa))
    local y0 = cy - math.floor(r * math.sin(pa))
    local x1 = cx + math.floor(r * math.cos(a))
    local y1 = cy - math.floor(r * math.sin(a))
    local segColor
    if i <= 3 or i >= steps - 2 then
      segColor = C_RED
    elseif i <= 6 or i >= steps - 5 then
      segColor = C_YELLOW
    else
      segColor = C_GREEN
    end
    lcd.drawLine(x0, y0, x1, y1, SOLID, segColor)
  end
  -- Inner arc
  local ri = r - 6
  for i = 1, steps do
    local a = math.pi - (i / steps) * math.pi
    local pa = math.pi - ((i - 1) / steps) * math.pi
    local x0 = cx + math.floor(ri * math.cos(pa))
    local y0 = cy - math.floor(ri * math.sin(pa))
    local x1 = cx + math.floor(ri * math.cos(a))
    local y1 = cy - math.floor(ri * math.sin(a))
    lcd.drawLine(x0, y0, x1, y1, SOLID, C_BORDER)
  end
  -- Tick marks at 0%, 25%, 50%, 75%, 100%
  local ticks = { 0, 0.25, 0.5, 0.75, 1.0 }
  for _, t in ipairs(ticks) do
    local a = math.pi - t * math.pi
    local ox = cx + math.floor((r + 4) * math.cos(a))
    local oy = cy - math.floor((r + 4) * math.sin(a))
    local ix = cx + math.floor((r - 8) * math.cos(a))
    local iy = cy - math.floor((r - 8) * math.sin(a))
    local tc = (t == 0.5) and C_CENTER or C_DIM
    lcd.drawLine(ox, oy, ix, iy, SOLID, tc)
  end
  -- Endpoint labels
  lcd.drawText(cx - r - 12, cy + 2, "1000", SMLSIZE + C_DIM)
  lcd.drawText(cx - 5, cy - r - 14, "1500", SMLSIZE + C_CENTER)
  lcd.drawText(cx + r - 2, cy + 2, "2000", SMLSIZE + C_DIM)
  -- Needle
  local angle = math.pi - pwmToAngle(pwm)
  local nx = cx + math.floor((r - 10) * math.cos(angle))
  local ny = cy - math.floor((r - 10) * math.sin(angle))
  lcd.drawLine(cx, cy, nx, ny, SOLID, C_NEEDLE)
  lcd.drawLine(cx + 1, cy, nx + 1, ny, SOLID, C_NEEDLE)
  -- Pivot
  lcd.drawFilledRectangle(cx - 2, cy - 2, 5, 5, C_NEEDLE)
end

local function run(event, touchState)
  -- Read channel values from radio outputs
  for i = 1, 8 do
    local val = getValue("ch" .. i)
    if val then
      channels[i].pwm = math.floor(val / 10.24 + 1500 + 0.5)
      channels[i].pwm = math.max(1000, math.min(2000, channels[i].pwm))
    end
  end

  -- Armed state: CH5 > 1700 is common convention
  armed = channels[5].pwm > 1700

  -- Handle touch input
  if touchState and event == EVT_TOUCH_TAP then
    local tx, ty = touchState.x, touchState.y
    if tx < LCD_W * 0.42 then
      local col = (tx < LCD_W * 0.21) and 0 or 1
      local row = math.floor((ty - 30) / 56)
      row = math.max(0, math.min(3, row))
      local ch = row * 2 + col + 1
      if ch >= 1 and ch <= 8 then sel = ch end
    end
  end

  -- Handle rotary/button navigation
  if event == EVT_VIRTUAL_PREV or event == EVT_ROT_LEFT then
    sel = sel > 1 and sel - 1 or 8
  elseif event == EVT_VIRTUAL_NEXT or event == EVT_ROT_RIGHT then
    sel = sel < 8 and sel + 1 or 1
  end

  -- Clear
  lcd.clear(C_BG)

  -- Header bar
  local hdrColor = armed and C_ARMED_BG or C_PANEL
  lcd.drawFilledRectangle(0, 0, LCD_W, 22, hdrColor)
  lcd.drawText(4, 3, "SERVO TEST", BOLD + C_WHITE)
  local stateText = armed and "ARMED" or "DISARMED"
  local stateColor = armed and C_RED or C_GREEN
  lcd.drawText(LCD_W - 80, 3, stateText, BOLD + stateColor)
  lcd.drawLine(0, 22, LCD_W, 22, SOLID, C_BORDER)

  -- Left panel: 2x4 grid of mini servo arcs
  local gx0, gy0 = 4, 28
  local cellW, cellH = 96, 56
  for i = 1, 8 do
    local col = (i - 1) % 2
    local row = math.floor((i - 1) / 2)
    local cx = gx0 + col * cellW + cellW / 2
    local cy = gy0 + row * cellH + 30
    local isSel = (i == sel)

    if isSel then
      lcd.drawFilledRectangle(gx0 + col * cellW, gy0 + row * cellH,
        cellW - 2, cellH - 2, C_SEL)
    end
    lcd.drawRectangle(gx0 + col * cellW, gy0 + row * cellH,
      cellW - 2, cellH - 2, isSel and C_NEEDLE or C_BORDER)

    lcd.drawText(gx0 + col * cellW + 3, gy0 + row * cellH + 2,
      "CH" .. i, SMLSIZE + (isSel and C_NEEDLE or C_DIM))
    lcd.drawText(gx0 + col * cellW + cellW - 42, gy0 + row * cellH + 2,
      channels[i].pwm .. "us", SMLSIZE + C_TEXT)

    drawMiniArc(cx, cy, 16, channels[i].pwm, isSel)
  end

  -- Right panel: detailed view of selected channel
  local rpx = 200
  lcd.drawFilledRectangle(rpx, 24, LCD_W - rpx, LCD_H - 24, C_PANEL)
  lcd.drawRectangle(rpx, 24, LCD_W - rpx, LCD_H - 24, C_BORDER)

  local ch = channels[sel]
  local detailCx = rpx + (LCD_W - rpx) / 2
  local detailCy = 140

  -- Channel title
  lcd.drawText(rpx + 8, 28, "CH" .. sel .. " - " .. ch.name,
    MIDSIZE + C_NEEDLE)

  -- Large arc
  drawDetailArc(detailCx, detailCy, 70, ch.pwm)

  -- PWM value large
  lcd.drawText(detailCx - 30, detailCy + 12, ch.pwm .. " us",
    MIDSIZE + C_WHITE)

  -- Percentage
  local pct = pwmToPct(ch.pwm)
  local pctStr = (pct >= 0 and "+" or "") .. pct .. "%"
  local pctColor = math.abs(pct) < 5 and C_CENTER
    or (math.abs(pct) > 80 and C_RED or C_GREEN)
  lcd.drawText(detailCx - 18, detailCy + 34, pctStr, BOLD + pctColor)

  -- Bar graph at bottom of detail panel
  local barX = rpx + 16
  local barY = LCD_H - 30
  local barW = LCD_W - rpx - 32
  local barH = 14
  lcd.drawRectangle(barX, barY, barW, barH, C_BORDER)
  local fill = math.floor(((ch.pwm - 1000) / 1000) * (barW - 2))
  local barColor = math.abs(pct) > 80 and C_RED or C_GREEN
  lcd.drawFilledRectangle(barX + 1, barY + 1, fill, barH - 2, barColor)
  -- Center marker on bar
  local cm = barX + math.floor(barW / 2)
  lcd.drawLine(cm, barY - 2, cm, barY + barH + 1, SOLID, C_CENTER)

  -- Source label
  lcd.drawText(rpx + 8, LCD_H - 48, "SRC: " .. ch.name, SMLSIZE + C_DIM)

  return 0
end

return { init = init, run = run }
