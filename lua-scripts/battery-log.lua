-- TNS|Battery Log|TNE
--
-- TX Battery Health Tracker for RadioMaster AX12
-- 2S Li-ion: 8.4V full, 6.0V empty
-- Logs voltage to file, displays real-time graph
--

local LOG_DIR = "/storage/emulated/0/AX12LUA/LOGS"
local LOG_INTERVAL = 60  -- seconds between file writes
local SAMPLE_INTERVAL = 2 -- seconds between graph samples
local GRAPH_DURATION = 1800 -- 30 minutes in seconds
local MAX_SAMPLES = math.floor(GRAPH_DURATION / SAMPLE_INTERVAL)

-- 2S Li-ion voltage constants
local V_FULL = 8.40
local V_EMPTY = 6.00
local V_RANGE = V_FULL - V_EMPTY
local CELLS = 2

-- Warning thresholds
local WARN_LOW = 20
local WARN_CRIT = 10

-- Colors (dark theme)
local C_BG = lcd.RGB(18, 18, 24)
local C_TEXT = lcd.RGB(200, 200, 210)
local C_DIM = lcd.RGB(100, 100, 120)
local C_GREEN = lcd.RGB(0, 200, 80)
local C_YELLOW = lcd.RGB(240, 200, 0)
local C_RED = lcd.RGB(240, 40, 40)
local C_GRAPH_BG = lcd.RGB(30, 30, 42)
local C_GRAPH_GRID = lcd.RGB(50, 50, 65)
local C_GRAPH_LINE = lcd.RGB(80, 180, 255)
local C_HEADER = lcd.RGB(40, 40, 55)
local C_WHITE = lcd.RGB(255, 255, 255)

-- State
local samples = {}
local startTime = 0
local lastSampleTime = 0
local lastLogTime = 0
local logFile = nil
local logFileName = ""
local rateSmoothed = 0
local prevVoltage = nil
local prevVoltageTime = 0

local function clamp(v, lo, hi)
    if v < lo then return lo end
    if v > hi then return hi end
    return v
end

local function voltToPercent(v)
    return clamp(math.floor(((v - V_EMPTY) / V_RANGE) * 100 + 0.5), 0, 100)
end

local function percentColor(pct)
    if pct > 50 then return C_GREEN end
    if pct > 20 then return C_YELLOW end
    return C_RED
end

local function formatTime(seconds)
    local h = math.floor(seconds / 3600)
    local m = math.floor((seconds % 3600) / 60)
    local s = math.floor(seconds % 60)
    if h > 0 then
        return string.format("%d:%02d:%02d", h, m, s)
    end
    return string.format("%02d:%02d", m, s)
end

local function getDateStr()
    local dt = getDateTime()
    if dt then
        return string.format("%04d-%02d-%02d_%02d%02d%02d",
            dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec)
    end
    return "unknown"
end

local function ensureLogDir()
    os.execute("mkdir -p " .. LOG_DIR)
end

local function openLogFile()
    ensureLogDir()
    logFileName = LOG_DIR .. "/batt_" .. getDateStr() .. ".csv"
    logFile = io.open(logFileName, "w")
    if logFile then
        logFile:write("elapsed_s,voltage,cell_avg,percent\n")
        logFile:flush()
    end
end

local function writeLogEntry(elapsed, voltage, cellAvg, pct)
    if logFile then
        logFile:write(string.format("%.0f,%.2f,%.2f,%d\n",
            elapsed, voltage, cellAvg, pct))
        logFile:flush()
    end
end

local function init()
    startTime = getTime() / 100
    lastSampleTime = 0
    lastLogTime = 0
    samples = {}
    prevVoltage = nil
    rateSmoothed = 0
    openLogFile()
end

local function drawHeader(w)
    lcd.drawFilledRectangle(0, 0, w, 28, C_HEADER)
    lcd.setColor(CUSTOM_COLOR, C_WHITE)
    lcd.drawText(8, 5, "BATTERY LOG", MIDSIZE + CUSTOM_COLOR)
    lcd.setColor(CUSTOM_COLOR, C_DIM)
    local dt = getDateTime()
    if dt then
        local ts = string.format("%02d:%02d:%02d", dt.hour, dt.min, dt.sec)
        lcd.drawText(w - 8, 8, ts, RIGHT + SMLSIZE + CUSTOM_COLOR)
    end
end

local function drawVoltage(x, y, voltage, pct)
    local col = percentColor(pct)
    lcd.setColor(CUSTOM_COLOR, col)
    lcd.drawText(x, y, string.format("%.2fV", voltage), DBLSIZE + CUSTOM_COLOR)

    lcd.setColor(CUSTOM_COLOR, col)
    lcd.drawText(x, y + 38, string.format("%d%%", pct), MIDSIZE + CUSTOM_COLOR)

    -- Per-cell voltage
    local cellV = voltage / CELLS
    lcd.setColor(CUSTOM_COLOR, C_DIM)
    lcd.drawText(x, y + 62, string.format("Cell avg: %.2fV", cellV), SMLSIZE + CUSTOM_COLOR)
end

local function drawRuntimeInfo(x, y, elapsed, voltage, pct)
    lcd.setColor(CUSTOM_COLOR, C_TEXT)
    lcd.drawText(x, y, "Session:", SMLSIZE + CUSTOM_COLOR)
    lcd.setColor(CUSTOM_COLOR, C_WHITE)
    lcd.drawText(x + 58, y, formatTime(elapsed), SMLSIZE + CUSTOM_COLOR)

    -- Estimated remaining
    lcd.setColor(CUSTOM_COLOR, C_TEXT)
    lcd.drawText(x, y + 18, "Remain:", SMLSIZE + CUSTOM_COLOR)
    if rateSmoothed > 0.00001 then
        local vRemaining = voltage - V_EMPTY
        local secsLeft = vRemaining / rateSmoothed
        if secsLeft > 36000 then secsLeft = 36000 end
        local col = percentColor(pct)
        lcd.setColor(CUSTOM_COLOR, col)
        lcd.drawText(x + 58, y + 18, "~" .. formatTime(secsLeft), SMLSIZE + CUSTOM_COLOR)
    else
        lcd.setColor(CUSTOM_COLOR, C_DIM)
        lcd.drawText(x + 58, y + 18, "calc...", SMLSIZE + CUSTOM_COLOR)
    end

    -- Discharge rate
    lcd.setColor(CUSTOM_COLOR, C_TEXT)
    lcd.drawText(x, y + 36, "Rate:", SMLSIZE + CUSTOM_COLOR)
    if rateSmoothed > 0.00001 then
        local ratePerMin = rateSmoothed * 60
        lcd.setColor(CUSTOM_COLOR, C_DIM)
        lcd.drawText(x + 58, y + 36, string.format("-%.3fV/m", ratePerMin), SMLSIZE + CUSTOM_COLOR)
    else
        lcd.setColor(CUSTOM_COLOR, C_DIM)
        lcd.drawText(x + 58, y + 36, "---", SMLSIZE + CUSTOM_COLOR)
    end
end

local function drawGraph(gx, gy, gw, gh)
    -- Graph background
    lcd.drawFilledRectangle(gx, gy, gw, gh, C_GRAPH_BG)

    -- Horizontal grid lines (voltage levels)
    local gridSteps = 4
    lcd.setColor(CUSTOM_COLOR, C_GRAPH_GRID)
    for i = 1, gridSteps - 1 do
        local ly = gy + math.floor(i * gh / gridSteps)
        lcd.drawLine(gx, ly, gx + gw - 1, ly, DOTTED, CUSTOM_COLOR)
    end

    -- Y-axis labels
    lcd.setColor(CUSTOM_COLOR, C_DIM)
    lcd.drawText(gx + 2, gy + 1, string.format("%.1f", V_FULL), SMLSIZE + CUSTOM_COLOR)
    lcd.drawText(gx + 2, gy + gh - 14, string.format("%.1f", V_EMPTY), SMLSIZE + CUSTOM_COLOR)

    -- X-axis label
    lcd.drawText(gx + gw - 28, gy + gh - 14, "30m", SMLSIZE + CUSTOM_COLOR)

    -- Plot data
    local n = #samples
    if n < 2 then
        lcd.setColor(CUSTOM_COLOR, C_DIM)
        lcd.drawText(gx + gw / 2 - 30, gy + gh / 2 - 6, "Collecting...", SMLSIZE + CUSTOM_COLOR)
        return
    end

    lcd.setColor(CUSTOM_COLOR, C_GRAPH_LINE)
    local timeSpan = GRAPH_DURATION
    local firstTime = samples[1].t

    for i = 2, n do
        local s1 = samples[i - 1]
        local s2 = samples[i]
        local x1 = gx + math.floor(((s1.t - firstTime) / timeSpan) * gw)
        local x2 = gx + math.floor(((s2.t - firstTime) / timeSpan) * gw)
        local y1 = gy + gh - math.floor(((s1.v - V_EMPTY) / V_RANGE) * gh)
        local y2 = gy + gh - math.floor(((s2.v - V_EMPTY) / V_RANGE) * gh)
        x1 = clamp(x1, gx, gx + gw - 1)
        x2 = clamp(x2, gx, gx + gw - 1)
        y1 = clamp(y1, gy, gy + gh - 1)
        y2 = clamp(y2, gy, gy + gh - 1)
        lcd.drawLine(x1, y1, x2, y2, SOLID, CUSTOM_COLOR)
    end

    -- Border
    lcd.setColor(CUSTOM_COLOR, C_GRAPH_GRID)
    lcd.drawRectangle(gx, gy, gw, gh, CUSTOM_COLOR)
end

local function drawWarning(w, h, pct)
    if pct <= WARN_CRIT then
        lcd.drawFilledRectangle(0, h - 28, w, 28, C_RED)
        lcd.setColor(CUSTOM_COLOR, C_WHITE)
        lcd.drawText(w / 2, h - 24, "!! CRITICAL BATTERY !!", MIDSIZE + CENTER + CUSTOM_COLOR)
    elseif pct <= WARN_LOW then
        lcd.drawFilledRectangle(0, h - 24, w, 24, lcd.RGB(60, 50, 0))
        lcd.setColor(CUSTOM_COLOR, C_YELLOW)
        lcd.drawText(w / 2, h - 21, "LOW BATTERY WARNING", SMLSIZE + CENTER + CUSTOM_COLOR)
    end
end

local function run(event, touchState)
    local w, h = lcd.getWindowSize()
    local now = getTime() / 100
    local elapsed = now - startTime

    -- Read voltage
    local voltage = getValue("tx-voltage")
    if type(voltage) ~= "number" or voltage < 1 then
        voltage = 0
    end
    -- Some radios return millivolts
    if voltage > 100 then voltage = voltage / 100 end

    local pct = voltToPercent(voltage)
    local cellAvg = voltage / CELLS

    -- Sample for graph
    if now - lastSampleTime >= SAMPLE_INTERVAL then
        lastSampleTime = now
        table.insert(samples, { t = elapsed, v = voltage })
        -- Trim old samples beyond 30 min window
        while #samples > MAX_SAMPLES do
            table.remove(samples, 1)
        end
        -- Update discharge rate (exponential smoothing)
        if prevVoltage and prevVoltage > voltage and (now - prevVoltageTime) > 0 then
            local instantRate = (prevVoltage - voltage) / (now - prevVoltageTime)
            if rateSmoothed < 0.000001 then
                rateSmoothed = instantRate
            else
                rateSmoothed = rateSmoothed * 0.9 + instantRate * 0.1
            end
        end
        prevVoltage = voltage
        prevVoltageTime = now
    end

    -- Log to file every 60 seconds
    if now - lastLogTime >= LOG_INTERVAL then
        lastLogTime = now
        writeLogEntry(elapsed, voltage, cellAvg, pct)
    end

    -- Draw UI
    lcd.clear(C_BG)
    lcd.setColor(CUSTOM_COLOR, C_WHITE)

    drawHeader(w)

    -- Left panel: voltage display
    drawVoltage(12, 34, voltage, pct)

    -- Right panel: runtime info
    drawRuntimeInfo(w / 2 + 10, 34, elapsed, voltage, pct)

    -- Percentage bar
    local barX = 12
    local barY = 100
    local barW = w - 24
    local barH = 10
    lcd.drawRectangle(barX, barY, barW, barH, C_DIM)
    local fillW = math.floor(barW * pct / 100)
    if fillW > 0 then
        lcd.drawFilledRectangle(barX + 1, barY + 1, fillW - 2, barH - 2, percentColor(pct))
    end

    -- Graph area
    local graphY = barY + barH + 10
    local graphH = h - graphY - 6
    if pct <= WARN_LOW then graphH = graphH - 28 end
    if graphH < 40 then graphH = 40 end
    drawGraph(12, graphY, w - 24, graphH)

    -- Warning overlay
    drawWarning(w, h, pct)

    return 0
end

return { init = init, run = run }
