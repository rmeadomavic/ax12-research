-- TNS|Motor Test|TNE
-- Motor/ESC test display for quadcopter
-- Shows 4 motors with throttle fill, RPM, spin direction, armed state
-- Touch center area to toggle X / + frame layout

local frameX = true
local W, H, cx, cy
local motorR = 32
local lastTouch = 0
local mPos = {}

local BG       = lcd.RGB(18, 18, 24)
local FG       = lcd.RGB(200, 200, 210)
local DIM      = lcd.RGB(80, 80, 100)
local GREEN    = lcd.RGB(0, 200, 60)
local YELLOW   = lcd.RGB(240, 200, 0)
local RED      = lcd.RGB(240, 40, 40)
local ARMED_C  = lcd.RGB(240, 60, 60)
local DISARM_C = lcd.RGB(60, 180, 60)
local CIRCLE_BG = lcd.RGB(36, 36, 48)
local ARROW_C  = lcd.RGB(130, 130, 160)
local FRAME_C  = lcd.RGB(50, 50, 70)

local motorCW = { true, true, false, false }

local function calcPositions()
  W = LCD_W or 480
  H = LCD_H or 272
  cx = math.floor(W / 2)
  cy = math.floor(H / 2)
  local spread = math.min(W, H) * 0.32
  if frameX then
    local d = spread * 0.707
    mPos = {
      { x = cx + d, y = cy - d, label = "FR" },
      { x = cx - d, y = cy + d, label = "BL" },
      { x = cx - d, y = cy - d, label = "FL" },
      { x = cx + d, y = cy + d, label = "BR" },
    }
  else
    mPos = {
      { x = cx,          y = cy - spread, label = "F" },
      { x = cx,          y = cy + spread, label = "B" },
      { x = cx - spread, y = cy,          label = "L" },
      { x = cx + spread, y = cy,          label = "R" },
    }
  end
end

local function getThrottle()
  local thr = getValue("thr")
  if thr == nil then thr = -1024 end
  return math.floor(((thr + 1024) / 2048) * 100 + 0.5)
end

local function getMotorPct(i)
  local src = getValue("esc" .. i)
  if src and src ~= 0 then
    return math.max(0, math.min(100, math.floor(src + 0.5)))
  end
  return getThrottle()
end

local function getRPM(i)
  local src = getValue("erpm" .. i)
  if src and src ~= 0 then return math.floor(src) end
  return nil
end

local function isArmed()
  local sa = getValue("sa")
  if sa and sa > 0 then return true end
  local armed = getValue("armed")
  if armed and armed > 0 then return true end
  return false
end

local function thrColor(pct)
  if pct >= 90 then return RED
  elseif pct >= 60 then return YELLOW
  else return GREEN end
end

local function drawMotorCircle(x, y, pct, rpm, cw, label)
  x = math.floor(x)
  y = math.floor(y)
  lcd.drawFilledCircle(x, y, motorR, CIRCLE_BG)
  lcd.drawCircle(x, y, motorR, DIM)
  if pct > 0 then
    local fillH = math.floor(motorR * 2 * pct / 100)
    local col = thrColor(pct)
    for row = 0, fillH - 1 do
      local py = y + motorR - row
      if py >= y - motorR and py <= y + motorR then
        local dy = py - y
        local hw = math.floor(math.sqrt(math.max(0, motorR * motorR - dy * dy)))
        if hw > 0 then
          lcd.drawFilledRectangle(x - hw, py, hw * 2, 1, col)
        end
      end
    end
    lcd.drawCircle(x, y, motorR, DIM)
  end
  lcd.drawText(x, y - motorR + 3, label, FONT_XS + FG + CENTER)
  lcd.drawText(x, y - 4, pct .. "%", FONT_S + FG + CENTER)
  if rpm then
    lcd.drawText(x, y + 10, rpm, FONT_XS + DIM + CENTER)
  end
  local aOff = motorR + 6
  if cw then
    lcd.drawLine(x + aOff, y - 4, x + aOff - 4, y - 8, SOLID, ARROW_C)
    lcd.drawLine(x + aOff, y - 4, x + aOff - 1, y - 9, SOLID, ARROW_C)
    lcd.drawText(x + aOff - 8, y - 18, "CW", FONT_XS + ARROW_C)
  else
    lcd.drawLine(x - aOff, y - 4, x - aOff + 4, y - 8, SOLID, ARROW_C)
    lcd.drawLine(x - aOff, y - 4, x - aOff + 1, y - 9, SOLID, ARROW_C)
    lcd.drawText(x - aOff + 8, y - 18, "CCW", FONT_XS + ARROW_C + CENTER)
  end
end

local function drawFrame()
  for i = 1, #mPos do
    lcd.drawLine(
      math.floor(mPos[i].x), math.floor(mPos[i].y),
      cx, cy, DOTTED, FRAME_C
    )
  end
end

local function drawCenter(thr, armed)
  lcd.drawFilledCircle(cx, cy, 18, CIRCLE_BG)
  lcd.drawCircle(cx, cy, 18, DIM)
  lcd.drawText(cx, cy - 6, thr .. "%", FONT_S + FG + CENTER)
  if armed then
    lcd.drawText(cx, cy + 24, "ARMED", FONT_S + ARMED_C + CENTER)
  else
    lcd.drawText(cx, cy + 24, "SAFE", FONT_S + DISARM_C + CENTER)
  end
  local fLabel = frameX and "X-FRAME" or "+-FRAME"
  lcd.drawText(cx, cy + 40, fLabel, FONT_XS + DIM + CENTER)
  lcd.drawText(cx, cy + 52, "tap to toggle", FONT_XS + DIM + CENTER)
end

local function drawHeader()
  lcd.drawText(4, 2, "MOTOR TEST", FONT_S + FG)
  lcd.drawText(W - 4, 2, "THR", FONT_XS + DIM + RIGHT)
end

local function init()
  calcPositions()
end

local function run(event, touchState)
  lcd.clear(BG)
  if touchState then
    local now = getTime()
    if now - lastTouch > 50 then
      local tx = touchState.x or 0
      local ty = touchState.y or 0
      local dx = tx - cx
      local dy = ty - cy
      if (dx * dx + dy * dy) < 3600 then
        frameX = not frameX
        calcPositions()
        lastTouch = now
      end
    end
  end
  local thr = getThrottle()
  local armed = isArmed()
  drawHeader()
  drawFrame()
  for i = 1, 4 do
    local pct = getMotorPct(i)
    local rpm = getRPM(i)
    drawMotorCircle(
      mPos[i].x, mPos[i].y,
      pct, rpm, motorCW[i], mPos[i].label
    )
  end
  drawCenter(thr, armed)
  return 0
end

return { init = init, run = run }
