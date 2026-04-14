-- TNS|Mixer Viz|TNE
local LCD_W, LCD_H = LCD_W or 480, LCD_H or 272
local NUM_CH = 16
local COLS = 2
local ROWS = 8
local BAR_H = 26
local BAR_W = 190
local COL_GAP = 240
local X_OFF = 4
local Y_OFF = 2
local VAL_MIN = -1024
local VAL_MAX = 1024

-- Colors (military green dark theme)
local C_BG     = lcd.RGB(20, 28, 20)
local C_PANEL  = lcd.RGB(30, 42, 30)
local C_GRID   = lcd.RGB(50, 65, 50)
local C_TEXT   = lcd.RGB(180, 200, 170)
local C_DIM    = lcd.RGB(90, 110, 85)
local C_POS    = lcd.RGB(40, 180, 60)
local C_NEG    = lcd.RGB(200, 50, 40)
local C_CTR    = lcd.RGB(80, 95, 80)
local C_ACTIVE = lcd.RGB(255, 220, 50)
local C_FREEZE = lcd.RGB(100, 160, 255)
local C_BTN    = lcd.RGB(55, 75, 55)
local C_BTN_HL = lcd.RGB(80, 120, 80)
local C_WHITE  = lcd.RGB(240, 240, 230)

local labels = {
  "AIL","ELE","THR","RUD","CH5","CH6","CH7","CH8",
  "CH9","C10","C11","C12","C13","C14","C15","C16"
}
local vals = {}
local prev = {}
local mn, mx = {}, {}
local active = {}
local frozen = false
local snap = {}
local editCh = nil
local editBuf = ""
local DELTA_THRESH = 15

local function clamp(v, lo, hi) return math.max(lo, math.min(hi, v)) end

local function init()
  for i = 1, NUM_CH do
    vals[i] = 0; prev[i] = 0; mn[i] = 0; mx[i] = 0
    active[i] = 0; snap[i] = 0
  end
end

local function readChannels()
  if frozen then return end
  for i = 1, NUM_CH do
    prev[i] = vals[i]
    local v = getValue("ch" .. i) or 0
    vals[i] = v
    if v < mn[i] then mn[i] = v end
    if v > mx[i] then mx[i] = v end
    local d = math.abs(v - prev[i])
    active[i] = d > DELTA_THRESH and 10 or math.max(0, active[i] - 1)
  end
end

local function resetMinMax()
  for i = 1, NUM_CH do mn[i] = vals[i]; mx[i] = vals[i] end
end

local function freezeSnap()
  frozen = not frozen
  if frozen then
    for i = 1, NUM_CH do snap[i] = vals[i] end
  end
end

local function drawBar(x, y, ch)
  local v = frozen and snap[ch] or vals[ch]
  local pct = clamp(v / VAL_MAX, -1, 1)
  local midX = x + BAR_W // 2
  local bw = math.floor(math.abs(pct) * (BAR_W // 2))

  -- background
  lcd.drawFilledRectangle(x, y, BAR_W, BAR_H - 2, C_PANEL)

  -- min/max ticks
  local mnPct = clamp(mn[ch] / VAL_MAX, -1, 1)
  local mxPct = clamp(mx[ch] / VAL_MAX, -1, 1)
  local mnX = midX + math.floor(mnPct * (BAR_W // 2))
  local mxX = midX + math.floor(mxPct * (BAR_W // 2))
  lcd.drawLine(mnX, y, mnX, y + BAR_H - 3, SOLID, C_DIM)
  lcd.drawLine(mxX, y, mxX, y + BAR_H - 3, SOLID, C_DIM)

  -- bar fill
  if pct > 0.01 then
    lcd.drawFilledRectangle(midX, y + 1, bw, BAR_H - 4, C_POS)
  elseif pct < -0.01 then
    lcd.drawFilledRectangle(midX - bw, y + 1, bw, BAR_H - 4, C_NEG)
  else
    lcd.drawFilledRectangle(midX - 2, y + 1, 4, BAR_H - 4, C_CTR)
  end

  -- center line
  lcd.drawLine(midX, y, midX, y + BAR_H - 3, SOLID, C_GRID)

  -- label
  local lbl = labels[ch] or ("C" .. ch)
  local lc = active[ch] > 0 and C_ACTIVE or C_TEXT
  lcd.drawText(x - 1, y + 2, lbl, SMLSIZE + lc)

  -- value
  local vStr = tostring(v)
  lcd.drawText(x + BAR_W + 3, y + 2, vStr, SMLSIZE + C_TEXT)
end

local function hitTest(tx, ty)
  for col = 0, COLS - 1 do
    for row = 0, ROWS - 1 do
      local ch = col * ROWS + row + 1
      local bx = X_OFF + 28 + col * COL_GAP
      local by = Y_OFF + row * (BAR_H + 1)
      if tx >= X_OFF and tx < bx + BAR_W and ty >= by and ty < by + BAR_H then
        return ch
      end
    end
  end
  return nil
end

local function drawButtons()
  -- FREEZE button
  local fx, fy, fw, fh = LCD_W - 72, LCD_H - 30, 34, 24
  local fc = frozen and C_FREEZE or C_BTN
  lcd.drawFilledRectangle(fx, fy, fw, fh, fc)
  lcd.drawRectangle(fx, fy, fw, fh, C_GRID)
  lcd.drawText(fx + 2, fy + 5, frozen and "FRZ" or "FRZ", SMLSIZE + C_WHITE)

  -- RESET button
  local rx = LCD_W - 36
  lcd.drawFilledRectangle(rx, fy, fw, fh, C_BTN)
  lcd.drawRectangle(rx, fy, fw, fh, C_GRID)
  lcd.drawText(rx + 2, fy + 5, "RST", SMLSIZE + C_WHITE)

  return fx, fy, fw, fh, rx
end

local function run(event, touchState)
  readChannels()
  lcd.clear(C_BG)

  -- draw all 16 channel bars
  for col = 0, COLS - 1 do
    for row = 0, ROWS - 1 do
      local ch = col * ROWS + row + 1
      if ch <= NUM_CH then
        local bx = X_OFF + 28 + col * COL_GAP
        local by = Y_OFF + row * (BAR_H + 1)
        drawBar(bx, by, ch)
      end
    end
  end

  -- buttons
  local fx, fy, fw, fh, rx = drawButtons()

  -- frozen indicator
  if frozen then
    lcd.drawText(LCD_W // 2 - 30, LCD_H - 14, "FROZEN", SMLSIZE + C_FREEZE)
  end

  -- edit overlay
  if editCh then
    lcd.drawFilledRectangle(LCD_W // 2 - 70, LCD_H // 2 - 20, 140, 40, C_PANEL)
    lcd.drawRectangle(LCD_W // 2 - 70, LCD_H // 2 - 20, 140, 40, C_ACTIVE)
    lcd.drawText(LCD_W // 2 - 60, LCD_H // 2 - 14, "CH" .. editCh .. ": " .. editBuf .. "_", SMLSIZE + C_ACTIVE)
    lcd.drawText(LCD_W // 2 - 60, LCD_H // 2 + 2, "Scroll=char Enter=ok", SMLSIZE + C_DIM)
  end

  -- touch handling
  if touchState and event == EVT_TOUCH_TAP then
    local tx, ty = touchState.x or 0, touchState.y or 0

    -- freeze button
    if tx >= fx and tx < fx + fw and ty >= fy and ty < fy + fh then
      freezeSnap()
      return 0
    end
    -- reset button
    if tx >= rx and tx < rx + fw and ty >= fy and ty < fy + fh then
      resetMinMax()
      return 0
    end
    -- channel label tap to rename
    if not editCh then
      local ch = hitTest(tx, ty)
      if ch then
        editCh = ch
        editBuf = labels[ch] or ""
        return 0
      end
    else
      -- confirm edit on any tap outside overlay
      if editBuf ~= "" then labels[editCh] = editBuf end
      editCh = nil
      editBuf = ""
      return 0
    end
  end

  -- rotary encoder for label editing
  if editCh then
    if event == EVT_VIRTUAL_INC or event == EVT_ROT_RIGHT then
      local c = #editBuf > 0 and string.byte(editBuf, #editBuf) or 64
      c = c + 1; if c > 90 then c = 65 end
      editBuf = editBuf:sub(1, #editBuf - 1) .. string.char(c)
    elseif event == EVT_VIRTUAL_DEC or event == EVT_ROT_LEFT then
      local c = #editBuf > 0 and string.byte(editBuf, #editBuf) or 66
      c = c - 1; if c < 65 then c = 90 end
      editBuf = editBuf:sub(1, #editBuf - 1) .. string.char(c)
    elseif event == EVT_VIRTUAL_ENTER then
      if editBuf ~= "" then labels[editCh] = editBuf end
      editCh = nil; editBuf = ""
    elseif event == EVT_VIRTUAL_EXIT then
      editCh = nil; editBuf = ""
    elseif event == EVT_VIRTUAL_NEXT then
      editBuf = editBuf .. "A"
    elseif event == EVT_VIRTUAL_PREV then
      if #editBuf > 0 then editBuf = editBuf:sub(1, #editBuf - 1) end
    end
    return 0
  end

  -- exit on RTN
  if event == EVT_VIRTUAL_EXIT then return 1 end
  return 0
end

return { init=init, run=run }
