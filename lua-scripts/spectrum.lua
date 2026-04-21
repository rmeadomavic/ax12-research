-- TNS|Spectrum|TNE
local LCD_W, LCD_H = 480, 272
local scrollX = 0
local MAX_SCROLL = 200

local bands = {
  { name="433 LoRa",   fStart=430,  fEnd=440,   color=PURPLE  },
  { name="868 ELRS",   fStart=863,  fEnd=870,   color=ORANGE  },
  { name="915 ELRS",   fStart=902,  fEnd=928,   color=ORANGE  },
  { name="1.2G Video", fStart=1080, fEnd=1360,  color=YELLOW  },
  { name="WiFi 2.4",   fStart=2400, fEnd=2484,  color=GREEN   },
  { name="ELRS 2.4",   fStart=2400, fEnd=2500,  color=GREEN   },
  { name="BT 2.4",     fStart=2402, fEnd=2480,  color=GREEN   },
  { name="Overlap",    fStart=2400, fEnd=2480,  color=RED     },
  { name="5.8 A",      fStart=5725, fEnd=5770,  color=CYAN    },
  { name="5.8 B",      fStart=5771, fEnd=5810,  color=CYAN    },
  { name="5.8 E",      fStart=5650, fEnd=5720,  color=CYAN    },
  { name="5.8 F",      fStart=5740, fEnd=5800,  color=CYAN    },
  { name="5.8 R",      fStart=5658, fEnd=5917,  color=CYAN    },
  { name="5.8 L",      fStart=5362, fEnd=5945,  color=CYAN    },
}

local FREQ_MIN = 300
local FREQ_MAX = 6200
local FREQ_RANGE = FREQ_MAX - FREQ_MIN

local function freqToX(freq)
  return math.floor(((freq - FREQ_MIN) / FREQ_RANGE) * (LCD_W * 2)) - scrollX
end

local function init()
  scrollX = 0
end

local function run(event, touchState)
  if touchState then
    if touchState.x < LCD_W / 2 then
      scrollX = math.max(0, scrollX - 40)
    else
      scrollX = math.min(MAX_SCROLL, scrollX + 40)
    end
  end
  if event == EVT_VIRTUAL_INC or event == EVT_ROT_RIGHT then
    scrollX = math.min(MAX_SCROLL, scrollX + 30)
  elseif event == EVT_VIRTUAL_DEC or event == EVT_ROT_LEFT then
    scrollX = math.max(0, scrollX - 30)
  end

  lcd.clear(BLACK)

  lcd.drawText(LCD_W/2 - 100, 2, "RF SPECTRUM - DRONE SYSTEMS", MIDSIZE + WHITE)

  local axisY = LCD_H - 30
  lcd.drawLine(0, axisY, LCD_W, axisY, SOLID, WHITE)

  for freq = 500, 6000, 500 do
    local x = freqToX(freq)
    if x >= 0 and x < LCD_W then
      lcd.drawLine(x, axisY, x, axisY + 4, SOLID, WHITE)
      lcd.drawText(x - 8, axisY + 6, tostring(freq), SMLSIZE + WHITE)
    end
  end

  local barTop = 30
  local barBot = axisY - 2
  local barH = barBot - barTop

  for i, band in ipairs(bands) do
    local x1 = freqToX(band.fStart)
    local x2 = freqToX(band.fEnd)
    if x2 > 0 and x1 < LCD_W then
      x1 = math.max(0, x1)
      x2 = math.min(LCD_W - 1, x2)
      local w = x2 - x1
      if w < 4 then w = 4 end

      for y = barTop, barBot do
        lcd.drawLine(x1, y, x1 + w, y, SOLID, band.color)
      end

      if w > 30 then
        local lblY = barTop + ((i % 5) * (barH / 6))
        lcd.drawText(x1 + 2, lblY, band.name, SMLSIZE + BLACK)
      end
    end
  end

  lcd.drawText(4, LCD_H - 12, "< SCROLL", SMLSIZE + WHITE)
  lcd.drawText(LCD_W - 70, LCD_H - 12, "SCROLL >", SMLSIZE + WHITE)

  return 0
end

return { init=init, run=run }
