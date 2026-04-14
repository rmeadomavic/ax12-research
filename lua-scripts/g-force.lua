-- TNS|G-Force|TNE
-- G-Force & Attitude Display | RadioMaster AX12

local C = {}
local curG, maxG, roll, pitch = 1.0, 0, 0, 0
local hasSensor, lastUpdate = false, 0
local sin, cos, rad, deg = math.sin, math.cos, math.rad, math.deg
local floor, abs, sqrt, min = math.floor, math.abs, math.sqrt, math.min
local dialCx, dialCy, dialR, horizCx, horizCy, horizR, margin, titleH

local function clamp(v, lo, hi)
  return (v < lo) and lo or (v > hi) and hi or v
end

local function readSensors()
  local accX, accY, accZ
  if getShmVar then
    local okx, vx = pcall(getShmVar, "accel_x")
    local oky, vy = pcall(getShmVar, "accel_y")
    local okz, vz = pcall(getShmVar, "accel_z")
    if okx and vx and type(vx) == "number" then accX = vx end
    if oky and vy and type(vy) == "number" then accY = vy end
    if okz and vz and type(vz) == "number" then accZ = vz end
  end
  if not accX then
    local vx, vy, vz = getValue("AccX"), getValue("AccY"), getValue("AccZ")
    if vx and vx ~= 0 then accX, accY, accZ = vx, vy, vz end
  end
  if accX and accY and accZ then
    curG = sqrt(accX*accX + accY*accY + accZ*accZ)
    if curG > 20 then curG = curG / 9.81 end
    hasSensor = true
    if accZ ~= 0 then
      roll = clamp(deg(math.atan2(accY, accZ)), -90, 90)
      pitch = clamp(deg(math.atan2(-accX, sqrt(accY*accY + accZ*accZ))), -90, 90)
    end
  else
    hasSensor = false
    local thr = getValue("thr")
    curG = thr and (1.0 + (thr + 1024) / 2048 * 3.0) or 1.0
    local ail, ele = getValue("ail"), getValue("ele")
    if ail then roll = clamp(ail / 1024 * 45, -45, 45) end
    if ele then pitch = clamp(ele / 1024 * 45, -45, 45) end
  end
  if curG > maxG then maxG = curG end
end

local function drawHorizon()
  local cx, cy, r = horizCx, horizCy, horizR
  local pitchPx = clamp(pitch * r / 60, -r, r)
  for dy = -r, r do
    local dx2 = r*r - dy*dy
    if dx2 > 0 then
      local dx = floor(sqrt(dx2))
      lcd.setColor(CUSTOM_COLOR, (cy + dy < cy - pitchPx) and C.sky or C.ground)
      lcd.drawLine(cx - dx, cy + dy, cx + dx, cy + dy, SOLID, CUSTOM_COLOR)
    end
  end
  local rollRad, hLen = rad(-roll), r - 2
  local cosR, sinR = cos(rollRad), sin(rollRad)
  lcd.setColor(CUSTOM_COLOR, C.horizLine)
  lcd.drawLine(floor(cx - hLen*cosR), floor(cy - pitchPx - hLen*sinR),
               floor(cx + hLen*cosR), floor(cy - pitchPx + hLen*sinR), SOLID, FORCE)
  lcd.setColor(CUSTOM_COLOR, C.aircraft)
  lcd.drawLine(cx-15, cy, cx-5, cy, SOLID, FORCE)
  lcd.drawLine(cx+5, cy, cx+15, cy, SOLID, FORCE)
  lcd.drawLine(cx, cy-2, cx, cy+2, SOLID, FORCE)
  for p = -20, 20, 10 do
    if p ~= 0 then
      local py = cy - pitchPx - p * r / 60
      if abs(py - cy) < r - 5 then
        lcd.setColor(CUSTOM_COLOR, C.dim)
        lcd.drawLine(cx - 8, floor(py), cx + 8, floor(py), DOTTED, FORCE)
      end
    end
  end
  lcd.setColor(CUSTOM_COLOR, C.ring)
  lcd.drawCircle(cx, cy, r)
  lcd.drawCircle(cx, cy, r + 1)
end

local function drawDial()
  local cx, cy, r = dialCx, dialCy, dialR
  local maxDial = 6
  lcd.setColor(CUSTOM_COLOR, C.ring)
  lcd.drawCircle(cx, cy, r)
  lcd.drawCircle(cx, cy, r + 1)
  for d = 135, 405, 2 do
    local gVal = (d - 135) / 270 * maxDial
    local a = rad(d)
    lcd.setColor(CUSTOM_COLOR, gVal < 2 and C.zoneGreen or (gVal < 4 and C.zoneYellow or C.zoneRed))
    lcd.drawLine(floor(cx+cos(a)*(r-10)), floor(cy+sin(a)*(r-10)),
                 floor(cx+cos(a)*(r-3)),  floor(cy+sin(a)*(r-3)), SOLID, FORCE)
  end
  for i = 0, maxDial do
    local a = rad(135 + (i / maxDial) * 270)
    lcd.setColor(CUSTOM_COLOR, C.dim)
    lcd.drawText(floor(cx+cos(a)*(r+10)-4), floor(cy+sin(a)*(r+10)-6), tostring(i), SMLSIZE+CUSTOM_COLOR)
  end
  if maxG > 0.1 then
    local pa = rad(135 + (clamp(maxG, 0, maxDial) / maxDial) * 270)
    lcd.setColor(CUSTOM_COLOR, C.peak)
    lcd.drawFilledCircle(floor(cx+cos(pa)*(r-14)), floor(cy+sin(pa)*(r-14)), 3, CUSTOM_COLOR)
  end
  local na = rad(135 + (clamp(curG, 0, maxDial) / maxDial) * 270)
  local nx, ny = floor(cx+cos(na)*(r-16)), floor(cy+sin(na)*(r-16))
  lcd.setColor(CUSTOM_COLOR, C.needle)
  lcd.drawLine(cx, cy, nx, ny, SOLID, FORCE)
  lcd.drawLine(cx+1, cy, nx+1, ny, SOLID, FORCE)
  lcd.drawLine(cx, cy+1, nx, ny+1, SOLID, FORCE)
  lcd.setColor(CUSTOM_COLOR, C.center)
  lcd.drawFilledCircle(cx, cy, 4, CUSTOM_COLOR)
end

local function gColor(g)
  return g >= 4 and C.zoneRed or (g >= 2 and C.zoneYellow or C.zoneGreen)
end

local function drawHUD()
  local W, H = LCD_W, LCD_H
  lcd.setColor(CUSTOM_COLOR, gColor(curG))
  lcd.drawText(floor(W*0.38), titleH+4, string.format("%.1f", curG), XXLSIZE+CUSTOM_COLOR)
  lcd.drawText(floor(W*0.38)+68, titleH+14, "G", DBLSIZE+CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(margin, titleH+4, "PEAK", SMLSIZE+CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, gColor(maxG))
  lcd.drawText(margin, titleH+18, string.format("%.1f", maxG), MIDSIZE+CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(margin+44, titleH+22, "G", SMLSIZE+CUSTOM_COLOR)
  local botY = H - 32
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(margin, botY, "ROLL", SMLSIZE+CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.cyan)
  lcd.drawText(margin, botY+14, string.format("%+.0f", roll), MIDSIZE+CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(margin+70, botY, "PITCH", SMLSIZE+CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.cyan)
  lcd.drawText(margin+70, botY+14, string.format("%+.0f", pitch), MIDSIZE+CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, hasSensor and C.zoneGreen or C.warn)
  lcd.drawText(W-margin-36, titleH+4, hasSensor and "LIVE" or "SIM", BOLD+CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.dim)
  lcd.drawText(W-margin-115, H-16, "TAP TO RESET PEAK", SMLSIZE+CUSTOM_COLOR)
end

local function runColor(event, touchState)
  if touchState and touchState.tapCount and touchState.tapCount > 0 then maxG = 0 end
  if event == EVT_VIRTUAL_ENTER then maxG = 0 end
  local now = getTime()
  if now - lastUpdate >= 5 then readSensors(); lastUpdate = now end
  lcd.clear()
  lcd.setColor(CUSTOM_COLOR, C.bg)
  lcd.drawFilledRectangle(0, 0, LCD_W, LCD_H, CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.titleBg)
  lcd.drawFilledRectangle(0, 0, LCD_W, titleH, CUSTOM_COLOR)
  lcd.setColor(CUSTOM_COLOR, C.titleFg)
  lcd.drawText(margin, 2, "G-FORCE", BOLD+CUSTOM_COLOR)
  drawHorizon(); drawDial(); drawHUD()
  return 0
end

local function init()
  lastUpdate = getTime(); curG = 1.0; maxG = 0; roll = 0; pitch = 0
  C.bg        = lcd.RGB(0x0a, 0x0a, 0x12)
  C.titleBg   = lcd.RGB(0x18, 0x18, 0x28)
  C.titleFg   = lcd.RGB(0xff, 0x80, 0x00)
  C.ring      = lcd.RGB(0x50, 0x50, 0x60)
  C.dim       = lcd.RGB(0x55, 0x55, 0x55)
  C.center    = lcd.RGB(0xff, 0xff, 0xff)
  C.needle    = lcd.RGB(0xff, 0xff, 0xff)
  C.peak      = lcd.RGB(0xff, 0x40, 0xff)
  C.zoneGreen = lcd.RGB(0x00, 0xcc, 0x44)
  C.zoneYellow= lcd.RGB(0xff, 0xcc, 0x00)
  C.zoneRed   = lcd.RGB(0xff, 0x30, 0x30)
  C.sky       = lcd.RGB(0x14, 0x20, 0x40)
  C.ground    = lcd.RGB(0x3a, 0x28, 0x14)
  C.horizLine = lcd.RGB(0xff, 0xff, 0x00)
  C.aircraft  = lcd.RGB(0xff, 0xff, 0xff)
  C.cyan      = lcd.RGB(0x00, 0xbb, 0xdd)
  C.warn      = lcd.RGB(0xff, 0xb3, 0x00)
  margin = 6; titleH = 22
  local usableH = LCD_H - titleH - 10
  horizR = floor(min(LCD_W * 0.22, usableH * 0.38))
  if horizR < 35 then horizR = 35 end
  horizCx = floor(LCD_W * 0.22)
  horizCy = floor(titleH + 46 + horizR)
  dialR = floor(min(LCD_W * 0.22, usableH * 0.38))
  if dialR < 35 then dialR = 35 end
  dialCx = floor(LCD_W * 0.75)
  dialCy = floor(titleH + 46 + dialR)
end

local function run(event, touchState)
  if event == nil then return 0 end
  if event == EVT_VIRTUAL_EXIT then return 1 end
  return runColor(event, touchState)
end

return { init=init, run=run }
