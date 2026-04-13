# Flyshark Lua API Reference — RadioMaster AX12

Extracted from `libRadioMasterAX_arm64-v8a.so` via `strings` analysis.
Confirmed symbols marked with **[C]** (called by existing scripts: `elrsV3.lua`, `Game-simulator.lua`).

Source: `/data/app/com.Flyshark.RadioMasterAX-HwyJL_quVLb4P2WhS2EpcA==/lib/arm64/libRadioMasterAX_arm64-v8a.so`

---

## 1. LCD Drawing Functions (`lcd.*`)

These are methods on the global `lcd` table.

| Function | Description | Status |
|---|---|---|
| `lcd.clear()` | Clear the screen | **[C]** |
| `lcd.drawArc()` | Draw an arc | inferred |
| `lcd.drawBitmap()` | Draw a bitmap image | inferred |
| `lcd.drawBitmapPattern()` | Draw a patterned bitmap | inferred |
| `lcd.drawBitmapPatternPie()` | Draw a pie-shaped bitmap pattern | inferred |
| `lcd.drawChannel()` | Draw a channel value | inferred |
| `lcd.drawCircle()` | Draw circle outline | inferred |
| `lcd.drawFilledCircle()` | Draw filled circle | inferred |
| `lcd.drawFilledRectangle()` | Draw filled rectangle | **[C]** |
| `lcd.drawFilledTriangle()` | Draw filled triangle | inferred |
| `lcd.drawGauge()` | Draw a gauge/progress bar | **[C]** |
| `lcd.drawLine()` | Draw a line | **[C]** |
| `lcd.drawLineWithClipping()` | Draw a clipped line | inferred |
| `lcd.drawNumber()` | Draw a number | **[C]** |
| `lcd.drawPie()` | Draw a pie shape | inferred |
| `lcd.drawPoint()` | Draw a single pixel | inferred |
| `lcd.drawRectangle()` | Draw rectangle outline | **[C]** |
| `lcd.drawSource()` | Draw source name by index | inferred |
| `lcd.drawSwitch()` | Draw switch name by index | inferred |
| `lcd.drawText()` | Draw text string | **[C]** |
| `lcd.drawTextLines()` | Draw multi-line text | inferred |
| `lcd.drawTimer()` | Draw a timer value formatted | **[C]** |
| `lcd.drawTriangle()` | Draw triangle outline | inferred |
| `lcd.getColor()` | Get a theme/named color | inferred |
| `lcd.getLastPos()` | Get X position after last draw | **[C]** |
| `lcd.RGB()` | Create color from R,G,B values | **[C]** |
| `lcd.setColor()` | Set a named color | **[C]** |
| `lcd.sizeText()` | Get pixel width of text string | **[C]** |
| `lcd.refresh()` | Force screen refresh | inferred |

Additional drawing functions found (possibly internal/C-level, may be accessible):
- `drawAnnulus()` — ring/donut shape
- `drawHudRectangle()` — HUD-style tilted rectangle
- `drawLinkLine()` — connection line
- `drawQuadraticBezier()` — bezier curve
- `drawQuadraticBezierPoint()` — point on bezier

## 2. Model Functions (`model.*`)

Methods on the global `model` table.

| Function | Description | Status |
|---|---|---|
| `model.defaultInputs()` | Reset inputs to defaults | inferred |
| `model.deleteInput()` | Delete a specific input line | inferred |
| `model.deleteInputs()` | Delete all inputs | inferred |
| `model.deleteMix()` | Delete a specific mix | inferred |
| `model.deleteMixes()` | Delete all mixes | inferred |
| `model.getCurve()` | Get curve definition | inferred |
| `model.getCurveList()` | Get list of all curves | inferred |
| `model.getCustomFunction()` | Get special function config | inferred |
| `model.getGlobalVariable()` | Get a GVar value | inferred |
| `model.getGlobalVariableDetails()` | Get GVar name/min/max/unit | inferred |
| `model.getInfo()` | Get model name and bitmap | inferred |
| `model.getInput()` | Get input line definition | inferred |
| `model.getInputsCount()` | Get number of input lines | inferred |
| `model.getLogicalSwitch()` | Get logical switch config | inferred |
| `model.getLogicalSwitchValue()` | Get LS current state (bool) | inferred |
| `model.getMix()` | Get mix definition | inferred |
| `model.getMixCfgData()` | Get mix config data (RM-specific?) | inferred |
| `model.getMixesCount()` | Get number of mixes | inferred |
| `model.getModule()` | Get RF module config | **[C]** |
| `model.getOutput()` | Get output channel config | inferred |
| `model.getOutputValue()` | Get live output value | inferred |
| `model.getSensor()` | Get telemetry sensor definition | inferred |
| `model.getTimer()` | Get timer config | inferred |
| `model.insertInput()` | Insert an input line | inferred |
| `model.insertMix()` | Insert a mix line | inferred |
| `model.resetSensor()` | Reset a telemetry sensor | inferred |
| `model.resetTimer()` | Reset a timer | inferred |
| `model.setCurve()` | Set curve definition | inferred |
| `model.setCurveCfg()` | Set curve config (RM-specific?) | inferred |
| `model.setCustomFunction()` | Set special function config | inferred |
| `model.setGlobalVariable()` | Set a GVar value | inferred |
| `model.setGlobalVariableDetails()` | Set GVar details | inferred |
| `model.setInfo()` | Set model name and bitmap | inferred |
| `model.setLogicalSwitch()` | Set logical switch config | inferred |
| `model.setOutput()` | Set output channel config | inferred |
| `model.setTimer()` | Set timer config | inferred |

## 3. Telemetry & CRSF Functions

| Function | Description | Status |
|---|---|---|
| `crossfireTelemetryPop()` | Pop CRSF telemetry frame from RX queue | **[C]** |
| `crossfireTelemetryPush()` | Push CRSF telemetry frame to TX queue | **[C]** |
| `sportTelemetryPop()` | Pop S.PORT telemetry frame | inferred |
| `sportTelemetryPush()` | Push S.PORT telemetry frame | inferred |
| `setTelemetryValue()` | Set a telemetry sensor value | inferred |
| `getRSSI()` | Get current RSSI value | inferred |
| `getRAS()` | Get RAS (SWR) value | inferred |

## 4. Input / Value Functions

| Function | Description | Status |
|---|---|---|
| `getValue()` | Get value of source by ID | **[C]** |
| `getFieldInfo()` | Get field info (name, id, desc) by name | **[C]** |
| `getFlightMode()` | Get active flight mode index and name | inferred |
| `getSourceIndex()` | Get source index by name | inferred |
| `getSourceName()` | Get source name by index | inferred |
| `getSourceInfo()` | Get source info (min/max/name) | inferred |
| `getSourceValue()` | Get source value by index | inferred |
| `getSwitchIndex()` | Get switch index by name | inferred |
| `getSwitchName()` | Get switch name by index | inferred |
| `getSwitchValue()` | Get switch state | inferred |
| `getLogicalSwitchValue()` | Get logical switch state | inferred |
| `defaultStick()` | Get default stick source index | inferred |
| `defaultChannel()` | Get default channel source index | inferred |

## 5. System Functions

| Function | Description | Status |
|---|---|---|
| `getTime()` | Get system time in 10ms ticks | **[C]** |
| `getDateTime()` | Get date/time table | inferred |
| `getRtcTime()` | Get RTC time (epoch seconds) | inferred |
| `getVersion()` | Get firmware version string | **[C]** |
| `getGeneralSettings()` | Get radio general settings table | inferred |
| `getAvailableMemory()` | Get free Lua memory in bytes | inferred |
| `getUsage()` | Get Lua CPU usage percentage | inferred |
| `getGlobalTimer()` | Get global timer value | inferred |
| `resetGlobalTimer()` | Reset global timer | inferred |
| `getTrainerStatus()` | Get trainer port status | inferred |
| `getTxGPS()` | Get transmitter GPS data | inferred |
| `loadScript()` | Load and return a Lua script chunk | **[C]** |
| `killEvents()` | Kill pending UI events | inferred |

## 6. Audio Functions

| Function | Description | Status |
|---|---|---|
| `playFile()` | Play an audio WAV file | inferred |
| `playTone()` | Play a tone (freq, duration, pause) | **[C]** |
| `playNumber()` | Speak a number with units | inferred |
| `playHaptic()` | Trigger haptic vibration | inferred |
| `playDuration()` | Speak a duration value | inferred |

## 7. Popup / UI Functions

| Function | Description | Status |
|---|---|---|
| `popupConfirmation()` | Show confirmation dialog | **[C]** |
| `popupWarning()` | Show warning dialog | inferred |

## 8. Shared Memory (RadioMaster-Specific)

| Function | Description | Status |
|---|---|---|
| `setShmVar()` | Set shared memory variable | inferred |
| `getShmVar()` | Get shared memory variable | inferred |

## 9. Serial Port Access — DEAD STUBS

**These functions are registered but non-functional on the AX12.** `serialPutc` and `serialCrlf` are bare `ret` instructions. The `serialRead` FIFO is never fed — no data will ever be returned. There is no "LUA serial mode" in the AX12 settings. The functions exist in the symbol table (inherited from the EdgeTX-lineage codebase) but were never wired to actual hardware on this platform.

| Function | Description | Status |
|---|---|---|
| `serialRead()` | Read bytes from serial port | **DEAD STUB** — FIFO never fed |
| `serialWrite()` | Write bytes to serial port | **DEAD STUB** |
| `setSerialBaudrate()` | Set serial port baud rate | **DEAD STUB** |

## 10. File I/O (Lua Standard)

Confirmed present by `Game-simulator.lua`:

| Function | Status |
|---|---|
| `io.open()` | **[C]** |
| `io.close()` | **[C]** |
| `io.read()` | **[C]** |
| `io.write()` | **[C]** |
| `chdir()` | inferred |

## 11. Lua Standard Libraries

Confirmed present via strings analysis:

| Library | Status |
|---|---|
| `string` (`.char`, `.format`, `.sub`, ...) | **[C]** |
| `math` (`.floor`, `.abs`, `.random`, ...) | **[C]** |
| `table` (`.sort`, `.insert`, ...) | **[C]** |
| `bit32` (`.band`, `.btest`, `.lshift`, `.rshift`) | **[C]** |
| `package` | present |
| `debug` | present |
| `pcall()` | **[C]** |
| `ipairs()` | **[C]** |
| `pairs()` | **[C]** |
| `tostring()` | **[C]** |
| `tonumber()` | **[C]** |
| `collectgarbage()` | **[C]** |
| `load()` | **[C]** |

## 12. Constants

### Text Size/Style Flags
| Constant | Description |
|---|---|
| `BOLD` | Bold text |
| `INVERS` | Inverted (highlight) |
| `BLINK` | Blinking text |
| `SMLSIZE` | Small font |
| `MIDSIZE` | Medium font |
| `DBLSIZE` | Double-size font |
| `XXLSIZE` | Extra-extra-large font |
| `SHADOWED` | Drop shadow |
| `LEFT` | Left-aligned |
| `RIGHT` | Right-aligned |
| `CENTER` | Center-aligned |
| `PREC1` | 1 decimal precision |
| `PREC2` | 2 decimal precision |
| `SOLID` | Solid line style |
| `CUSTOM_COLOR` | Use custom color |

### Colors
`BLACK`, `WHITE`, `GREY`, `BLUE`, `RED`, `YELLOW`, `GREEN`, `ORANGE`

### Theme Colors
`COLOR_THEME_PRIMARY1` through `PRIMARY3`, `SECONDARY1` through `SECONDARY3`, `COLOR_THEME_ACTIVE`, `COLOR_THEME_FOCUS`, `COLOR_THEME_EDIT`, `COLOR_THEME_DISABLED`, `COLOR_THEME_WARNING`

### Screen Dimensions
`LCD_W`, `LCD_H` — screen width and height in pixels

### Event Constants
| Event | Description |
|---|---|
| `EVT_ENTER_BREAK/FIRST/LONG/REPT` | Enter button events |
| `EVT_EXIT_BREAK/FIRST/LONG/REPT` | Exit/back button events |
| `EVT_PAGEDN_BREAK/FIRST/LONG/REPT` | Page down events |
| `EVT_PAGEUP_BREAK/FIRST/LONG/REPT` | Page up events |
| `EVT_ROT_BREAK/FIRST/LEFT/LONG/REPT/RIGHT` | Rotary encoder events |
| `EVT_SYS_BREAK/FIRST/LONG/REPT` | System button events |
| `EVT_MODEL_BREAK/FIRST/LONG/REPT` | Model button events |
| `EVT_TELEM_BREAK/FIRST/LONG/REPT` | Telemetry button events |
| `EVT_TOUCH_BREAK/FIRST/SLIDE/TAP` | Touchscreen events |
| `EVT_VIRTUAL_*` | Virtual button events (DEC, INC, ENTER, EXIT, MENU, NEXT, PREV, NEXT_PAGE, PREV_PAGE) |

### Source/Mix Constants
`MIXSRC_CH1`, `MIXSRC_FIRST_INPUT`, `MIXSRC_MAX`, `MIXSRC_MIN`, `SWSRC_LAST`

### Character Icons
`CHAR_CHANNEL`, `CHAR_CURVE`, `CHAR_CYC`, `CHAR_DELTA`, `CHAR_DOWN`, `CHAR_FUNCTION`, `CHAR_INPUT`, `CHAR_LEFT`, `CHAR_LUA`, `CHAR_POT`, `CHAR_RIGHT`, `CHAR_SLIDER`, `CHAR_STICK`, `CHAR_SWITCH`, `CHAR_TELEMETRY`, `CHAR_TRAINER`, `CHAR_TRIM`, `CHAR_UP`

### Logical Switch Functions
`LS_FUNC_NONE`, `LS_FUNC_EQUAL`, `LS_FUNC_GREATER`, `LS_FUNC_LESS`, `LS_FUNC_AND`, `LS_FUNC_OR`, `LS_FUNC_XOR`, `LS_FUNC_EDGE`, `LS_FUNC_STICKY`, `LS_FUNC_TIMER`, `LS_FUNC_APOS`, `LS_FUNC_ANEG`, `LS_FUNC_VPOS`, `LS_FUNC_VNEG`, `LS_FUNC_VEQUAL`, `LS_FUNC_VALMOSTEQUAL`, `LS_FUNC_DIFFEGREATER`, `LS_FUNC_ADIFFEGREATER`

### Unit Constants
`UNIT_RAW`, `UNIT_VOLTS`, `UNIT_AMPS`, `UNIT_MILLIAMPS`, `UNIT_MAH`, `UNIT_WATTS`, `UNIT_MILLIWATTS`, `UNIT_DB`, `UNIT_DBM`, `UNIT_RPMS`, `UNIT_G`, `UNIT_DEGREE`, `UNIT_RADIANS`, `UNIT_CELSIUS`, `UNIT_FAHRENHEIT`, `UNIT_PERCENT`, `UNIT_METERS`, `UNIT_FEET`, `UNIT_KM`, `UNIT_KMH`, `UNIT_MPH`, `UNIT_KTS`, `UNIT_METERS_PER_SECOND`, `UNIT_FEET_PER_SECOND`, `UNIT_HERTZ`, `UNIT_MS`, `UNIT_US`, `UNIT_HOURS`, `UNIT_MINUTES`, `UNIT_SECONDS`, `UNIT_CELLS`, `UNIT_DATETIME`, `UNIT_GPS`, `UNIT_BITFIELD`, `UNIT_TEXT`, `UNIT_FLOZ`, `UNIT_MILLILITERS`, `UNIT_MILLILITERS_PER_MINUTE`

## 13. LVGL Bindings

The library contains a **full LVGL v8.x binding** exposed to Lua via the `lvgl` global table. This includes:

### Widget Creation
`lv_arc_create`, `lv_bar_create`, `lv_btn_create`, `lv_btnmatrix_create`, `lv_canvas_create`, `lv_img_create`, `lv_keyboard_create`, `lv_label_create`, `lv_line_create`, `lv_obj_create`, `lv_qrcode_create`, `lv_slider_create`, `lv_switch_create`, `lv_table_create`, `lv_textarea_create`, `lv_tileview_create`

### Layout
Flex (`lv_flex_init`, `lv_obj_set_flex_flow/align/grow`) and Grid (`lv_grid_init`, `lv_obj_set_grid_*`) layouts.

### Styling
Full `lv_obj_set_style_*` and `lv_style_set_*` for: bg, border, outline, shadow, text, line, arc, image, padding, margin, size, transforms, transitions, opacity.

### Animation
`lv_anim_init/start/del/del_all` with path functions: `linear`, `ease_in`, `ease_out`, `ease_in_out`, `bounce`, `overshoot`, `step`.

### Drawing
`lv_draw_rect`, `lv_draw_arc`, `lv_draw_line`, `lv_draw_img`, `lv_draw_label`, `lv_draw_polygon`, `lv_draw_triangle`; canvas operations for direct pixel manipulation.

### Events
`lv_obj_add_event_cb`, `lv_obj_remove_event_cb`, `lv_event_send`, `lv_event_get_code/target/param/key`

### File System
`lv_fs_open/close/read/write/seek/tell`, `lv_fs_dir_open/read/close`

### Timer
`lv_timer_create/del/set_period/set_repeat_count/pause/resume/ready/reset`

### QR Code
`lv_qrcode_create`, `lv_qrcode_update`, `lv_qrcode_delete`

### Fonts Available
`lv_font_en_XS`, `lv_font_en_XXS`, `lv_font_en_L`, `lv_font_en_STD`, `lv_font_en_bold_STD`, `lv_font_en_bold_XL`, `lv_font_en_bold_XXL`

> **Note:** The LVGL API appears to be the internal C API exposed as-is. Whether all functions are directly callable from Lua depends on the registration bindings. The `lvgl_mt_ROTable` and `lvgllib_ROTable` suggest a read-only metatable binding. The runtime probe script (`test-api.lua`) will clarify exactly which are exposed.

---

## Script Entry Points

Tool scripts in `SCRIPTS/TOOLS/` must return a table with:

```lua
return {
  init = function() end,        -- Called once on load
  run = function(event, touchState) end,  -- Called per frame
  -- Optional:
  background = function() end,  -- Called in background (if registered)
}
```

`run()` return values:
- `0` — continue running
- `2` — exit script (return to menu)

---

## Runtime API Probe

A probe script has been installed at `/sdcard/AX12LUA/SCRIPTS/TOOLS/test-api.lua`.
Run it from the AX12's **Tools** menu. Results will be written to `/sdcard/AX12LUA/api-probe-results.txt` and will provide the definitive list of every symbol available at runtime, including values for all numeric constants.
