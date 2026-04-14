-- TNS|Freq Decon|TNE
-- Multi-drone frequency deconfliction tool
-- Touch to add/remove pilots, auto-assign clean frequencies
local M = {}
local W, H = 720, 1280
local BG, GREEN, DKGREEN, RED, AMBER, WHITE, GRAY, CYAN
local PILOT_CLR = {}
local BANDS = {
  { name="900MHz", label="ELRS/LoRa" },
  { name="2.4GHz", label="ELRS/WiFi" },
  { name="5.8GHz", label="FPV Video" },
}
local CHANNELS = {
  { 868, 880, 890, 900, 910, 915, 920, 925 },
  { 2410, 2420, 2430, 2440, 2450, 2460, 2470, 2480 },
  { 5658, 5695, 5732, 5769, 5806, 5843, 5880, 5917 },
}
local MIN_SEP = { 10, 15, 37 }
local MAX_PILOTS = 6
local numPilots = 0
local assignments = {}
local conflicts = { {}, {}, {} }
local statusMsg, statusTimer = "", 0

local function setStatus(msg) statusMsg = msg; statusTimer = 60 end

local function detectConflicts()
  conflicts = { {}, {}, {} }
  for b = 1, 3 do
    for p1 = 1, numPilots do
      for p2 = p1 + 1, numPilots do
        if assignments[p1] and assignments[p2] then
          local f1 = CHANNELS[b][assignments[p1][b]]
          local f2 = CHANNELS[b][assignments[p2][b]]
          if f1 and f2 and math.abs(f1 - f2) < MIN_SEP[b] then
            conflicts[b][#conflicts[b] + 1] = { p1, p2 }
          end
        end
      end
    end
  end
end

local function cleanAssign()
  if numPilots == 0 then return end
  for b = 1, 3 do
    local nCh = #CHANNELS[b]
    local step = math.max(1, math.floor(nCh / numPilots))
    for p = 1, numPilots do
      if not assignments[p] then assignments[p] = { 1, 1, 1 } end
      local idx = ((p - 1) * step) + 1
      if idx > nCh then idx = ((p - 1) % nCh) + 1 end
      assignments[p][b] = idx
    end
  end
  detectConflicts()
  setStatus("CLEAN ASSIGN COMPLETE")
end

-- Check if pilot p has a conflict in band b
local function hasConflict(p, b)
  for _, cf in ipairs(conflicts[b] or {}) do
    if cf[1] == p or cf[2] == p then return true end
  end
  return false
end

local function drawHeader()
  lcd.drawFilledRectangle(0, 0, W, 52, DKGREEN)
  lcd.drawText(15, 8, "FREQ DECONFLICTION", MIDSIZE + WHITE)
  lcd.drawText(W - 180, 14, numPilots .. "/" .. MAX_PILOTS .. " PILOTS", SMLSIZE + GREEN)
  lcd.drawLine(0, 52, W, 52, SOLID, GREEN)
end

local function drawBands()
  local bandW = math.floor((W - 40) / 3)
  local topY, bandH = 65, 520
  for b = 1, 3 do
    local x0 = 10 + (b - 1) * (bandW + 10)
    lcd.drawFilledRectangle(x0, topY, bandW, bandH, lcd.RGB(0x0C, 0x14, 0x0C))
    lcd.drawRectangle(x0, topY, bandW, bandH, DKGREEN)
    lcd.drawFilledRectangle(x0, topY, bandW, 36, lcd.RGB(0x10, 0x28, 0x10))
    lcd.drawText(x0 + 5, topY + 2, BANDS[b].name, SMLSIZE + GREEN)
    lcd.drawText(x0 + 5, topY + 18, BANDS[b].label, TINSIZE + GRAY)
    local gridY = topY + 42
    local nCh = #CHANNELS[b]
    local slotH = math.floor((bandH - 48) / nCh)
    for ch = 1, nCh do
      local cy = gridY + (ch - 1) * slotH
      lcd.drawText(x0 + 4, cy + 2, CHANNELS[b][ch], TINSIZE + GRAY)
      lcd.drawLine(x0 + 45, cy + slotH - 1, x0 + bandW - 5, cy + slotH - 1, DOTTED, GRAY)
      for p = 1, numPilots do
        if assignments[p] and assignments[p][b] == ch then
          local blkW = math.floor((bandW - 55) / math.max(numPilots, 1))
          local bx = x0 + 50 + (p - 1) * blkW
          local clr = hasConflict(p, b) and RED or PILOT_CLR[p]
          lcd.drawFilledRectangle(bx, cy + 1, blkW - 2, slotH - 3, clr)
          lcd.drawText(bx + 3, cy + 3, "P" .. p, TINSIZE + WHITE)
        end
      end
    end
  end
end

local function drawPilotLegend()
  local y = 600
  lcd.drawFilledRectangle(10, y, W - 20, 50, lcd.RGB(0x0C, 0x14, 0x0C))
  lcd.drawRectangle(10, y, W - 20, 50, DKGREEN)
  lcd.drawText(15, y + 4, "PILOTS", TINSIZE + GREEN)
  for p = 1, MAX_PILOTS do
    local px = 15 + (p - 1) * 115
    if p <= numPilots then
      lcd.drawFilledRectangle(px, y + 22, 30, 20, PILOT_CLR[p])
      lcd.drawText(px + 35, y + 24, "P" .. p, TINSIZE + WHITE)
    else
      lcd.drawRectangle(px, y + 22, 30, 20, GRAY)
      lcd.drawText(px + 35, y + 24, "P" .. p, TINSIZE + GRAY)
    end
  end
end

local function drawAssignmentTable()
  local y, tH = 665, 30 + numPilots * 28
  lcd.drawFilledRectangle(10, y, W - 20, tH, lcd.RGB(0x0C, 0x14, 0x0C))
  lcd.drawRectangle(10, y, W - 20, tH, DKGREEN)
  lcd.drawText(20, y + 6, "PILOT", TINSIZE + GREEN)
  lcd.drawText(150, y + 6, "900MHz", TINSIZE + GREEN)
  lcd.drawText(330, y + 6, "2.4GHz", TINSIZE + GREEN)
  lcd.drawText(510, y + 6, "5.8GHz", TINSIZE + GREEN)
  lcd.drawLine(15, y + 25, W - 15, y + 25, SOLID, DKGREEN)
  local colX = { 150, 330, 510 }
  for p = 1, numPilots do
    local ry = y + 30 + (p - 1) * 28
    lcd.drawFilledRectangle(20, ry + 2, 14, 14, PILOT_CLR[p])
    lcd.drawText(40, ry + 2, "Pilot " .. p, TINSIZE + WHITE)
    for b = 1, 3 do
      if assignments[p] then
        local freq = CHANNELS[b][assignments[p][b]]
        local clr = hasConflict(p, b) and RED or WHITE
        lcd.drawText(colX[b], ry + 2, tostring(freq), TINSIZE + clr)
      end
    end
  end
end

local function drawButtons()
  local y = H - 200
  local addClr = numPilots < MAX_PILOTS and GREEN or GRAY
  lcd.drawFilledRectangle(15, y, 220, 55, lcd.RGB(0x10, 0x28, 0x10))
  lcd.drawRectangle(15, y, 220, 55, addClr)
  lcd.drawText(40, y + 14, "+ ADD PILOT", SMLSIZE + addClr)
  local remClr = numPilots > 0 and AMBER or GRAY
  lcd.drawFilledRectangle(250, y, 220, 55, lcd.RGB(0x1A, 0x14, 0x0C))
  lcd.drawRectangle(250, y, 220, 55, remClr)
  lcd.drawText(272, y + 14, "- REM PILOT", SMLSIZE + remClr)
  local cleanClr = numPilots > 0 and CYAN or GRAY
  lcd.drawFilledRectangle(485, y, 220, 55, lcd.RGB(0x0C, 0x14, 0x1A))
  lcd.drawRectangle(485, y, 220, 55, cleanClr)
  lcd.drawText(530, y + 14, "CLEAN", SMLSIZE + cleanClr)
  local totalConf = 0
  for b = 1, 3 do totalConf = totalConf + #(conflicts[b] or {}) end
  if totalConf > 0 then
    lcd.drawText(15, y + 65, "WARNING: " .. totalConf .. " CONFLICT(S)", SMLSIZE + RED)
  elseif numPilots > 0 then
    lcd.drawText(15, y + 65, "ALL CLEAR - NO CONFLICTS", SMLSIZE + GREEN)
  end
end

local function drawStatusBar()
  if statusTimer > 0 then
    statusTimer = statusTimer - 1
    lcd.drawFilledRectangle(0, H - 45, W, 45, lcd.RGB(0x10, 0x28, 0x10))
    lcd.drawText(15, H - 38, statusMsg, SMLSIZE + AMBER)
  else
    lcd.drawFilledRectangle(0, H - 45, W, 45, BG)
    lcd.drawText(15, H - 35, "TAP: +/- PILOTS | CLEAN: AUTO-ASSIGN", TINSIZE + GRAY)
  end
end

function M.init()
  BG      = lcd.RGB(0x0A, 0x0A, 0x0A)
  GREEN   = lcd.RGB(0x00, 0xFF, 0x00)
  DKGREEN = lcd.RGB(0x00, 0x66, 0x00)
  RED     = lcd.RGB(0xFF, 0x20, 0x20)
  AMBER   = lcd.RGB(0xFF, 0xAA, 0x00)
  WHITE   = lcd.RGB(0xFF, 0xFF, 0xFF)
  GRAY    = lcd.RGB(0x55, 0x55, 0x55)
  CYAN    = lcd.RGB(0x00, 0xCC, 0xCC)
  PILOT_CLR = {
    lcd.RGB(0x00, 0xAA, 0xFF),  -- Blue
    lcd.RGB(0xFF, 0xCC, 0x00),  -- Yellow
    lcd.RGB(0xFF, 0x44, 0xFF),  -- Magenta
    lcd.RGB(0x00, 0xFF, 0xAA),  -- Teal
    lcd.RGB(0xFF, 0x88, 0x00),  -- Orange
    lcd.RGB(0xAA, 0xAA, 0xFF),  -- Lavender
  }
end

function M.run(event, touchState)
  lcd.clear(BG)
  if event == EVT_TOUCH_TAP and touchState then
    local tx, ty = touchState.x, touchState.y
    local btnY = H - 200
    -- Add pilot
    if tx >= 15 and tx <= 235 and ty >= btnY and ty <= btnY + 55 then
      if numPilots < MAX_PILOTS then
        numPilots = numPilots + 1
        assignments[numPilots] = { 1, 1, 1 }
        cleanAssign()
        setStatus("PILOT " .. numPilots .. " ADDED")
      end
    end
    -- Remove pilot
    if tx >= 250 and tx <= 470 and ty >= btnY and ty <= btnY + 55 then
      if numPilots > 0 then
        assignments[numPilots] = nil
        numPilots = numPilots - 1
        conflicts = { {}, {}, {} }
        if numPilots > 0 then cleanAssign() end
        setStatus("PILOT REMOVED")
      end
    end
    -- Clean assign
    if tx >= 485 and tx <= 705 and ty >= btnY and ty <= btnY + 55 then
      if numPilots > 0 then cleanAssign() end
    end
    -- Tap band column to cycle last pilot channel
    local bandW = math.floor((W - 40) / 3)
    if ty >= 107 and ty <= 585 and numPilots > 0 then
      for b = 1, 3 do
        local x0 = 10 + (b - 1) * (bandW + 10)
        if tx >= x0 and tx <= x0 + bandW then
          local p = numPilots
          if assignments[p] then
            assignments[p][b] = (assignments[p][b] % #CHANNELS[b]) + 1
            detectConflicts()
            setStatus("P" .. p .. " " .. BANDS[b].name .. " -> " .. CHANNELS[b][assignments[p][b]])
          end
        end
      end
    end
    if tx < 60 and ty < 60 then return 1 end
  end
  drawHeader()
  drawBands()
  drawPilotLegend()
  if numPilots > 0 then drawAssignmentTable() end
  drawButtons()
  drawStatusBar()
  return 0
end

return M
