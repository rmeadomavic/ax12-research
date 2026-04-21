-- TNS|VTx Manager|TNE
---- #########################################################################
---- #                                                                       #
---- # VTx Manager -- Multi-pilot frequency coordination tool                #
---- # Avoid interference on race day, training, and team operations         #
---- #                                                                       #
---- # RadioMaster AX12 | github.com/rmeadomavic/ax12-research               #
---- #                                                                       #
---- #########################################################################

---------------------------------------------------------------------------
-- FPV VTx Frequency Table (MHz) -- all 6 standard bands, 8 channels each
---------------------------------------------------------------------------

local BANDS = {
  { name = "A", label = "Boscam A",
    freq = {5865, 5845, 5825, 5805, 5785, 5765, 5745, 5725} },
  { name = "B", label = "Boscam B",
    freq = {5733, 5752, 5771, 5790, 5809, 5828, 5847, 5866} },
  { name = "E", label = "Foxeer",
    freq = {5705, 5685, 5665, 5645, 5885, 5905, 5925, 5945} },
  { name = "F", label = "FatShark",
    freq = {5740, 5760, 5780, 5800, 5820, 5840, 5860, 5880} },
  { name = "R", label = "Raceband",
    freq = {5658, 5695, 5732, 5769, 5806, 5843, 5880, 5917} },
  { name = "L", label = "Low Race",
    freq = {5362, 5399, 5436, 5473, 5510, 5547, 5584, 5621} },
}

-- Raceband quick-setup: 6 pilots on R1/R2/R4/R5/R7/R8 (skip R3/R6)
local RACE_QUICK = {1, 2, 4, 5, 7, 8}

---------------------------------------------------------------------------
-- Pilot colors (8 pilots max)
---------------------------------------------------------------------------

local PILOT_NAMES = {"P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"}

---------------------------------------------------------------------------
-- State
---------------------------------------------------------------------------

local W = 480
local H = 272

-- assignments[bandIdx][chanIdx] = pilotNum (1-8) or 0 (unassigned)
local assignments = {}

-- Current view mode
local VIEW_GRID = 0
local VIEW_PILOT_SEL = 1
local VIEW_INTERFERENCE = 2
local viewMode = VIEW_GRID

-- For pilot selection dialog
local selBand = 0
local selChan = 0

-- Scroll offset for grid (bands may not all fit)
local scrollY = 0
local maxScrollY = 0

-- Interference cache (rebuilt on assignment change)
local interference = {}

-- Colors (initialized in init)
local C = {}

-- Pilot palette (initialized in init)
local pilotColors = {}

-- Layout
local HEADER_H = 28
local CELL_W = 52
local CELL_H = 32
local BAND_LABEL_W = 28
local GRID_X = BAND_LABEL_W + 2
local GRID_Y = HEADER_H + 2

---------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------

local function initColors()
  C.bg        = lcd.RGB(0x12, 0x12, 0x20)
  C.headerBg  = lcd.RGB(0x1a, 0x3a, 0x5c)
  C.headerFg  = lcd.RGB(0xff, 0xff, 0xff)
  C.gridBorder= lcd.RGB(0x40, 0x40, 0x55)
  C.text      = lcd.RGB(0xd0, 0xd0, 0xd0)
  C.textDim   = lcd.RGB(0x60, 0x60, 0x70)
  C.freqText  = lcd.RGB(0xa0, 0xa0, 0xb0)
  C.bandLabel = lcd.RGB(0xff, 0xb3, 0x00)
  C.chanLabel = lcd.RGB(0x80, 0xc0, 0xff)
  C.unassigned= lcd.RGB(0x30, 0x30, 0x40)
  C.safe      = lcd.RGB(0x2e, 0x7d, 0x32)
  C.marginal  = lcd.RGB(0xf9, 0xa8, 0x25)
  C.conflict  = lcd.RGB(0xc6, 0x28, 0x28)
  C.safeText  = lcd.RGB(0x66, 0xbb, 0x6a)
  C.margText  = lcd.RGB(0xff, 0xee, 0x58)
  C.confText  = lcd.RGB(0xef, 0x53, 0x50)
  C.btnBg     = lcd.RGB(0x2d, 0x6b, 0x2d)
  C.btnBgAlt  = lcd.RGB(0x5c, 0x35, 0x8c)
  C.btnBgWarn = lcd.RGB(0x8b, 0x20, 0x20)
  C.btnText   = lcd.RGB(0xff, 0xff, 0xff)
  C.dialogBg  = lcd.RGB(0x1a, 0x1a, 0x2e)
  C.dialogBrd = lcd.RGB(0x60, 0x80, 0xc0)
  C.white     = lcd.RGB(0xff, 0xff, 0xff)
  C.black     = lcd.RGB(0x00, 0x00, 0x00)

  pilotColors = {
    lcd.RGB(0xe5, 0x39, 0x35),  -- P1 red
    lcd.RGB(0x43, 0xa0, 0x47),  -- P2 green
    lcd.RGB(0x1e, 0x88, 0xe5),  -- P3 blue
    lcd.RGB(0xfb, 0x8c, 0x00),  -- P4 orange
    lcd.RGB(0x8e, 0x24, 0xaa),  -- P5 purple
    lcd.RGB(0x00, 0xac, 0xc1),  -- P6 cyan
    lcd.RGB(0xfd, 0xd8, 0x35),  -- P7 yellow
    lcd.RGB(0xf0, 0x62, 0xc0),  -- P8 pink
  }
end

local function initAssignments()
  for b = 1, #BANDS do
    assignments[b] = {}
    for ch = 1, 8 do
      assignments[b][ch] = 0
    end
  end
end

local function getAssignedFreqs()
  local list = {}
  for b = 1, #BANDS do
    for ch = 1, 8 do
      if assignments[b][ch] > 0 then
        list[#list + 1] = {
          freq = BANDS[b].freq[ch],
          band = b,
          chan = ch,
          pilot = assignments[b][ch]
        }
      end
    end
  end
  return list
end

local function rebuildInterference()
  local assigned = getAssignedFreqs()

  for b = 1, #BANDS do
    interference[b] = {}
    for ch = 1, 8 do
      interference[b][ch] = "none"
    end
  end

  for i = 1, #assigned do
    local a = assigned[i]
    local worst = "safe"
    for j = 1, #assigned do
      if i ~= j then
        local sep = math.abs(a.freq - assigned[j].freq)
        if sep < 25 then
          worst = "conflict"
          break
        elseif sep < 37 and worst ~= "conflict" then
          worst = "marginal"
        end
      end
    end
    interference[a.band][a.chan] = worst
  end
end

local function clearAllAssignments()
  for b = 1, #BANDS do
    for ch = 1, 8 do
      assignments[b][ch] = 0
    end
  end
  rebuildInterference()
end

local function applyRacebandQuick()
  clearAllAssignments()
  -- Raceband is band index 5
  for pilotNum, chanIdx in ipairs(RACE_QUICK) do
    assignments[5][chanIdx] = pilotNum
  end
  rebuildInterference()
end

local function countAssigned()
  local n = 0
  for b = 1, #BANDS do
    for ch = 1, 8 do
      if assignments[b][ch] > 0 then n = n + 1 end
    end
  end
  return n
end

---------------------------------------------------------------------------
-- Drawing helpers
---------------------------------------------------------------------------

local function inBox(tx, ty, x, y, w, h)
  return tx >= x and tx <= x + w and ty >= y and ty <= y + h
end

local function drawBtn(x, y, w, h, text, bg, fg)
  lcd.drawFilledRectangle(x, y, w, h, bg)
  lcd.drawRectangle(x, y, w, h, fg)
  local tw = #text * 6
  lcd.drawText(x + math.floor((w - tw) / 2), y + math.floor((h - 14) / 2), text, fg)
end

---------------------------------------------------------------------------
-- GRID VIEW (main screen)
---------------------------------------------------------------------------

local function drawGrid()
  lcd.clear(C.bg)

  -- Header bar
  lcd.drawFilledRectangle(0, 0, W, HEADER_H, C.headerBg)
  lcd.drawText(4, 4, "VTx Manager", C.headerFg + BOLD)

  local cnt = countAssigned()
  if cnt > 0 then
    lcd.drawText(120, 6, cnt .. " assigned", C.safeText)
  end

  -- Buttons in header
  local bw = 68
  local bh = 22
  local by = 3
  drawBtn(W - bw - 4, by, bw, bh, "RACE 6", C.btnBg, C.btnText)
  drawBtn(W - bw * 2 - 10, by, bw, bh, "CLEAR", C.btnBgWarn, C.btnText)
  drawBtn(W - bw * 3 - 16, by, bw, bh, "CHECK", C.btnBgAlt, C.btnText)

  -- Column headers
  local gy = GRID_Y + 14
  for ch = 1, 8 do
    local cx = GRID_X + (ch - 1) * CELL_W
    lcd.drawText(cx + 14, GRID_Y, "C" .. ch, C.chanLabel)
  end

  -- Compute scroll limits
  local visibleH = H - gy
  local totalH = #BANDS * CELL_H
  maxScrollY = math.max(0, totalH - visibleH)
  if scrollY > maxScrollY then scrollY = maxScrollY end
  if scrollY < 0 then scrollY = 0 end

  -- Draw band rows
  for b = 1, #BANDS do
    local rowY = gy + (b - 1) * CELL_H - scrollY
    if rowY + CELL_H > gy - 2 and rowY < H then
      -- Band label
      lcd.drawText(2, rowY + math.floor(CELL_H / 2) - 7, BANDS[b].name, C.bandLabel + BOLD)

      -- Channel cells
      for ch = 1, 8 do
        local cx = GRID_X + (ch - 1) * CELL_W
        local pilot = assignments[b][ch]
        local intfStatus = interference[b] and interference[b][ch] or "none"

        -- Cell background
        local cellBg = C.unassigned
        if pilot > 0 then
          if intfStatus == "conflict" then
            cellBg = C.conflict
          elseif intfStatus == "marginal" then
            cellBg = C.marginal
          else
            cellBg = pilotColors[pilot]
          end
        end

        lcd.drawFilledRectangle(cx, rowY, CELL_W - 1, CELL_H - 1, cellBg)
        lcd.drawRectangle(cx, rowY, CELL_W - 1, CELL_H - 1, C.gridBorder)

        -- Frequency (top line)
        local freqColor = (pilot > 0) and C.white or C.freqText
        lcd.drawText(cx + 3, rowY + 2, tostring(BANDS[b].freq[ch]), freqColor)

        -- Pilot or channel label (bottom line)
        if pilot > 0 then
          lcd.drawText(cx + 3, rowY + 17, PILOT_NAMES[pilot], C.white + BOLD)
        else
          lcd.drawText(cx + 3, rowY + 17, BANDS[b].name .. ch, C.textDim)
        end
      end
    end
  end

  -- Scroll indicators
  if scrollY > 0 then
    lcd.drawText(W - 14, gy, "^", C.chanLabel)
  end
  if scrollY < maxScrollY then
    lcd.drawText(W - 14, H - 14, "v", C.chanLabel)
  end
end

local function handleGridTouch(tx, ty)
  -- Header buttons
  local bw = 68
  local bh = 22
  local by = 3
  if inBox(tx, ty, W - bw - 4, by, bw, bh) then
    applyRacebandQuick()
    return
  end
  if inBox(tx, ty, W - bw * 2 - 10, by, bw, bh) then
    clearAllAssignments()
    return
  end
  if inBox(tx, ty, W - bw * 3 - 16, by, bw, bh) then
    viewMode = VIEW_INTERFERENCE
    return
  end

  -- Scroll zones (right edge)
  if tx > W - 20 and ty < H / 2 and scrollY > 0 then
    scrollY = scrollY - CELL_H
    return
  end
  if tx > W - 20 and ty > H / 2 and scrollY < maxScrollY then
    scrollY = scrollY + CELL_H
    return
  end

  -- Grid cell tap
  local gy = GRID_Y + 14
  for b = 1, #BANDS do
    local rowY = gy + (b - 1) * CELL_H - scrollY
    if ty >= rowY and ty < rowY + CELL_H and rowY >= gy - 2 then
      for ch = 1, 8 do
        local cx = GRID_X + (ch - 1) * CELL_W
        if tx >= cx and tx < cx + CELL_W then
          selBand = b
          selChan = ch
          viewMode = VIEW_PILOT_SEL
          return
        end
      end
    end
  end
end

---------------------------------------------------------------------------
-- PILOT SELECTION dialog
---------------------------------------------------------------------------

local function drawPilotSelect()
  -- Draw grid underneath (dimmed)
  drawGrid()

  -- Overlay
  lcd.drawFilledRectangle(0, 0, W, H, C.black)

  -- Dialog box
  local dw = 320
  local dh = 180
  local dx = math.floor((W - dw) / 2)
  local dy = math.floor((H - dh) / 2)

  lcd.drawFilledRectangle(dx, dy, dw, dh, C.dialogBg)
  lcd.drawRectangle(dx, dy, dw, dh, C.dialogBrd)
  lcd.drawRectangle(dx + 1, dy + 1, dw - 2, dh - 2, C.dialogBrd)

  -- Title
  local bName = BANDS[selBand].name .. selChan
  local freq = BANDS[selBand].freq[selChan]
  lcd.drawText(dx + 10, dy + 6, "Assign " .. bName .. " (" .. freq .. " MHz)", C.headerFg + BOLD)

  -- Current assignment
  local cur = assignments[selBand][selChan]
  if cur > 0 then
    lcd.drawText(dx + 10, dy + 24, "Current: " .. PILOT_NAMES[cur], pilotColors[cur])
  end

  -- Pilot buttons (2 rows of 4)
  local pbw = 64
  local pbh = 36
  local pgap = 8
  local startX = dx + 16
  local startY = dy + 46

  for p = 1, 8 do
    local col = ((p - 1) % 4)
    local row = math.floor((p - 1) / 4)
    local px = startX + col * (pbw + pgap)
    local py = startY + row * (pbh + pgap)

    lcd.drawFilledRectangle(px, py, pbw, pbh, pilotColors[p])
    lcd.drawRectangle(px, py, pbw, pbh, C.white)
    lcd.drawText(px + 16, py + 4, PILOT_NAMES[p], C.white + BOLD)

    -- Show how many channels this pilot already has
    local count = 0
    for b = 1, #BANDS do
      for ch = 1, 8 do
        if assignments[b][ch] == p then count = count + 1 end
      end
    end
    if count > 0 then
      lcd.drawText(px + 16, py + 22, "(" .. count .. ")", C.white)
    end
  end

  -- Unassign / Cancel buttons
  local bottomY = dy + dh - 34
  drawBtn(dx + 10, bottomY, 90, 28, "UNASSIGN", C.btnBgWarn, C.btnText)
  drawBtn(dx + dw - 100, bottomY, 90, 28, "CANCEL", C.unassigned, C.text)
end

local function handlePilotSelectTouch(tx, ty)
  local dw = 320
  local dh = 180
  local dx = math.floor((W - dw) / 2)
  local dy = math.floor((H - dh) / 2)

  -- Pilot buttons
  local pbw = 64
  local pbh = 36
  local pgap = 8
  local startX = dx + 16
  local startY = dy + 46

  for p = 1, 8 do
    local col = ((p - 1) % 4)
    local row = math.floor((p - 1) / 4)
    local px = startX + col * (pbw + pgap)
    local py = startY + row * (pbh + pgap)
    if inBox(tx, ty, px, py, pbw, pbh) then
      assignments[selBand][selChan] = p
      rebuildInterference()
      viewMode = VIEW_GRID
      return
    end
  end

  -- Unassign
  local bottomY = dy + dh - 34
  if inBox(tx, ty, dx + 10, bottomY, 90, 28) then
    assignments[selBand][selChan] = 0
    rebuildInterference()
    viewMode = VIEW_GRID
    return
  end

  -- Cancel
  if inBox(tx, ty, dx + dw - 100, bottomY, 90, 28) then
    viewMode = VIEW_GRID
    return
  end

  -- Tap outside dialog = cancel
  if not inBox(tx, ty, dx, dy, dw, dh) then
    viewMode = VIEW_GRID
  end
end

---------------------------------------------------------------------------
-- INTERFERENCE CHECK view
---------------------------------------------------------------------------

local function drawInterferenceCheck()
  lcd.clear(C.bg)

  -- Header
  lcd.drawFilledRectangle(0, 0, W, HEADER_H, C.headerBg)
  lcd.drawText(4, 4, "Interference Check", C.headerFg + BOLD)
  drawBtn(W - 72, 3, 68, 22, "BACK", C.btnBgAlt, C.btnText)

  local assigned = getAssignedFreqs()

  if #assigned == 0 then
    lcd.drawText(W / 2 - 60, H / 2 - 10, "No channels assigned", C.textDim)
    lcd.drawText(W / 2 - 80, H / 2 + 10, "Tap channels in grid view", C.textDim)
    return
  end

  -- Sort by frequency
  table.sort(assigned, function(a, b) return a.freq < b.freq end)

  -- Column headers
  local y = HEADER_H + 6
  local rowH = 22

  lcd.drawText(4, y, "Chan", C.chanLabel)
  lcd.drawText(56, y, "Freq", C.chanLabel)
  lcd.drawText(112, y, "Pilot", C.chanLabel)
  lcd.drawText(168, y, "Sep", C.chanLabel)
  lcd.drawText(218, y, "Status", C.chanLabel)
  lcd.drawText(310, y, "Nearest", C.chanLabel)
  y = y + rowH

  lcd.drawLine(0, y - 4, W, y - 4, C.gridBorder)

  for i, a in ipairs(assigned) do
    if y > H - 24 then break end

    local bandName = BANDS[a.band].name .. a.chan
    lcd.drawText(4, y, bandName, C.text + BOLD)
    lcd.drawText(56, y, tostring(a.freq), C.freqText)
    lcd.drawText(112, y, PILOT_NAMES[a.pilot], pilotColors[a.pilot])

    -- Find nearest neighbor
    local minSep = 9999
    local nearestName = ""
    for j, b in ipairs(assigned) do
      if i ~= j then
        local sep = math.abs(a.freq - b.freq)
        if sep < minSep then
          minSep = sep
          nearestName = BANDS[b.band].name .. b.chan
        end
      end
    end

    if minSep < 9999 then
      local sepColor = C.safeText
      local statusText = "SAFE"
      local statusColor = C.safeText
      if minSep < 25 then
        sepColor = C.confText
        statusText = "CONFLICT"
        statusColor = C.confText
      elseif minSep < 37 then
        sepColor = C.margText
        statusText = "MARGINAL"
        statusColor = C.margText
      end
      lcd.drawText(168, y, tostring(minSep) .. "M", sepColor)
      lcd.drawText(218, y, statusText, statusColor + BOLD)
      lcd.drawText(310, y, nearestName, C.text)
    else
      lcd.drawText(168, y, "--", C.textDim)
      lcd.drawText(218, y, "ONLY", C.safeText)
    end

    y = y + rowH
  end

  -- Legend at bottom
  local ly = H - 16
  lcd.drawFilledRectangle(0, ly - 4, W, 20, C.headerBg)
  lcd.drawFilledRectangle(4, ly, 10, 10, C.safe)
  lcd.drawText(18, ly - 2, ">37MHz", C.safeText)
  lcd.drawFilledRectangle(100, ly, 10, 10, C.marginal)
  lcd.drawText(114, ly - 2, "25-37", C.margText)
  lcd.drawFilledRectangle(190, ly, 10, 10, C.conflict)
  lcd.drawText(204, ly - 2, "<25MHz", C.confText)
end

local function handleInterferenceTouch(tx, ty)
  if inBox(tx, ty, W - 72, 3, 68, 22) then
    viewMode = VIEW_GRID
  end
end

---------------------------------------------------------------------------
-- Init
---------------------------------------------------------------------------

local function init()
  initColors()
  initAssignments()
  rebuildInterference()
end

---------------------------------------------------------------------------
-- Main run
---------------------------------------------------------------------------

local function run(event, touchState)
  if event == nil then return 0 end
  if event == EVT_VIRTUAL_EXIT then
    if viewMode ~= VIEW_GRID then
      viewMode = VIEW_GRID
      return 0
    end
    return 1
  end

  -- Touch handling
  if event == EVT_TOUCH_TAP and touchState then
    local tx = touchState.x or 0
    local ty = touchState.y or 0

    if viewMode == VIEW_GRID then
      handleGridTouch(tx, ty)
    elseif viewMode == VIEW_PILOT_SEL then
      handlePilotSelectTouch(tx, ty)
    elseif viewMode == VIEW_INTERFERENCE then
      handleInterferenceTouch(tx, ty)
    end
  end

  -- Scroll via encoder or swipe
  if viewMode == VIEW_GRID then
    if event == EVT_VIRTUAL_PREV then
      scrollY = math.max(scrollY - CELL_H, 0)
    elseif event == EVT_VIRTUAL_NEXT then
      scrollY = math.min(scrollY + CELL_H, maxScrollY)
    end
  end

  -- Draw
  if viewMode == VIEW_GRID then
    drawGrid()
  elseif viewMode == VIEW_PILOT_SEL then
    drawPilotSelect()
  elseif viewMode == VIEW_INTERFERENCE then
    drawInterferenceCheck()
  end

  return 0
end

return { init = init, run = run }
