-- TNS|CCIP Targeting|TNE
-- Continuously Computed Impact Point reticle for payload drops
-- Physics: fall_time = sqrt(2*alt/g), drift = speed * fall_time

local SCREEN_W = 720
local SCREEN_H = 1280
local CENTER_X = SCREEN_W / 2
local CENTER_Y = SCREEN_H / 2
local G = 9.81
local FOV_FACTOR = 300  -- pixels_per_meter = FOV_FACTOR / altitude
local MAX_RANGE = 100   -- meters, max useful range

-- Colors (HUD green theme)
local COL_BG        = lcd.RGB(0, 0, 0)
local COL_HUD       = lcd.RGB(0, 255, 0)
local COL_HUD_DIM   = lcd.RGB(0, 120, 0)
local COL_HUD_DARK  = lcd.RGB(0, 60, 0)
local COL_RELEASE   = lcd.RGB(0, 255, 0)
local COL_WARNING   = lcd.RGB(255, 80, 0)
local COL_RED       = lcd.RGB(255, 0, 0)
local COL_WHITE     = lcd.RGB(255, 255, 255)
local COL_LABEL     = lcd.RGB(0, 180, 0)

-- State
local altitude = 30       -- meters AGL
local groundspeed = 5     -- m/s
local heading = 0         -- degrees
local wind_speed = 0      -- m/s
local wind_dir = 0        -- degrees (direction wind blows FROM)
local manual_mode = true
local release_flash = 0
local touch_active = false
local touch_x0 = 0
local touch_y0 = 0
local alt_at_touch = 0
local gs_at_touch = 0

-- Telemetry sensor IDs (ELRS/CRSF)
local id_alt = nil
local id_gs  = nil
local id_hdg = nil

local function tryGetValue(name)
    local v = getValue(name)
    if v and v ~= 0 then return v end
    return nil
end

local function initSensors()
    id_alt = tryGetValue("Alt") or tryGetValue("GAlt") or tryGetValue("Altitude")
    id_gs  = tryGetValue("GSpd") or tryGetValue("Gspd") or tryGetValue("GPS Speed")
    id_hdg = tryGetValue("Hdg") or tryGetValue("Heading") or tryGetValue("Yaw")
end

local function readTelemetry()
    local a = tryGetValue("Alt") or tryGetValue("GAlt")
    local s = tryGetValue("GSpd") or tryGetValue("Gspd")
    local h = tryGetValue("Hdg") or tryGetValue("Yaw")
    if a and a > 0 then
        altitude = a
        manual_mode = false
    end
    if s then
        groundspeed = s
        manual_mode = false
    end
    if h then
        heading = h
    end
end

-- Physics calculations
local function calcFallTime(alt)
    if alt <= 0 then return 0 end
    return math.sqrt(2 * alt / G)
end

local function calcDrift(speed, fall_time)
    return speed * fall_time
end

local function pixelsPerMeter(alt)
    if alt <= 0 then return 10 end
    return FOV_FACTOR / alt
end

-- Draw functions
local function drawCrosshair()
    -- Dim green fixed crosshair at center (nadir)
    local len = 40
    local gap = 8
    lcd.drawLine(CENTER_X - len, CENTER_Y, CENTER_X - gap, CENTER_Y, DOTTED, COL_HUD_DIM)
    lcd.drawLine(CENTER_X + gap, CENTER_Y, CENTER_X + len, CENTER_Y, DOTTED, COL_HUD_DIM)
    lcd.drawLine(CENTER_X, CENTER_Y - len, CENTER_X, CENTER_Y - gap, DOTTED, COL_HUD_DIM)
    lcd.drawLine(CENTER_X, CENTER_Y + gap, CENTER_X, CENTER_Y + len, DOTTED, COL_HUD_DIM)
    -- Small center dot
    lcd.drawFilledCircle(CENTER_X, CENTER_Y, 2, COL_HUD_DIM)
end

local function drawRangeRings(ppm)
    -- Range rings at 10m, 25m, 50m intervals
    local rings = {10, 25, 50}
    for _, r in ipairs(rings) do
        local px = math.floor(r * ppm)
        if px > 10 and px < SCREEN_H then
            lcd.drawCircle(CENTER_X, CENTER_Y, px, COL_HUD_DARK)
            lcd.drawText(CENTER_X + px + 4, CENTER_Y - 10, tostring(r) .. "m", SMLSIZE + COL_HUD_DARK)
        end
    end
end

local function drawHeadingBar()
    -- Heading indicator bar at top
    local bar_y = 30
    local bar_w = 400
    local bar_x = CENTER_X - bar_w / 2
    lcd.drawLine(bar_x, bar_y, bar_x + bar_w, bar_y, SOLID, COL_HUD_DIM)
    -- Tick marks every 10 degrees
    for i = -20, 20 do
        local deg = (math.floor(heading / 10) + i) * 10
        local x = CENTER_X + (deg - heading) * 3
        if x >= bar_x and x <= bar_x + bar_w then
            local tick_len = (deg % 30 == 0) and 12 or 6
            lcd.drawLine(x, bar_y - tick_len, x, bar_y, SOLID, COL_HUD_DIM)
            if deg % 30 == 0 then
                local lbl = tostring(deg % 360)
                if deg % 360 == 0 then lbl = "N"
                elseif deg % 360 == 90 then lbl = "E"
                elseif deg % 360 == 180 then lbl = "S"
                elseif deg % 360 == 270 then lbl = "W"
                end
                lcd.drawText(x - 6, bar_y - 26, lbl, SMLSIZE + COL_HUD)
            end
        end
    end
    -- Center caret
    lcd.drawLine(CENTER_X, bar_y + 2, CENTER_X - 6, bar_y + 10, SOLID, COL_HUD)
    lcd.drawLine(CENTER_X, bar_y + 2, CENTER_X + 6, bar_y + 10, SOLID, COL_HUD)
    -- Heading readout
    lcd.drawText(CENTER_X - 18, bar_y + 12, string.format("%03d", heading % 360), MIDSIZE + COL_HUD)
end

local function drawDiamond(cx, cy, size, color)
    lcd.drawLine(cx, cy - size, cx + size, cy, SOLID, color)
    lcd.drawLine(cx + size, cy, cx, cy + size, SOLID, color)
    lcd.drawLine(cx, cy + size, cx - size, cy, SOLID, color)
    lcd.drawLine(cx - size, cy, cx, cy - size, SOLID, color)
end

local function drawCCIPReticle(rx, ry, in_range)
    local col = in_range and COL_HUD or COL_WARNING
    -- Diamond reticle
    drawDiamond(rx, ry, 16, col)
    drawDiamond(rx, ry, 18, col)
    -- Inner dot
    lcd.drawFilledCircle(rx, ry, 3, col)
    -- Drift vector line from center to CCIP
    lcd.drawLine(CENTER_X, CENTER_Y, rx, ry, DOTTED, COL_HUD_DIM)
    -- Arrow head on the drift line
    local dx = rx - CENTER_X
    local dy = ry - CENTER_Y
    local dist = math.sqrt(dx * dx + dy * dy)
    if dist > 30 then
        local nx = dx / dist
        local ny = dy / dist
        local ax = rx - nx * 12
        local ay = ry - ny * 12
        lcd.drawLine(rx, ry, math.floor(ax - ny * 6), math.floor(ay + nx * 6), SOLID, col)
        lcd.drawLine(rx, ry, math.floor(ax + ny * 6), math.floor(ay - nx * 6), SOLID, col)
    end
end

local function drawDataPanel(fall_time, fwd_drift, wind_drift_lat, total_drift, in_range)
    local x = 10
    local y = SCREEN_H - 260
    local lh = 32

    lcd.drawText(x, y, "ALT", SMLSIZE + COL_LABEL)
    lcd.drawText(x + 80, y, string.format("%.1f m", altitude), MIDSIZE + COL_HUD)
    y = y + lh

    lcd.drawText(x, y, "GS", SMLSIZE + COL_LABEL)
    lcd.drawText(x + 80, y, string.format("%.1f m/s", groundspeed), MIDSIZE + COL_HUD)
    y = y + lh

    lcd.drawText(x, y, "WIND", SMLSIZE + COL_LABEL)
    lcd.drawText(x + 80, y, string.format("%.1f m/s %03d", wind_speed, wind_dir), MIDSIZE + COL_HUD)
    y = y + lh

    lcd.drawText(x, y, "FALL", SMLSIZE + COL_LABEL)
    lcd.drawText(x + 80, y, string.format("%.2f s", fall_time), MIDSIZE + COL_HUD)
    y = y + lh

    lcd.drawText(x, y, "DRIFT", SMLSIZE + COL_LABEL)
    lcd.drawText(x + 80, y, string.format("%.1f m", total_drift), MIDSIZE + COL_HUD)
    y = y + lh

    -- Mode indicator
    if manual_mode then
        lcd.drawText(x, y, "MANUAL", MIDSIZE + COL_WARNING)
    else
        lcd.drawText(x, y, "TELEM", MIDSIZE + COL_HUD)
    end
    y = y + lh

    -- Range indicator
    if in_range then
        lcd.drawText(x, y, "IN RANGE", MIDSIZE + COL_HUD)
    else
        lcd.drawText(x, y, "OUT OF RANGE", MIDSIZE + COL_RED)
    end
end

local function drawReleaseCue()
    if release_flash > 0 then
        -- Flash RELEASE text
        if math.floor(release_flash * 4) % 2 == 0 then
            lcd.drawFilledRectangle(CENTER_X - 120, CENTER_Y - 80, 240, 50, COL_BG)
            lcd.drawRectangle(CENTER_X - 120, CENTER_Y - 80, 240, 50, COL_RELEASE)
            lcd.drawText(CENTER_X - 80, CENTER_Y - 72, "RELEASE", DBLSIZE + COL_RELEASE)
        end
    end
end

local function drawWindIndicator()
    -- Wind arrow in top-right corner
    local wx = SCREEN_W - 80
    local wy = 80
    local arrow_len = math.min(wind_speed * 5, 40)
    if wind_speed > 0 then
        local rad = math.rad(wind_dir)
        local ex = wx + math.sin(rad) * arrow_len
        local ey = wy - math.cos(rad) * arrow_len
        lcd.drawLine(wx, wy, math.floor(ex), math.floor(ey), SOLID, COL_HUD)
        lcd.drawCircle(wx, wy, 3, COL_HUD_DIM)
        lcd.drawText(wx - 20, wy + 20, "WIND", SMLSIZE + COL_HUD_DIM)
    else
        lcd.drawText(wx - 20, wy, "CALM", SMLSIZE + COL_HUD_DIM)
    end
end

local function drawManualHelp()
    if manual_mode then
        local y = SCREEN_H - 50
        lcd.drawText(10, y, "TOUCH: Slide V=ALT  H=SPD  Tap=WIND", SMLSIZE + COL_HUD_DARK)
    end
end

-- Touch handling for manual mode
local function handleTouch(event, touchState)
    if event == EVT_TOUCH_FIRST then
        touch_active = true
        touch_x0 = (touchState and touchState.x) or CENTER_X
        touch_y0 = (touchState and touchState.y) or CENTER_Y
        alt_at_touch = altitude
        gs_at_touch = groundspeed
    elseif event == EVT_TOUCH_SLIDE and touch_active then
        local tx = (touchState and touchState.x) or touch_x0
        local ty = (touchState and touchState.y) or touch_y0
        local dx = tx - touch_x0
        local dy = ty - touch_y0
        -- Vertical slide = altitude (up = higher)
        altitude = math.max(1, math.min(200, alt_at_touch - dy * 0.3))
        -- Horizontal slide = groundspeed
        groundspeed = math.max(0, math.min(50, gs_at_touch + dx * 0.05))
    elseif event == EVT_TOUCH_TAP then
        -- Tap cycles wind speed: 0 -> 2 -> 5 -> 8 -> 0
        local winds = {0, 2, 5, 8}
        local idx = 1
        for i, w in ipairs(winds) do
            if math.abs(wind_speed - w) < 0.5 then idx = i + 1 end
        end
        if idx > #winds then idx = 1 end
        wind_speed = winds[idx]
        touch_active = false
    elseif event == EVT_TOUCH_BREAK then
        touch_active = false
    end
end

-- Main functions
local function init()
    initSensors()
end

local function run(event, touchState)
    -- Clear screen
    lcd.clear(COL_BG)

    -- Try reading telemetry
    readTelemetry()

    -- Handle touch input (manual mode adjustments)
    if event and manual_mode then
        handleTouch(event, touchState)
    end

    -- Physics
    local fall_time = calcFallTime(altitude)
    local fwd_drift = calcDrift(groundspeed, fall_time)

    -- Wind drift components (relative to drone heading)
    local wind_rad = math.rad(wind_dir - heading)
    local wind_drift_fwd = wind_speed * fall_time * math.cos(wind_rad)
    local wind_drift_lat = wind_speed * fall_time * math.sin(wind_rad)

    -- Total drift in body frame (forward, lateral)
    local total_fwd = fwd_drift + wind_drift_fwd
    local total_lat = wind_drift_lat
    local total_drift = math.sqrt(total_fwd * total_fwd + total_lat * total_lat)

    -- Pixel conversion
    local ppm = pixelsPerMeter(altitude)

    -- Reticle position (forward = down on screen, lateral = right)
    local reticle_x = math.floor(CENTER_X + total_lat * ppm)
    local reticle_y = math.floor(CENTER_Y + total_fwd * ppm)

    -- Clamp to screen
    reticle_x = math.max(20, math.min(SCREEN_W - 20, reticle_x))
    reticle_y = math.max(60, math.min(SCREEN_H - 60, reticle_y))

    -- Check if in range (reticle near center = aligned for release)
    local reticle_dist = math.sqrt((reticle_x - CENTER_X)^2 + (reticle_y - CENTER_Y)^2)
    local in_range = total_drift < MAX_RANGE

    -- Release detection: CCIP within 20px of center
    if reticle_dist < 20 and groundspeed > 0.5 then
        release_flash = 2.0  -- seconds of flash
    elseif release_flash > 0 then
        release_flash = release_flash - 0.05
    end

    -- Draw layers (back to front)
    drawRangeRings(ppm)
    drawCrosshair()
    drawCCIPReticle(reticle_x, reticle_y, in_range)
    drawHeadingBar()
    drawWindIndicator()
    drawDataPanel(fall_time, fwd_drift, wind_drift_lat, total_drift, in_range)
    drawReleaseCue()
    drawManualHelp()

    -- Border frame
    lcd.drawRectangle(0, 0, SCREEN_W, SCREEN_H, COL_HUD_DARK)

    return 0
end

return { init=init, run=run }
