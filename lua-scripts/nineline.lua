-- TNS|9-Line Brief|TNE
-- 9-Line CAS brief template -- standard JTAC format
-- Auto-fills TGT ELEV (line 4) and TGT LOC (line 6) from GPS
local M = {}
local W, H = 720, 1280
local BG, HUD, DIM, DARK, AMB, RED, GRY, WHT, CYN
local scrollY, selField, showReadback = 0, 0, false
local statusMsg, statusTimer = "", 0
local HDR_H, FIELD_H, FIELD_X, FIELD_W, BTN_H = 55, 90, 20, 680, 50
-- WGS84
local a_w = 6378137.0
local f_w = 1/298.257223563
local e2 = 2*f_w - f_w*f_w
local k0, ep2 = 0.9996, e2/(1-e2)
local BL = "CDEFGHJKLMNPQRSTUVWX"

local function latLonToUTM(lat, lon)
  local zone = math.floor((lon+180)/6)+1
  local bi = math.max(1, math.min(#BL, math.floor((lat+80)/8)+1))
  local band = BL:sub(bi,bi)
  local lr = math.rad(lat)
  local sn,cs,tn = math.sin(lr), math.cos(lr), math.tan(lr)
  local N = a_w/math.sqrt(1-e2*sn*sn)
  local T, C = tn*tn, ep2*cs*cs
  local A = math.rad(lon-((zone-1)*6-177))*cs
  local Mp = a_w*((1-e2/4-3*e2*e2/64)*lr-(3*e2/8+3*e2*e2/32)*math.sin(2*lr)
    +(15*e2*e2/256)*math.sin(4*lr))
  local E = k0*N*(A+(1-T+C)*A^3/6)+500000
  local Nn = k0*(Mp+N*tn*(A*A/2+(5-T+9*C)*A^4/24))
  if lat < 0 then Nn = Nn+10000000 end
  return zone, band, E, Nn
end

local function get100k(zone, E, Nn)
  local s = (zone-1)%6
  local cl = ({"ABCDEFGH","JKLMNPQR","STUVWXYZ","ABCDEFGH","JKLMNPQR","STUVWXYZ"})[s+1]
  local ci = math.max(1,math.min(#cl,((math.floor(E/100000)-1)%8)+1))
  local rs = (s%2==0) and "ABCDEFGHJKLMNPQRSTUV" or "FGHJKLMNPQRSTUVABCDE"
  local ri = math.max(1,math.min(#rs,(math.floor(Nn%2000000/100000)%20)+1))
  return cl:sub(ci,ci)..rs:sub(ri,ri)
end

local function toMGRS(lat, lon)
  if lat==0 and lon==0 then return "NO FIX" end
  local z,b,E,N = latLonToUTM(lat,lon)
  return string.format("%02d%s %s %05d %05d",z,b,get100k(z,E,N),
    math.floor(E%100000),math.floor(N%100000))
end

-- Presets per line (nil = auto from telemetry)
local presets = {
  {"N/A","IP ALPHA","IP BRAVO","IP CHARLIE","IP DELTA"},
  {"N/A","360","090","180","270","045","135","225","315"},
  {"N/A","1 KM","2 KM","3 KM","5 KM","8 KM","10 KM","15 KM"},
  nil, -- line 4: auto GPS alt
  {"TROOPS IN OPEN","VEHICLE","ARMOR","BUNKER","BUILDING",
   "ARTILLERY","MORTAR","AAA","SAM","SNIPER","CP"},
  nil, -- line 6: auto GPS MGRS
  {"NONE","WP","IR","LASER 1688","LASER 1111","SMOKE","IR PTR"},
  {"N/A","N 300M","S 300M","E 300M","W 300M",
   "N 500M","S 500M","E 500M","W 500M","N 1KM","S 1KM","E 1KM","W 1KM"},
  {"N/A","EGRESS N","EGRESS S","EGRESS E","EGRESS W","AS BRIEFED","RTB"},
}
local pIdx = {1,1,1,1,1,1,1,1,1}
local labels = {"1. IP/BP","2. HDG (IP-TGT)","3. DIST (IP-TGT)","4. TGT ELEV",
  "5. TGT DESCR","6. TGT LOC","7. MARK/CODE","8. FRIENDLIES","9. EGRESS"}

-- Helpers
local function sep(y) lcd.drawLine(15,y,W-15,y,SOLID,DARK) end
local function btn(x,y,w,h,lbl,bg,fg)
  lcd.drawFilledRectangle(x,y,w,h,bg); lcd.drawRectangle(x,y,w,h,DIM)
  lcd.drawText(x+10,y+math.floor((h-16)/2),lbl,SMLSIZE+fg)
end
local function corners(x1,y1,x2,y2,l)
  for _,p in ipairs({{x1,y1,1,0},{x1,y1,0,1},{x2,y1,-1,0},{x2,y1,0,1},
    {x1,y2,1,0},{x1,y2,0,-1},{x2,y2,-1,0},{x2,y2,0,-1}}) do
    lcd.drawLine(p[1],p[2],p[1]+p[3]*l,p[2]+p[4]*l,SOLID,DARK)
  end
end

-- Telemetry
local function getAltFt()
  local alt = getValue("Alt") or getValue("GAlt") or 0
  if alt==0 then return "NO ALT" end
  return string.format("%.0f FT MSL", alt*3.28084)
end
local function getGrid()
  return toMGRS(getValue("gps-lat") or 0, getValue("gps-lon") or 0)
end
local function fval(i)
  if i==4 then return getAltFt() end
  if i==6 then return getGrid() end
  return presets[i] and presets[i][pIdx[i]] or "---"
end

-- Header
local function drawHeader()
  lcd.drawFilledRectangle(0,0,W,HDR_H,BG)
  lcd.drawText(10,5,"9-LINE CAS BRIEF",MIDSIZE+HUD)
  lcd.drawText(W-100,5,"UNCLASS",SMLSIZE+DARK)
  local dt = getRtcTime and getRtcTime() or nil
  local ts = dt and string.format("%02d:%02d:%02dZ",dt.hour or 0,dt.min or 0,dt.sec or 0)
    or string.format("T+%05d",math.floor(getTime()/100))
  lcd.drawText(W-100,30,ts,SMLSIZE+HUD); sep(HDR_H)
end

-- Fields
local function drawFields()
  local top, bot = HDR_H+5, H-120
  for i=1,9 do
    local fy = top+(i-1)*FIELD_H+scrollY
    if fy+FIELD_H > top and fy < bot then
      local auto = (i==4 or i==6)
      if selField==i then
        lcd.drawFilledRectangle(FIELD_X,fy,FIELD_W,FIELD_H-6,lcd.RGB(0x08,0x28,0x08))
        lcd.drawRectangle(FIELD_X,fy,FIELD_W,FIELD_H-6,AMB)
      end
      lcd.drawText(FIELD_X+8,fy+4,labels[i],SMLSIZE+(auto and CYN or DIM))
      if auto then lcd.drawText(FIELD_X+FIELD_W-65,fy+4,"[AUTO]",SMLSIZE+CYN) end
      local v = fval(i)
      local vc = HUD
      if v=="N/A" or v=="NO FIX" or v=="NO ALT" or v=="---" then vc=GRY end
      lcd.drawText(FIELD_X+16,fy+30,v,MIDSIZE+vc)
      if not auto and presets[i] then
        lcd.drawText(FIELD_X+FIELD_W-55,fy+35,
          string.format("%d/%d",pIdx[i],#presets[i]),SMLSIZE+GRY)
      end
      sep(fy+FIELD_H-6)
    end
  end
  local visH = bot-top; local totalH = 9*FIELD_H
  if totalH > visH then
    local bH = math.max(30,math.floor(visH*visH/totalH))
    local bY = math.max(top,math.min(bot-bH,
      top+math.floor((-scrollY/(totalH-visH))*(visH-bH))))
    lcd.drawFilledRectangle(W-8,bY,5,bH,DIM)
  end
end

-- Readback
local function drawReadback()
  lcd.drawFilledRectangle(0,0,W,H,lcd.RGB(0,0,0))
  lcd.drawText(15,10,"9-LINE READBACK",MIDSIZE+AMB)
  lcd.drawText(W-100,10,"UNCLASS",SMLSIZE+DARK); sep(45)
  local y = 55
  for i=1,9 do
    lcd.drawText(20,y,labels[i],SMLSIZE+((i==4 or i==6) and CYN or DIM))
    y=y+22; lcd.drawText(35,y,fval(i),SMLSIZE+HUD); y=y+30
    if i==3 or i==6 then sep(y); y=y+8 end
  end
  y=y+10; sep(y); y=y+10
  lcd.drawText(20,y,"REMARKS:",SMLSIZE+AMB); y=y+25
  lcd.drawText(35,y,"TOT: ON STATION",SMLSIZE+HUD); y=y+22
  lcd.drawText(35,y,"RESTRICTIONS: NONE",SMLSIZE+HUD)
  btn(W/2-100,H-90,200,BTN_H,"CLOSE READBACK",DARK,HUD)
  corners(5,5,W-5,H-5,20)
end

-- Bottom bar
local function drawBottom()
  local by = H-110
  lcd.drawFilledRectangle(0,by,W,110,BG); sep(by)
  btn(20,by+15,280,BTN_H,"READBACK",lcd.RGB(0x10,0x30,0x10),AMB)
  btn(320,by+15,170,BTN_H,"CLEAR ALL",lcd.RGB(0x20,0x08,0x08),RED)
  btn(510,by+5,90,30,"UP",DARK,HUD); btn(620,by+5,90,30,"DN",DARK,HUD)
  if statusTimer > 0 and statusMsg ~= "" then
    lcd.drawText(20,by+75,statusMsg,SMLSIZE+AMB); statusTimer=statusTimer-1
  else lcd.drawText(20,by+75,"TAP field to cycle | READBACK to review",SMLSIZE+GRY) end
end

-- Touch
local lastTY = nil
local function handleTouch(tx, ty)
  if showReadback then
    if ty>=H-90 and ty<=H-40 and tx>=W/2-100 and tx<=W/2+100 then showReadback=false end
    return
  end
  local by = H-110
  if ty >= by then
    if tx>=20 and tx<=300 and ty>=by+15 and ty<=by+65 then showReadback=true; return end
    if tx>=320 and tx<=490 and ty>=by+15 and ty<=by+65 then
      for i=1,9 do pIdx[i]=1 end; selField=0
      statusMsg="ALL CLEARED"; statusTimer=40; return
    end
    if tx>=510 and tx<=600 and ty>=by+5 and ty<=by+35 then
      scrollY=math.min(0,scrollY+FIELD_H); return end
    if tx>=620 and tx<=710 and ty>=by+5 and ty<=by+35 then
      scrollY=math.max(-(9*FIELD_H-(by-HDR_H-5)),scrollY-FIELD_H); return end
    return
  end
  local top = HDR_H+5
  for i=1,9 do
    local fy = top+(i-1)*FIELD_H+scrollY
    if ty>=fy and ty<fy+FIELD_H-6 then
      if i==4 or i==6 then
        selField=i; statusMsg=labels[i].." [AUTO]"; statusTimer=30
      elseif presets[i] then
        selField=i; pIdx[i]=(pIdx[i]%#presets[i])+1
        statusMsg=labels[i]..": "..presets[i][pIdx[i]]; statusTimer=30
      end
      return
    end
  end
end

local function handleSlide(ty)
  if showReadback then return end
  if lastTY then
    local dy=ty-lastTY
    if math.abs(dy)>3 then
      scrollY=math.max(-(9*FIELD_H-(H-110-HDR_H-5)),math.min(0,scrollY+dy))
    end
  end
  lastTY=ty
end

function M.init()
  BG  =lcd.RGB(0x0A,0x0A,0x0A); HUD=lcd.RGB(0x00,0xFF,0x00)
  DIM =lcd.RGB(0x00,0x88,0x00); DARK=lcd.RGB(0x00,0x44,0x00)
  AMB =lcd.RGB(0xFF,0xAA,0x00); RED=lcd.RGB(0xFF,0x00,0x00)
  GRY =lcd.RGB(0x44,0x44,0x44); WHT=lcd.RGB(0xFF,0xFF,0xFF)
  CYN =lcd.RGB(0x00,0xCC,0xCC)
end

function M.run(event, touchState)
  lcd.clear(BG)
  if event==EVT_TOUCH_TAP and touchState then
    handleTouch(touchState.x,touchState.y); lastTY=nil
  elseif event==EVT_TOUCH_SLIDE and touchState then handleSlide(touchState.y)
  elseif event==EVT_TOUCH_BREAK then lastTY=nil end
  if showReadback then drawReadback()
  else drawHeader(); drawFields(); drawBottom()
    corners(5,HDR_H+2,W-5,H-115,15) end
  return 0
end

return M
