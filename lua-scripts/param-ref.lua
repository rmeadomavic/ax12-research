-- TNS|Param Ref|TNE

local LCD_W, LCD_H = LCD_W or 480, LCD_H or 272
local COLOR_BG = lcd.RGB(0x1a, 0x1a, 0x2e)
local COLOR_TAB = lcd.RGB(0x2d, 0x2d, 0x44)
local COLOR_TAB_SEL = lcd.RGB(0x00, 0x7a, 0xcc)
local COLOR_TEXT = lcd.RGB(0xff, 0xff, 0xff)
local COLOR_DIM = lcd.RGB(0x99, 0x99, 0xaa)
local COLOR_HIGHLIGHT = lcd.RGB(0x33, 0x33, 0x55)
local COLOR_VAL = lcd.RGB(0x66, 0xdd, 0xff)
local COLOR_HDR = lcd.RGB(0xff, 0xcc, 0x00)

local TAB_H = 28
local ROW_H = 22
local DETAIL_H = 60

local categories = {"SAFETY","FLIGHT","TUNING","GPS/NAV","SERIAL","RC"}
local selectedTab = 1
local scrollPos = 1
local selectedParam = 0
local showDetail = false

local params = {}

params[1] = {
  {n="ARMING_CHECK",def="1",rng="0-1",desc="Enable pre-arm safety checks (1=all)"},
  {n="FS_THR_ENABLE",def="1",rng="0-3",desc="Throttle failsafe: 0=off,1=RTL,2=Land,3=SmartRTL"},
  {n="FS_THR_VALUE",def="975",rng="925-1100",desc="PWM below which throttle failsafe triggers"},
  {n="FS_GCS_ENABLE",def="1",rng="0-2",desc="GCS failsafe: 0=off,1=RTL,2=Land"},
  {n="FENCE_ENABLE",def="0",rng="0-1",desc="Geofence enable (1=on)"},
  {n="FENCE_ALT_MAX",def="100",rng="10-1000",desc="Max altitude fence in meters"},
  {n="FENCE_RADIUS",def="300",rng="30-10000",desc="Circular fence radius in meters"},
}

params[2] = {
  {n="WPNAV_SPEED",def="500",rng="20-2000",desc="Waypoint horizontal speed cm/s (500=5m/s)"},
  {n="WPNAV_SPEED_DN",def="150",rng="10-500",desc="Waypoint descent speed cm/s"},
  {n="WPNAV_SPEED_UP",def="250",rng="10-1000",desc="Waypoint climb speed cm/s"},
  {n="RTL_ALT",def="1500",rng="0-8000",desc="RTL altitude cm (1500=15m, 0=current)"},
  {n="RTL_SPEED",def="0",rng="0-2000",desc="RTL speed cm/s (0=WPNAV_SPEED)"},
  {n="LAND_SPEED",def="50",rng="30-200",desc="Final landing descent speed cm/s"},
  {n="ANGLE_MAX",def="3000",rng="1000-8000",desc="Max lean angle centidegrees (3000=30deg)"},
}

params[3] = {
  {n="ATC_RAT_RLL_P",def="0.135",rng="0.01-0.5",desc="Roll rate P gain"},
  {n="ATC_RAT_RLL_I",def="0.135",rng="0.01-0.5",desc="Roll rate I gain (usually=P)"},
  {n="ATC_RAT_RLL_D",def="0.0036",rng="0.0-0.02",desc="Roll rate D gain"},
  {n="ATC_RAT_PIT_P",def="0.135",rng="0.01-0.5",desc="Pitch rate P gain"},
  {n="ATC_RAT_PIT_I",def="0.135",rng="0.01-0.5",desc="Pitch rate I gain"},
  {n="ATC_RAT_PIT_D",def="0.0036",rng="0.0-0.02",desc="Pitch rate D gain"},
  {n="ATC_RAT_YAW_P",def="0.18",rng="0.1-0.5",desc="Yaw rate P gain"},
  {n="ATC_RAT_YAW_I",def="0.018",rng="0.01-0.05",desc="Yaw rate I gain"},
  {n="ATC_RAT_YAW_D",def="0.0",rng="0.0-0.02",desc="Yaw rate D gain"},
  {n="INS_GYRO_FILTER",def="20",rng="10-256",desc="Gyro lowpass filter Hz"},
  {n="MOT_SPIN_ARM",def="0.1",rng="0.0-0.3",desc="Motor spin when armed (0-1 throttle fraction)"},
}

params[4] = {
  {n="GPS_TYPE",def="1",rng="0-21",desc="GPS type: 0=none,1=auto,2=uBlox,9=NMEA"},
  {n="EK3_SRC1_POSXY",def="1",rng="0-6",desc="Pos XY source: 1=GPS,2=ExtNav,6=Wheel"},
  {n="EK3_SRC1_VELXY",def="1",rng="0-7",desc="Vel XY source: 0=none,1=GPS,5=OptFlow"},
  {n="EK3_SRC1_POSZ",def="1",rng="0-6",desc="Pos Z source: 1=Baro,2=Rangefinder,3=GPS"},
  {n="AHRS_EKF_TYPE",def="3",rng="2-3",desc="EKF type: 3=EKF3 (recommended)"},
}

params[5] = {
  {n="SERIAL1_PROTOCOL",def="2",rng="0-38",desc="Protocol: 1=MAVLink1,2=MAVLink2,23=RCIN"},
  {n="SERIAL2_PROTOCOL",def="2",rng="0-38",desc="Protocol for SERIAL2 port"},
  {n="SERIAL1_BAUD",def="57",rng="1-2000",desc="Baud rate (57=57600, 115=115200, 921=921600)"},
  {n="BRD_SERIAL_NUM",def="0",rng="0-32767",desc="Vehicle serial number for identification"},
}

params[6] = {
  {n="RC1_MIN",def="1100",rng="800-2200",desc="RC ch1 min PWM"},
  {n="RC1_MAX",def="1900",rng="800-2200",desc="RC ch1 max PWM"},
  {n="RC1_TRIM",def="1500",rng="800-2200",desc="RC ch1 center PWM"},
  {n="RCMAP_ROLL",def="1",rng="1-16",desc="RC channel mapped to roll"},
  {n="RCMAP_PITCH",def="2",rng="1-16",desc="RC channel mapped to pitch"},
  {n="RCMAP_THROTTLE",def="3",rng="1-16",desc="RC channel mapped to throttle"},
  {n="RCMAP_YAW",def="4",rng="1-16",desc="RC channel mapped to yaw"},
  {n="FLTMODE_CH",def="5",rng="1-16",desc="Flight mode switch channel"},
  {n="FLTMODE1",def="0",rng="0-27",desc="Mode slot 1: 0=Stab,2=AltHold,5=Loiter,6=RTL"},
  {n="FLTMODE2",def="0",rng="0-27",desc="Mode slot 2"},
  {n="FLTMODE3",def="0",rng="0-27",desc="Mode slot 3"},
  {n="FLTMODE4",def="0",rng="0-27",desc="Mode slot 4"},
  {n="FLTMODE5",def="0",rng="0-27",desc="Mode slot 5"},
  {n="FLTMODE6",def="0",rng="0-27",desc="Mode slot 6"},
}

local function getVisibleRows()
  local area = LCD_H - TAB_H - 4
  if showDetail then area = area - DETAIL_H end
  return math.floor(area / ROW_H)
end

local function clampScroll()
  local cat = params[selectedTab]
  local maxScroll = math.max(1, #cat - getVisibleRows() + 1)
  if scrollPos > maxScroll then scrollPos = maxScroll end
  if scrollPos < 1 then scrollPos = 1 end
end

local function init()
  selectedTab = 1
  scrollPos = 1
  selectedParam = 0
  showDetail = false
end

local function run(event, touchState)
  lcd.clear(COLOR_BG)

  -- Handle touch on tabs
  if touchState and touchState.tapCount then
    local tx, ty = touchState.x or 0, touchState.y or 0
    if ty < TAB_H then
      local tabW = math.floor(LCD_W / #categories)
      local tapped = math.floor(tx / tabW) + 1
      if tapped >= 1 and tapped <= #categories then
        if tapped ~= selectedTab then
          selectedTab = tapped
          scrollPos = 1
          selectedParam = 0
          showDetail = false
        end
      end
    else
      -- Touch on param list
      local listY = TAB_H + 2
      local row = math.floor((ty - listY) / ROW_H) + 1
      local idx = row + scrollPos - 1
      local cat = params[selectedTab]
      if idx >= 1 and idx <= #cat then
        if selectedParam == idx then
          showDetail = not showDetail
        else
          selectedParam = idx
          showDetail = true
        end
      end
    end
  end

  -- EVT handling for scrolling
  if event == EVT_MINUS_FIRST or event == EVT_MINUS_RPT or event == EVT_ROT_LEFT then
    scrollPos = scrollPos + 1
    clampScroll()
  elseif event == EVT_PLUS_FIRST or event == EVT_PLUS_RPT or event == EVT_ROT_RIGHT then
    scrollPos = scrollPos - 1
    clampScroll()
  elseif event == EVT_ENTER_BREAK then
    local cat = params[selectedTab]
    if selectedParam >= 1 and selectedParam <= #cat then
      showDetail = not showDetail
    end
  elseif event == EVT_EXIT_BREAK then
    if showDetail then
      showDetail = false
    else
      return 1
    end
  end

  -- Draw tabs
  local tabW = math.floor(LCD_W / #categories)
  for i, name in ipairs(categories) do
    local x = (i-1) * tabW
    local col = (i == selectedTab) and COLOR_TAB_SEL or COLOR_TAB
    lcd.drawFilledRectangle(x, 0, tabW - 1, TAB_H, col)
    lcd.drawText(x + 4, 6, name, SMLSIZE + COLOR_TEXT)
  end

  -- Draw param list
  local cat = params[selectedTab]
  local visRows = getVisibleRows()
  local listY = TAB_H + 2

  clampScroll()

  for i = 0, visRows - 1 do
    local idx = scrollPos + i
    if idx > #cat then break end
    local p = cat[idx]
    local y = listY + i * ROW_H

    if idx == selectedParam then
      lcd.drawFilledRectangle(0, y, LCD_W, ROW_H, COLOR_HIGHLIGHT)
    end

    lcd.drawText(4, y + 2, p.n, SMLSIZE + COLOR_HDR)
    lcd.drawText(220, y + 2, "Def:" .. p.def, SMLSIZE + COLOR_VAL)
    lcd.drawText(330, y + 2, "[" .. p.rng .. "]", SMLSIZE + COLOR_DIM)
  end

  -- Draw detail panel
  if showDetail and selectedParam >= 1 and selectedParam <= #cat then
    local p = cat[selectedParam]
    local dy = LCD_H - DETAIL_H
    lcd.drawFilledRectangle(0, dy, LCD_W, DETAIL_H, lcd.RGB(0x11, 0x11, 0x22))
    lcd.drawRectangle(0, dy, LCD_W, DETAIL_H, COLOR_TAB_SEL)
    lcd.drawText(6, dy + 4, p.n, MIDSIZE + COLOR_HDR)
    lcd.drawText(6, dy + 22, p.desc, SMLSIZE + COLOR_TEXT)
    lcd.drawText(6, dy + 40, "Default: " .. p.def .. "  Range: " .. p.rng, SMLSIZE + COLOR_VAL)
  end

  -- Scroll indicator
  if #cat > visRows then
    local barH = math.max(10, math.floor(LCD_H * visRows / #cat))
    local barY = TAB_H + math.floor((LCD_H - TAB_H) * (scrollPos - 1) / #cat)
    lcd.drawFilledRectangle(LCD_W - 4, barY, 4, barH, COLOR_DIM)
  end

  return 0
end

return { init=init, run=run }
