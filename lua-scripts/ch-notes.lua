-- TNS|Ch Notes|TNE
local PRESETS = {"AIL","ELE","THR","RUD","GEAR","FLAP","AUX1","AUX2","AUX3","AUX4","AUX5","AUX6","ARM","MODE","BEEP","CAMERA","GIMBAL","DROP","LIGHT"}
local DEFAULTS = {"AIL","ELE","THR","RUD","CH5","CH6","CH7","CH8","CH9","CH10","CH11","CH12","CH13","CH14","CH15","CH16"}
local SAVE_PATH = "/storage/emulated/0/AX12LUA/ch_labels.json"

local labels = {}
local notes = {}
local scroll = 0
local lastTouch = 0
local touchCh = -1
local W, H = LCD_W or 480, LCD_H or 320
local ROW_H = 36
local VISIBLE = math.floor((H - 30) / ROW_H)
local COL_LABEL = 70
local COL_BAR = 160
local BAR_W = 200

local function loadLabels()
  local f = io.open(SAVE_PATH, "r")
  if f then
    local data = f:read("*a")
    f:close()
    for i = 1, 16 do
      local pat_l = '"ch' .. i .. '_label"%s*:%s*"([^"]*)"'
      local pat_n = '"ch' .. i .. '_note"%s*:%s*"([^"]*)"'
      local lbl = data:match(pat_l)
      local nt = data:match(pat_n)
      labels[i] = lbl or DEFAULTS[i]
      notes[i] = nt or ""
    end
  else
    for i = 1, 16 do
      labels[i] = DEFAULTS[i]
      notes[i] = ""
    end
  end
end

local function saveLabels()
  local f = io.open(SAVE_PATH, "w")
  if f then
    f:write("{\n")
    for i = 1, 16 do
      local comma = i < 16 and "," or ""
      f:write(string.format('  "ch%d_label": "%s",\n  "ch%d_note": "%s"%s\n', i, labels[i], i, notes[i], comma))
    end
    f:write("}\n")
    f:close()
  end
end

local function nextPreset(current)
  for idx, p in ipairs(PRESETS) do
    if p == current then
      return PRESETS[(idx % #PRESETS) + 1]
    end
  end
  return PRESETS[1]
end

local function getChannelValue(ch)
  if getValue then
    local src = getValue(ch - 1 + 224)
    if src then return src end
  end
  return 0
end

local prevValues = {}
local function isActive(ch)
  local val = getChannelValue(ch)
  local prev = prevValues[ch] or val
  prevValues[ch] = val
  return math.abs(val - prev) > 20
end

local function init()
  loadLabels()
end

local function run(event, touchState)
  lcd.clear(lcd.RGB(20, 20, 25))

  -- Title bar
  lcd.color(lcd.RGB(40, 120, 200))
  lcd.drawFilledRectangle(0, 0, W, 26)
  lcd.color(lcd.RGB(255, 255, 255))
  lcd.font(FONT_STD)
  lcd.drawText(W/2 - 40, 4, "CH NOTES", 0)

  -- Handle touch
  if touchState then
    local tx, ty = touchState.x or 0, touchState.y or 0
    if touchState.event == EVT_TOUCH_TAP then
      local row = math.floor((ty - 28) / ROW_H)
      local ch = row + scroll + 1
      if ch >= 1 and ch <= 16 then
        labels[ch] = nextPreset(labels[ch])
        saveLabels()
      end
    elseif touchState.event == EVT_TOUCH_LONG then
      local row = math.floor((ty - 28) / ROW_H)
      local ch = row + scroll + 1
      if ch >= 1 and ch <= 16 then
        local notePresets = {"", "SWITCH", "KNOB", "SLIDER", "BUTTON", "MOMENTARY", "3-POS", "2-POS", "SPRING"}
        local found = 1
        for idx, np in ipairs(notePresets) do
          if notes[ch] == np then found = idx; break end
        end
        notes[ch] = notePresets[(found % #notePresets) + 1]
        saveLabels()
      end
    elseif touchState.event == EVT_TOUCH_SLIDE then
      if touchState.slideY and math.abs(touchState.slideY) > 10 then
        if touchState.slideY < 0 and scroll < 16 - VISIBLE then
          scroll = scroll + 1
        elseif touchState.slideY > 0 and scroll > 0 then
          scroll = scroll - 1
        end
      end
    end
  end

  -- Handle scroll via buttons
  if event then
    if event == EVT_VIRTUAL_PREV or event == EVT_ROT_LEFT then
      if scroll > 0 then scroll = scroll - 1 end
    elseif event == EVT_VIRTUAL_NEXT or event == EVT_ROT_RIGHT then
      if scroll < 16 - VISIBLE then scroll = scroll + 1 end
    end
  end

  -- Draw channel rows
  for row = 0, VISIBLE - 1 do
    local ch = row + scroll + 1
    if ch > 16 then break end
    local y = 28 + row * ROW_H
    local active = isActive(ch)

    -- Row background
    if active then
      lcd.color(lcd.RGB(40, 55, 40))
      lcd.drawFilledRectangle(0, y, W, ROW_H - 2)
    elseif ch % 2 == 0 then
      lcd.color(lcd.RGB(30, 30, 35))
      lcd.drawFilledRectangle(0, y, W, ROW_H - 2)
    end

    -- Channel number
    lcd.color(lcd.RGB(120, 120, 140))
    lcd.font(FONT_S)
    lcd.drawText(4, y + 4, string.format("CH%02d", ch), 0)

    -- Label
    if active then
      lcd.color(lcd.RGB(100, 255, 100))
    else
      lcd.color(lcd.RGB(220, 220, 240))
    end
    lcd.font(FONT_STD)
    lcd.drawText(COL_LABEL, y + 4, labels[ch], 0)

    -- Value bar
    local val = getChannelValue(ch)
    local pct = (val + 1024) / 2048
    if pct < 0 then pct = 0 end
    if pct > 1 then pct = 1 end
    lcd.color(lcd.RGB(50, 50, 60))
    lcd.drawFilledRectangle(COL_BAR, y + 6, BAR_W, 12)
    local barColor = active and lcd.RGB(80, 200, 80) or lcd.RGB(60, 140, 220)
    lcd.color(barColor)
    lcd.drawFilledRectangle(COL_BAR, y + 6, math.floor(BAR_W * pct), 12)
    -- Center mark
    lcd.color(lcd.RGB(180, 180, 180))
    lcd.drawLine(COL_BAR + BAR_W/2, y + 5, COL_BAR + BAR_W/2, y + 19)

    -- Value text
    lcd.color(lcd.RGB(160, 160, 180))
    lcd.font(FONT_XS)
    lcd.drawText(COL_BAR + BAR_W + 6, y + 6, tostring(val), 0)

    -- Note
    if notes[ch] ~= "" then
      lcd.color(lcd.RGB(180, 140, 60))
      lcd.font(FONT_XS)
      lcd.drawText(COL_LABEL, y + 20, notes[ch], 0)
    end
  end

  -- Scroll indicators
  if scroll > 0 then
    lcd.color(lcd.RGB(200, 200, 200))
    lcd.font(FONT_XS)
    lcd.drawText(W - 20, 28, "^", 0)
  end
  if scroll < 16 - VISIBLE then
    lcd.color(lcd.RGB(200, 200, 200))
    lcd.font(FONT_XS)
    lcd.drawText(W - 20, H - 16, "v", 0)
  end

  return 0
end

return { init=init, run=run }
