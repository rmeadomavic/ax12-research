-- TNS|Pre-Flight|TNE
-- Interactive pre-flight checklist for drone operations
-- Touch to check items, auto-checks from telemetry
-- GO/NO-GO status with progress bar

local M = {}

-- Color definitions (TAK military palette)
local CLR_GREEN    = nil
local CLR_DKGREEN  = nil
local CLR_AMBER    = nil
local CLR_RED      = nil
local CLR_BG       = nil
local CLR_GRAY     = nil
local CLR_WHITE    = nil
local CLR_DARKRED  = nil

-- Screen dimensions
local W = 720
local H = 1280

-- Checklist items
-- Fields: name, checked, autoCheck (function or nil), category
local items = {}
local scrollOffset = 0
local statusMsg = ""
local statusTimer = 0
local NUM_ITEMS = 12
local ITEM_HEIGHT = 72
local LIST_TOP = 130
local LIST_BOTTOM = H - 160

---------------------------------------------------------------------------
-- Telemetry Auto-Check Functions
---------------------------------------------------------------------------

local function checkBattery()
  local v = getValue("tx-voltage") or 0
  if v <= 0 then return false end
  local pct = ((v - 6.0) / (8.4 - 6.0)) * 100
  return pct >= 90
end

local function checkGPS()
  local sats = getValue("Sats") or getValue("Tmp2") or 0
  return sats >= 6
end

local function checkRSSI()
  local rssi = getRSSI and getRSSI() or 0
  return rssi > 0 and rssi < 100
end

---------------------------------------------------------------------------
-- Initialize Checklist
---------------------------------------------------------------------------

local function initChecklist()
  items = {
    {
      name = "Battery charged (>90%)",
      checked = false,
      autoFn = checkBattery,
      autoLabel = "AUTO",
      cat = "POWER"
    },
    {
      name = "Props inspected",
      checked = false,
      autoFn = nil,
      autoLabel = nil,
      cat = "AIRFRAME"
    },
    {
      name = "Arms secure",
      checked = false,
      autoFn = nil,
      autoLabel = nil,
      cat = "AIRFRAME"
    },
    {
      name = "GPS lock confirmed",
      checked = false,
      autoFn = checkGPS,
      autoLabel = "AUTO",
      cat = "NAV"
    },
    {
      name = "ELRS link active",
      checked = false,
      autoFn = checkRSSI,
      autoLabel = "AUTO",
      cat = "COMMS"
    },
    {
      name = "Failsafe set (RTL)",
      checked = false,
      autoFn = nil,
      autoLabel = nil,
      cat = "SAFETY"
    },
    {
      name = "Airspace clear",
      checked = false,
      autoFn = nil,
      autoLabel = nil,
      cat = "OPS"
    },
    {
      name = "Crew briefed",
      checked = false,
      autoFn = nil,
      autoLabel = nil,
      cat = "OPS"
    },
    {
      name = "Frequencies deconflicted",
      checked = false,
      autoFn = nil,
      autoLabel = nil,
      cat = "COMMS"
    },
    {
      name = "Camera/payload secure",
      checked = false,
      autoFn = nil,
      autoLabel = nil,
      cat = "PAYLOAD"
    },
    {
      name = "Wind check (<15 kts)",
      checked = false,
      autoFn = nil,
      autoLabel = nil,
      cat = "WX"
    },
    {
      name = "NOTAMs reviewed",
      checked = false,
      autoFn = nil,
      autoLabel = nil,
      cat = "AIRSPACE"
    },
  }
end

---------------------------------------------------------------------------
-- Drawing Helpers
---------------------------------------------------------------------------

local function drawCornerBrackets(x1, y1, x2, y2, len)
  lcd.drawLine(x1, y1, x1 + len, y1, SOLID, CLR_DKGREEN)
  lcd.drawLine(x1, y1, x1, y1 + len, SOLID, CLR_DKGREEN)
  lcd.drawLine(x2 - len, y1, x2, y1, SOLID, CLR_DKGREEN)
  lcd.drawLine(x2, y1, x2, y1 + len, SOLID, CLR_DKGREEN)
  lcd.drawLine(x1, y2 - len, x1, y2, SOLID, CLR_DKGREEN)
  lcd.drawLine(x1, y2, x1 + len, y2, SOLID, CLR_DKGREEN)
  lcd.drawLine(x2, y2 - len, x2, y2, SOLID, CLR_DKGREEN)
  lcd.drawLine(x2 - len, y2, x2, y2, SOLID, CLR_DKGREEN)
end

local function countChecked()
  local n = 0
  for _, item in ipairs(items) do
    if item.checked then n = n + 1 end
  end
  return n
end

---------------------------------------------------------------------------
-- Header with Progress Bar
---------------------------------------------------------------------------

local function drawHeader()
  lcd.drawFilledRectangle(0, 0, W, 120, CLR_BG)

  -- Title
  lcd.drawText(10, 5, "PRE-FLIGHT CHECKLIST", MIDSIZE + CLR_GREEN)
  lcd.drawText(W - 100, 5, "UNCLASS", SMLSIZE + CLR_DKGREEN)

  -- UTC time
  local dt = getRtcTime and getRtcTime() or nil
  local timeStr
  if dt then
    timeStr = string.format("%02d:%02d:%02dZ", dt.hour or 0, dt.min or 0, dt.sec or 0)
  else
    local secs = math.floor(getTime() / 100)
    timeStr = string.format("T+%05d", secs)
  end
  lcd.drawText(W - 100, 28, timeStr, SMLSIZE + CLR_GREEN)

  lcd.drawLine(0, 48, W, 48, SOLID, CLR_DKGREEN)

  -- Progress bar
  local checked = countChecked()
  local pct = checked / NUM_ITEMS
  local barX = 15
  local barY = 58
  local barW = W - 30
  local barH = 24

  -- Background
  lcd.drawRectangle(barX, barY, barW, barH, CLR_DKGREEN)

  -- Fill
  local fillW = math.floor((barW - 2) * pct)
  if fillW > 0 then
    local fillClr = CLR_GREEN
    if pct < 0.5 then fillClr = CLR_RED
    elseif pct < 1.0 then fillClr = CLR_AMBER end
    lcd.drawFilledRectangle(barX + 1, barY + 1, fillW, barH - 2, fillClr)
  end

  -- Progress text
  local progStr = string.format("%d / %d COMPLETE", checked, NUM_ITEMS)
  lcd.drawText(barX + 10, barY + 3, progStr, SMLSIZE + CLR_BG)
  lcd.drawText(barX + barW - 50, barY + 3, string.format("%d%%", math.floor(pct * 100)), SMLSIZE + CLR_BG)

  -- Reset button
  local resetX = W - 130
  local resetY = 92
  lcd.drawFilledRectangle(resetX, resetY, 115, 24, CLR_DARKRED)
  lcd.drawText(resetX + 15, resetY + 4, "RESET ALL", SMLSIZE + CLR_WHITE)

  -- Item count label
  lcd.drawText(15, 95, string.format("ITEMS: %d", NUM_ITEMS), SMLSIZE + CLR_DKGREEN)

  lcd.drawLine(0, 120, W, 120, SOLID, CLR_DKGREEN)
end

---------------------------------------------------------------------------
-- Checklist Items
---------------------------------------------------------------------------

local function drawChecklist()
  -- Clip region
  local visibleItems = math.floor((LIST_BOTTOM - LIST_TOP) / ITEM_HEIGHT)

  for idx = 1, NUM_ITEMS do
    local drawIdx = idx - scrollOffset
    if drawIdx >= 1 and drawIdx <= visibleItems then
      local item = items[idx]
      local y = LIST_TOP + (drawIdx - 1) * ITEM_HEIGHT

      -- Row background (alternating subtle shading)
      if idx % 2 == 0 then
        lcd.drawFilledRectangle(5, y, W - 10, ITEM_HEIGHT - 4, lcd.RGB(0x08, 0x12, 0x08))
      end

      -- Auto-check from telemetry
      if item.autoFn then
        local autoResult = item.autoFn()
        if autoResult and not item.checked then
          item.checked = true
        end
      end

      -- Checkbox
      local cbX = 15
      local cbY = y + 10
      local cbSize = 36

      if item.checked then
        -- Green filled checkbox with X
        lcd.drawFilledRectangle(cbX, cbY, cbSize, cbSize, CLR_GREEN)
        lcd.drawLine(cbX + 6, cbY + 6, cbX + cbSize - 6, cbY + cbSize - 6, SOLID, CLR_BG)
        lcd.drawLine(cbX + 6, cbY + cbSize - 6, cbX + cbSize - 6, cbY + 6, SOLID, CLR_BG)
        -- Thicken the X
        lcd.drawLine(cbX + 7, cbY + 6, cbX + cbSize - 5, cbY + cbSize - 6, SOLID, CLR_BG)
        lcd.drawLine(cbX + 7, cbY + cbSize - 6, cbX + cbSize - 5, cbY + 6, SOLID, CLR_BG)
      else
        -- Red empty checkbox
        lcd.drawRectangle(cbX, cbY, cbSize, cbSize, CLR_RED)
        lcd.drawRectangle(cbX + 1, cbY + 1, cbSize - 2, cbSize - 2, CLR_RED)
      end

      -- Item number
      local numX = cbX + cbSize + 10
      lcd.drawText(numX, y + 6, string.format("%02d", idx), SMLSIZE + CLR_DKGREEN)

      -- Category badge
      local catX = numX + 30
      local catClr = CLR_DKGREEN
      lcd.drawText(catX, y + 6, "[" .. item.cat .. "]", SMLSIZE + catClr)

      -- Item name
      local nameX = cbX + cbSize + 15
      local nameClr = item.checked and CLR_GREEN or CLR_RED
      lcd.drawText(nameX, y + 28, item.name, SMLSIZE + nameClr)

      -- Auto-check indicator
      if item.autoLabel then
        local autoX = W - 70
        local autoClr = item.checked and CLR_GREEN or CLR_AMBER
        lcd.drawText(autoX, y + 18, item.autoLabel, SMLSIZE + autoClr)
      end

      -- Separator line
      lcd.drawLine(15, y + ITEM_HEIGHT - 5, W - 15, y + ITEM_HEIGHT - 5, DOTTED, CLR_GRAY)
    end
  end

  -- Scroll indicators
  if scrollOffset > 0 then
    lcd.drawText(W / 2 - 15, LIST_TOP - 15, "^^^", SMLSIZE + CLR_AMBER)
  end
  if scrollOffset + visibleItems < NUM_ITEMS then
    lcd.drawText(W / 2 - 15, LIST_BOTTOM + 2, "vvv", SMLSIZE + CLR_AMBER)
  end
end

---------------------------------------------------------------------------
-- GO / NO-GO Status
---------------------------------------------------------------------------

local function drawGoNoGo()
  local by = H - 150
  lcd.drawLine(0, by, W, by, SOLID, CLR_DKGREEN)

  local checked = countChecked()
  local isGo = (checked == NUM_ITEMS)

  -- Large status box
  local boxY = by + 10
  local boxH = 80
  lcd.drawFilledRectangle(10, boxY, W - 20, boxH,
    isGo and lcd.RGB(0x00, 0x22, 0x00) or lcd.RGB(0x22, 0x00, 0x00))
  drawCornerBrackets(10, boxY, W - 10, boxY + boxH, 15)

  if isGo then
    lcd.drawText(W / 2 - 80, boxY + 10, "STATUS: GO", DBLSIZE + CLR_GREEN)
    lcd.drawText(W / 2 - 90, boxY + 50, "All checks passed", SMLSIZE + CLR_GREEN)
  else
    local remaining = NUM_ITEMS - checked
    lcd.drawText(W / 2 - 100, boxY + 10, "STATUS: NO-GO", DBLSIZE + CLR_RED)
    lcd.drawText(W / 2 - 90, boxY + 50,
      string.format("%d item%s remaining", remaining, remaining == 1 and "" or "s"),
      SMLSIZE + CLR_RED)
  end

  -- Status message bar
  local msgY = by + boxH + 20
  lcd.drawFilledRectangle(0, msgY, W, 30, CLR_BG)
  if statusTimer > 0 and statusMsg ~= "" then
    lcd.drawText(15, msgY + 6, statusMsg, SMLSIZE + CLR_AMBER)
    statusTimer = statusTimer - 1
  else
    lcd.drawText(15, msgY + 6, "TAP checkbox to toggle | RESET to clear all", SMLSIZE + CLR_GRAY)
  end

  lcd.drawText(W - 120, msgY + 6, "2xTAP EXIT", SMLSIZE + CLR_DKGREEN)
end

---------------------------------------------------------------------------
-- INIT
---------------------------------------------------------------------------

function M.init()
  CLR_GREEN   = lcd.RGB(0x00, 0xFF, 0x00)
  CLR_DKGREEN = lcd.RGB(0x00, 0x88, 0x00)
  CLR_AMBER   = lcd.RGB(0xFF, 0xAA, 0x00)
  CLR_RED     = lcd.RGB(0xFF, 0x00, 0x00)
  CLR_BG      = lcd.RGB(0x0A, 0x0A, 0x0A)
  CLR_GRAY    = lcd.RGB(0x44, 0x44, 0x44)
  CLR_WHITE   = lcd.RGB(0xFF, 0xFF, 0xFF)
  CLR_DARKRED = lcd.RGB(0x88, 0x00, 0x00)

  initChecklist()
end

---------------------------------------------------------------------------
-- RUN
---------------------------------------------------------------------------

function M.run(event, touchState)
  lcd.clear(CLR_BG)

  -- Handle touch events
  if event == EVT_TOUCH_TAP and touchState then
    local tx, ty = touchState.x, touchState.y

    -- Reset button
    if tx >= (W - 130) and tx <= W and ty >= 92 and ty <= 116 then
      for _, item in ipairs(items) do
        item.checked = false
      end
      statusMsg = "CHECKLIST RESET"
      statusTimer = 40
    end

    -- Checklist item toggle
    local visibleItems = math.floor((LIST_BOTTOM - LIST_TOP) / ITEM_HEIGHT)
    if ty >= LIST_TOP and ty <= LIST_BOTTOM then
      local drawIdx = math.floor((ty - LIST_TOP) / ITEM_HEIGHT) + 1
      local itemIdx = drawIdx + scrollOffset
      if itemIdx >= 1 and itemIdx <= NUM_ITEMS then
        items[itemIdx].checked = not items[itemIdx].checked
        local state = items[itemIdx].checked and "CHECKED" or "UNCHECKED"
        statusMsg = string.format("%02d: %s - %s", itemIdx, items[itemIdx].name, state)
        statusTimer = 30
      end
    end

    -- Scroll up (tap above list)
    if ty < LIST_TOP and ty > 120 and scrollOffset > 0 then
      scrollOffset = scrollOffset - 1
    end

    -- Scroll down (tap below list, above go/nogo)
    if ty > LIST_BOTTOM and ty < (H - 150) then
      local visItems = math.floor((LIST_BOTTOM - LIST_TOP) / ITEM_HEIGHT)
      if scrollOffset + visItems < NUM_ITEMS then
        scrollOffset = scrollOffset + 1
      end
    end

    -- Double-tap top-left to exit
    if tx < 60 and ty < 60 then
      return 1
    end
  end

  -- Handle scroll via swipe
  if event == EVT_TOUCH_SLIDE and touchState then
    if touchState.swipeUp then
      local visItems = math.floor((LIST_BOTTOM - LIST_TOP) / ITEM_HEIGHT)
      if scrollOffset + visItems < NUM_ITEMS then
        scrollOffset = scrollOffset + 1
      end
    elseif touchState.swipeDown then
      if scrollOffset > 0 then
        scrollOffset = scrollOffset - 1
      end
    end
  end

  -- Draw all sections
  drawHeader()
  drawChecklist()
  drawGoNoGo()

  -- HUD corner brackets
  drawCornerBrackets(3, 3, W - 3, H - 3, 20)

  return 0
end

return M
