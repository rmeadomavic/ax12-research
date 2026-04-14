-- TNS|Mission Timer|TNE
-- Military mission phase timer for drone operations
-- Phases: STARTUP > LAUNCH > TRANSIT > ON STATION > RTB > RECOVERY

local phases = {
  { name="STARTUP",    dur=300, color={0,200,200},   label="Pre-Flight" },
  { name="LAUNCH",     dur=60,  color={0,200,0},     label="Takeoff" },
  { name="TRANSIT",    dur=600, color={200,200,0},    label="En Route" },
  { name="ON STATION", dur=900, color={220,160,0},    label="Operations" },
  { name="RTB",        dur=600, color={220,120,0},    label="Return" },
  { name="RECOVERY",   dur=300, color={60,120,220},   label="Post-Flight" },
}

local NUM_PHASES = #phases
local curPhase = 1
local phaseRemain = 0
local missionElapsed = 0
local paused = true
local lastTime = 0
local flashState = false
local flashTick = 0

-- Colors
local BLACK   = lcd.RGB(0, 0, 0)
local DKGREEN = lcd.RGB(10, 30, 10)
local MILGREEN= lcd.RGB(30, 60, 30)
local GRID    = lcd.RGB(20, 50, 20)
local WHITE   = lcd.RGB(255, 255, 255)
local RED     = lcd.RGB(255, 40, 40)
local YELLOW  = lcd.RGB(255, 255, 0)
local GREY    = lcd.RGB(120, 120, 120)
local DKGREY  = lcd.RGB(60, 60, 60)
local LTGREEN = lcd.RGB(100, 200, 100)
local ORANGE  = lcd.RGB(255, 140, 0)

local W = LCD_W or 480
local H = LCD_H or 272

local function phaseColor(idx)
  local c = phases[idx].color
  return lcd.RGB(c[1], c[2], c[3])
end

local function phaseColorDim(idx)
  local c = phases[idx].color
  return lcd.RGB(math.floor(c[1]*0.4), math.floor(c[2]*0.4), math.floor(c[3]*0.4))
end

local function fmtTime(s)
  if s < 0 then s = 0 end
  local m = math.floor(s / 60)
  local sec = s % 60
  return string.format("%02d:%02d", m, sec)
end

local function fmtTimeLong(s)
  if s < 0 then s = 0 end
  local h = math.floor(s / 3600)
  local m = math.floor((s % 3600) / 60)
  local sec = s % 60
  if h > 0 then
    return string.format("%d:%02d:%02d", h, m, sec)
  end
  return string.format("%02d:%02d", m, sec)
end

local function resetAll()
  curPhase = 1
  phaseRemain = phases[1].dur
  missionElapsed = 0
  paused = true
  lastTime = 0
end

local function nextPhase()
  if curPhase < NUM_PHASES then
    curPhase = curPhase + 1
    phaseRemain = phases[curPhase].dur
  else
    paused = true
  end
end

local function drawRect(x, y, w, h, color)
  lcd.drawFilledRectangle(x, y, w, h, color)
end

local function init()
  resetAll()
end

local function run(event, touchState)
  local now = getTime() / 100

  -- Flash toggle ~2Hz
  flashTick = flashTick + 1
  if flashTick >= 5 then
    flashTick = 0
    flashState = not flashState
  end

  -- Time update
  if not paused then
    if lastTime > 0 then
      local dt = math.floor((now - lastTime) + 0.5)
      if dt >= 1 then
        for i = 1, dt do
          if phaseRemain > 0 then
            phaseRemain = phaseRemain - 1
            missionElapsed = missionElapsed + 1
          else
            missionElapsed = missionElapsed + 1
            nextPhase()
          end
        end
        lastTime = now
      end
    else
      lastTime = now
    end
  else
    lastTime = 0
  end

  -- Touch handling
  if touchState then
    local tx = touchState.x or 0
    local ty = touchState.y or 0
    if touchState.event == EVT_TOUCH_TAP then
      -- Top-right corner: reset (70x45 area)
      if tx > W - 70 and ty < 45 then
        resetAll()
      -- Left half: next phase
      elseif tx < W / 2 then
        nextPhase()
      -- Right half: pause/resume
      else
        paused = not paused
      end
    end
  end

  -- Also handle button events for non-touch
  if event == EVT_VIRTUAL_ENTER then
    paused = not paused
  elseif event == EVT_VIRTUAL_NEXT then
    nextPhase()
  elseif event == EVT_VIRTUAL_PREV then
    resetAll()
  end

  -- === DRAWING ===
  lcd.clear(BLACK)

  -- Dark military green background
  drawRect(0, 0, W, H, DKGREEN)

  -- Subtle grid lines
  for gx = 0, W, 20 do
    lcd.drawLine(gx, 0, gx, H, DOTTED, GRID)
  end
  for gy = 0, H, 20 do
    lcd.drawLine(0, gy, W, gy, DOTTED, GRID)
  end

  -- Top bar
  drawRect(0, 0, W, 44, MILGREEN)
  lcd.drawLine(0, 44, W, 44, SOLID, LTGREEN)

  -- Phase indicator: "PHASE 3/6"
  lcd.setColor(CUSTOM_COLOR, WHITE)
  lcd.drawText(8, 4, "PHASE", SMLSIZE + CUSTOM_COLOR)
  lcd.drawText(8, 17, curPhase .. "/" .. NUM_PHASES, MIDSIZE + CUSTOM_COLOR)

  -- Current phase name (large, centered top)
  local pColor = phaseColor(curPhase)
  local warning = phaseRemain <= 30 and phaseRemain > 10
  local critical = phaseRemain <= 10

  if critical and flashState then
    pColor = RED
  elseif warning and flashState then
    pColor = YELLOW
  end

  lcd.setColor(CUSTOM_COLOR, pColor)
  lcd.drawText(W/2, 6, phases[curPhase].name, DBLSIZE + CENTER + CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, GREY)
  lcd.drawText(W/2, 32, phases[curPhase].label, SMLSIZE + CENTER + CUSTOM_COLOR)

  -- Reset button indicator top-right
  lcd.setColor(CUSTOM_COLOR, DKGREY)
  drawRect(W - 65, 2, 60, 20, DKGREY)
  lcd.setColor(CUSTOM_COLOR, GREY)
  lcd.drawText(W - 35, 4, "RST", SMLSIZE + CENTER + CUSTOM_COLOR)

  -- Status indicator top-right
  if paused then
    lcd.setColor(CUSTOM_COLOR, ORANGE)
    lcd.drawText(W - 35, 25, "PAUSE", SMLSIZE + CENTER + CUSTOM_COLOR)
  else
    lcd.setColor(CUSTOM_COLOR, LTGREEN)
    lcd.drawText(W - 35, 25, "RUN", SMLSIZE + CENTER + CUSTOM_COLOR)
  end

  -- === MAIN COUNTDOWN (huge center) ===
  local bgFlash = DKGREEN
  if critical and flashState then
    bgFlash = lcd.RGB(60, 0, 0)
  elseif warning and flashState then
    bgFlash = lcd.RGB(50, 50, 0)
  end
  drawRect(30, 52, W - 60, 90, bgFlash)

  -- Border around countdown
  local borderColor = pColor
  if critical then borderColor = RED end
  lcd.setColor(CUSTOM_COLOR, borderColor)
  lcd.drawRectangle(30, 52, W - 60, 90, CUSTOM_COLOR)

  -- Countdown time
  lcd.setColor(CUSTOM_COLOR, WHITE)
  lcd.drawText(W/2, 60, fmtTime(phaseRemain), XXLSIZE + CENTER + CUSTOM_COLOR)

  -- "REMAINING" label
  lcd.setColor(CUSTOM_COLOR, GREY)
  lcd.drawText(W/2, 120, "REMAINING", SMLSIZE + CENTER + CUSTOM_COLOR)

  -- === PROGRESS BAR ===
  local barX = 30
  local barY = 150
  local barW = W - 60
  local barH = 16

  drawRect(barX, barY, barW, barH, lcd.RGB(15, 25, 15))
  lcd.drawRectangle(barX, barY, barW, barH, MILGREEN)

  local totalDur = phases[curPhase].dur
  local elapsed = totalDur - phaseRemain
  local pct = 0
  if totalDur > 0 then
    pct = elapsed / totalDur
  end
  if pct > 1 then pct = 1 end
  local fillW = math.floor(barW * pct)
  if fillW > 0 then
    drawRect(barX + 1, barY + 1, fillW - 2, barH - 2, phaseColor(curPhase))
  end

  -- Percentage text
  lcd.setColor(CUSTOM_COLOR, WHITE)
  lcd.drawText(W/2, barY + 1, math.floor(pct * 100) .. "%", SMLSIZE + CENTER + CUSTOM_COLOR)

  -- === BOTTOM INFO ROW ===
  local infoY = 175

  -- Mission elapsed time
  lcd.setColor(CUSTOM_COLOR, LTGREEN)
  lcd.drawText(8, infoY, "MISSION", SMLSIZE + CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, WHITE)
  lcd.drawText(8, infoY + 16, fmtTimeLong(missionElapsed), MIDSIZE + CUSTOM_COLOR)

  -- Next phase preview
  lcd.setColor(CUSTOM_COLOR, GREY)
  lcd.drawText(W/2, infoY, "NEXT PHASE", SMLSIZE + CENTER + CUSTOM_COLOR)
  if curPhase < NUM_PHASES then
    local np = curPhase + 1
    lcd.setColor(CUSTOM_COLOR, phaseColorDim(np))
    lcd.drawText(W/2, infoY + 16, phases[np].name .. " (" .. fmtTime(phases[np].dur) .. ")", MIDSIZE + CENTER + CUSTOM_COLOR)
  else
    lcd.setColor(CUSTOM_COLOR, DKGREY)
    lcd.drawText(W/2, infoY + 16, "-- END --", MIDSIZE + CENTER + CUSTOM_COLOR)
  end

  -- TX Battery voltage
  local txv = getValue("tx-voltage")
  if txv == nil or txv == 0 then
    txv = getValue("VFAS")
  end
  local battColor = LTGREEN
  if txv ~= nil and txv > 0 then
    if txv < 6.4 then
      battColor = RED
    elseif txv < 6.8 then
      battColor = ORANGE
    elseif txv < 7.2 then
      battColor = YELLOW
    end
    lcd.setColor(CUSTOM_COLOR, GREY)
    lcd.drawText(W - 8, infoY, "TX BATT", SMLSIZE + RIGHT + CUSTOM_COLOR)
    lcd.setColor(CUSTOM_COLOR, battColor)
    lcd.drawText(W - 8, infoY + 16, string.format("%.1fV", txv), MIDSIZE + RIGHT + CUSTOM_COLOR)
  else
    lcd.setColor(CUSTOM_COLOR, GREY)
    lcd.drawText(W - 8, infoY, "TX BATT", SMLSIZE + RIGHT + CUSTOM_COLOR)
    lcd.setColor(CUSTOM_COLOR, DKGREY)
    lcd.drawText(W - 8, infoY + 16, "N/A", MIDSIZE + RIGHT + CUSTOM_COLOR)
  end

  -- === PHASE TIMELINE (bottom strip) ===
  local tlY = H - 50
  local tlH = 30
  local segW = math.floor((W - 20) / NUM_PHASES)
  local tlX = 10

  lcd.setColor(CUSTOM_COLOR, GREY)
  lcd.drawText(W/2, tlY - 14, "MISSION TIMELINE", SMLSIZE + CENTER + CUSTOM_COLOR)

  for i = 1, NUM_PHASES do
    local sx = tlX + (i - 1) * segW
    local sw = segW - 2

    if i == curPhase then
      drawRect(sx, tlY, sw, tlH, phaseColor(i))
      lcd.setColor(CUSTOM_COLOR, BLACK)
      lcd.drawText(sx + sw/2, tlY + 8, phases[i].name, SMLSIZE + CENTER + CUSTOM_COLOR)
    elseif i < curPhase then
      drawRect(sx, tlY, sw, tlH, phaseColorDim(i))
      lcd.setColor(CUSTOM_COLOR, GREY)
      lcd.drawText(sx + sw/2, tlY + 8, phases[i].name, SMLSIZE + CENTER + CUSTOM_COLOR)
    else
      drawRect(sx, tlY, sw, tlH, lcd.RGB(20, 35, 20))
      lcd.setColor(CUSTOM_COLOR, DKGREY)
      lcd.drawText(sx + sw/2, tlY + 8, phases[i].name, SMLSIZE + CENTER + CUSTOM_COLOR)
    end

    lcd.drawRectangle(sx, tlY, sw, tlH, MILGREEN)
  end

  -- Touch zone hints (very subtle)
  lcd.setColor(CUSTOM_COLOR, lcd.RGB(40, 60, 40))
  lcd.drawText(W/4, H - 8, "< NEXT", SMLSIZE + CENTER + CUSTOM_COLOR)
  lcd.drawText(W*3/4, H - 8, "PAUSE >", SMLSIZE + CENTER + CUSTOM_COLOR)

  return 0
end

return { init=init, run=run }
