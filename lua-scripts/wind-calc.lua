-- TNS|Wind Calc|TNE
-- Wind Component Calculator for Drone Operations
-- Military HUD styling, touch-enabled for AX12 color LCD

local LCD_W = 480
local LCD_H = 272

-- State
local windSpeed = 10      -- knots
local windDir = 0          -- degrees true
local droneHdg = 0         -- degrees true
local useTelemHdg = false  -- use telemetry heading

-- Touch zones (populated in run)
local touchAreas = {}

-- Colors - Military Green HUD
local C = {
    bg       = lcd.RGB(10, 18, 10),
    panel    = lcd.RGB(18, 30, 18),
    border   = lcd.RGB(40, 70, 40),
    text     = lcd.RGB(0, 255, 70),
    textDim  = lcd.RGB(0, 150, 50),
    textBrt  = lcd.RGB(100, 255, 130),
    warn     = lcd.RGB(255, 200, 0),
    danger   = lcd.RGB(255, 60, 40),
    safe     = lcd.RGB(0, 220, 80),
    rose     = lcd.RGB(0, 200, 60),
    roseDim  = lcd.RGB(0, 80, 30),
    arrow    = lcd.RGB(255, 80, 40),
    hdgLine  = lcd.RGB(0, 180, 255),
    slider   = lcd.RGB(0, 120, 50),
    sliderKnob = lcd.RGB(0, 255, 100),
    white    = lcd.RGB(255, 255, 255),
    black    = lcd.RGB(0, 0, 0),
}

-- Beaufort scale thresholds in knots
local beaufort = {
    { max = 1,   name = "Calm",       num = 0 },
    { max = 3,   name = "Light Air",  num = 1 },
    { max = 6,   name = "Lt Breeze",  num = 2 },
    { max = 10,  name = "Gnt Breeze", num = 3 },
    { max = 16,  name = "Mod Breeze", num = 4 },
    { max = 21,  name = "Fresh",      num = 5 },
    { max = 27,  name = "Strong",     num = 6 },
    { max = 33,  name = "Near Gale",  num = 7 },
    { max = 40,  name = "Gale",       num = 8 },
    { max = 47,  name = "Str Gale",   num = 9 },
    { max = 55,  name = "Storm",      num = 10 },
    { max = 63,  name = "Viol Storm", num = 11 },
    { max = 999, name = "Hurricane",  num = 12 },
}

-- Drone type limits in knots
local droneTypes = {
    { name = "MICRO",  limit = 10 },
    { name = "5-INCH", limit = 20 },
    { name = "LARGE",  limit = 30 },
}

-- Math helpers
local function rad(d) return d * math.pi / 180 end
local function deg(r) return r * 180 / math.pi end
local function clamp(v, lo, hi) return math.max(lo, math.min(hi, v)) end
local function normAngle(a) return ((a % 360) + 360) % 360 end

-- Get Beaufort info for wind speed
local function getBeaufort(kt)
    for _, b in ipairs(beaufort) do
        if kt <= b.max then return b end
    end
    return beaufort[#beaufort]
end

-- Calculate wind components relative to heading
local function calcComponents()
    local relAngle = normAngle(windDir - droneHdg)
    local relRad = rad(relAngle)

    -- Headwind is positive when wind is coming FROM ahead
    local headwind = windSpeed * math.cos(relRad)
    local crosswind = windSpeed * math.sin(relRad)

    -- Wind correction angle (crab angle)
    local wca = 0
    if windSpeed > 0 then
        local sinWCA = crosswind / math.max(windSpeed, 1)
        sinWCA = clamp(sinWCA, -1, 1)
        wca = deg(math.asin(sinWCA))
    end

    -- Max safe speed recommendation: ground speed needed to maintain control
    local maxSafe = math.max(0, 40 - windSpeed * 0.8)

    return headwind, crosswind, wca, maxSafe, relAngle
end

-- Draw filled rectangle
local function drawPanel(x, y, w, h)
    lcd.drawFilledRectangle(x, y, w, h, C.panel)
    lcd.drawRectangle(x, y, w, h, C.border)
end

-- Draw increment/decrement button
local function drawBtn(x, y, w, h, label, id)
    lcd.drawFilledRectangle(x, y, w, h, C.slider)
    lcd.drawRectangle(x, y, w, h, C.border)
    lcd.drawText(x + w/2 - 4, y + 2, label, SMLSIZE + C.textBrt)
    touchAreas[#touchAreas + 1] = { x=x, y=y, w=w, h=h, id=id }
end

-- Draw wind rose with heading and wind direction
local function drawWindRose(cx, cy, radius)
    -- Background circle
    for r = radius, radius - 1, -1 do
        lcd.drawCircle(cx, cy, r, C.roseDim)
    end

    -- Cardinal directions relative to drone heading (N is drone heading)
    local cardinals = { {0, "N"}, {90, "E"}, {180, "S"}, {270, "W"} }
    for _, c in ipairs(cardinals) do
        local a = rad(c[1] - 90)  -- -90 to put N at top
        local tx = cx + (radius + 8) * math.cos(a)
        local ty = cy + (radius + 8) * math.sin(a)
        lcd.drawText(tx - 3, ty - 4, c[2], SMLSIZE + C.textDim)
    end

    -- Tick marks every 30 degrees
    for i = 0, 350, 30 do
        local a = rad(i - 90)
        local x1 = cx + (radius - 3) * math.cos(a)
        local y1 = cy + (radius - 3) * math.sin(a)
        local x2 = cx + radius * math.cos(a)
        local y2 = cy + radius * math.sin(a)
        lcd.drawLine(x1, y1, x2, y2, SOLID, C.rose)
    end

    -- Drone heading line (always points up = North on rose)
    local hdgA = rad(-90)  -- straight up
    local hx = cx + (radius - 5) * math.cos(hdgA)
    local hy = cy + (radius - 5) * math.sin(hdgA)
    lcd.drawLine(cx, cy, hx, hy, SOLID, C.hdgLine)
    -- Small triangle at tip for heading
    local triSize = 5
    local ta1 = hdgA - rad(150)
    local ta2 = hdgA + rad(150)
    lcd.drawLine(hx, hy,
        hx + triSize * math.cos(ta1), hy + triSize * math.sin(ta1),
        SOLID, C.hdgLine)
    lcd.drawLine(hx, hy,
        hx + triSize * math.cos(ta2), hy + triSize * math.sin(ta2),
        SOLID, C.hdgLine)

    -- Wind direction arrow (where wind comes FROM, relative to heading)
    local relWind = normAngle(windDir - droneHdg)
    local windA = rad(relWind - 90)  -- rotate so 0=top
    -- Arrow from edge toward center (wind blows FROM this direction)
    local wx1 = cx + (radius - 5) * math.cos(windA)
    local wy1 = cy + (radius - 5) * math.sin(windA)
    local wx2 = cx + 10 * math.cos(windA + math.pi)
    local wy2 = cy + 10 * math.sin(windA + math.pi)
    -- Don't draw to center, draw reverse direction
    wx2 = cx + (radius * 0.3) * math.cos(windA + math.pi)
    wy2 = cy + (radius * 0.3) * math.sin(windA + math.pi)
    lcd.drawLine(wx1, wy1, wx2, wy2, SOLID, C.arrow)
    -- Arrowhead at center-ish end
    local arrSize = 6
    local aa1 = windA + math.pi - rad(30)
    local aa2 = windA + math.pi + rad(30)
    lcd.drawLine(wx2, wy2,
        wx2 + arrSize * math.cos(aa1), wy2 + arrSize * math.sin(aa1),
        SOLID, C.arrow)
    lcd.drawLine(wx2, wy2,
        wx2 + arrSize * math.cos(aa2), wy2 + arrSize * math.sin(aa2),
        SOLID, C.arrow)

    -- Center dot
    lcd.drawFilledRectangle(cx - 1, cy - 1, 3, 3, C.text)

    -- Labels
    lcd.drawText(cx - 10, cy + radius + 14, "HDG", SMLSIZE + C.hdgLine)
    lcd.drawText(cx + 6, cy + radius + 14, "WIND", SMLSIZE + C.arrow)
end

-- Draw drone status indicators
local function drawDroneStatus(x, y, w)
    lcd.drawText(x, y, "PLATFORM STATUS", SMLSIZE + C.textDim)
    y = y + 12

    for _, dt in ipairs(droneTypes) do
        local ok = windSpeed <= dt.limit
        local col = ok and C.safe or C.danger
        local status = ok and "GO" or "NO-GO"
        local bar = ok and C.safe or C.danger

        lcd.drawFilledRectangle(x, y, 6, 8, bar)
        lcd.drawText(x + 9, y, dt.name, SMLSIZE + col)
        lcd.drawText(x + w - 30, y, status, SMLSIZE + col)
        y = y + 11
    end
end

-- Draw Beaufort indicator
local function drawBeaufort(x, y)
    local b = getBeaufort(windSpeed)
    lcd.drawText(x, y, "BEAUFORT", SMLSIZE + C.textDim)
    lcd.drawText(x, y + 11, "F" .. b.num, MIDSIZE + C.text)
    lcd.drawText(x + 28, y + 14, b.name, SMLSIZE + C.textDim)
end

-- Init
local function init()
    -- nothing needed
end

-- Main run function
local function run(event, touchState)
    touchAreas = {}

    lcd.clear(C.bg)

    -- Try to get telemetry heading
    local telemHdg = nil
    local hdgField = getFieldInfo("Hdg")
    if hdgField then
        local val = getValue(hdgField.id)
        if val and val ~= 0 then
            telemHdg = val
        end
    end
    if useTelemHdg and telemHdg then
        droneHdg = math.floor(telemHdg)
    end

    -- HEADER
    lcd.drawFilledRectangle(0, 0, LCD_W, 14, C.panel)
    lcd.drawText(4, 1, "WIND COMPONENT CALCULATOR", SMLSIZE + C.textBrt)
    lcd.drawText(LCD_W - 60, 1, string.format("%03d@%02dKT", windDir, windSpeed), SMLSIZE + C.text)

    -- LEFT PANEL: Input Controls (x=0..155)
    local lx = 4
    local ly = 18

    -- Wind Speed
    drawPanel(lx, ly, 150, 48)
    lcd.drawText(lx + 4, ly + 2, "WIND SPEED (KT)", SMLSIZE + C.textDim)
    lcd.drawText(lx + 30, ly + 14, string.format("%d", windSpeed), DBLSIZE + C.text)
    drawBtn(lx + 4, ly + 16, 22, 22, "-", "ws_dec")
    drawBtn(lx + 110, ly + 16, 22, 22, "+", "ws_inc")
    drawBtn(lx + 82, ly + 16, 24, 22, "+5", "ws_inc5")
    drawBtn(lx + 134, ly + 16, 14, 22, "0", "ws_zero")

    ly = ly + 52

    -- Wind Direction
    drawPanel(lx, ly, 150, 48)
    lcd.drawText(lx + 4, ly + 2, "WIND DIR (TRUE)", SMLSIZE + C.textDim)
    lcd.drawText(lx + 25, ly + 14, string.format("%03d", windDir) .. "\194\176", DBLSIZE + C.text)
    drawBtn(lx + 4, ly + 16, 22, 22, "-", "wd_dec")
    drawBtn(lx + 110, ly + 16, 22, 22, "+", "wd_inc")
    drawBtn(lx + 82, ly + 16, 24, 22, "+10", "wd_inc10")
    drawBtn(lx + 134, ly + 16, 14, 22, "0", "wd_zero")

    ly = ly + 52

    -- Drone Heading
    drawPanel(lx, ly, 150, 48)
    local hdgLabel = useTelemHdg and "HEADING (TELEM)" or "HEADING (MANUAL)"
    lcd.drawText(lx + 4, ly + 2, hdgLabel, SMLSIZE + C.textDim)
    lcd.drawText(lx + 25, ly + 14, string.format("%03d", droneHdg) .. "\194\176", DBLSIZE + C.text)
    if not useTelemHdg then
        drawBtn(lx + 4, ly + 16, 22, 22, "-", "hd_dec")
        drawBtn(lx + 110, ly + 16, 22, 22, "+", "hd_inc")
        drawBtn(lx + 82, ly + 16, 24, 22, "+10", "hd_inc10")
    end
    -- Telemetry toggle
    local tCol = useTelemHdg and C.safe or C.textDim
    drawBtn(lx + 134, ly + 16, 14, 22, "T", "hd_telem")

    ly = ly + 52

    -- Beaufort
    drawPanel(lx, ly, 150, 28)
    drawBeaufort(lx + 6, ly + 3)

    -- CENTER: Wind Rose (x=160..315)
    local roseCX = 235
    local roseCY = 130
    local roseR = 52
    drawPanel(158, 18, 155, 148)
    drawWindRose(roseCX, roseCY, roseR)

    -- Below rose: drone status
    drawPanel(158, 170, 155, 50)
    drawDroneStatus(163, 174, 145)

    -- Calculations
    local headwind, crosswind, wca, maxSafe, relAngle = calcComponents()

    -- RIGHT PANEL: Results (x=318..476)
    local rx = 318
    local ry = 18

    drawPanel(rx, ry, 158, LCD_H - 22)

    -- Headwind / Tailwind
    ry = ry + 4
    lcd.drawText(rx + 4, ry, "HEAD/TAIL WIND", SMLSIZE + C.textDim)
    ry = ry + 12
    local hwLabel, hwColor
    if headwind >= 0 then
        hwLabel = "HEADWIND"
        hwColor = C.warn
    else
        hwLabel = "TAILWIND"
        hwColor = C.safe
    end
    lcd.drawText(rx + 4, ry, hwLabel, SMLSIZE + hwColor)
    lcd.drawText(rx + 70, ry, string.format("%.1f KT", math.abs(headwind)), MIDSIZE + hwColor)

    -- Crosswind
    ry = ry + 22
    lcd.drawLine(rx + 4, ry, rx + 154, ry, DOTTED, C.border)
    ry = ry + 4
    lcd.drawText(rx + 4, ry, "CROSSWIND", SMLSIZE + C.textDim)
    ry = ry + 12
    local cwLabel, cwColor
    if math.abs(crosswind) < 0.5 then
        cwLabel = "NONE"
        cwColor = C.safe
    elseif crosswind > 0 then
        cwLabel = "FROM RIGHT"
        cwColor = C.warn
    else
        cwLabel = "FROM LEFT"
        cwColor = C.warn
    end
    lcd.drawText(rx + 4, ry, cwLabel, SMLSIZE + cwColor)
    lcd.drawText(rx + 70, ry, string.format("%.1f KT", math.abs(crosswind)), MIDSIZE + cwColor)

    -- Wind Correction Angle
    ry = ry + 22
    lcd.drawLine(rx + 4, ry, rx + 154, ry, DOTTED, C.border)
    ry = ry + 4
    lcd.drawText(rx + 4, ry, "WIND CORRECTION", SMLSIZE + C.textDim)
    ry = ry + 12
    local wcaDir = ""
    if wca > 0.5 then wcaDir = "R"
    elseif wca < -0.5 then wcaDir = "L"
    end
    lcd.drawText(rx + 4, ry, string.format("WCA: %.1f", math.abs(wca)) .. "\194\176 " .. wcaDir, MIDSIZE + C.text)

    -- Corrected heading
    ry = ry + 18
    local corrHdg = normAngle(droneHdg + wca)
    lcd.drawText(rx + 4, ry, string.format("CORR HDG: %03d", corrHdg) .. "\194\176", SMLSIZE + C.textBrt)

    -- Max Safe Speed
    ry = ry + 16
    lcd.drawLine(rx + 4, ry, rx + 154, ry, DOTTED, C.border)
    ry = ry + 4
    lcd.drawText(rx + 4, ry, "MAX SAFE GND SPD", SMLSIZE + C.textDim)
    ry = ry + 12
    local spdColor = maxSafe > 20 and C.safe or (maxSafe > 10 and C.warn or C.danger)
    lcd.drawText(rx + 4, ry, string.format("%.0f KT", maxSafe), MIDSIZE + spdColor)

    -- Relative wind angle
    ry = ry + 22
    lcd.drawLine(rx + 4, ry, rx + 154, ry, DOTTED, C.border)
    ry = ry + 4
    lcd.drawText(rx + 4, ry, "RELATIVE WIND", SMLSIZE + C.textDim)
    ry = ry + 12
    lcd.drawText(rx + 4, ry, string.format("%03d", relAngle) .. "\194\176 REL", SMLSIZE + C.text)

    -- Overall status bar at bottom
    local statusY = LCD_H - 18
    local overallOk = true
    for _, dt in ipairs(droneTypes) do
        if windSpeed > dt.limit then overallOk = false end
    end

    local b = getBeaufort(windSpeed)
    local statusCol, statusText
    if b.num <= 3 then
        statusCol = C.safe
        statusText = "CONDITIONS: FAVORABLE"
    elseif b.num <= 5 then
        statusCol = C.warn
        statusText = "CONDITIONS: MARGINAL"
    else
        statusCol = C.danger
        statusText = "CONDITIONS: HAZARDOUS"
    end
    lcd.drawFilledRectangle(0, LCD_H - 16, LCD_W, 16, C.black)
    lcd.drawText(LCD_W / 2 - 60, LCD_H - 14, statusText, SMLSIZE + statusCol)

    -- Handle touch events
    if touchState then
        local tx, ty = touchState.x, touchState.y
        if touchState.event == EVT_TOUCH_TAP or touchState.event == EVT_TOUCH_FIRST then
            for _, area in ipairs(touchAreas) do
                if tx >= area.x and tx <= area.x + area.w and
                   ty >= area.y and ty <= area.y + area.h then
                    if area.id == "ws_inc" then windSpeed = clamp(windSpeed + 1, 0, 99) end
                    if area.id == "ws_dec" then windSpeed = clamp(windSpeed - 1, 0, 99) end
                    if area.id == "ws_inc5" then windSpeed = clamp(windSpeed + 5, 0, 99) end
                    if area.id == "ws_zero" then windSpeed = 0 end
                    if area.id == "wd_inc" then windDir = normAngle(windDir + 5) end
                    if area.id == "wd_dec" then windDir = normAngle(windDir - 5) end
                    if area.id == "wd_inc10" then windDir = normAngle(windDir + 10) end
                    if area.id == "wd_zero" then windDir = 0 end
                    if area.id == "hd_inc" and not useTelemHdg then droneHdg = normAngle(droneHdg + 5) end
                    if area.id == "hd_dec" and not useTelemHdg then droneHdg = normAngle(droneHdg - 5) end
                    if area.id == "hd_inc10" and not useTelemHdg then droneHdg = normAngle(droneHdg + 10) end
                    if area.id == "hd_telem" then useTelemHdg = not useTelemHdg end
                end
            end
        end
    end

    -- Handle physical button events (rotary encoder / keys)
    if event == EVT_VIRTUAL_INC or event == EVT_ROT_RIGHT then
        windSpeed = clamp(windSpeed + 1, 0, 99)
    elseif event == EVT_VIRTUAL_DEC or event == EVT_ROT_LEFT then
        windSpeed = clamp(windSpeed - 1, 0, 99)
    end

    return 0
end

return { init=init, run=run }
