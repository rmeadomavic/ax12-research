-- TNS|ELRS Info|TNE
-- ELRS link monitoring display with connection history and sparkline graphs
-- Color LCD (720x1280), touch enabled, military green styling

local W, H = 720, 1280

-- Military green palette
local C_BG       = nil
local C_GREEN    = nil
local C_DKGREEN  = nil
local C_AMBER    = nil
local C_RED      = nil
local C_GRAY     = nil
local C_DKGRAY   = nil
local C_WHITE    = nil
local C_LABEL    = nil
local C_BAR_BG   = nil

-- Telemetry state
local rssi1, rssi2, rqly, rsnr, tpwr, rfmd, ant = 0, 0, 0, 0, 0, 0, 0
local hasLink = false
local hasDiversity = false

-- Connection history
local lastPktTime = 0
local longestGap = 0
local gapStart = 0
local connectTime = 0
local connectStart = 0
local disconnectCount = 0
local wasConnected = false

-- Sparkline buffers (60 samples, 1/sec)
local rssiHist = {}
local lqHist = {}
local HIST_LEN = 60
local lastSampleT = 0

-- Last known values for NO LINK display
local lastRssi1, lastRssi2, lastRqly, lastRsnr, lastTpwr = -999, -999, 0, 0, 0

---------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------

local function clamp(v, lo, hi) return math.max(lo, math.min(hi, v)) end

local function colorForRSSI(v)
  if v > -80 then return C_GREEN end
  if v > -100 then return C_AMBER end
  return C_RED
end

local function colorForLQ(v)
  if v > 90 then return C_GREEN end
  if v > 70 then return C_AMBER end
  return C_RED
end

local function colorForSNR(v)
  if v > 5 then return C_GREEN end
  if v > 0 then return C_AMBER end
  return C_RED
end

local function fmtTime(sec)
  sec = math.floor(sec)
  if sec < 60 then return string.format("%ds", sec) end
  if sec < 3600 then return string.format("%dm%02ds", sec/60, sec%60) end
  return string.format("%dh%02dm", sec/3600, (sec%3600)/60)
end

local function drawBar(x, y, w, h, pct, col)
  lcd.drawFilledRectangle(x, y, w, h, C_BAR_BG)
  local fill = math.floor(w * clamp(pct, 0, 100) / 100)
  if fill > 0 then lcd.drawFilledRectangle(x, y, fill, h, col) end
  lcd.drawRectangle(x, y, w, h, C_DKGREEN)
end

local function drawSparkline(x, y, w, h, data, minV, maxV, colFn)
  lcd.drawFilledRectangle(x, y, w, h, C_BAR_BG)
  lcd.drawRectangle(x, y, w, h, C_DKGREEN)
  local n = #data
  if n < 2 then return end
  local range = maxV - minV
  if range == 0 then range = 1 end
  local step = w / HIST_LEN
  for i = 2, n do
    local x1 = x + math.floor((i - 2) * step)
    local x2 = x + math.floor((i - 1) * step)
    local y1 = y + h - math.floor(clamp((data[i-1] - minV) / range, 0, 1) * (h - 2)) - 1
    local y2 = y + h - math.floor(clamp((data[i] - minV) / range, 0, 1) * (h - 2)) - 1
    local col = colFn and colFn(data[i]) or C_GREEN
    lcd.drawLine(x1, y1, x2, y2, SOLID, col)
  end
end

---------------------------------------------------------------------------
-- Section renderers
---------------------------------------------------------------------------

local function drawHeader()
  lcd.drawFilledRectangle(0, 0, W, 56, C_DKGREEN)
  lcd.drawText(W/2, 8, "ELRS LINK MONITOR", MIDSIZE + CENTER + COLOR_THEME_SECONDARY1)
  if not hasLink then
    lcd.drawFilledRectangle(W/2 - 80, 60, 160, 36, C_RED)
    lcd.drawText(W/2, 64, "NO LINK", MIDSIZE + CENTER + INVERS)
  else
    lcd.drawFilledRectangle(W/2 - 80, 60, 160, 36, C_GREEN)
    lcd.drawText(W/2, 64, "CONNECTED", MIDSIZE + CENTER + INVERS)
  end
end

local function drawLinkPanel(yOff)
  local LX = 30
  local LW = W - 60
  local LH = 44
  local BAR_W = 260
  local BAR_H = 20
  local BAR_X = W - 40 - BAR_W

  lcd.drawText(LX, yOff, "LINK STATUS", BOLD + COLOR_THEME_SECONDARY1)
  lcd.drawLine(LX, yOff + 26, LX + LW, yOff + 26, SOLID, C_DKGREEN)
  yOff = yOff + 34

  local valCol = hasLink and C_WHITE or C_GRAY
  local r1 = hasLink and rssi1 or lastRssi1
  local r2 = hasLink and rssi2 or lastRssi2
  local lq = hasLink and rqly or lastRqly
  local sn = hasLink and rsnr or lastRsnr
  local pw = hasLink and tpwr or lastTpwr

  -- 1RSS
  lcd.drawText(LX, yOff + 4, "1RSS", SMLSIZE + COLOR_THEME_SECONDARY1)
  lcd.drawText(LX + 100, yOff, string.format("%d dBm", r1), valCol)
  local rssiPct = clamp((r1 + 130) * 100 / 80, 0, 100)
  drawBar(BAR_X, yOff + 2, BAR_W, BAR_H, rssiPct, colorForRSSI(r1))
  yOff = yOff + LH

  -- 2RSS (diversity)
  if hasDiversity then
    lcd.drawText(LX, yOff + 4, "2RSS", SMLSIZE + COLOR_THEME_SECONDARY1)
    lcd.drawText(LX + 100, yOff, string.format("%d dBm", r2), valCol)
    local rssi2Pct = clamp((r2 + 130) * 100 / 80, 0, 100)
    drawBar(BAR_X, yOff + 2, BAR_W, BAR_H, rssi2Pct, colorForRSSI(r2))
    yOff = yOff + LH
  end

  -- LQ
  lcd.drawText(LX, yOff + 4, "RQly", SMLSIZE + COLOR_THEME_SECONDARY1)
  lcd.drawText(LX + 100, yOff, string.format("%d%%", lq), valCol)
  drawBar(BAR_X, yOff + 2, BAR_W, BAR_H, lq, colorForLQ(lq))
  yOff = yOff + LH

  -- SNR
  lcd.drawText(LX, yOff + 4, "RSNR", SMLSIZE + COLOR_THEME_SECONDARY1)
  lcd.drawText(LX + 100, yOff, string.format("%.1f dB", sn), valCol)
  local snrPct = clamp((sn + 10) * 100 / 20, 0, 100)
  drawBar(BAR_X, yOff + 2, BAR_W, BAR_H, snrPct, colorForSNR(sn))
  yOff = yOff + LH

  -- TX Power
  lcd.drawText(LX, yOff + 4, "TPWR", SMLSIZE + COLOR_THEME_SECONDARY1)
  lcd.drawText(LX + 100, yOff, string.format("%d mW", pw), valCol)
  yOff = yOff + LH

  -- RF Mode
  lcd.drawText(LX, yOff + 4, "RF Mode", SMLSIZE + COLOR_THEME_SECONDARY1)
  lcd.drawText(LX + 140, yOff, tostring(rfmd), valCol)
  yOff = yOff + LH

  -- Antenna
  if hasDiversity then
    lcd.drawText(LX, yOff + 4, "Antenna", SMLSIZE + COLOR_THEME_SECONDARY1)
    lcd.drawText(LX + 140, yOff, tostring(ant), valCol)
    yOff = yOff + LH
  end

  return yOff + 10
end

local function drawHistoryPanel(yOff)
  local LX = 30
  local LW = W - 60
  local now = getTime() / 100

  lcd.drawText(LX, yOff, "CONNECTION HISTORY", BOLD + COLOR_THEME_SECONDARY1)
  lcd.drawLine(LX, yOff + 26, LX + LW, yOff + 26, SOLID, C_DKGREEN)
  yOff = yOff + 36

  local sinceLastPkt = hasLink and 0 or (lastPktTime > 0 and (now - lastPktTime) or 0)

  local labels = {"Last Pkt", "Max Gap", "Uptime", "Disconnects"}
  local values = {
    sinceLastPkt > 0 and fmtTime(sinceLastPkt) or (hasLink and "NOW" or "--"),
    longestGap > 0 and fmtTime(longestGap) or "--",
    connectTime > 0 and fmtTime(connectTime) or "--",
    tostring(disconnectCount)
  }

  for i = 1, 4 do
    lcd.drawText(LX, yOff, labels[i], SMLSIZE + COLOR_THEME_SECONDARY1)
    lcd.drawText(LX + 240, yOff, values[i], C_WHITE)
    yOff = yOff + 38
  end

  return yOff + 10
end

local function drawGraphs(yOff)
  local LX = 30
  local GW = W - 60
  local GH = 80

  lcd.drawText(LX, yOff, "RSSI (60s)", SMLSIZE + COLOR_THEME_SECONDARY1)
  drawSparkline(LX, yOff + 20, GW, GH, rssiHist, -130, -20, colorForRSSI)
  yOff = yOff + GH + 30

  lcd.drawText(LX, yOff, "LINK QUALITY (60s)", SMLSIZE + COLOR_THEME_SECONDARY1)
  drawSparkline(LX, yOff + 20, GW, GH, lqHist, 0, 100, colorForLQ)
  yOff = yOff + GH + 20

  return yOff
end

---------------------------------------------------------------------------
-- Main
---------------------------------------------------------------------------

local function init()
  C_BG      = lcd.RGB(10, 20, 10)
  C_GREEN   = lcd.RGB(0, 220, 0)
  C_DKGREEN = lcd.RGB(0, 80, 0)
  C_AMBER   = lcd.RGB(255, 180, 0)
  C_RED     = lcd.RGB(220, 30, 30)
  C_GRAY    = lcd.RGB(80, 80, 80)
  C_DKGRAY  = lcd.RGB(40, 40, 40)
  C_WHITE   = lcd.RGB(220, 220, 220)
  C_LABEL   = lcd.RGB(0, 160, 0)
  C_BAR_BG  = lcd.RGB(20, 30, 20)

  for i = 1, HIST_LEN do
    rssiHist[i] = -130
    lqHist[i] = 0
  end
end

local function run(event, touchState)
  lcd.clear(C_BG)

  -- Read telemetry
  local r1 = getValue("1RSS")
  local r2 = getValue("2RSS")
  local lq = getValue("RQly")
  local sn = getValue("RSNR")
  local pw = getValue("TPWR")
  local rm = getValue("RFMD")
  local an = getValue("ANT")
  local now = getTime() / 100

  -- Determine link state
  rssi1 = r1 or 0
  rssi2 = r2 or 0
  rqly = lq or 0
  rsnr = sn or 0
  tpwr = pw or 0
  rfmd = rm or 0
  ant = an or 0

  hasDiversity = (rssi2 ~= 0 and rssi2 ~= nil)
  hasLink = (rssi1 ~= 0 and rqly > 0)

  -- Track connection state
  if hasLink then
    lastPktTime = now
    lastRssi1 = rssi1
    lastRssi2 = rssi2
    lastRqly = rqly
    lastRsnr = rsnr
    lastTpwr = tpwr

    if not wasConnected then
      connectStart = now
      wasConnected = true
    end
    connectTime = now - connectStart
  else
    if wasConnected then
      disconnectCount = disconnectCount + 1
      wasConnected = false
    end
    if lastPktTime > 0 then
      local gap = now - lastPktTime
      if gap > longestGap then longestGap = gap end
    end
  end

  -- Sample sparklines at 1Hz
  if now - lastSampleT >= 1 then
    lastSampleT = now
    table.insert(rssiHist, hasLink and rssi1 or -130)
    table.insert(lqHist, hasLink and rqly or 0)
    if #rssiHist > HIST_LEN then table.remove(rssiHist, 1) end
    if #lqHist > HIST_LEN then table.remove(lqHist, 1) end
  end

  -- Render
  drawHeader()
  local y = drawLinkPanel(110)
  y = drawHistoryPanel(y)
  drawGraphs(y)

  -- Border
  lcd.drawRectangle(0, 0, W, H, C_DKGREEN)

  return 0
end

return { init=init, run=run }
