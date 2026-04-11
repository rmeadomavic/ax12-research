# RadioMaster AX12 Device Tree Analysis

Device tree source: `~/ax12-research/device-tree/ax12.dts` (6601 lines, dumped from `/proc/device-tree`)

## SoC Summary

- **Model**: MT8788 (device tree root `model = "MT8788"`)
- **Compatible**: `mediatek,mt6771` (MT8788 is a tablet variant of the MT6771/Helio P60 family)
- **CPU**: 8-core big.LITTLE ARMv8
  - Cluster 0 (cores 0-3): Cortex-A53 (LITTLE), CPU part 0xd03
  - Cluster 1 (cores 4-7): Cortex-A73 (big), CPU part 0xd09
- **GPU**: ARM Mali-Bifrost @ `0x13040000` (compatible: `arm,mali-midgard`, `arm,mali-bifrost`)
- **PMIC**: MediaTek MT6358 (gauge node) + Richtek MT6370 PMU (sub-PMIC for charger, LED, flash, DSV)

---

## UART Controllers

| Node | Address | Compatible | Status | Notes |
|------|---------|------------|--------|-------|
| `serial@11002000` | `0x11002000` | `mediatek,mt6577-uart` | **okay** | UART0 - primary debug/console UART. Has DMA, pinctrl for RX/TX. Maps to `/dev/ttyS0` |
| `serial@11003000` | `0x11003000` | `mediatek,mt6577-uart` | (default) | UART1 - Has DMA. Maps to `/dev/ttyS1` |
| `serial@11004000` | `0x11004000` | `mediatek,mt6577-uart` | (default) | UART2 - Has DMA. Maps to `/dev/ttyS2` |
| `md_uart0@80010000` | `0x80010000` | `mediatek,md_uart0` | - | Modem UART 0 (internal to MD subsystem) |
| `md_uart1@80330000` | `0x80330000` | `mediatek,md_uart1` | - | Modem UART 1 (internal to MD subsystem) |
| `md_uart2@80340000` | `0x80340000` | `mediatek,md_uart2` | - | Modem UART 2 (internal to MD subsystem) |
| `idc_suart@80207000` | `0x80207000` | `mediatek,idc_suart` | - | Modem IDC SUART |
| `scp_uart@105c9000` | `0x105c9000` | `mediatek,scp_uart` | - | SCP co-processor UART |
| `scp_uart1@105ce000` | `0x105ce000` | `mediatek,scp_uart1` | - | SCP co-processor UART 1 |

**RC-relevant**: UART0 (`ttyS0`) and UART1 (`ttyS1`) are the most likely candidates for communication with ELRS/gimbal modules. Both are accessible at `/dev/ttyS0` and `/dev/ttyS1` with world-rwx permissions.

---

## SPI Buses

| Node | Address | Compatible | Attached Devices | Notes |
|------|---------|------------|-----------------|-------|
| `spi@1100a000` | `0x1100a000` | `mediatek,mt6771-spi` | `ethernet_dm9051@1` (DM9051 Ethernet, **disabled**); `fingerprint@0` (Goodix, **disabled**) | SPI0 - Both sub-devices disabled in DT |
| `spi@11010000` | `0x11010000` | `mediatek,mt6771-spi` | `spi1_plat_drv@0` (`mediatek,mt8788_spi1_plat_drv`, **okay**, 20 MHz max) | SPI1 - Platform driver, likely used for RadioMaster-specific communication |
| `spi@11012000` | `0x11012000` | `mediatek,mt6771-spi` | (none) | SPI2 - No attached devices |
| `spi@11013000` | `0x11013000` | `mediatek,mt6771-spi` | (none) | SPI3 - No attached devices |
| `spi@11018000` | `0x11018000` | `mediatek,mt6771-spi` | (none) | SPI4 - No attached devices |
| `spi@11019000` | `0x11019000` | `mediatek,mt6771-spi` | (none) | SPI5 - No attached devices |

SCP co-processor SPI buses:
- `scp_spi0@105cf000`, `scp_spi1@105d0000`, `scp_spi2@105d1000`

Sysfs reports one active SPI device: `spi32765.0`

**RC-relevant**: SPI1 with the `mt8788_spi1_plat_drv` is the most interesting -- this is a custom platform SPI driver likely used for ELRS RF module communication. The `nm_miscdev` node (New-Mobi misc driver) also references SPI1 pins in its pinctrl names.

---

## I2C Buses

All I2C controllers are compatible with `mediatek,mt6771-i2c`. Clock divider is 5 for all.

### I2C Bus 0 (i2c@11007000) - Touch
- **Address**: `0x11007000`
- **Clock frequency**: 200 kHz (0x30d40)
- **Devices**:
  - `cap_touch@40` (addr 0x40) - Capacitive touch controller

### I2C Bus 1 (i2c@11011000) - Sensors
- **Address**: `0x11011000`
- **Clock frequency**: 200 kHz
- **Devices**:
  - `msensor@0c` (addr 0x0C) - Magnetic sensor (compass)
  - `icm42607_a@10` (addr 0x10) - ICM-42607 accelerometer (direction=3)
  - `icm42607_g@11` (addr 0x11) - ICM-42607 gyroscope (direction=7)
  - `nm_i2c1@01` (addr 0x01) - New-Mobi I2C demo driver
  - `gsensor@68` (addr 0x68) - G-sensor (generic, likely fallback)
  - `gyro@69` (addr 0x69) - Gyro (generic, likely fallback)

### I2C Bus 2 (i2c@11009000) - Camera (Main + Sub)
- **Address**: `0x11009000`
- **Clock frequency**: 200 kHz
- **Devices**:
  - `camera_main@36` (addr 0x36) - Main camera sensor
  - `camera_main_af@0c` (addr 0x0C) - Main camera autofocus
  - `camera_main_eeprom@50` (addr 0x50) - Main camera EEPROM
  - `camera_sub@10` (addr 0x10) - Sub (front) camera sensor
  - `camera_sub_af@15` (addr 0x15) - Sub camera autofocus
  - `camera_sub_eeprom@54` (addr 0x54) - Sub camera EEPROM
  - `ccu_sensor_i2c_main_hw@33` (addr 0x33) - CCU sensor bridge (main)
  - `ccu_sensor_i2c_sub_hw@43` (addr 0x43) - CCU sensor bridge (sub)

### I2C Bus 3 (i2c@1100f000) - NFC / Ambient Light
- **Address**: `0x1100f000`
- **Clock frequency**: 400 kHz (0x61a80)
- **Devices**:
  - `nfc@08` (addr 0x08) - NFC controller
  - `alsps@1e` (addr 0x1E) - Ambient light / proximity sensor (interrupt on EINT94)

### I2C Bus 4 (i2c@11008000) - Camera (Secondary)
- **Address**: `0x11008000`
- **Clock frequency**: 200 kHz
- **Devices**:
  - `camera_main_two@38` (addr 0x38) - Second main camera
  - `camera_main_two_af@0e` (addr 0x0E) - Second main camera AF
  - `camera_main_two_eeprom@52` (addr 0x52) - Second main camera EEPROM
  - `ccu_sensor_i2c_main2_hw@11` (addr 0x11) - CCU bridge
  - `ccu_sensor_i2c_main3_hw@12` (addr 0x12) - CCU bridge

### I2C Bus 5 (i2c@11017000) - USB Type-C / Sub-PMIC
- **Address**: `0x11017000`
- **Clock frequency**: 3.4 MHz (0x33e140) - Fast mode plus
- **Devices**:
  - `usb_type_c@4e` (addr 0x4E) - USB Type-C controller
  - `subpmic_pmu@34` (addr 0x34) - MT6370 sub-PMIC PMU

### I2C Bus 6 (i2c@11005000) - Charger / Audio Amp
- **Address**: `0x11005000`
- **Clock frequency**: 400 kHz
- **Devices**:
  - `rt9465@4b` (addr 0x4B) - Richtek RT9465 secondary charger
  - `slave_charger@4b` (addr 0x4B) - MediaTek slave charger driver (same physical device as rt9465)
  - `speaker_amp@34` (addr 0x34) - Speaker amplifier

### I2C Bus 7 (i2c@1101a000) - Empty
- **Address**: `0x1101a000`
- **Clock frequency**: 400 kHz
- No attached devices in DT

### I2C Bus 8 (i2c@1101b000) - Empty
- **Address**: `0x1101b000`
- **Clock frequency**: 400 kHz
- No attached devices in DT

### I2C Bus 9 (i2c@11014000) - Empty
- **Address**: `0x11014000`
- **Clock frequency**: 400 kHz
- No attached devices in DT

### I2C Bus 10 (i2c@11015000) - Empty
- **Address**: `0x11015000`
- **Clock frequency**: 400 kHz
- No attached devices in DT

### I2C Bus 11 (i2c@11016000) - Empty
- **Address**: `0x11016000`
- **Clock frequency**: 400 kHz
- No attached devices in DT

Additional I2C buses:
- `i2c6@11005000` (same as bus 6, `mediatek,i2c6` compatible alias)
- `md_i2c@80100000` - Modem subsystem I2C
- `scp_i2c0@105c5000`, `scp_i2c1@105c6000`, `scp_i2c2@105c7000` - SCP co-processor I2C

**RC-relevant**: I2C Bus 1 (sensors - ICM-42607 IMU) is directly relevant to the RC controller for gimbal/head-tracking. I2C Bus 0 (cap_touch) is the stick/button touch interface. The New-Mobi I2C demo driver on bus 1 and `nm_miscdev` are RadioMaster/New-Mobi custom drivers.

---

## GPIO Controller

- **Node**: `gpio@10005000`
- **Compatible**: `mediatek,gpio`
- Contains a large `gpio_init_default` table defining initial states for GPIOs 0x00 through 0xBF (192 GPIOs)
- No `/sys/class/gpio/` sysfs interface exported (common on MediaTek Android devices)

### GPIO Usage Mapping
From the `gpio` node:
- GPIO 0x13 (19): NFC reset
- GPIO 0x14 (20): NFC IRQ
- GPIO 0x23-0x28: SIM card signals (SIM1/SIM2 SIO, SCLK, SRST)
- GPIO 0x47 (71): FDD band detect
- GPIO 0x48 (72): HDMI power / DM9051 power
- GPIO 0x49 (73): DM9051 reset
- GPIO 0x57 (87): HDMI reset
- GPIO 0xB1 (177): USB switch select
- GPIO 0xB3 (179): RT9465 charger enable

---

## ADC Channels (AUXADC)

- **Node**: `auxadc@11001000`
- **Compatible**: `mediatek,auxadc`
- **Channels**:
  - Channel 0: Temperature sensor 0
  - Channel 1: Temperature sensor 1
  - Channel 2: FDD RF params dynamic custom channel

Accessible via `/dev/mtk-adc-cali` and `/dev/MT_pmic_adc_cali`

---

## Display / Touchscreen

### Display Pipeline (MIPI DSI)
- `dsi0@14014000` - MIPI DSI0 output controller
- `disp_ovl0@14008000` - Display overlay 0
- `disp_ovl0_2l@14009000` - Display overlay 0 (2-layer)
- `disp_ovl1_2l@1400a000` - Display overlay 1 (2-layer)
- `disp_rdma0@1400b000` - Display RDMA 0
- `disp_rdma1@1400c000` - Display RDMA 1
- `disp_wdma0@1400d000` - Display WDMA 0
- `disp_color0@1400e000` - Color processing
- `disp_ccorr0@1400f000` - Color correction
- `disp_aal0@14010000` - Ambient-light adaptive luma (AAL)
- `disp_gamma0@14011000` - Gamma correction
- `disp_dither0@14012000` - Dithering
- `disp_rsz@1401a000` - Display resizer
- `disp_split@14013000` - Display split
- `disp_mutex@14016000` - Display mutex/sync
- `disp_pwm0@1100e000` - Display PWM (backlight control)
- `dpi0@14015000` - DPI (parallel) output
- `dbi@1401d000` - DBI output
- `mipi_tx0@11e50000` - MIPI TX PHY

### Framebuffer
- `mtkfb@0` - MediaTek framebuffer (compatible: `mediatek,mtkfb`)

### Backlight
- MT6370 BLED controller (4-channel, PWM, max brightness 512)
- LCD backlight LED mode = 5 (MT6370 BLED)
- `/sys/class/leds/lcd-backlight/max_brightness` = 255

### Touchscreen
- **Node**: `touch`
- **Compatible**: `mediatek,mt6771-touch`
- **Resolution**: 720 x 1280 (0x2D0 x 0x500)
- **Max touch points**: 5
- **Power supply**: `vtouch-supply`
- **Interrupt**: EINT8 (mtk-eint 8, `TOUCH_PANEL-eint`)
- **Input device**: `/dev/input/event2` (name: `mtk-tpd`)
- **Cap touch on I2C Bus 0**: `cap_touch@40` (address 0x40)

### HDMI Output
- `ite166121_hdmi@0` - ITE IT66121 HDMI bridge IC
  - Power GPIO: 72, Reset GPIO: 87
  - I2C port: 1 (from `mediatek,hdmi_bridgeic_port`)
  - Supplies: VCN18, VCN33, VRF12

---

## MT6370 Sub-PMIC

The MT6370 is a major sub-PMIC connected via I2C bus 5 (addr 0x34) with interrupt on EINT10. It provides:

- **Charger**: Primary charger controller (CV=4.2V, ICHG=2A, IEOC=150mA, MIVR=4.4V)
- **DSV**: Display supply voltage (boost + positive/negative rails for OLED/LCD)
- **BLED**: Backlight LED driver (4 channels, PWM mode)
- **FLED1/FLED2**: Flash LED drivers
- **RGB LED**: 4-channel ISINK LED driver (mapped to `mt6370_pmu_led1` through `mt6370_pmu_led4`)
- **LDO**: Auxiliary LDO (used for IRTX)

---

## Other Peripherals

### Connectivity
- **WiFi**: `wifi@180f0000` (MediaTek integrated, `mediatek,wifi`) + `consys@18070000` (combo connectivity)
- **Bluetooth**: Integrated via WMT (Wireless Management Technology) combo chip
  - `/dev/stpbt` - BT character device
  - BTIF @ `0x1100c000` with DMA
- **GPS**: Integrated via WMT, `/dev/stpgps`
- **FM Radio**: Integrated, `/dev/fm` (major 213)

### DM9051 SPI Ethernet
- **DT node**: `dm9051` with GPIO reset (pin 73), power (pin 72), interrupt on EINT7
- **SPI sub-device**: `ethernet_dm9051@1` on SPI0 (`davicom,dm9051`, 20 MHz, **status=disabled**)
- This is a Davicom DM9051 SPI-to-Ethernet controller. Disabled in this firmware.

### NFC
- **DT node**: `nfc` (compatible: `mediatek,nfc-gpio-v2`)
- **I2C device**: `nfc@08` on I2C bus 3 (address 0x08)
- **GPIO**: IRQ=20, Reset=19

### Fingerprint
- **DT node**: `fingerprint` (compatible: `mediatek,goodix-fp`)
- **SPI device**: `fingerprint@0` on SPI0 (Goodix, 8 MHz, **status=disabled**)

### Cameras
- Camera ISP system at `0x1a000000` (camsys)
- 8 SENINF (sensor interface) blocks
- 6 CAMSV (camera slave) blocks
- CCU (Camera Control Unit) @ `0x1a0a0000`
- IPU (Image Processing Unit) cores 0 and 1 at `0x19100000` and `0x19200000`
- Image sensors on I2C buses 2 and 4

### IR Transmitter
- `irtx@1100d000` (compatible: `mediatek,irtx`)
- `irtx_pwm` PWM output

### Keypad
- `kp@10010000` - MediaTek keypad controller
  - Power key mapped (key code 0x74 = 116 = KEY_POWER)
  - Volume keys in init map (0x72=KEY_VOLUMEUP, 0x73=KEY_VOLUMEDOWN, 0x9e=KEY_BACK, 0x8b=KEY_MENU)
  - Input device: `/dev/input/event1` (name: `mtk-kpd`)

### Audio
- Audio subsystem @ `0x11220000` with SRAM @ `0x11221000`
- BTCVSD (Bluetooth CVSD codec) @ `0x10001000`
- Speaker amplifier on I2C bus 6 (address 0x34)
- MT6358 PMIC audio codec (`mt_soc_codec_63xx`)
- Headset jack detection: `accdet` (`/dev/accdet`, input: `/dev/input/event0` name `ACCDET`)

### USB
- USB 3.0 controller @ `0x11200000` (compatible: `mediatek,usb3`, xHCI)
- USB Type-C controller on I2C bus 5 (address 0x4E)
- USB C pinctrl with re-driver control (C1/C2 pins) and USB3 switch

### Storage
- eMMC (MSDC0): `msdc@11230000` - 8-bit, HS400, non-removable, bootable
- SD card (MSDC1): `msdc@11240000` - 4-bit, SDR104, removable (CD on GPIO 99)

### PWM
- `pwm@11006000` - 4 PWM channels (PWM1-PWM4)

### Thermal
- `therm_ctrl@1100b000` - Thermal controller
- EEM (Extreme Energy Management) @ `0x1100b000`

### SCP (System Control Processor)
- `scp@10500000` - ARM co-processor with its own I2C, SPI, UART, GPIO, timer, DMA

### Modem
- Full cellular modem subsystem (MD1) with CCIF, CLDMA interfaces
- SIM card support (SIM1, SIM2 GPIOs defined)
- LTE support (opt_lte_support=1, opt_ps1_rat=Lf/Lt/W/G)

---

## New-Mobi / RadioMaster Custom Hardware

These nodes are specific to the AX12 hardware (not generic MediaTek reference design):

| Node | Description |
|------|-------------|
| `nm_miscdev` | New-Mobi misc device driver (`new-mobi,mt8788-misc_drv`). Controls GPIO 5, 85, 86 and SPI1 pins. Has interrupt on EINT85. |
| `nm_i2c1@01` | New-Mobi I2C demo driver on I2C bus 1 (addr 0x01) |
| `spi1_plat_drv@0` | MediaTek MT8788 SPI1 platform driver (`mediatek,mt8788_spi1_plat_drv`, 20 MHz) |
| `mse` | Interrupt on EINT5 -- possibly RC-related input/encoder |

### RC-Relevance Summary

**Directly relevant to RC radio functionality**:
- SPI1 platform driver (likely ELRS RF module interface)
- nm_miscdev (New-Mobi hardware control GPIOs/SPI1)
- I2C bus 1 sensors (ICM-42607 IMU for head-tracking/gimbal)
- I2C bus 0 cap_touch (stick position sensing)
- UART0/UART1 (potential gimbal/ELRS serial interfaces)
- PWM channels (potential servo/signal output)
- nm_i2c1 demo driver

**Generic phone/tablet hardware (not RC-specific)**:
- Camera subsystem (2+ cameras, ISP, VPU)
- NFC controller
- Fingerprint sensor (disabled)
- Cellular modem (LTE)
- DM9051 Ethernet (disabled)
- HDMI bridge (ITE IT66121)
- SIM card interfaces
- FM Radio
