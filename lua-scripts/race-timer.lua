-- TNS|Race Timer|TNE
-- FPV Race Timing & Lap Tracker
-- Practice mode, Race mode, Results display

local MODE_MENU = 0
local MODE_PRACTICE = 1
local MODE_RACE = 2
local MODE_RESULTS = 3
local MODE_RACE_SETUP = 4

-- Colors (FPV racing aesthetic)
local BLACK = lcd.RGB(0, 0, 0)
local WHITE = lcd.RGB(255, 255, 255)
local GREEN = lcd.RGB(0, 255, 80)
local RED = lcd.RGB(255, 40, 40)
local YELLOW = lcd.RGB(255, 220, 0)
local CYAN = lcd.RGB(0, 220, 255)
local ORANGE = lcd.RGB(255, 140, 0)
local GRAY = lcd.RGB(100, 100, 100)
local DARKGRAY = lcd.RGB(40, 40, 40)
local PURPLE = lcd.RGB(180, 60, 255)

-- State
local mode = MODE_MENU
local running = false
local startTime = 0
local elapsed = 0
local laps = {}
local bestLap = nil
local lastLapTime = 0
local raceTime = 120  -- default 2 min in seconds
local raceDurations = {60, 120, 180, 300}
local raceDurIdx = 2
local countdown = 0
local countdownStart = 0
local raceFinished = false
local savedFile = nil

-- Screen dimensions (AX12)
local W = 480
local H = 272

local function getElapsed()
    if running then
        return getTime() - startTime
    end
    return elapsed
end

local function formatTime(ticks)
    -- ticks are in 10ms units from getTime()
    local totalMs = ticks * 10
    local mins = math.floor(totalMs / 60000)
    local secs = math.floor((totalMs % 60000) / 1000)
    local ms = totalMs % 1000
    if mins > 0 then
        return string.format("%d:%02d.%03d", mins, secs, ms)
    else
        return string.format("%d.%03d", secs, ms)
    end
end

local function formatTimeSec(seconds)
    local mins = math.floor(seconds / 60)
    local secs = seconds % 60
    return string.format("%d:%02d", mins, secs)
end

local function getBestLap()
    if #laps == 0 then return nil end
    local best = laps[1]
    for i = 2, #laps do
        if laps[i] < best then best = laps[i] end
    end
    return best
end

local function getAvgLap()
    if #laps == 0 then return 0 end
    local sum = 0
    for _, v in ipairs(laps) do sum = sum + v end
    return sum / #laps
end

local function getWorstLap()
    if #laps == 0 then return nil end
    local worst = laps[1]
    for i = 2, #laps do
        if laps[i] > worst then worst = laps[i] end
    end
    return worst
end

local function recordLap()
    local now = getElapsed()
    local lapTime = now - lastLapTime
    if lapTime > 10 then  -- minimum 100ms lap
        laps[#laps + 1] = lapTime
        lastLapTime = now
        bestLap = getBestLap()
    end
end

local function saveResults()
    local filename = "/storage/emulated/0/AX12LUA/SCRIPTS/TOOLS/race-results.jsonl"
    local f = io.open(filename, "a")
    if f then
        local totalMs = getElapsed() * 10
        local lapStr = "["
        for i, v in ipairs(laps) do
            if i > 1 then lapStr = lapStr .. "," end
            lapStr = lapStr .. tostring(v * 10)
        end
        lapStr = lapStr .. "]"
        local modeStr = (mode == MODE_PRACTICE) and "practice" or "race"
        local best = getBestLap()
        local avg = getAvgLap()
        local line = string.format(
            '{"mode":"%s","date":"%s","total_ms":%d,"laps_ms":%s,"lap_count":%d,"best_ms":%s,"avg_ms":%d,"race_time_s":%d}',
            modeStr,
            os.date("%Y-%m-%dT%H:%M:%S"),
            totalMs,
            lapStr,
            #laps,
            best and tostring(best * 10) or "null",
            math.floor(avg * 10),
            raceTime
        )
        f:write(line .. "\n")
        f:close()
        savedFile = filename
        return true
    end
    return false
end

local function resetState()
    running = false
    startTime = 0
    elapsed = 0
    laps = {}
    bestLap = nil
    lastLapTime = 0
    countdown = 0
    raceFinished = false
    savedFile = nil
end

local function drawButton(x, y, w, h, text, bgColor, textColor)
    lcd.drawFilledRectangle(x, y, w, h, bgColor)
    lcd.drawRectangle(x, y, w, h, textColor)
    local tw = #text * 7
    lcd.drawText(x + (w - tw) / 2, y + (h - 16) / 2, text, textColor)
end

local function inBox(tx, ty, x, y, w, h)
    return tx >= x and tx <= x + w and ty >= y and ty <= y + h
end

-- MENU SCREEN
local function drawMenu()
    lcd.clear(BLACK)
    lcd.drawText(W/2 - 70, 20, "FPV RACE TIMER", CYAN + BOLD)
    lcd.drawText(W/2 - 50, 50, "Lap Tracker", GRAY)

    drawButton(W/2 - 100, 90, 200, 50, "PRACTICE", GREEN, BLACK)
    drawButton(W/2 - 100, 155, 200, 50, "RACE MODE", ORANGE, BLACK)

    if savedFile then
        lcd.drawText(10, H - 20, "Results saved!", GREEN)
    end
end

local function handleMenuTouch(tx, ty)
    if inBox(tx, ty, W/2 - 100, 90, 200, 50) then
        resetState()
        mode = MODE_PRACTICE
    elseif inBox(tx, ty, W/2 - 100, 155, 200, 50) then
        resetState()
        mode = MODE_RACE_SETUP
    end
end

-- RACE SETUP SCREEN
local function drawRaceSetup()
    lcd.clear(BLACK)
    lcd.drawText(W/2 - 60, 15, "RACE SETUP", ORANGE + BOLD)

    lcd.drawText(W/2 - 40, 55, "Duration:", WHITE)
    lcd.drawText(W/2 - 30, 80, formatTimeSec(raceDurations[raceDurIdx]), YELLOW + BOLD + DBLSIZE)

    drawButton(W/2 - 120, 75, 40, 35, "<", GRAY, WHITE)
    drawButton(W/2 + 80, 75, 40, 35, ">", GRAY, WHITE)

    drawButton(W/2 - 80, 140, 160, 50, "START RACE", GREEN, BLACK)
    drawButton(W/2 - 80, 210, 160, 40, "BACK", DARKGRAY, WHITE)
end

local function handleRaceSetupTouch(tx, ty)
    if inBox(tx, ty, W/2 - 120, 75, 40, 35) then
        raceDurIdx = raceDurIdx - 1
        if raceDurIdx < 1 then raceDurIdx = #raceDurations end
    elseif inBox(tx, ty, W/2 + 80, 75, 40, 35) then
        raceDurIdx = raceDurIdx + 1
        if raceDurIdx > #raceDurations then raceDurIdx = 1 end
    elseif inBox(tx, ty, W/2 - 80, 140, 160, 50) then
        raceTime = raceDurations[raceDurIdx]
        countdown = 4  -- 3, 2, 1, GO
        countdownStart = getTime()
        mode = MODE_RACE
    elseif inBox(tx, ty, W/2 - 80, 210, 160, 40) then
        mode = MODE_MENU
    end
end

-- PRACTICE MODE
local function drawPractice()
    lcd.clear(BLACK)

    -- Header
    lcd.drawText(10, 5, "PRACTICE", CYAN)
    drawButton(W - 70, 2, 65, 25, "MENU", DARKGRAY, WHITE)

    -- Main timer (large)
    local timeStr = formatTime(getElapsed())
    lcd.drawText(W/2 - 80, 30, timeStr, WHITE + BOLD + DBLSIZE)

    -- Status
    if not running and #laps == 0 then
        lcd.drawText(W/2 - 50, 65, "TAP TO START", YELLOW)
    elseif running then
        lcd.drawText(W/2 - 30, 65, "RUNNING", GREEN)
    else
        lcd.drawText(W/2 - 30, 65, "STOPPED", RED)
    end

    -- Lap info
    local infoY = 85
    lcd.drawText(10, infoY, "Laps: " .. #laps, WHITE)
    if bestLap then
        lcd.drawText(10, infoY + 18, "Best: " .. formatTime(bestLap), GREEN)
    end
    if #laps > 0 then
        lcd.drawText(10, infoY + 36, "Avg:  " .. formatTime(math.floor(getAvgLap())), CYAN)
    end

    -- Last 4 laps with delta
    local lapY = infoY
    local startIdx = math.max(1, #laps - 3)
    lcd.drawText(200, lapY, "Recent Laps:", GRAY)
    for i = startIdx, #laps do
        lapY = lapY + 18
        local delta = ""
        local deltaColor = WHITE
        if bestLap and laps[i] ~= bestLap then
            local diff = laps[i] - bestLap
            delta = " +" .. formatTime(diff)
            deltaColor = RED
        elseif laps[i] == bestLap then
            delta = " BEST"
            deltaColor = GREEN
        end
        lcd.drawText(200, lapY, string.format("L%d %s", i, formatTime(laps[i])), WHITE)
        lcd.drawText(350, lapY, delta, deltaColor)
    end

    -- Bottom zone indicator
    lcd.drawLine(0, H - 60, W, H - 60, GRAY)
    if running then
        drawButton(10, H - 55, W/2 - 20, 50, "LAP", PURPLE, WHITE)
        drawButton(W/2 + 10, H - 55, W/2 - 20, 50, "STOP", RED, WHITE)
    elseif #laps > 0 then
        drawButton(10, H - 55, W/2 - 20, 50, "RESULTS", CYAN, BLACK)
        drawButton(W/2 + 10, H - 55, W/2 - 20, 50, "RESET", ORANGE, BLACK)
    else
        drawButton(10, H - 55, W - 20, 50, "TAP TO START", GREEN, BLACK)
    end
end

local function handlePracticeTouch(tx, ty)
    -- Menu button
    if inBox(tx, ty, W - 70, 2, 65, 25) then
        mode = MODE_MENU
        return
    end

    -- Bottom zone
    if ty >= H - 60 then
        if running then
            if tx < W/2 then
                recordLap()
            else
                running = false
                elapsed = getTime() - startTime
            end
        elseif #laps > 0 then
            if tx < W/2 then
                mode = MODE_RESULTS
            else
                resetState()
            end
        else
            -- Start
            startTime = getTime()
            lastLapTime = 0
            running = true
        end
    elseif not running and #laps == 0 then
        -- Tap anywhere to start
        startTime = getTime()
        lastLapTime = 0
        running = true
    end
end

-- RACE MODE
local function drawRace()
    lcd.clear(BLACK)

    -- Countdown
    if countdown > 0 then
        local cdElapsed = getTime() - countdownStart
        local cdPhase = math.floor(cdElapsed / 100)  -- 1 second per phase
        local display = countdown - 1 - cdPhase

        if display > 0 then
            lcd.drawText(W/2 - 20, H/2 - 30, tostring(display), RED + BOLD + DBLSIZE)
        elseif display == 0 then
            lcd.drawText(W/2 - 30, H/2 - 30, "GO!", GREEN + BOLD + DBLSIZE)
        end

        if cdPhase >= countdown then
            countdown = 0
            startTime = getTime()
            lastLapTime = 0
            running = true
        end
        return
    end

    -- Header
    lcd.drawText(10, 5, "RACE", ORANGE)
    lcd.drawText(80, 5, formatTimeSec(raceTime), GRAY)
    drawButton(W - 70, 2, 65, 25, "STOP", RED, WHITE)

    -- Remaining time (large)
    local el = getElapsed()
    local remainTicks = (raceTime * 100) - el
    if remainTicks <= 0 and running then
        running = false
        elapsed = raceTime * 100
        raceFinished = true
    end

    if remainTicks < 0 then remainTicks = 0 end
    local timeColor = WHITE
    if remainTicks < 3000 then timeColor = YELLOW end  -- last 30 sec
    if remainTicks < 1000 then timeColor = RED end  -- last 10 sec

    lcd.drawText(W/2 - 80, 30, formatTime(math.max(0, remainTicks)), timeColor + BOLD + DBLSIZE)

    if raceFinished then
        lcd.drawText(W/2 - 50, 65, "RACE OVER!", RED + BOLD)
    elseif running then
        lcd.drawText(W/2 - 40, 65, "RACING!", GREEN)
    end

    -- Lap info
    local infoY = 85
    lcd.drawText(10, infoY, "Laps: " .. #laps, WHITE + BOLD)
    if bestLap then
        lcd.drawText(10, infoY + 18, "Best: " .. formatTime(bestLap), GREEN)
    end
    if #laps > 0 then
        lcd.drawText(10, infoY + 36, "Last: " .. formatTime(laps[#laps]), CYAN)
        if bestLap and laps[#laps] ~= bestLap then
            local diff = laps[#laps] - bestLap
            lcd.drawText(200, infoY + 36, "+" .. formatTime(diff), RED)
        end
    end

    -- Bottom zone
    lcd.drawLine(0, H - 60, W, H - 60, GRAY)
    if running then
        drawButton(10, H - 55, W - 20, 50, "LAP", PURPLE, WHITE)
    elseif raceFinished then
        drawButton(10, H - 55, W/2 - 20, 50, "RESULTS", CYAN, BLACK)
        drawButton(W/2 + 10, H - 55, W/2 - 20, 50, "MENU", DARKGRAY, WHITE)
    end
end

local function handleRaceTouch(tx, ty)
    if countdown > 0 then return end

    -- Stop button
    if inBox(tx, ty, W - 70, 2, 65, 25) then
        if running then
            running = false
            elapsed = getTime() - startTime
            raceFinished = true
        else
            mode = MODE_MENU
        end
        return
    end

    -- Bottom zone
    if ty >= H - 60 then
        if running then
            recordLap()
        elseif raceFinished then
            if tx < W/2 then
                mode = MODE_RESULTS
            else
                mode = MODE_MENU
            end
        end
    end
end

-- RESULTS SCREEN
local function drawResults()
    lcd.clear(BLACK)
    lcd.drawText(10, 5, "RESULTS", YELLOW + BOLD)
    drawButton(W - 70, 2, 65, 25, "MENU", DARKGRAY, WHITE)

    if #laps == 0 then
        lcd.drawText(W/2 - 40, H/2, "No laps!", WHITE)
        return
    end

    -- Summary
    lcd.drawText(10, 30, "Total Laps: " .. #laps, WHITE)
    lcd.drawText(10, 48, "Total Time: " .. formatTime(getElapsed()), WHITE)
    lcd.drawText(10, 66, "Best Lap:   " .. formatTime(getBestLap()), GREEN)
    lcd.drawText(10, 84, "Worst Lap:  " .. formatTime(getWorstLap()), RED)
    lcd.drawText(10, 102, "Average:    " .. formatTime(math.floor(getAvgLap())), CYAN)

    -- Lap list (show last 6)
    local listY = 125
    lcd.drawLine(0, listY - 3, W, listY - 3, GRAY)
    local startIdx = math.max(1, #laps - 5)
    for i = startIdx, #laps do
        local color = WHITE
        if laps[i] == getBestLap() then color = GREEN end
        if laps[i] == getWorstLap() then color = RED end
        lcd.drawText(10, listY, string.format("Lap %2d: %s", i, formatTime(laps[i])), color)

        if bestLap and laps[i] ~= bestLap then
            local diff = laps[i] - bestLap
            lcd.drawText(250, listY, "+" .. formatTime(diff), RED)
        end
        listY = listY + 18
    end

    -- Save button
    drawButton(10, H - 40, 120, 35, "SAVE", GREEN, BLACK)
    if savedFile then
        lcd.drawText(140, H - 35, "Saved!", GREEN)
    end
end

local function handleResultsTouch(tx, ty)
    if inBox(tx, ty, W - 70, 2, 65, 25) then
        mode = MODE_MENU
    elseif inBox(tx, ty, 10, H - 40, 120, 35) then
        saveResults()
    end
end

-- Main functions
local function init()
    mode = MODE_MENU
    resetState()
end

local function run(event, touchState)
    -- Handle touch
    if event == EVT_TOUCH_TAP and touchState then
        local tx = touchState.x or 0
        local ty = touchState.y or 0

        if mode == MODE_MENU then
            handleMenuTouch(tx, ty)
        elseif mode == MODE_PRACTICE then
            handlePracticeTouch(tx, ty)
        elseif mode == MODE_RACE then
            handleRaceTouch(tx, ty)
        elseif mode == MODE_RESULTS then
            handleResultsTouch(tx, ty)
        elseif mode == MODE_RACE_SETUP then
            handleRaceSetupTouch(tx, ty)
        end
    end

    -- Draw
    if mode == MODE_MENU then
        drawMenu()
    elseif mode == MODE_PRACTICE then
        drawPractice()
    elseif mode == MODE_RACE then
        drawRace()
    elseif mode == MODE_RESULTS then
        drawResults()
    elseif mode == MODE_RACE_SETUP then
        drawRaceSetup()
    end

    return 0
end

return { init=init, run=run }
