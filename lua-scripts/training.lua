-- TNS|Training|TNE
local LCD_W, LCD_H = 480, 272
local DARK = lcd.RGB(18, 18, 24)
local WHITE = lcd.RGB(240, 240, 240)
local GRAY = lcd.RGB(100, 100, 110)
local DIM = lcd.RGB(50, 50, 60)
local GREEN = lcd.RGB(0, 220, 80)
local RED = lcd.RGB(220, 40, 40)

local scenarios = {
  { name="HOVER",     desc="Hold altitude & position",  color=lcd.RGB(0,180,255),  inst="Hold sticks centered" },
  { name="BOX",       desc="Fly a square pattern",      color=lcd.RGB(255,180,0),  inst="Follow waypoint sequence" },
  { name="FIGURE 8",  desc="Fly a figure-8 pattern",    color=lcd.RGB(200,80,255), inst="Smooth curves, constant speed" },
  { name="ORBIT",     desc="Circle a fixed point",      color=lcd.RGB(0,220,180),  inst="Maintain distance & heading" },
  { name="SPEED RUN", desc="Fast line and stop",         color=lcd.RGB(255,60,60),  inst="Full forward, then brake" },
  { name="LANDING",   desc="Smooth descent to zero",     color=lcd.RGB(120,200,60), inst="Lower throttle smoothly" },
}

local STATE_MENU, STATE_READY, STATE_RUN, STATE_DONE = 0, 1, 2, 3
local state = STATE_MENU
local sel = 1
local scroll = 0
local timer = 0
local score = 0
local startTime = 0
local elapsed = 0
local cumErr = 0
local samples = 0
local bestScores = {}
local SCORE_FILE = "/storage/emulated/0/AX12LUA/SCRIPTS/TOOLS/training_best.txt"
local durations = { 15, 30, 25, 30, 10, 20 }
local phase = 0
local phaseTime = 0

local function clamp(v, lo, hi) return math.max(lo, math.min(hi, v)) end

local function loadBest()
  local f = io.open(SCORE_FILE, "r")
  if f then
    for i = 1, #scenarios do
      local line = f:read("*l")
      bestScores[i] = tonumber(line) or 0
    end
    f:close()
  else
    for i = 1, #scenarios do bestScores[i] = 0 end
  end
end

local function saveBest()
  local f = io.open(SCORE_FILE, "w")
  if f then
    for i = 1, #scenarios do f:write(tostring(bestScores[i]) .. "\n") end
    f:close()
  end
end

local function getSticks()
  local ail = getValue("ail") or 0
  local ele = getValue("ele") or 0
  local thr = getValue("thr") or 0
  local rud = getValue("rud") or 0
  return ail, ele, thr, rud
end

local function drawStick(x, y, r, sx, sy, accent)
  lcd.drawFilledCircle(x, y, r, DIM)
  lcd.drawCircle(x, y, r, GRAY)
  local dx = math.floor(sx / 1024 * r)
  local dy = math.floor(-sy / 1024 * r)
  lcd.drawFilledCircle(x + dx, y + dy, 5, accent)
end

local function drawBar(x, y, w, h, pct, col)
  lcd.drawFilledRectangle(x, y, w, h, DIM)
  local fill = math.floor(w * clamp(pct, 0, 1))
  if fill > 0 then lcd.drawFilledRectangle(x, y, fill, h, col) end
  lcd.drawRectangle(x, y, w, h, GRAY)
end

local function drawBtn(x, y, w, h, txt, col)
  lcd.drawFilledRectangle(x, y, w, h, col)
  local tw, th = lcd.sizeText(txt, FONT_STD)
  lcd.drawText(x + (w - tw) / 2, y + (h - th) / 2, txt, WHITE)
end

local function inBox(tx, ty, x, y, w, h)
  return tx >= x and tx <= x + w and ty >= y and ty <= y + h
end

local function init()
  loadBest()
  state = STATE_MENU
  sel = 1
  scroll = 0
end

local function startExercise()
  state = STATE_RUN
  startTime = getTime()
  timer = durations[sel]
  cumErr = 0
  samples = 0
  elapsed = 0
  score = 0
  phase = 0
  phaseTime = getTime()
end

local function computeScore()
  if samples == 0 then return 50 end
  local avgErr = cumErr / samples
  local s = math.floor(100 - avgErr * 100 / 1024)
  return clamp(s, 0, 100)
end

local function getInstruction()
  if sel == 1 then return scenarios[sel].inst
  elseif sel == 2 then
    local wp = {"FWD-RIGHT","RIGHT-BACK","BACK-LEFT","LEFT-FWD"}
    return "Leg " .. (phase % 4 + 1) .. ": " .. (wp[phase % 4 + 1] or "")
  elseif sel == 3 then
    return phase % 2 == 0 and "Curve LEFT" or "Curve RIGHT"
  elseif sel == 4 then return "Hold circle -- steady rudder"
  elseif sel == 5 then
    return phase == 0 and "FULL FORWARD NOW!" or "BRAKE! Center sticks!"
  elseif sel == 6 then
    local pct = math.floor((1 - elapsed / durations[sel]) * 100)
    return "Target throttle: " .. clamp(pct, 0, 100) .. "%"
  end
  return scenarios[sel].inst
end

local function sampleError()
  local ail, ele, thr, rud = getSticks()
  local err = 0
  if sel == 1 then
    err = (math.abs(ail) + math.abs(ele) + math.abs(rud)) / 3
    err = err + math.abs(thr) * 0.5
  elseif sel == 2 then
    local seg = phase % 4
    local target_ail = (seg == 0 or seg == 3) and 0 or ((seg == 1) and 512 or -512)
    local target_ele = (seg == 1 or seg == 2) and 0 or ((seg == 0) and 512 or -512)
    err = (math.abs(ail - target_ail) + math.abs(ele - target_ele)) / 2
    local now = getTime()
    if now - phaseTime > 700 then phase = phase + 1; phaseTime = now end
  elseif sel == 3 then
    local target_ail = phase % 2 == 0 and -400 or 400
    err = math.abs(ail - target_ail) + math.abs(math.abs(ele) - 300)
    err = err / 2
    local now = getTime()
    if now - phaseTime > 500 then phase = phase + 1; phaseTime = now end
  elseif sel == 4 then
    local target_rud = 350
    err = math.abs(rud - target_rud) + math.abs(ail) * 0.5
  elseif sel == 5 then
    if elapsed < durations[sel] * 0.5 then
      phase = 0
      err = math.abs(1024 - ele)
    else
      phase = 1
      err = (math.abs(ele) + math.abs(ail) + math.abs(rud)) / 3
    end
  elseif sel == 6 then
    local target = -1024 + math.floor(2048 * (1 - elapsed / durations[sel]))
    err = math.abs(thr - target)
  end
  cumErr = cumErr + clamp(err, 0, 1024)
  samples = samples + 1
end

local function drawMenu(event, touchState)
  lcd.drawFilledRectangle(0, 0, LCD_W, LCD_H, DARK)
  lcd.drawText(LCD_W / 2 - 80, 6, "TRAINING SCENARIOS", WHITE + FONT_STD)
  lcd.drawLine(10, 28, LCD_W - 10, 28, SOLID, GRAY)
  local ROW_H = 38
  local VISIBLE = 6
  for i = 1, math.min(VISIBLE, #scenarios) do
    local idx = i + scroll
    if idx > #scenarios then break end
    local sc = scenarios[idx]
    local y = 32 + (i - 1) * ROW_H
    local bg = idx == sel and sc.color or DIM
    lcd.drawFilledRectangle(10, y, LCD_W - 20, ROW_H - 4, bg)
    lcd.drawText(18, y + 4, idx .. ". " .. sc.name, WHITE + FONT_STD)
    lcd.drawText(18, y + 19, sc.desc, GRAY + FONT_XS)
    local best = bestScores[idx] or 0
    if best > 0 then
      lcd.drawText(LCD_W - 90, y + 8, "BEST:" .. best, GREEN + FONT_XS)
    end
    if touchState then
      local tx, ty = touchState.x or 0, touchState.y or 0
      if event == EVT_TOUCH_TAP and inBox(tx, ty, 10, y, LCD_W - 20, ROW_H - 4) then
        sel = idx
        state = STATE_READY
      end
    end
  end
end

local function drawReady(event, touchState)
  local sc = scenarios[sel]
  lcd.drawFilledRectangle(0, 0, LCD_W, LCD_H, DARK)
  lcd.drawText(LCD_W / 2 - 60, 20, sc.name, sc.color + FONT_XL)
  lcd.drawText(LCD_W / 2 - 80, 60, sc.desc, WHITE + FONT_STD)
  lcd.drawText(LCD_W / 2 - 90, 90, "Duration: " .. durations[sel] .. "s", GRAY + FONT_STD)
  lcd.drawText(LCD_W / 2 - 90, 115, "Instruction: " .. sc.inst, WHITE + FONT_XS)
  local best = bestScores[sel] or 0
  if best > 0 then
    lcd.drawText(LCD_W / 2 - 50, 145, "Best Score: " .. best, GREEN + FONT_STD)
  end
  drawBtn(LCD_W / 2 - 60, 185, 120, 36, "START", sc.color)
  drawBtn(20, 185, 80, 36, "BACK", GRAY)
  if touchState and event == EVT_TOUCH_TAP then
    local tx, ty = touchState.x or 0, touchState.y or 0
    if inBox(tx, ty, LCD_W / 2 - 60, 185, 120, 36) then startExercise() end
    if inBox(tx, ty, 20, 185, 80, 36) then state = STATE_MENU end
  end
end

local function drawRun(event, touchState)
  local sc = scenarios[sel]
  local now = getTime()
  elapsed = (now - startTime) / 100
  local remaining = math.max(0, timer - elapsed)
  sampleError()
  if remaining <= 0 then
    score = computeScore()
    state = STATE_DONE
    if score > (bestScores[sel] or 0) then
      bestScores[sel] = score
      saveBest()
    end
    return
  end
  lcd.drawFilledRectangle(0, 0, LCD_W, LCD_H, DARK)
  lcd.drawText(10, 4, sc.name, sc.color + FONT_STD)
  local tStr = string.format("%d:%02d", math.floor(remaining / 60), math.floor(remaining) % 60)
  lcd.drawText(LCD_W / 2 - 30, 2, tStr, WHITE + FONT_XXL)
  drawBar(10, 38, LCD_W - 20, 10, elapsed / timer, sc.color)
  lcd.drawText(10, 56, getInstruction(), WHITE + FONT_STD)
  local liveScore = computeScore()
  local sCol = liveScore >= 70 and GREEN or (liveScore >= 40 and sc.color or RED)
  lcd.drawText(LCD_W - 120, 56, "SCORE: " .. liveScore, sCol + FONT_STD)
  local ail, ele, thr, rud = getSticks()
  drawStick(100, 180, 50, ail, ele, sc.color)
  drawStick(380, 180, 50, rud, thr, sc.color)
  lcd.drawText(70, 240, "AIL/ELE", GRAY + FONT_XS)
  lcd.drawText(350, 240, "RUD/THR", GRAY + FONT_XS)
  drawBar(180, 100, 120, 12, (thr + 1024) / 2048, sc.color)
  lcd.drawText(185, 115, "THR", GRAY + FONT_XS)
  drawBar(180, 140, 120, 12, (ail + 1024) / 2048, sc.color)
  lcd.drawText(185, 155, "AIL", GRAY + FONT_XS)
  drawBar(180, 170, 120, 12, (ele + 1024) / 2048, sc.color)
  lcd.drawText(185, 185, "ELE", GRAY + FONT_XS)
  drawBar(180, 200, 120, 12, (rud + 1024) / 2048, sc.color)
  lcd.drawText(185, 215, "RUD", GRAY + FONT_XS)
end

local function drawDone(event, touchState)
  local sc = scenarios[sel]
  lcd.drawFilledRectangle(0, 0, LCD_W, LCD_H, DARK)
  lcd.drawText(LCD_W / 2 - 70, 10, "EXERCISE COMPLETE", WHITE + FONT_STD)
  lcd.drawText(LCD_W / 2 - 40, 40, sc.name, sc.color + FONT_XL)
  local sCol = score >= 70 and GREEN or (score >= 40 and sc.color or RED)
  lcd.drawText(LCD_W / 2 - 30, 85, tostring(score), sCol + FONT_XXL)
  lcd.drawText(LCD_W / 2 - 20, 120, "/ 100", GRAY + FONT_STD)
  local tStr = string.format("Time: %ds", durations[sel])
  lcd.drawText(LCD_W / 2 - 40, 148, tStr, WHITE + FONT_STD)
  local best = bestScores[sel] or 0
  if score >= best then
    lcd.drawText(LCD_W / 2 - 50, 170, "NEW BEST!", GREEN + FONT_STD)
  else
    lcd.drawText(LCD_W / 2 - 50, 170, "Best: " .. best, GRAY + FONT_STD)
  end
  local hasNext = sel < #scenarios
  if hasNext then drawBtn(LCD_W / 2 + 10, 210, 100, 36, "NEXT", sc.color) end
  drawBtn(20, 210, 100, 36, "RETRY", GRAY)
  drawBtn(LCD_W / 2 - 50, 210, 100, 36, "MENU", DIM)
  if not hasNext then
    drawBtn(LCD_W / 2 + 10, 210, 100, 36, "MENU", DIM)
  end
  if touchState and event == EVT_TOUCH_TAP then
    local tx, ty = touchState.x or 0, touchState.y or 0
    if inBox(tx, ty, 20, 210, 100, 36) then state = STATE_READY end
    if inBox(tx, ty, LCD_W / 2 - 50, 210, 100, 36) then state = STATE_MENU end
    if hasNext and inBox(tx, ty, LCD_W / 2 + 10, 210, 100, 36) then
      sel = sel + 1
      state = STATE_READY
    end
  end
end

local function run(event, touchState)
  if state == STATE_MENU then drawMenu(event, touchState)
  elseif state == STATE_READY then drawReady(event, touchState)
  elseif state == STATE_RUN then drawRun(event, touchState)
  elseif state == STATE_DONE then drawDone(event, touchState)
  end
  return 0
end

return { init=init, run=run }
