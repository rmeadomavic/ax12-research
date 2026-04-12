# AX12 Peripheral Exploration

Catalog of onboard hardware beyond the primary UMBUS/ttyS0 link.
Status indicates whether the peripheral is actively used, dormant (hardware
present but not exercised), or dead (wired but no driver/firmware).

---

## 1. ICM-42607 IMU (6-Axis)

| Property | Value |
|----------|-------|
| Status | **Active** — high-frequency polling (61 588 interrupts on IRQ 236) |
| Chip | InvenSense/TDK ICM-42607 |
| Bus | I2C bus 1 (`i2c@11011000`), 200 kHz, push-pull |
| Accel node | `icm42607_a@10`, compatible `icm42607,gsensor_a`, direction 0x03 |
| Gyro node | `icm42607_g@11`, compatible `icm42607,gyro_g`, direction 0x07 |
| Fallback nodes | `gsensor@68` (`mediatek,gsensor`), `gyro@69` (`mediatek,gyro`) |
| Batch support | Accel yes, gyro no |
| FIR filter | Accel 16 taps, gyro disabled |
| Power | Always-on (`power_id = 0xFFFF`) |
| DT lines | `device-tree/ax12.dts:1887-1950` |

### Software interface

| Class / Method | Purpose |
|----------------|---------|
| `QSensorControl` | Primary sensor API |
| `reqOscData()` | Request raw waveform data |
| `oscDataRxEnd(QList<int>)` | Signal: data batch received |
| `fillLogToWaveView()` | Render waveform on screen |
| `setLineGroup(int)` | Select display channel group |
| `setAttitude(double, double, double)` | Set pitch/roll/yaw |
| `attitudeChanged(...)` | Signal: orientation update |

The app already consumes IMU data for an oscilloscope view and AHRS
(Attitude & Heading Reference System) display.  Head-tracking and
tilt-control are the obvious extension points.

---

## 2. Magnetometer

| Property | Value |
|----------|-------|
| Status | **Active** — shares IRQ 236 polling with IMU |
| Chip | Unknown (likely AKM896x or Yamaha YAS53x) |
| Bus | I2C bus 1, address 0x0C |
| DT node | `msensor@0c`, compatible `mediatek,msensor` |
| Direction | 0x01 |
| FIR filter | 16 taps |
| DT lines | `device-tree/ax12.dts:1872-1885` |

Combined with the ICM-42607 this gives 9-axis orientation.  The app
exposes compass heading through `QmlPack_TelemetryItem` for the GCS map
display.

---

## 3. SPI1 — Secondary MCU/RF Bus

| Property | Value |
|----------|-------|
| Status | **Active** — only registered SPI device on the system |
| Controller | `spi@11010000`, compatible `mediatek,mt6771-spi` |
| Child device | `spi1_plat_drv@0`, compatible `mediatek,mt8788_spi1_plat_drv` |
| Max frequency | 20 MHz |
| Netlink event | 30 (`0x1e`) — sends kernel→userspace notifications |
| IRQ | 124 (0x7c), level-triggered |
| Sysfs | `/sys/bus/spi/devices/spi32765.0` |
| DT lines | `device-tree/ax12.dts:3021-3040` |

### Pin mapping (controlled by nm_miscdev)

| Signal | Pinmux | Physical pin | Default |
|--------|--------|-------------|---------|
| CLK | 0xa401 | 164 | Output low |
| CS | 0xa201 | 162 | Output low |
| MISO | 0xa101 | 161 | Pull-up input |
| MOSI | 0xa301 | 163 | Output low |

SPI1 runs at 1000x the bandwidth of the UMBUS link (20 MHz vs 921.6 kbps).
Likely purpose: ELRS RF module direct communication, firmware flashing,
or high-speed telemetry streaming alongside the UART control channel.

---

## 4. nm_miscdev — New-Mobi Custom Driver

| Property | Value |
|----------|-------|
| Status | **Active** |
| Compatible | `new-mobi,mt8788-misc_drv` |
| Interrupt | EINT85 (external interrupt 85), level-triggered |
| DT lines | `device-tree/ax12.dts:6582-6600` |

### Pinctrl states (10 total)

| Index | Name | Pins | Purpose |
|-------|------|------|---------|
| 0 | `pin_default` | — | Initialization |
| 1 | `pin5_pwmc` | GPIO 5 | PWM output mode |
| 2 | `pin5_out0` | GPIO 5 | GPIO output low |
| 3 | `pin85_input` | GPIO 85 | Input with pull-up (EINT source) |
| 4 | `pin86_out1` | GPIO 86 | Output high |
| 5 | `pin86_out0` | GPIO 86 | Output low |
| 6-9 | `pin_spi1_*` | SPI1 bus | SPI1 MO/MI/CS/CLK |

This driver owns the SPI1 pin mux and three GPIOs.  GPIO 85 is the
interrupt input (MCU data-ready?), GPIO 86 is an output toggle (MCU
reset/boot-mode?), and GPIO 5 can switch between PWM and GPIO modes.

Also on I2C bus 1: `nm_i2c1@01`, compatible `new-mobi,i2c_demo` — a
vendor demo/debug driver at address 0x01.

---

## 5. Bluetooth

| Property | Value |
|----------|-------|
| Status | **Functional** — driver loaded, device nodes present |
| Chip | MT6631 combo (integrated in MT8788) |
| Driver | `bt_drv` (24 KB), depends on `wmt_drv` (1.1 MB) |
| Device nodes | `/dev/stpbt` (192,0), `/dev/btif` (224,0) |
| USB gadget | `/dev/ttyGS2` (223,2) — BT over USB |
| Thermal | `thermal_zone4` (mtktswmt) — active |
| DT lines | `device-tree/ax12.dts:199-213` (consys), BTIF at `0x1100c000` |

### Software

| Class | Role |
|-------|------|
| `QCommUsart` | UART transport (ttyS0) |
| `QCommTcp` | TCP transport (simulator) |
| USB-HID | PC connection transport |

Bluetooth is not listed as a transport in the native lib architecture
diagram, but the full BT stack is running.  Potential uses: wireless
trainer link, BT gamepad output to simulators, BLE sensor streaming.

---

## 6. USB HID Gadget

| Property | Value |
|----------|-------|
| Status | **Functional** — sysfs class `hidg` registered |
| Controller | USB 3.0 at `usb3@11200000` (xHCI + musb-hdrc) |
| Type-C | `usb_type_c@4e` on I2C bus 5, dual-role OTG |
| Sysfs classes | `hidg`, `udc`, `dual_role_usb`, `android_usb` |

### Software

| Method | Purpose |
|--------|---------|
| `usbhidPackReceived()` | Receive HID packets → UMBUS router |
| `rcJoystickMap(int*, int*, int)` | Map stick axes to joystick channels |

This is how the AX12 works as a USB joystick for simulators.  HID
descriptors are likely defined in the native library or configured via
sysfs at runtime (not in device tree).

---

## 7. LEDs

| Property | Value |
|----------|-------|
| Status | **Functional** — controllable via sysfs |
| Controller | MT6370 sub-PMIC (I2C bus 5, addr 0x34) |

### LED channels

| Sysfs name | Type | Mode | Purpose |
|------------|------|------|---------|
| `red` | ISINK | CC (led_mode=3) | RGB indicator |
| `green` | ISINK | CC (led_mode=3) | RGB indicator |
| `blue` | ISINK | CC (led_mode=3) | RGB indicator |
| `lcd-backlight` | BLED | PWM (led_mode=5) | Display, max 255 |
| `mt6370_pmu_led1` | ISINK | CC | PMU channel 1 |
| `mt6370_pmu_led2` | ISINK | CC | PMU channel 2 |
| `mt6370_pmu_led3` | ISINK | CC | PMU channel 3 |
| `mt6370_pmu_led4` | ISINK | CC | PMU channel 4 |

Control: `echo N > /sys/class/leds/<name>/brightness` (0-255).

BLED backlight: 4-channel, PWM mode, 512 levels internally, OCP/OVP
protection, deglitch filtering.

DT lines: `device-tree/ax12.dts:53-114` (generic), `716-765` (MT6370).

---

## 8. Vibrator / Haptics

| Property | Value |
|----------|-------|
| Status | **Present** — DT configured, `timed_output` class registered |
| DT node | `vibrator@0`, compatible `mediatek,vibrator` |
| Power | LDO_VIBR regulator (MT6358 PMIC) |
| Settings | limit=9, timer=25ms, vol=9 |
| Control | `/sys/class/timed_output/vibrator/enable` (write ms duration) |
| DT lines | `device-tree/ax12.dts:116-123` |

---

## 9. PWM

| Property | Value |
|----------|-------|
| Status | **Present** — 4 channels + display PWM + IR TX |
| Controller | `pwm@11006000`, compatible `mediatek,pwm` |
| Channels | PWM1-PWM4, each with dedicated clock |
| IRQ | 75 (0x4b) |
| Sysfs | `/sys/class/pwm/pwmchip0/pwm{0-3}/` |

### Additional PWM consumers

| Consumer | Address | Purpose |
|----------|---------|---------|
| `disp_pwm0` | `0x1100e000` | LCD backlight (feeds MT6370 BLED) |
| `irtx_pwm` | — | IR transmitter, channel 0, non-inverted |
| `nm_miscdev` | GPIO 5 | `pin5_pwmc` state — unknown load |

The IR transmitter is interesting — the AX12 can emit IR signals.
Could be used for IR-based protocols or remote control of external
devices.

DT lines: `device-tree/ax12.dts:2327-2333`.

---

## 10. AUXADC

| Property | Value |
|----------|-------|
| Status | **Active** |
| Controller | `auxadc@11001000`, compatible `mediatek,auxadc` |
| IRQ | 74 (0x4a), level-triggered |
| Calibration | `/dev/mtk-adc-cali` (244,0), `/dev/MT_pmic_adc_cali` (219,0) |
| DT lines | `device-tree/ax12.dts:2414-2430` |

### Channels

| Channel | DT property | Purpose |
|---------|-------------|---------|
| 0 | `mediatek,temperature0` | Temperature sensor 0 |
| 1 | `mediatek,temperature1` | Temperature sensor 1 |
| 2 | `mediatek,adc_fdd_rf_params_dynamic_custom_ch` | **FDD RF parameter monitoring** |

Channel 2 is a custom MediaTek extension for real-time RF diagnostics —
likely reads TX power, RSSI, VSWR, or temperature-compensated RF metrics
from the ELRS module or combo chip.

---

## 11. ALS / Proximity Sensor

| Property | Value |
|----------|-------|
| Status | **Present** — configured in DT |
| Chip | Unknown (generic `mediatek,alsps` driver) |
| Bus | I2C bus 3, address 0x1E (fallbacks: 0x1C, 0x1D) |
| DT lines | `device-tree/ax12.dts:2047-2095` |

### ALS (Ambient Light Sensor)

- Mode: polling
- 16-level lux→brightness mapping curve
- Range: 5 lux (dim indoor) to 20 000 lux (direct sun)
- Brightness output: 40 (minimum) to 10 240 (maximum)
- Tuned for outdoor flying: aggressive ramp above 5 000 lux

### Proximity Sensor

- Mode: interrupt-driven (not polled)
- Threshold: 224 (both low and high — binary near/far)
- Could trigger screen on/off or proximity-aware UI

---

## 12. NFC

| Property | Value |
|----------|-------|
| Status | **Dead** — wired but no driver loaded, no device node |
| DT node | `nfc@08`, compatible `mediatek,nfc`, status "okay" |
| Bus | I2C bus 3, address 0x08 |
| GPIOs | 19 (reset), 20 (interrupt) |
| DT lines | `device-tree/ax12.dts:2063-2069` |

Hardware is present on the PCB and enabled in the device tree, but no
kernel module or Android NFC stack appears active.  Would require loading
a driver to test.

---

## 13. FM Radio

| Property | Value |
|----------|-------|
| Status | **Dormant** — device node exists, driver not loaded |
| Chip | MT6631 combo (shared with WiFi/BT/GPS) |
| Device node | `/dev/fm` (213,0), owner: media |
| Driver | `fmradio_drv` (172 KB) — present in kernel but 0 users |
| Audio paths | `mt_soc_fm_mrgtx_pcm` (TX), `mt_soc_fm_i2s_pcm` (I2S), `mt_soc_fm_i2s_awb_pcm` (AWB) |

The FM radio has full audio routing configured in the device tree (I2S
playback, write-back capture, merge TX).  The driver module exists but
is not loaded.  Could potentially be activated by loading `fmradio_drv`
through the WMT stack.

---

## 14. ttyS1 (UART1)

| Property | Value |
|----------|-------|
| Status | **Unknown** — no data observed at idle |
| Address | `0x11003000`, compatible `mediatek,mt6577-uart` |
| Baud | Observed as 9600 (default?) |
| Permissions | World-accessible (`crwxrwxrwx`) |
| DMA | TX channel 0x02, RX channel 0x03 |
| IRQ | 92 (0x5c) |
| Pinctrl | **None defined** — may not be wired to PCB pads |
| DT lines | `device-tree/ax12.dts:5779-5789` |

No pinctrl mapping suggests this UART may not be physically connected.
Could be a test point on the PCB or reserved for future use.  Worth
probing with a logic analyzer if the board is ever opened.

---

## 15. ttyS2 (UART2)

| Property | Value |
|----------|-------|
| Status | **Unknown** — root-only, never tested |
| Address | `0x11004000`, compatible `mediatek,mt6577-uart` |
| Permissions | Root-only (`crw-------`) |
| DMA | TX channel 0x04, RX channel 0x05 |
| IRQ | 93 (0x5d) |
| Pinctrl | **None defined** |
| DT lines | `device-tree/ax12.dts:5796-5806` |

Root-only permissions suggest a debug/factory UART.  Same "no pinctrl"
situation as ttyS1.

---

## 16. Cellular Modem (CCCI)

| Property | Value |
|----------|-------|
| Status | **Dormant** — full stack in kernel, unused by RadioMaster |
| SoC modem | MT8788 integrated LTE baseband |
| Firmware | `md1img` partition, 100 MB (`mmcblk0p14`) |
| Reserved RAM | ~279 MB across 3 memory blocks |
| Supported RATs | LTE-FDD, LTE-TDD, WCDMA, GSM (`opt_ps1_rat = "Lf/Lt/W/G"`) |
| CCCI controller | `mdcldma@10014000`, 4 IRQs |
| Modem UARTs | `md_uart0-2` at `0x8003x000` (internal to modem) |
| SIM GPIOs | GPIO 0x23-0x28 (SIM1/SIM2 defined) |
| Device nodes | `/dev/ccci_*` (major 225, 226, 249) — FS, IPC, IOCTL, CCB, monitor |
| Modem TTYs | `/dev/ttyC0-C3` (225,3/7/5/6), owner: radio |
| DT lines | `device-tree/ax12.dts:5054-5069` (memory), `5175-5185` (CLDMA), `2656-2670` (config) |

The entire MediaTek cellular modem subsystem is present and configured:
firmware partition, DMA engine, cross-core IPC, SIM card interfaces,
and multi-RAT support.  This is standard MT8788 tablet firmware that
RadioMaster did not strip out.  Almost certainly no cellular antenna is
connected, but the software stack is fully present.  The 279 MB of
reserved RAM is notable — that memory is unavailable to Android even
though the modem is unused.

---

## Exploration Priority

Ranked by likely payoff for understanding or extending the AX12:

| Priority | Peripheral | Rationale |
|----------|-----------|-----------|
| 1 | SPI1 + nm_miscdev | Unknown data path, 20 MHz, likely RF module link — sniffing this could reveal the ELRS control protocol |
| 2 | IMU / Magnetometer | Already active, well-documented chip — could dump raw data, test head tracking |
| 3 | USB HID | Working joystick mode — could characterize HID descriptors for custom sim integration |
| 4 | Bluetooth | Full stack running, untapped — wireless trainer or BLE telemetry |
| 5 | LEDs / Vibrator | Easy sysfs control — quick wins for custom status feedback |
| 6 | AUXADC ch2 | RF parameter monitoring — could reveal real-time link quality metrics |
| 7 | ALS / Proximity | Auto-brightness working, proximity could be useful for screen management |
| 8 | FM Radio | Fun novelty — driver exists, might just work if loaded |
| 9 | IR TX | PWM-based IR transmitter — could emit IR protocols |
| 10 | NFC | Dead without driver work |
| 11 | Cellular modem | Academic interest only, but the wasted 279 MB RAM is worth noting |
| 12 | ttyS1 / ttyS2 | Need PCB access to determine if wired |
