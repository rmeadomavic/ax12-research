-- TNS|Stopwatch|TNE
local LCD_W, LCD_H = LCD_W or 480, LCD_H or 272
local BLACK   = lcd.RGB(0, 0, 0)
local WHITE   = lcd.RGB(255, 255, 255)
local GREEN   = lcd.RGB(0, 220, 80)
local RED     = lcd.RGB(255, 60, 60)
local GREY    = lcd.RGB(100, 100, 100)
local DKGREY  = lcd.RGB(40, 40, 40)
local YELLOW  = lcd.RGB(255, 220, 0)

local running = false
local startTime = 0
local elapsed = 0
local laps = {}
local MAX_LAPS = 5

local countdown = false
local countdownDur = 0
local countdownSet = false
local setDigit = 1
local setDigits = {0, 0, 0, 0}

local function now()
  return getTime() * 10
end

local function fmtTime(ms)
  if ms < 0 then ms = 0 end
  local cs = math.floor(ms / 10) % 100
  local totalSec = math.floor(ms / 1000)
  local s = totalSec % 60
  local m = math.floor(totalSec / 60)
  return string.format("%02d:%02d.%02d", m, s, cs)
end

local function getElapsed()
  if running then
    return elapsed + (now() - startTime)
  end
  return elapsed
end

local function getDisplay()
  local e = getElapsed()
  if countdown and countdownDur > 0 then
    return countdownDur - e
  end
  return e
end

local function init()
  running = false
  elapsed = 0
  startTime = 0
  laps = {}
  countdown = false
  countdownDur = 0
  countdownSet = false
  setDigits = {0, 0, 0, 0}
  setDigit = 1
end

local function reset()
  running = false
  elapsed = 0
  startTime = 0
  laps = {}
end

local function toggleRun()
  if countdownSet then return end
  if running then
    elapsed = elapsed + (now() - startTime)
    running = false
  else
    startTime = now()
    running = true
  end
end

local function addLap()
  if countdownSet then return end
  if not running and elapsed == 0 then return end
  local e = getElapsed()
  local prev = 0
  if #laps > 0 then prev = laps[#laps].total end
  local split = e - prev
  table.insert(laps, {total = e, split = split})
  if #laps > MAX_LAPS then
    table.remove(laps, 1)
  end
end

local function enterCountdownSet()
  if running then return end
  reset()
  countdownSet = true
  countdown = true
  setDigits = {0, 0, 0, 0}
  setDigit = 1
end

local function applyCountdown()
  local m = setDigits[1] * 10 + setDigits[2]
  local s = setDigits[3] * 10 + setDigits[4]
  countdownDur = (m * 60 + s) * 1000
  countdownSet = false
  if countdownDur == 0 then countdown = false end
end

local function drawSetMode(touchState)
  lcd.clear(BLACK)
  lcd.setColor(CUSTOM_COLOR, WHITE)
  lcd.drawText(LCD_W / 2, 20, "SET COUNTDOWN", MIDSIZE + CENTER + CUSTOM_COLOR)

  local bw, bh = 60, 70
  local gap = 10
  local totalW = 4 * bw + 3 * gap + 20
  local sx = (LCD_W - totalW) / 2
  local sy = 60

  for i = 1, 4 do
    local x = sx + (i - 1) * (bw + gap)
    if i > 2 then x = x + 20 end
    local bg = (i == setDigit) and GREEN or DKGREY
    lcd.setColor(CUSTOM_COLOR, bg)
    lcd.drawFilledRectangle(x, sy, bw, bh, CUSTOM_COLOR)
    lcd.setColor(CUSTOM_COLOR, (i == setDigit) and BLACK or WHITE)
    lcd.drawText(x + bw / 2, sy + 8, tostring(setDigits[i]), DBLSIZE + CENTER + CUSTOM_COLOR)
    lcd.setColor(CUSTOM_COLOR, GREY)
    lcd.drawText(x + bw / 2, sy - 16, "+", SMLSIZE + CENTER + CUSTOM_COLOR)
    lcd.drawText(x + bw / 2, sy + bh + 2, "-", SMLSIZE + CENTER + CUSTOM_COLOR)
  end

  lcd.setColor(CUSTOM_COLOR, WHITE)
  lcd.drawText(sx + 2 * (bw + gap) + 6, sy + 15, ":", DBLSIZE + CUSTOM_COLOR)

  lcd.setColor(CUSTOM_COLOR, GREEN)
  lcd.drawFilledRectangle(LCD_W / 2 - 60, 165, 120, 40, CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, BLACK)
  lcd.drawText(LCD_W / 2, 170, "GO", MIDSIZE + CENTER + CUSTOM_COLOR)

  lcd.setColor(CUSTOM_COLOR, RED)
  lcd.drawText(LCD_W / 2, 215, "CANCEL", SMLSIZE + CENTER + CUSTOM_COLOR)

  if touchState and touchState.event == EVT_TOUCH_TAP then
    local tx, ty = touchState.x, touchState.y
    for i = 1, 4 do
      local x = sx + (i - 1) * (bw + gap)
      if i > 2 then x = x + 20 end
      local maxD = 9
      if i == 1 or i == 3 then maxD = 5 end
      if tx >= x and tx <= x + bw then
        if ty >= sy - 20 and ty < sy then
          setDigit = i
          setDigits[i] = (setDigits[i] + 1) % (maxD + 1)
        elseif ty > sy + bh and ty <= sy + bh + 20 then
          setDigit = i
          setDigits[i] = setDigits[i] - 1
          if setDigits[i] < 0 then setDigits[i] = maxD end
        elseif ty >= sy and ty <= sy + bh then
          if setDigit == i then
            setDigits[i] = (setDigits[i] + 1) % (maxD + 1)
          end
          setDigit = i
        end
      end
    end
    if tx >= LCD_W / 2 - 60 and tx <= LCD_W / 2 + 60 and ty >= 165 and ty <= 205 then
      applyCountdown()
    end
    if ty >= 210 and ty <= 240 then
      countdownSet = false
      countdown = false
    end
  end
end

local function run(event, touchState)
  if countdownSet then
    drawSetMode(touchState)
    return 0
  end

  lcd.clear(BLACK)

  local displayMs = getDisplay()
  local isNeg = countdown and displayMs <= 0 and (running or elapsed > 0)
  local timerColor = isNeg and RED or (running and GREEN or WHITE)

  lcd.setColor(CUSTOM_COLOR, GREY)
  lcd.drawText(LCD_W - 8, 4, "RST", SMLSIZE + RIGHT + CUSTOM_COLOR)

  if countdown and countdownDur > 0 then
    lcd.setColor(CUSTOM_COLOR, YELLOW)
    local label = "CDN " .. fmtTime(countdownDur)
    lcd.drawText(8, 4, label, SMLSIZE + CUSTOM_COLOR)
  end

  local timeStr = fmtTime(math.abs(displayMs))
  if isNeg then timeStr = "-" .. timeStr end
  lcd.setColor(CUSTOM_COLOR, timerColor)
  lcd.drawText(LCD_W / 2, 25, timeStr, XXLSIZE + CENTER + CUSTOM_COLOR)

  if isNeg and running then
    local blink = (math.floor(now() / 250) % 2 == 0)
    if blink then
      lcd.setColor(CUSTOM_COLOR, lcd.RGB(80, 0, 0))
      lcd.drawFilledRectangle(0, 0, LCD_W, 4, CUSTOM_COLOR)
      lcd.drawFilledRectangle(0, LCD_H - 4, LCD_W, 4, CUSTOM_COLOR)
    end
  end

  local divY = 90
  lcd.setColor(CUSTOM_COLOR, DKGREY)
  lcd.drawFilledRectangle(10, divY, LCD_W - 20, 1, CUSTOM_COLOR)

  lcd.setColor(CUSTOM_COLOR, running and RED or GREEN)
  lcd.drawText(LCD_W / 4, LCD_H - 20, running and "STOP" or "START", SMLSIZE + CENTER + CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, GREY)
  lcd.drawText(3 * LCD_W / 4, LCD_H - 20, "LAP", SMLSIZE + CENTER + CUSTOM_COLOR)

  if #laps > 0 then
    lcd.setColor(CUSTOM_COLOR, GREY)
    lcd.drawText(20, divY + 8, "LAP", SMLSIZE + CUSTOM_COLOR)
    lcd.drawText(LCD_W / 2 - 40, divY + 8, "SPLIT", SMLSIZE + CUSTOM_COLOR)
    lcd.drawText(LCD_W - 20, divY + 8, "TOTAL", SMLSIZE + RIGHT + CUSTOM_COLOR)
    for i = #laps, math.max(1, #laps - MAX_LAPS + 1), -1 do
      local row = #laps - i
      local y = divY + 28 + row * 22
      if y > LCD_H - 28 then break end
      local c = (i == #laps) and WHITE or GREY
      lcd.setColor(CUSTOM_COLOR, c)
      lcd.drawText(20, y, string.format("#%d", i), SMLSIZE + CUSTOM_COLOR)
      lcd.drawText(LCD_W / 2 - 40, y, fmtTime(laps[i].split), SMLSIZE + CUSTOM_COLOR)
      lcd.drawText(LCD_W - 20, y, fmtTime(laps[i].total), SMLSIZE + RIGHT + CUSTOM_COLOR)
    end
  else
    lcd.setColor(CUSTOM_COLOR, DKGREY)
    lcd.drawText(LCD_W / 2, divY + 35, "Tap left: start / stop", SMLSIZE + CENTER + CUSTOM_COLOR)
    lcd.drawText(LCD_W / 2, divY + 55, "Tap right: lap", SMLSIZE + CENTER + CUSTOM_COLOR)
    lcd.drawText(LCD_W / 2, divY + 75, "Tap timer: countdown mode", SMLSIZE + CENTER + CUSTOM_COLOR)
  end

  if touchState and touchState.event == EVT_TOUCH_TAP then
    local tx, ty = touchState.x, touchState.y
    if tx > LCD_W - 70 and ty < 30 then
      reset()
      return 0
    end
    if ty >= 20 and ty < divY and tx > 60 and tx < LCD_W - 60 then
      if not running and elapsed == 0 then
        enterCountdownSet()
        return 0
      end
    end
    if ty >= divY then
      if tx < LCD_W / 2 then
        toggleRun()
      else
        addLap()
      end
    end
  end

  return 0
end

return { init = init, run = run }
