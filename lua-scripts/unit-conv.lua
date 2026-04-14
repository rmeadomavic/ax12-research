-- TNS|Unit Conv|TNE
local LCD_W, LCD_H = 480, 272
local categories = {"Speed","Dist","Alt","Temp","Wt","Press"}
local selCat = 1
local inputVal = 1.0
local selUnit = 1
local stepIdx = 4
local steps = {0.01, 0.1, 0.5, 1, 5, 10, 50, 100}

-- Colors (dark theme)
local BG       = BLACK
local FG       = WHITE
local ACCENT   = BLUE
local HILIGHT  = YELLOW
local DARKGREY = lcd.RGB(40, 40, 40)
local DIMWHITE = lcd.RGB(180, 180, 180)
local GREEN    = lcd.RGB(0, 200, 80)
local ROWALT   = lcd.RGB(25, 25, 25)
local ROWSEL   = lcd.RGB(30, 30, 60)
local BTNRED   = lcd.RGB(120, 20, 20)
local BTNGRN   = lcd.RGB(20, 100, 20)

-- Unit defs: {name, toBase(v), fromBase(v)}
local units = {
  Speed = {
    {"m/s",  function(v) return v end,              function(v) return v end},
    {"km/h", function(v) return v/3.6 end,          function(v) return v*3.6 end},
    {"mph",  function(v) return v*0.44704 end,      function(v) return v/0.44704 end},
    {"kts",  function(v) return v*0.514444 end,     function(v) return v/0.514444 end},
    {"ft/s", function(v) return v*0.3048 end,       function(v) return v/0.3048 end},
  },
  Dist = {
    {"m",    function(v) return v end,              function(v) return v end},
    {"ft",   function(v) return v*0.3048 end,       function(v) return v/0.3048 end},
    {"mi",   function(v) return v*1609.344 end,     function(v) return v/1609.344 end},
    {"NM",   function(v) return v*1852 end,         function(v) return v/1852 end},
    {"yd",   function(v) return v*0.9144 end,       function(v) return v/0.9144 end},
    {"km",   function(v) return v*1000 end,         function(v) return v/1000 end},
  },
  Alt = {
    {"m",    function(v) return v end,              function(v) return v end},
    {"ft",   function(v) return v*0.3048 end,       function(v) return v/0.3048 end},
    {"FL",   function(v) return v*30.48 end,        function(v) return v/30.48 end},
  },
  Temp = {
    {"C",    function(v) return v end,              function(v) return v end},
    {"F",    function(v) return (v-32)*5/9 end,     function(v) return v*9/5+32 end},
  },
  Wt = {
    {"g",    function(v) return v end,              function(v) return v end},
    {"oz",   function(v) return v*28.3495 end,      function(v) return v/28.3495 end},
    {"lb",   function(v) return v*453.592 end,      function(v) return v/453.592 end},
    {"kg",   function(v) return v*1000 end,         function(v) return v/1000 end},
  },
  Press = {
    {"hPa",  function(v) return v end,              function(v) return v end},
    {"inHg", function(v) return v*33.8639 end,      function(v) return v/33.8639 end},
    {"mmHg", function(v) return v*1.33322 end,      function(v) return v/1.33322 end},
    {"PSI",  function(v) return v*68.9476 end,      function(v) return v/68.9476 end},
  },
}

local resultY = {}

local function fmt(v)
  local a = math.abs(v)
  if a >= 10000 then return string.format("%.1f", v)
  elseif a >= 100 then return string.format("%.2f", v)
  elseif a >= 1 then return string.format("%.3f", v)
  else return string.format("%.4f", v) end
end

local function init()
  selCat = 1
  inputVal = 1.0
  selUnit = 1
  stepIdx = 4
end

local function run(event, touchState)
  lcd.clear(BG)
  local cat = categories[selCat]
  local u = units[cat]

  -- TAB BAR
  local tabW = math.floor(LCD_W / #categories)
  for i, c in ipairs(categories) do
    local x = (i-1) * tabW
    if i == selCat then
      lcd.drawFilledRectangle(x, 0, tabW, 24, ACCENT)
      lcd.drawText(x + math.floor(tabW/2), 4, c, MIDSIZE + WHITE + CENTER)
    else
      lcd.drawFilledRectangle(x, 0, tabW, 24, DARKGREY)
      lcd.drawText(x + math.floor(tabW/2), 5, c, SMLSIZE + DIMWHITE + CENTER)
    end
  end
  lcd.drawLine(0, 24, LCD_W, 24, SOLID, GREY_DEFAULT)

  -- INPUT ROW
  local iy = 28
  local uName = u[selUnit][1]
  lcd.drawText(8, iy, uName, MIDSIZE + GREEN)
  lcd.drawText(56, iy-2, fmt(inputVal), DBLSIZE + WHITE)

  -- Step indicator
  lcd.drawText(LCD_W-8, iy, "step:"..steps[stepIdx], SMLSIZE + DIMWHITE + RIGHT)

  -- +/- buttons
  local btnW, btnH = 50, 28
  local minusX = LCD_W - 120
  local plusX  = LCD_W - 60
  local btnY = iy + 20
  lcd.drawFilledRectangle(minusX, btnY, btnW, btnH, BTNRED)
  lcd.drawText(minusX + math.floor(btnW/2), btnY+4, "-", MIDSIZE + WHITE + CENTER)
  lcd.drawFilledRectangle(plusX, btnY, btnW, btnH, BTNGRN)
  lcd.drawText(plusX + math.floor(btnW/2), btnY+4, "+", MIDSIZE + WHITE + CENTER)

  -- RESULTS
  local baseVal = u[selUnit][2](inputVal)
  local ry = 72
  local rowH = math.min(32, math.floor((LCD_H - ry) / #u))
  resultY = {}
  for i, entry in ipairs(u) do
    local y = ry + (i-1) * rowH
    resultY[i] = y
    if i == selUnit then
      lcd.drawFilledRectangle(0, y, LCD_W, rowH, ROWSEL)
    elseif i % 2 == 0 then
      lcd.drawFilledRectangle(0, y, LCD_W, rowH, ROWALT)
    end
    local converted = entry[3](baseVal)
    lcd.drawText(12, y + math.floor(rowH/2) - 6, entry[1], SMLSIZE + HILIGHT)
    lcd.drawText(60, y + math.floor(rowH/2) - 9, fmt(converted), MIDSIZE + FG)
  end

  -- TOUCH
  if touchState and event == EVT_TOUCH_TAP then
    local tx, ty = touchState.x, touchState.y
    -- Tabs
    if ty < 24 then
      local nc = math.floor(tx / tabW) + 1
      if nc >= 1 and nc <= #categories then
        selCat = nc; selUnit = 1; inputVal = 1.0
      end
    end
    -- +/- buttons
    if ty >= btnY and ty <= btnY + btnH then
      if tx >= minusX and tx < minusX + btnW then
        inputVal = inputVal - steps[stepIdx]
      elseif tx >= plusX and tx < plusX + btnW then
        inputVal = inputVal + steps[stepIdx]
      end
    end
    -- Result row tap -> adopt value as new input
    for i, y in ipairs(resultY) do
      if ty >= y and ty < y + rowH and i ~= selUnit then
        inputVal = u[i][3](u[selUnit][2](inputVal))
        selUnit = i
        break
      end
    end
  end

  -- ENCODER / KEYS
  if event == EVT_VIRTUAL_INC or event == EVT_ROT_RIGHT then
    inputVal = inputVal + steps[stepIdx]
  elseif event == EVT_VIRTUAL_DEC or event == EVT_ROT_LEFT then
    inputVal = inputVal - steps[stepIdx]
  elseif event == EVT_VIRTUAL_NEXT then
    selUnit = selUnit % #u + 1
  elseif event == EVT_VIRTUAL_PREV then
    selUnit = (selUnit - 2) % #u + 1
  elseif event == EVT_VIRTUAL_ENTER then
    stepIdx = stepIdx % #steps + 1
  end

  return 0
end

return { init=init, run=run }
