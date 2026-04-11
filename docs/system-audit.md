# RadioMaster AX12 System Hardware Audit

Audit date: 2026-04-12

## System Identity

| Property | Value |
|----------|-------|
| Hardware | MT8788 |
| Platform | MT6771 (ro.board.platform, ro.mediatek.platform) |
| Boot hardware | mt8788 (ro.boot.hardware) |
| Product/Model | tb8788p1_64_bsp |
| Build ID | K908-V2.0-XY8788WA-F-DRDI.3224&6432&12848.P0.66.V2.0-userdebug |
| Android version | 9 (SDK 28) |
| Build type | userdebug (test-keys) |
| Build date | Wed Jan 7 10:41:00 CST 2026 |
| Security patch | 2019-12-05 |
| SELinux | permissive (ro.boot.selinux) |
| Kernel | 4.4.146 (Linux) |
| Base build | noah |
| Boot state | green (verified boot) |
| Serial | 0123456789ABCDEF (placeholder) |
| Brand | MTK |
| Build fingerprint | alps/full_tb8788p1_64_bsp/tb8788p1_64_bsp:9/PPR1.180610.011/csh01071041:userdebug/test-keys |
| Characteristics | tablet |

---

## CPU Information

8-core ARMv8 big.LITTLE SoC at 26 BogoMIPS per core:

| Cores | Part | Type | Revision |
|-------|------|------|----------|
| 0-3 | 0xd03 (Cortex-A53) | LITTLE | rev 4 |
| 4-7 | 0xd09 (Cortex-A73) | big | rev 2 |

Features: fp asimd evtstrm aes pmull sha1 sha2 crc32

---

## Memory

| Metric | Value |
|--------|-------|
| MemTotal | 3,899,372 kB (~3.7 GB) |
| MemFree | 58,692 kB |
| MemAvailable | 1,840,380 kB (~1.75 GB) |
| Buffers | 36,588 kB |
| Cached | 1,795,356 kB |
| SwapCached | 0 kB |
| Active | 2,233,544 kB |
| Inactive | 1,036,432 kB |
| ZRAM swap | 1,048,576 kB (1 GB, /dev/zram0) |

---

## Storage / Partition Map

**eMMC**: `/dev/block/mmcblk0` (61,071,360 blocks = ~58.2 GB)

| Partition | Block Device | Size (KB) | Purpose |
|-----------|-------------|-----------|--------|
| boot_para | mmcblk0p1 | 1,024 | Boot parameters |
| recovery | mmcblk0p2 | 32,768 | Recovery image |
| para | mmcblk0p3 | 512 | Parameters |
| expdb | mmcblk0p4 | 20,480 | Exception DB |
| frp | mmcblk0p5 | 1,024 | Factory reset protection |
| nvcfg | mmcblk0p6 | 32,768 | NV config |
| nvdata | mmcblk0p7 | 65,536 | NV data |
| metadata | mmcblk0p8 | 32,768 | Metadata |
| protect1 | mmcblk0p9 | 8,192 | Protected storage 1 |
| protect2 | mmcblk0p10 | 9,696 | Protected storage 2 |
| seccfg | mmcblk0p11 | 8,192 | Security config |
| sec1 | mmcblk0p12 | 2,048 | Security 1 |
| proinfo | mmcblk0p13 | 3,072 | Product info |
| md1img | mmcblk0p14 | 102,400 | Modem firmware |
| spmfw | mmcblk0p15 | 1,024 | SPM firmware |
| scp1 | mmcblk0p16 | 6,144 | SCP firmware 1 |
| scp2 | mmcblk0p17 | 6,144 | SCP firmware 2 |
| sspm_1 | mmcblk0p18 | 1,024 | SSPM firmware 1 |
| sspm_2 | mmcblk0p19 | 1,024 | SSPM firmware 2 |
| cam_vpu1 | mmcblk0p20 | 15,360 | Camera VPU 1 |
| cam_vpu2 | mmcblk0p21 | 15,360 | Camera VPU 2 |
| cam_vpu3 | mmcblk0p22 | 15,360 | Camera VPU 3 |
| gz1 | mmcblk0p23 | 16,384 | GenieZone TEE 1 |
| gz2 | mmcblk0p24 | 16,384 | GenieZone TEE 2 |
| nvram | mmcblk0p25 | 65,536 | NVRAM |
| lk | mmcblk0p26 | 1,024 | Bootloader (LK) |
| lk2 | mmcblk0p27 | 1,024 | Bootloader backup |
| boot | mmcblk0p28 | 32,768 | Boot image |
| logo | mmcblk0p29 | 8,192 | Boot logo |
| dtbo | mmcblk0p30 | 8,192 | Device tree blob overlay |
| tee1 | mmcblk0p31 | 5,120 | TEE 1 |
| tee2 | mmcblk0p32 | 12,288 | TEE 2 |
| vendor | mmcblk0p33 | 876,544 | Vendor partition (~856 MB) |
| system | mmcblk0p34 | 3,145,728 | System partition (~3 GB) |
| cache | mmcblk0p35 | 442,368 | Cache (~432 MB) |
| userdata | mmcblk0p36 | 55,997,408 | User data (~53.4 GB) |
| otp | mmcblk0p37 | 44,032 | OTP/calibration |
| flashinfo | mmcblk0p38 | 16,384 | Flash info |

Additional block devices:
- `mmcblk0rpmb` (16,384 KB) - Replay Protected Memory Block
- `mmcblk0boot0` (4,096 KB) - eMMC boot partition 0
- `mmcblk0boot1` (4,096 KB) - eMMC boot partition 1
- `dm-0` (3,096,620 KB) - dm-verity system
- `dm-1` (862,824 KB) - dm-verity vendor
- `dm-2` (55,997,408 KB) - dm-crypt userdata

---

## Kernel Modules

| Module | Size | Used By | Notes |
|--------|------|---------|-------|
| wlan_drv_gen3 | 4,874,240 | 0 | WiFi driver (Gen3 MT76xx) |
| wmt_chrdev_wifi | 20,480 | 1 (by wlan_drv_gen3) | WMT WiFi char device |
| gps_drv | 61,440 | 0 | GPS driver |
| fmradio_drv | 172,032 | 0 | FM radio driver |
| bt_drv | 24,576 | 1 | Bluetooth driver |
| wmt_drv | 1,167,360 | 7 | WMT combo connectivity core (used by all above) |
| fpsgo | 16,384 | 0 | Frame-rate aware Power/GPU Optimization |

All modules are out-of-tree (O flag). fpsgo has additional PO flag (proprietary out-of-tree).

---

## Device Nodes (Selected)

### Serial/UART
| Device | Major,Minor | Owner | Permissions | Notes |
|--------|-------------|-------|-------------|-------|
| `/dev/ttyS0` | 4,64 | root | crwxrwxrwx | UART0 - world accessible |
| `/dev/ttyS1` | 4,65 | root | crwxrwxrwx | UART1 - world accessible |
| `/dev/ttyS2` | 4,66 | root | crw------- | UART2 - root only |
| `/dev/ttyGS0` | 223,0 | system:radio | crw-rw---- | USB gadget serial 0 |
| `/dev/ttyGS1` | 223,1 | system:radio | crw-rw---- | USB gadget serial 1 |
| `/dev/ttyGS2` | 223,2 | bluetooth | crw-rw---- | USB gadget serial 2 (BT) |
| `/dev/ttyGS3` | 223,3 | system:radio | crw-rw---- | USB gadget serial 3 |
| `/dev/ttyC0-C3` | 225,3/7/5/6 | radio | crw-rw---- | CCCI modem TTYs |

### Camera/Media
| Device | Major,Minor | Notes |
|--------|-------------|-------|
| `/dev/kd_camera_hw` | 232,0 | Camera hardware |
| `/dev/camera-isp` | 239,0 | ISP driver |
| `/dev/camera-dip` | 240,0 | DIP driver |
| `/dev/camera-fdvt` | 233,0 | Face detection |
| `/dev/CAM_CAL_DRV` | 230,0 | Camera calibration |
| `/dev/MAINAF` | 222,0 | Main AF motor |
| `/dev/MAIN2AF` | 220,0 | Second AF motor |
| `/dev/SUBAF` | 221,0 | Sub AF motor |
| `/dev/flashlight` | 229,0 | Flash LED |
| `/dev/ccu` | 227,0 | Camera control unit |
| `/dev/vpu` | 228,0 | Vision processing unit |

### Connectivity
| Device | Major,Minor | Owner | Notes |
|--------|-------------|-------|-------|
| `/dev/stpwmt` | 190,0 | system | WMT combo core |
| `/dev/stpbt` | 192,0 | bluetooth | Bluetooth |
| `/dev/stpgps` | 191,0 | gps | GPS |
| `/dev/wmtWifi` | 153,0 | wifi | WiFi |
| `/dev/wmtdetect` | 154,0 | system | WMT detect |
| `/dev/fm` | 213,0 | media | FM radio |
| `/dev/gps_emi` | 212,0 | root | GPS EMI |

### Modem (CCCI)
Many `/dev/ccci_*` devices (major 225, 226, 249) for cellular modem communication: FS, IPC, IOCTL, raw data channels, CCB, monitoring.

### Other Notable Devices
| Device | Major,Minor | Notes |
|--------|-------------|-------|
| `/dev/mali0` | 10,59 | GPU |
| `/dev/ion` | 10,62 | ION memory allocator |
| `/dev/touch` | 10,23 | Touch input |
| `/dev/mtk-kpd` | 10,52 | Keypad |
| `/dev/accdet` | 243,0 | Headset jack detect |
| `/dev/btif` | 224,0 | BT interface |
| `/dev/hdmitx` | 216,0 | HDMI transmitter |
| `/dev/mtk_cmdq` | 250,0 | Command queue |
| `/dev/mtk_disp_mgr` | 242,0 | Display manager |
| `/dev/charger_ftm` | 215,0 | Charger factory test |
| `/dev/pmic_ftm` | 246,0 | PMIC factory test |
| `/dev/mtk-adc-cali` | 244,0 | ADC calibration |
| `/dev/MT_pmic_adc_cali` | 219,0 | PMIC ADC calibration |
| `/dev/sec` | 182,0 | Security |
| `/dev/BOOT` | 254,0 | Boot device |
| `/dev/Vcodec` | 160,0 | Video codec |
| `/dev/rtc0` | 248,0 | Real-time clock |
| `/dev/seninf` | 231,0 | Sensor interface |

---

## Input Devices

| Event Device | Name | Purpose |
|-------------|------|--------|
| `/dev/input/event0` | ACCDET | Headset/accessory detection |
| `/dev/input/event1` | mtk-kpd | Keypad (power, volume, etc.) |
| `/dev/input/event2` | mtk-tpd | Touchscreen |

---

## SPI Devices (sysfs)

```
/sys/bus/spi/devices/spi32765.0
```

Single active SPI device registered.

---

## I2C Devices (sysfs)

Buses: i2c-0 through i2c-11 (12 buses total)

Active device addresses detected on each bus:

| Bus | Addresses | Likely Devices |
|-----|-----------|---------------|
| i2c-0 | 0x40 | Cap touch controller |
| i2c-1 | 0x01, 0x0C, 0x10, 0x11, 0x4C, 0x68, 0x69 | NM demo, msensor, ICM42607 accel, ICM42607 gyro, unknown(0x4C), gsensor, gyro |
| i2c-2 | 0x0C, 0x10, 0x15, 0x33, 0x36, 0x43, 0x50, 0x54 | Camera AF, sub cam, sub AF, CCU main, main cam, CCU sub, main EEPROM, sub EEPROM |
| i2c-3 | 0x08, 0x1E | NFC, ALS/proximity |
| i2c-4 | 0x0E, 0x11, 0x12, 0x38, 0x52 | Main2 AF, CCU main2, CCU main3, main2 cam, main2 EEPROM |
| i2c-5 | 0x34, 0x4E | MT6370 sub-PMIC, USB Type-C |
| i2c-6 | 0x34, 0x4B | Speaker amp, RT9465 charger |
| i2c-7 | (none) | - |
| i2c-8 | (none) | - |
| i2c-9 | (none) | - |
| i2c-10 | (none) | - |
| i2c-11 | (none) | - |

---

## GPIO

`/sys/class/gpio/` does not exist on this device. GPIO access is via the MediaTek pinctrl driver at `0x10005000` with 7 IO config groups (iocfg_0 through iocfg_6).

---

## Power Supply

| Supply | Type | Status |
|--------|------|--------|
| ac | Mains | offline |
| battery | Battery | Charging, 6%, 3.832V, Li-ion, 2946mAh full capacity, 26.0C |
| charger | Unknown | online |
| usb | USB | online, 500mA max, 5V |

Battery details:
- Current draw: 1,750 mA (charging)
- Average current: 1,695 mA
- Cycle count: 0
- Charge counter: 176,760 uAh

---

## LEDs

| LED | Purpose |
|-----|--------|
| `red` | RGB indicator (MT6370 ISINK, led_mode=3) |
| `green` | RGB indicator (MT6370 ISINK, led_mode=3) |
| `blue` | RGB indicator (MT6370 ISINK, led_mode=3) |
| `lcd-backlight` | Display backlight (max brightness 255, MT6370 BLED, led_mode=5) |
| `mt6370_pmu_led1` | MT6370 PMU LED channel 1 |
| `mt6370_pmu_led2` | MT6370 PMU LED channel 2 |
| `mt6370_pmu_led3` | MT6370 PMU LED channel 3 |
| `mt6370_pmu_led4` | MT6370 PMU LED channel 4 |

---

## Sysfs Classes

Complete list of registered sysfs classes:

```
BOOT            CAM_CALdrv1     DPEdrv          MFBdrv          MTK_SMI
MT_pmic_adc_cali OWEdrv         RSCdrv          Vcodec          Vcodec2
WPEdrv          accdet          actuatordrv_main2_af actuatordrv_main_af
actuatordrv_sub_af android_usb  bdi             block           btif
camera-fdvt     ccci_md_sta     ccci_node       ccudrv          charger_ftm
devfreq         devmap          dipdrv          dma             dual_role_usb
firmware        flashlight      flashlight_core fm              gauge
gpsemi          graphics        hdmitx          hidg            hidraw
i2c-adapter     ieee80211       input           iommu           ispdrv
leds            mdio_bus        mem             misc            mmc_host
mtk-adc-cali    mtk_cmdq        mtk_dfrc        mtk_disp_mgr    net
pmic_ftm        pmsg            power_supply    ppp             regulator
rpmb            rpmb_dummy      rt5509_cal      rtc             scheddrv
scsi_device     scsi_disk       scsi_host       sec             seninf
sensor          sensordrv       sound           spi_master      stpbt
stpgps          stpwmt          switch          switching_charger tcpc
thermal         timed_output    tty             udc             usb_boost
usb_rawbulk     vpudrv          wmtWifi         wmtdetect       xt_idletimer
zram-control
```

Notable classes:
- `sensor`, `sensordrv` - MediaTek sensor framework
- `tcpc` - Type-C Port Controller
- `switching_charger` - Charger class
- `dual_role_usb` - USB dual-role (OTG) support
- `hidg` - HID gadget (USB HID device mode)
- `ieee80211` - WiFi

---

## Interrupts (Selected Active)

| IRQ | Source | Count (CPU0) | Notes |
|-----|--------|-------------|-------|
| 2 | arch_timer | 376,347 | ARM architecture timer |
| 5 | mt-gpt | 114,442 | General purpose timer |
| 13 | mtk-msdc | 9,275 | eMMC/SD controller |
| 27 | TOUCH_PANEL-eint | 197 | Touchscreen (EINT8) |
| 29 | mt6370_pmu_irq | 1,104 | MT6370 sub-PMIC (EINT10) |
| 231 | mt-i2c | 630 | I2C controller (highest traffic I2C) |
| 236 | mt-i2c | 61,588 | I2C controller (very high traffic - likely sensor polling) |
| 271 | AHB_SLAVE_HIF | 66,710 | WiFi HIF |
| 287 | (unlabeled) | 520,612 | Highest interrupt count - likely display vsync |
| 310 | 13040000.mali | 5,701 | GPU |
| 322-335 | Display pipeline | ~2,800-5,900 | OVL, RDMA, WDMA, AAL, mutex |
| 291-296 | SPI controllers | 0 | All SPI interrupts show 0 count |

I2C bus interrupt 236 (IRQ for mt-i2c at SYS_IRQ 133) has the highest I2C traffic at 61,588 on CPU0, suggesting frequent sensor polling.

---

## IO Memory Map (Selected)

| Address Range | Device |
|--------------|--------|
| `0x10005000-0x10005fff` | GPIO/pinctrl |
| `0x10012000-0x10012fff` | DVFSRC |
| `0x10219000-0x10219fff` | EMI controller |
| `0x10500000-0x1057ffff` | SCP |
| `0x11000080-0x110007ff` | I2C DMA channels (all 12 buses) |
| `0x11002000-0x1100201f` | UART0 (serial) |
| `0x11003000-0x1100301f` | UART1 (serial) |
| `0x11004000-0x1100401f` | UART2 (serial) |
| `0x11005000-0x11005fff` | I2C bus 6 |
| `0x11007000-0x1101bfff` | I2C buses 0-8 |
| `0x1100a000-0x1100afff` | SPI0 |
| `0x11010000-0x11010fff` | SPI1 |
| `0x11012000-0x11013fff` | SPI2, SPI3 |
| `0x11018000-0x11019fff` | SPI4, SPI5 |
| `0x11200000-0x1120ffff` | USB3 (ssusb_base) |
| `0x13040000-0x13043fff` | Mali GPU |
| `0x40000000-0x411d7fff` | System RAM (kernel code at 0x40080000) |

---

## Thermal Zones

| Zone | Type | Purpose |
|------|------|--------|
| thermal_zone0 | mtktsbattery | Battery temperature |
| thermal_zone1 | mtktscpu | CPU temperature |
| thermal_zone2 | mtktspa | PA temperature |
| thermal_zone3 | mtktspmic | PMIC temperature |
| thermal_zone4 | mtktswmt | WiFi/BT module temperature |
| thermal_zone5-10 | tzimgs0-5 | Image sensor temperatures |
| thermal_zone11-13 | mt6358tsbuck1-3 | MT6358 PMIC buck regulator temps |
| thermal_zone14 | battery | Battery (alternate) |
| thermal_zone15-16 | mtktscharger/2 | Charger IC temperatures |
| thermal_zone17 | mtktsAP | Application processor |
| thermal_zone18 | mtktsbtsmdpa | BTS MD PA |
| thermal_zone19-23 | tzts1-5 | Additional thermal sensors |

---

## Summary of RC-Relevant Hardware

Based on this audit, the following hardware interfaces are most relevant to RC radio controller functionality:

1. **SPI1** (`spi32765.0`, `mt8788_spi1_plat_drv`): Active SPI device, likely RF module communication
2. **UART0/UART1** (`/dev/ttyS0`, `/dev/ttyS1`): World-accessible serial ports for external peripherals
3. **I2C Bus 1**: ICM-42607 6-axis IMU (accel + gyro) for head-tracking, plus New-Mobi custom driver
4. **I2C Bus 0**: Capacitive touch controller for stick/button input
5. **nm_miscdev**: New-Mobi custom GPIO/SPI control driver
6. **Keypad** (`mtk-kpd`): Physical buttons (power, volume mapped)
7. **PWM**: 4 PWM channels available
8. **ADC**: AUXADC with temperature and custom RF parameter channels
9. **Bluetooth**: Integrated BT via WMT for wireless peripherals/trainers
10. **WiFi**: Integrated WiFi for network connectivity, firmware updates
