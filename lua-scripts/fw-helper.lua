-- TNS|FW Helper|TNE
-- Fixed-Wing Flight Helper for ArduPlane / INAV Operations
-- Military green styling, touch-enabled for AX12 color LCD
-- Approach calculator, stall speed, bank angle, wind triangle,
-- takeoff/landing checklists, pattern timer

local LCD_W = 480
local LCD_H = 272

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
    white    = lcd.RGB(255, 255, 255),
    black    = lcd.RGB(0, 0, 0),
    accent   = lcd.RGB(0, 180, 255),
    slider   = lcd.RGB(0, 120, 50),
    knob     = lcd.RGB(0, 255, 100),
    chkOn    = lcd.RGB(0, 220, 80),
    chkOff   = lcd.RGB(80, 80, 80),
}

-- Pages
local PAGE_APPROACH  = 1
local PAGE_STALL     = 2
local PAGE_BANK      = 3
local PAGE_WIND      = 4
local PAGE_CHECKLIST = 5
local PAGE_TIMER     = 6
local NUM_PAGES      = 6

local currentPage = PAGE_APPROACH

-- Touch areas
local touchAreas = {}

-- Math helpers
local function rad(d) return d * math.pi / 180 end
local function deg(r) return r * 180 / math.pi end
local function clamp(v, lo, hi) return math.max(lo, math.min(hi, v)) end

local function addTouch(x, y, w, h, id)
    touchAreas[#touchAreas + 1] = { x=x, y=y, w=w, h=h, id=id }
end

-- ---------------------------------------------------------------------------
-- Shared drawing helpers
-- ---------------------------------------------------------------------------
local function drawPanel(x, y, w, h)
    lcd.drawFilledRectangle(x, y, w, h, C.panel)
    lcd.drawRectangle(x, y, w, h, C.border)
end

local function drawBtn(x, y, w, h, label, id, active)
    local bg = active and C.knob or C.slider
    lcd.drawFilledRectangle(x, y, w, h, bg)
    lcd.drawRectangle(x, y, w, h, C.border)
    local col = active and C.black or C.textBrt
    lcd.drawText(x + 3, y + 2, label, SMLSIZE + col)
    addTouch(x, y, w, h, id)
end

local function drawHeader(title)
    lcd.drawFilledRectangle(0, 0, LCD_W, 16, C.panel)
    lcd.drawText(4, 1, "FW HELPER", SMLSIZE + C.textBrt)
    lcd.drawText(90, 1, title, SMLSIZE + C.text)
    -- Page nav dots
    for i = 1, NUM_PAGES do
        local dx = LCD_W - (NUM_PAGES - i + 1) * 14 - 4
        local col = (i == currentPage) and C.knob or C.textDim
        lcd.drawFilledRectangle(dx, 5, 10, 6, col)
        addTouch(dx - 2, 0, 14, 16, "page_" .. i)
    end
end

local function drawFooter(hint)
    lcd.drawFilledRectangle(0, LCD_H - 14, LCD_W, 14, C.black)
    lcd.drawText(4, LCD_H - 12, hint or "TAP dots to switch pages", SMLSIZE + C.textDim)
end

-- ---------------------------------------------------------------------------
-- PAGE 1: Approach Calculator
-- ---------------------------------------------------------------------------
local appr = {
    alt = 100,       -- meters AGL
    dist = 1000,     -- meters to threshold
    glide = 10,      -- glide ratio (e.g., 10:1)
    speed = 20,      -- approach speed m/s
}

local function drawApproach()
    drawHeader("APPROACH CALC")

    local y = 22
    drawPanel(4, y, 230, LCD_H - 40)

    -- Inputs
    local labels = {
        { name="ALT (m)",   key="alt",   val=appr.alt,   inc="alt_inc",   dec="alt_dec" },
        { name="DIST (m)",  key="dist",  val=appr.dist,  inc="dist_inc",  dec="dist_dec" },
        { name="GLIDE",     key="glide", val=appr.glide, inc="glide_inc", dec="glide_dec" },
        { name="SPD (m/s)", key="speed", val=appr.speed, inc="spd_inc",   dec="spd_dec" },
    }

    for i, l in ipairs(labels) do
        local ly = y + 6 + (i - 1) * 42
        lcd.drawText(10, ly, l.name, SMLSIZE + C.textDim)
        lcd.drawText(10, ly + 12, string.format("%d", l.val), MIDSIZE + C.text)
        drawBtn(140, ly + 8, 28, 22, "-", l.dec, false)
        drawBtn(174, ly + 8, 28, 22, "+", l.inc, false)
    end

    -- Results panel
    drawPanel(240, y, 236, LCD_H - 40)
    local rx = 248
    local ry = y + 6

    -- Descent angle
    local descentAngle = 0
    if appr.dist > 0 then
        descentAngle = deg(math.atan(appr.alt / appr.dist))
    end
    lcd.drawText(rx, ry, "DESCENT ANGLE", SMLSIZE + C.textDim)
    ry = ry + 12
    local angCol = C.safe
    if descentAngle > 5 then angCol = C.warn end
    if descentAngle > 10 then angCol = C.danger end
    lcd.drawText(rx, ry, string.format("%.1f", descentAngle) .. "\194\176", DBLSIZE + angCol)

    -- Required glide ratio
    ry = ry + 30
    lcd.drawText(rx, ry, "REQUIRED GLIDE", SMLSIZE + C.textDim)
    ry = ry + 12
    local reqGlide = 0
    if appr.alt > 0 then
        reqGlide = appr.dist / appr.alt
    end
    local glideCol = (reqGlide <= appr.glide) and C.safe or C.danger
    lcd.drawText(rx, ry, string.format("%.1f : 1", reqGlide), MIDSIZE + glideCol)
    lcd.drawText(rx + 90, ry + 2, reqGlide <= appr.glide and "MAKEABLE" or "TOO STEEP", SMLSIZE + glideCol)

    -- Time to landing
    ry = ry + 22
    lcd.drawText(rx, ry, "TIME TO THRESHOLD", SMLSIZE + C.textDim)
    ry = ry + 12
    local ttl = 0
    if appr.speed > 0 then
        ttl = appr.dist / appr.speed
    end
    local mins = math.floor(ttl / 60)
    local secs = math.floor(ttl % 60)
    lcd.drawText(rx, ry, string.format("%d:%02d", mins, secs), MIDSIZE + C.text)
    lcd.drawText(rx + 60, ry + 2, string.format("(%.0fs)", ttl), SMLSIZE + C.textDim)

    -- Descent rate
    ry = ry + 22
    lcd.drawText(rx, ry, "DESCENT RATE", SMLSIZE + C.textDim)
    ry = ry + 12
    local vspd = 0
    if ttl > 0 then
        vspd = appr.alt / ttl
    end
    lcd.drawText(rx, ry, string.format("%.1f m/s", vspd), MIDSIZE + C.text)
    lcd.drawText(rx + 90, ry + 2, string.format("%.0f ft/min", vspd * 196.85), SMLSIZE + C.textDim)

    drawFooter("Adjust inputs with +/- buttons")
end

local function handleApproach(id)
    if id == "alt_inc"   then appr.alt   = clamp(appr.alt + 10, 0, 5000) end
    if id == "alt_dec"   then appr.alt   = clamp(appr.alt - 10, 0, 5000) end
    if id == "dist_inc"  then appr.dist  = clamp(appr.dist + 100, 0, 50000) end
    if id == "dist_dec"  then appr.dist  = clamp(appr.dist - 100, 0, 50000) end
    if id == "glide_inc" then appr.glide = clamp(appr.glide + 1, 1, 50) end
    if id == "glide_dec" then appr.glide = clamp(appr.glide - 1, 1, 50) end
    if id == "spd_inc"   then appr.speed = clamp(appr.speed + 1, 1, 100) end
    if id == "spd_dec"   then appr.speed = clamp(appr.speed - 1, 1, 100) end
end

-- ---------------------------------------------------------------------------
-- PAGE 2: Stall Speed Warning
-- ---------------------------------------------------------------------------
local stall = {
    stallSpeed = 12,  -- m/s
    warnMargin = 5,   -- m/s above stall for yellow zone
}

local function drawStall()
    drawHeader("STALL SPEED")

    -- Get airspeed from telemetry
    local aspd = 0
    local aspdField = getFieldInfo("ASpd")
    if aspdField then
        aspd = getValue(aspdField.id) or 0
    end
    -- Fallback: try GSpd
    if aspd == 0 then
        local gspdField = getFieldInfo("GSpd")
        if gspdField then
            aspd = getValue(gspdField.id) or 0
        end
    end

    local y = 22
    drawPanel(4, y, LCD_W - 8, 80)

    -- Config row
    lcd.drawText(10, y + 4, "STALL SPD", SMLSIZE + C.textDim)
    lcd.drawText(10, y + 16, string.format("%d m/s", stall.stallSpeed), MIDSIZE + C.text)
    drawBtn(100, y + 14, 24, 20, "-", "stall_dec", false)
    drawBtn(128, y + 14, 24, 20, "+", "stall_inc", false)

    lcd.drawText(170, y + 4, "WARN MARGIN", SMLSIZE + C.textDim)
    lcd.drawText(170, y + 16, string.format("+%d m/s", stall.warnMargin), MIDSIZE + C.text)
    drawBtn(260, y + 14, 24, 20, "-", "margin_dec", false)
    drawBtn(288, y + 14, 24, 20, "+", "margin_inc", false)

    -- Current speed display
    lcd.drawText(340, y + 4, "AIRSPEED", SMLSIZE + C.textDim)
    local spdCol = C.safe
    local spdLabel = "SAFE"
    if aspd <= stall.stallSpeed then
        spdCol = C.danger
        spdLabel = "STALL"
    elseif aspd <= stall.stallSpeed + stall.warnMargin then
        spdCol = C.warn
        spdLabel = "CAUTION"
    end
    lcd.drawText(340, y + 14, string.format("%.0f", aspd), DBLSIZE + spdCol)
    lcd.drawText(400, y + 20, "m/s", SMLSIZE + spdCol)
    lcd.drawText(340, y + 44, spdLabel, MIDSIZE + spdCol)

    -- Speed bar
    y = 110
    drawPanel(4, y, LCD_W - 8, 80)

    local barX = 20
    local barY = y + 30
    local barW = LCD_W - 40
    local barH = 30

    -- Scale: 0 to stallSpeed * 3
    local maxSpd = stall.stallSpeed * 3
    local stallPx = (stall.stallSpeed / maxSpd) * barW
    local warnPx  = ((stall.stallSpeed + stall.warnMargin) / maxSpd) * barW

    -- Red zone
    lcd.drawFilledRectangle(barX, barY, math.floor(stallPx), barH, C.danger)
    -- Yellow zone
    lcd.drawFilledRectangle(barX + math.floor(stallPx), barY,
        math.floor(warnPx - stallPx), barH, C.warn)
    -- Green zone
    lcd.drawFilledRectangle(barX + math.floor(warnPx), barY,
        barW - math.floor(warnPx), barH, C.safe)

    -- Border
    lcd.drawRectangle(barX, barY, barW, barH, C.border)

    -- Labels
    lcd.drawText(barX, barY - 12, "STALL", SMLSIZE + C.danger)
    lcd.drawText(barX + math.floor(stallPx) + 2, barY - 12, "CAUTION", SMLSIZE + C.warn)
    lcd.drawText(barX + math.floor(warnPx) + 2, barY - 12, "SAFE", SMLSIZE + C.safe)

    -- Speed marker
    local spdPx = clamp((aspd / maxSpd) * barW, 0, barW - 2)
    lcd.drawFilledRectangle(barX + math.floor(spdPx) - 2, barY - 4, 5, barH + 8, C.white)

    -- Scale numbers
    for i = 0, maxSpd, math.floor(maxSpd / 6) do
        local px = barX + (i / maxSpd) * barW
        lcd.drawText(px - 4, barY + barH + 4, tostring(i), SMLSIZE + C.textDim)
    end

    lcd.drawText(barX, y + 6, "SPEED ENVELOPE (m/s)", SMLSIZE + C.textDim)

    drawFooter(spdLabel == "STALL" and "WARNING: BELOW STALL SPEED" or "Airspeed indicator active")
end

local function handleStall(id)
    if id == "stall_inc"  then stall.stallSpeed = clamp(stall.stallSpeed + 1, 5, 50) end
    if id == "stall_dec"  then stall.stallSpeed = clamp(stall.stallSpeed - 1, 5, 50) end
    if id == "margin_inc" then stall.warnMargin = clamp(stall.warnMargin + 1, 1, 20) end
    if id == "margin_dec" then stall.warnMargin = clamp(stall.warnMargin - 1, 1, 20) end
end

-- ---------------------------------------------------------------------------
-- PAGE 3: Bank Angle Advisor
-- ---------------------------------------------------------------------------
local function drawBank()
    drawHeader("BANK ANGLE")

    -- Get roll from telemetry
    local roll = 0
    local rollField = getFieldInfo("Roll")
    if rollField then
        roll = getValue(rollField.id) or 0
    end

    -- Get altitude from telemetry
    local alt = 0
    local altField = getFieldInfo("Alt")
    if altField then
        alt = getValue(altField.id) or 0
    end

    local absRoll = math.abs(roll)

    -- Recommended max bank for altitude
    local maxBank = 45
    if alt < 50 then maxBank = 15
    elseif alt < 100 then maxBank = 25
    elseif alt < 200 then maxBank = 35
    end

    local y = 22
    drawPanel(4, y, 230, LCD_H - 40)

    -- Artificial horizon style bank indicator
    local cx = 120
    local cy = y + 80
    local hR = 60

    -- Draw circle
    lcd.drawCircle(cx, cy, hR, C.border)
    lcd.drawCircle(cx, cy, hR - 1, C.border)

    -- Draw roll line
    local rollRad = rad(roll)
    local lx1 = cx - hR * math.cos(rollRad)
    local ly1 = cy - hR * math.sin(rollRad)
    local lx2 = cx + hR * math.cos(rollRad)
    local ly2 = cy + hR * math.sin(rollRad)
    local rollCol = C.safe
    if absRoll > maxBank then rollCol = C.danger
    elseif absRoll > maxBank - 10 then rollCol = C.warn
    end
    lcd.drawLine(lx1, ly1, lx2, ly2, SOLID, rollCol)

    -- Center dot
    lcd.drawFilledRectangle(cx - 2, cy - 2, 5, 5, C.text)

    -- Bank angle text
    lcd.drawText(10, cy + hR + 10, "BANK", SMLSIZE + C.textDim)
    lcd.drawText(10, cy + hR + 22, string.format("%.0f", roll) .. "\194\176", MIDSIZE + rollCol)
    local dir = "LEVEL"
    if roll > 2 then dir = "RIGHT" elseif roll < -2 then dir = "LEFT" end
    lcd.drawText(70, cy + hR + 24, dir, SMLSIZE + rollCol)

    -- Right panel: recommendations
    drawPanel(240, y, 236, LCD_H - 40)
    local rx = 248
    local ry = y + 6

    lcd.drawText(rx, ry, "ALTITUDE", SMLSIZE + C.textDim)
    ry = ry + 12
    lcd.drawText(rx, ry, string.format("%.0f m", alt), MIDSIZE + C.text)

    ry = ry + 24
    lcd.drawText(rx, ry, "MAX RECOMMENDED BANK", SMLSIZE + C.textDim)
    ry = ry + 12
    lcd.drawText(rx, ry, string.format("%d", maxBank) .. "\194\176", MIDSIZE + C.safe)

    ry = ry + 24
    lcd.drawText(rx, ry, "CURRENT BANK", SMLSIZE + C.textDim)
    ry = ry + 12
    lcd.drawText(rx, ry, string.format("%.0f", absRoll) .. "\194\176", MIDSIZE + rollCol)

    ry = ry + 24
    lcd.drawText(rx, ry, "STATUS", SMLSIZE + C.textDim)
    ry = ry + 12
    if absRoll > maxBank then
        lcd.drawText(rx, ry, "EXCESSIVE BANK", MIDSIZE + C.danger)
        lcd.drawText(rx, ry + 18, "Reduce bank angle!", SMLSIZE + C.danger)
    elseif absRoll > maxBank - 10 then
        lcd.drawText(rx, ry, "APPROACHING LIMIT", MIDSIZE + C.warn)
    else
        lcd.drawText(rx, ry, "WITHIN LIMITS", MIDSIZE + C.safe)
    end

    -- Altitude-bank table
    ry = ry + 30
    lcd.drawText(rx, ry, "ALT BANK LIMITS", SMLSIZE + C.textDim)
    ry = ry + 12
    local limits = { {"<50m", "15"}, {"50-100m", "25"}, {"100-200m", "35"}, {">200m", "45"} }
    for _, l in ipairs(limits) do
        lcd.drawText(rx + 4, ry, l[1], SMLSIZE + C.textDim)
        lcd.drawText(rx + 80, ry, l[2] .. "\194\176", SMLSIZE + C.text)
        ry = ry + 11
    end

    drawFooter("Bank limits based on altitude")
end

-- ---------------------------------------------------------------------------
-- PAGE 4: Wind Triangle
-- ---------------------------------------------------------------------------
local wind = {
    windSpd = 5,    -- knots
    windDir = 270,  -- degrees true (from)
    heading = 0,    -- degrees true
    airspeed = 40,  -- knots TAS
}

local function drawWind()
    drawHeader("WIND TRIANGLE")

    local y = 22

    -- Input panel
    drawPanel(4, y, 200, LCD_H - 40)
    local lx = 10
    local ly = y + 4

    local inputs = {
        { name="WIND SPD (kt)", val=wind.windSpd, inc="ws_inc", dec="ws_dec" },
        { name="WIND DIR",      val=wind.windDir, inc="wd_inc", dec="wd_dec" },
        { name="HEADING",       val=wind.heading, inc="hd_inc", dec="hd_dec" },
        { name="TAS (kt)",      val=wind.airspeed, inc="tas_inc", dec="tas_dec" },
    }

    for i, inp in ipairs(inputs) do
        lcd.drawText(lx, ly, inp.name, SMLSIZE + C.textDim)
        ly = ly + 11
        lcd.drawText(lx, ly, string.format("%d", inp.val), MIDSIZE + C.text)
        drawBtn(100, ly - 2, 28, 20, "-", inp.dec, false)
        drawBtn(132, ly - 2, 28, 20, "+", inp.inc, false)
        ly = ly + 24
    end

    -- Try telemetry
    local telemHdg = getFieldInfo("Hdg")
    if telemHdg then
        local v = getValue(telemHdg.id)
        if v and v ~= 0 then
            lcd.drawText(lx, ly, "TELEM HDG: " .. string.format("%d", v), SMLSIZE + C.accent)
        end
    end

    -- Calculate wind triangle
    local windRad = rad(wind.windDir)
    local hdgRad  = rad(wind.heading)

    -- Wind vector (where wind blows TO, opposite of FROM)
    local wx = wind.windSpd * math.sin(windRad + math.pi)
    local wy = wind.windSpd * math.cos(windRad + math.pi)

    -- Airspeed vector (direction aircraft is pointed)
    local ax = wind.airspeed * math.sin(hdgRad)
    local ay = wind.airspeed * math.cos(hdgRad)

    -- Groundspeed vector = airspeed + wind
    local gx = ax + wx
    local gy = ay + wy

    local groundspeed = math.sqrt(gx * gx + gy * gy)
    local track = deg(math.atan2(gx, gy))
    if track < 0 then track = track + 360 end

    -- Wind correction angle
    local wca = track - wind.heading
    if wca > 180 then wca = wca - 360 end
    if wca < -180 then wca = wca + 360 end

    -- Results panel
    drawPanel(210, y, 266, 110)
    local rx = 218
    local ry = y + 4

    lcd.drawText(rx, ry, "GROUNDSPEED", SMLSIZE + C.textDim)
    ry = ry + 12
    lcd.drawText(rx, ry, string.format("%.1f kt", groundspeed), MIDSIZE + C.text)
    lcd.drawText(rx + 100, ry + 2, string.format("(%.1f m/s)", groundspeed * 0.5144), SMLSIZE + C.textDim)

    ry = ry + 22
    lcd.drawText(rx, ry, "TRACK", SMLSIZE + C.textDim)
    lcd.drawText(rx + 60, ry, string.format("%03.0f", track) .. "\194\176", MIDSIZE + C.text)

    ry = ry + 22
    lcd.drawText(rx, ry, "WCA", SMLSIZE + C.textDim)
    local wcaDir = "NONE"
    if wca > 0.5 then wcaDir = string.format("+%.1f R", wca)
    elseif wca < -0.5 then wcaDir = string.format("%.1f L", wca) end
    lcd.drawText(rx + 60, ry, wcaDir, MIDSIZE + C.text)

    ry = ry + 22
    lcd.drawText(rx, ry, "HEAD/TAIL", SMLSIZE + C.textDim)
    local headComp = wind.windSpd * math.cos(rad(wind.windDir - wind.heading))
    local htLabel = headComp > 0 and "HEADWIND" or "TAILWIND"
    local htCol = headComp > 0 and C.warn or C.safe
    lcd.drawText(rx + 60, ry, string.format("%.1f kt %s", math.abs(headComp), htLabel), SMLSIZE + htCol)

    -- Wind rose mini
    drawPanel(210, y + 116, 266, LCD_H - 40 - 116)
    local roseCX = 340
    local roseCY = y + 116 + 60
    local roseR = 48

    lcd.drawCircle(roseCX, roseCY, roseR, C.border)

    -- Cardinal marks
    local cards = { {0,"N"}, {90,"E"}, {180,"S"}, {270,"W"} }
    for _, c in ipairs(cards) do
        local a = rad(c[1] - 90)
        local tx = roseCX + (roseR + 8) * math.cos(a)
        local ty = roseCY + (roseR + 8) * math.sin(a)
        lcd.drawText(tx - 3, ty - 4, c[2], SMLSIZE + C.textDim)
    end

    -- Heading arrow (blue)
    local ha = rad(wind.heading - 90)
    lcd.drawLine(roseCX, roseCY,
        roseCX + roseR * 0.8 * math.cos(ha),
        roseCY + roseR * 0.8 * math.sin(ha),
        SOLID, C.accent)

    -- Track arrow (green)
    local ta = rad(track - 90)
    lcd.drawLine(roseCX, roseCY,
        roseCX + roseR * 0.6 * math.cos(ta),
        roseCY + roseR * 0.6 * math.sin(ta),
        SOLID, C.safe)

    -- Wind arrow (red, from direction)
    local wa = rad(wind.windDir - 90)
    lcd.drawLine(roseCX + roseR * 0.8 * math.cos(wa),
        roseCY + roseR * 0.8 * math.sin(wa),
        roseCX, roseCY,
        SOLID, C.danger)

    -- Legend
    lcd.drawText(218, roseCY + roseR - 8, "HDG", SMLSIZE + C.accent)
    lcd.drawText(218, roseCY + roseR + 4, "TRK", SMLSIZE + C.safe)
    lcd.drawText(218, roseCY + roseR + 16, "WIND", SMLSIZE + C.danger)

    drawFooter("Wind FROM " .. string.format("%03d", wind.windDir) .. " at " .. wind.windSpd .. " kt")
end

local function handleWind(id)
    if id == "ws_inc"  then wind.windSpd = clamp(wind.windSpd + 1, 0, 80) end
    if id == "ws_dec"  then wind.windSpd = clamp(wind.windSpd - 1, 0, 80) end
    if id == "wd_inc"  then wind.windDir = (wind.windDir + 5) % 360 end
    if id == "wd_dec"  then wind.windDir = (wind.windDir - 5 + 360) % 360 end
    if id == "hd_inc"  then wind.heading = (wind.heading + 5) % 360 end
    if id == "hd_dec"  then wind.heading = (wind.heading - 5 + 360) % 360 end
    if id == "tas_inc" then wind.airspeed = clamp(wind.airspeed + 1, 1, 200) end
    if id == "tas_dec" then wind.airspeed = clamp(wind.airspeed - 1, 1, 200) end
end

-- ---------------------------------------------------------------------------
-- PAGE 5: Takeoff / Landing Checklists
-- ---------------------------------------------------------------------------
local checklists = {
    takeoff = {
        { text = "Control surfaces free",  done = false },
        { text = "Throttle response",      done = false },
        { text = "GPS lock confirmed",     done = false },
        { text = "Telemetry link active",  done = false },
        { text = "Flight mode correct",    done = false },
        { text = "Wind check complete",    done = false },
        { text = "Airspace clear",         done = false },
        { text = "Arm and launch",         done = false },
    },
    landing = {
        { text = "Approach altitude set",  done = false },
        { text = "Airspeed nominal",       done = false },
        { text = "Landing area clear",     done = false },
        { text = "Gear/flaps configured",  done = false },
        { text = "Wind check complete",    done = false },
        { text = "Final approach aligned", done = false },
        { text = "Throttle to idle",       done = false },
        { text = "Disarm after stop",      done = false },
    },
}
local activeChecklist = "takeoff"

local function drawChecklist()
    drawHeader("CHECKLISTS")

    local y = 22

    -- Tab buttons
    drawBtn(4, y, 80, 18, "TAKEOFF", "ck_takeoff", activeChecklist == "takeoff")
    drawBtn(90, y, 80, 18, "LANDING", "ck_landing", activeChecklist == "landing")
    drawBtn(200, y, 60, 18, "RESET", "ck_reset", false)

    y = y + 24
    local list = checklists[activeChecklist]
    local doneCount = 0

    drawPanel(4, y, LCD_W - 8, LCD_H - y - 18)

    for i, item in ipairs(list) do
        local iy = y + 4 + (i - 1) * 25
        local col = item.done and C.chkOn or C.chkOff
        local textCol = item.done and C.textDim or C.text

        -- Checkbox
        lcd.drawRectangle(12, iy + 2, 16, 16, col)
        if item.done then
            lcd.drawLine(14, iy + 10, 18, iy + 14, SOLID, C.chkOn)
            lcd.drawLine(18, iy + 14, 26, iy + 4, SOLID, C.chkOn)
            doneCount = doneCount + 1
        end

        -- Item text
        lcd.drawText(34, iy + 3, string.format("%d. %s", i, item.text), SMLSIZE + textCol)

        addTouch(4, iy, LCD_W - 8, 24, "ck_item_" .. i)
    end

    -- Progress
    local total = #list
    local pct = (doneCount / total) * 100
    local progCol = (doneCount == total) and C.safe or C.warn
    drawFooter(string.format("%s: %d/%d complete (%.0f%%)",
        activeChecklist:upper(), doneCount, total, pct))
end

local function handleChecklist(id)
    if id == "ck_takeoff" then activeChecklist = "takeoff" end
    if id == "ck_landing" then activeChecklist = "landing" end
    if id == "ck_reset" then
        for _, item in ipairs(checklists[activeChecklist]) do
            item.done = false
        end
    end
    -- Toggle individual items
    for i = 1, 8 do
        if id == "ck_item_" .. i then
            local list = checklists[activeChecklist]
            if list[i] then
                list[i].done = not list[i].done
            end
        end
    end
end

-- ---------------------------------------------------------------------------
-- PAGE 6: Pattern Timer
-- ---------------------------------------------------------------------------
local pattern = {
    legs = { "CROSSWIND", "DOWNWIND", "BASE", "FINAL" },
    legTimes = { 0, 0, 0, 0 },    -- elapsed time per leg in seconds
    currentLeg = 0,                 -- 0 = stopped
    legStart = 0,                   -- os.clock when leg started
    running = false,
    history = {},                   -- completed patterns
}

local function drawTimer()
    drawHeader("PATTERN TIMER")

    local y = 22
    local now = os.clock()

    -- Current leg elapsed
    local currentElapsed = 0
    if pattern.running and pattern.currentLeg > 0 then
        currentElapsed = now - pattern.legStart
    end

    -- Controls
    drawBtn(4, y, 60, 22, "START", "tmr_start", pattern.running and pattern.currentLeg == 1 and #pattern.history == 0)
    drawBtn(70, y, 50, 22, "NEXT", "tmr_next", pattern.running)
    drawBtn(126, y, 50, 22, "STOP", "tmr_stop", false)
    drawBtn(182, y, 55, 22, "RESET", "tmr_reset", false)

    y = y + 28

    -- Leg display
    drawPanel(4, y, LCD_W - 8, 120)

    for i, leg in ipairs(pattern.legs) do
        local ly = y + 4 + (i - 1) * 28
        local isActive = (pattern.currentLeg == i and pattern.running)
        local col = isActive and C.textBrt or C.textDim
        local timeCol = isActive and C.knob or C.text

        -- Leg name
        if isActive then
            lcd.drawFilledRectangle(8, ly, LCD_W - 16, 24, C.slider)
        end
        lcd.drawText(14, ly + 4, string.format("%d", i), SMLSIZE + col)
        lcd.drawText(30, ly + 2, leg, MIDSIZE + col)

        -- Time
        local t = pattern.legTimes[i]
        if isActive then
            t = currentElapsed
        end
        local mins = math.floor(t / 60)
        local secs = math.floor(t % 60)
        local tenths = math.floor((t % 1) * 10)
        lcd.drawText(250, ly + 2, string.format("%d:%02d.%d", mins, secs, tenths), MIDSIZE + timeCol)

        -- Bar graph
        local maxTime = 120 -- 2 minutes max display
        local barLen = clamp((t / maxTime) * 150, 0, 150)
        lcd.drawFilledRectangle(320, ly + 6, math.floor(barLen), 12, timeCol)
        lcd.drawRectangle(320, ly + 6, 150, 12, C.border)
    end

    -- Total time
    y = y + 124
    drawPanel(4, y, LCD_W - 8, 40)
    local totalTime = 0
    for i, t in ipairs(pattern.legTimes) do
        if pattern.currentLeg == i and pattern.running then
            totalTime = totalTime + currentElapsed
        else
            totalTime = totalTime + t
        end
    end
    lcd.drawText(10, y + 4, "TOTAL PATTERN", SMLSIZE + C.textDim)
    local tmins = math.floor(totalTime / 60)
    local tsecs = math.floor(totalTime % 60)
    lcd.drawText(10, y + 16, string.format("%d:%02d", tmins, tsecs), MIDSIZE + C.text)

    -- Status
    local statusText = "STOPPED"
    if pattern.running and pattern.currentLeg > 0 then
        statusText = pattern.legs[pattern.currentLeg] .. " LEG ACTIVE"
    end

    -- History count
    if #pattern.history > 0 then
        lcd.drawText(200, y + 4, "PATTERNS", SMLSIZE + C.textDim)
        lcd.drawText(200, y + 16, tostring(#pattern.history), MIDSIZE + C.text)
    end

    drawFooter(statusText)
end

local function handleTimer(id)
    local now = os.clock()
    if id == "tmr_start" and not pattern.running then
        pattern.running = true
        pattern.currentLeg = 1
        pattern.legStart = now
        pattern.legTimes = { 0, 0, 0, 0 }
    end
    if id == "tmr_next" and pattern.running then
        -- Save current leg time
        pattern.legTimes[pattern.currentLeg] = now - pattern.legStart
        if pattern.currentLeg < #pattern.legs then
            pattern.currentLeg = pattern.currentLeg + 1
            pattern.legStart = now
        else
            -- Pattern complete
            pattern.running = false
            pattern.history[#pattern.history + 1] = {
                legs = { pattern.legTimes[1], pattern.legTimes[2],
                         pattern.legTimes[3], pattern.legTimes[4] }
            }
            pattern.currentLeg = 0
        end
    end
    if id == "tmr_stop" then
        if pattern.running and pattern.currentLeg > 0 then
            pattern.legTimes[pattern.currentLeg] = now - pattern.legStart
        end
        pattern.running = false
        pattern.currentLeg = 0
    end
    if id == "tmr_reset" then
        pattern.running = false
        pattern.currentLeg = 0
        pattern.legTimes = { 0, 0, 0, 0 }
        pattern.history = {}
    end
end

-- ---------------------------------------------------------------------------
-- Main init / run
-- ---------------------------------------------------------------------------

local function init()
    -- nothing needed
end

local function run(event, touchState)
    touchAreas = {}
    lcd.clear(C.bg)

    -- Draw current page
    if currentPage == PAGE_APPROACH then
        drawApproach()
    elseif currentPage == PAGE_STALL then
        drawStall()
    elseif currentPage == PAGE_BANK then
        drawBank()
    elseif currentPage == PAGE_WIND then
        drawWind()
    elseif currentPage == PAGE_CHECKLIST then
        drawChecklist()
    elseif currentPage == PAGE_TIMER then
        drawTimer()
    end

    -- Handle touch
    if touchState then
        local tx, ty = touchState.x, touchState.y
        if touchState.event == EVT_TOUCH_TAP or touchState.event == EVT_TOUCH_FIRST then
            for _, area in ipairs(touchAreas) do
                if tx >= area.x and tx <= area.x + area.w and
                   ty >= area.y and ty <= area.y + area.h then
                    -- Page navigation
                    for p = 1, NUM_PAGES do
                        if area.id == "page_" .. p then
                            currentPage = p
                        end
                    end
                    -- Page-specific handlers
                    if currentPage == PAGE_APPROACH then handleApproach(area.id) end
                    if currentPage == PAGE_STALL then handleStall(area.id) end
                    if currentPage == PAGE_WIND then handleWind(area.id) end
                    if currentPage == PAGE_CHECKLIST then handleChecklist(area.id) end
                    if currentPage == PAGE_TIMER then handleTimer(area.id) end
                end
            end
        end
    end

    -- Handle rotary / keys for page switching
    if event == EVT_VIRTUAL_NEXT or event == EVT_PAGE_BREAK then
        currentPage = (currentPage % NUM_PAGES) + 1
    elseif event == EVT_VIRTUAL_PREV or event == EVT_PAGE_LONG then
        currentPage = ((currentPage - 2) % NUM_PAGES) + 1
    end

    return 0
end

return { init=init, run=run }
