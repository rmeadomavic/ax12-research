# AT32F435 RC Microcontroller

The AX12's RC functions are handled by an Artery AT32F435 MCU, not the Android
SoC. Every physical input (gimbals, switches, pots, trims) is read by the MCU
and encoded into UMBUS frames sent to the MT8788 over ttyS0 at 921600 baud.
Commands flow the other way: Android sends config and poll frames that the MCU
decodes and acts on. The AT32 is the hardware abstraction layer between the
analog control surface and the digital application processor.

## AT32F435 Specifications

| Parameter | Value |
|-----------|-------|
| Core | ARM Cortex-M4F, 288 MHz |
| Flash | Up to 4 MB (internal) |
| SRAM | Up to 512 KB |
| UARTs | 8 |
| ADCs | 3× 12-bit (up to 5.33 Msps combined) |
| Timers | 15 (including advanced-control timers) |
| Debug | SWD and JTAG |
| Package | LQFP64/100/144 (pin-compatible with STM32F405) |
| Vendor | Artery Technology (Chongqing, China) |

## Not an STM32 Clone

The AT32F435 is **pin-compatible** with the STM32F405 but it is a different
chip with different silicon:

- Register map differs — STM32 HAL code will not compile unmodified
- Flash programming algorithm differs — ST-Link software needs AT32 support
- Requires the **Artery HAL** (AT32F435_437 Firmware Library), not STM32 HAL
- Firmware library: [github.com/ArteryTek/AT32F435_437_Firmware_Library](https://github.com/ArteryTek/AT32F435_437_Firmware_Library) (BSD-3)
- Clock tree and PLL configuration differ (288 MHz max vs 168 MHz on STM32F405)

Pin compatibility means the same PCB footprint works, which is why RadioMaster
(and many drone manufacturers) switched from STM32 to AT32 during shortages.

## Role in the AX12

```
Physical Controls          AT32F435 MCU             MT8788 SoC (Android)
─────────────────    ──────────────────────    ──────────────────────────
4× gimbal axes ───►  ADC sampling + scaling ──►  UMBUS 0x57 frames (25 Hz)
6× switches    ───►  GPIO debounce         ──►  encoded in 0x57 payload
2× pots/sliders───►  ADC channels          ──►  encoded in 0x57 payload
4× trim buttons───►  GPIO edge detect      ──►  trim counters in 0x57
ELRS LR1121    ◄──►  SPI/UART to RF module ──►  UMBUS 0x15 telemetry (5 Hz)
                     heartbeat             ──►  UMBUS 0x08 (4 Hz)
               ◄──── config/poll/keepalive ◄──  UMBUS 0x0E/0x0C/0x07
```

The MCU owns all real-time I/O. Android never touches the ADCs or GPIOs
directly — everything is mediated through UMBUS.

## Firmware

The AT32 runs **RadioMaster proprietary firmware**, not EdgeTX:

- **No EdgeTX support** — EdgeTX does not target the AT32F435. The AT32 is
  supported by Betaflight (flight controller side), but no open-source TX
  firmware runs on it.
- Firmware updates are pushed from the Flyshark app via `QSharkFwControl`
  over the UMBUS link (OTA to MCU over UART).
- The firmware is the authoritative encoder/decoder for all UMBUS frames.
  Understanding it is the key to fully decoding the UMBUS command protocol.

## SWD Debug Access

If Flash Access Protection (FAP) is **not** enabled, the firmware can be
dumped via SWD test points on the PCB:

| Signal | Description |
|--------|-------------|
| SWDIO | Serial Wire Data I/O |
| SWCLK | Serial Wire Clock |
| GND | Ground reference |
| VCC | 3.3V reference (may be needed for level shifting) |

**Compatible tools:** J-Link, ST-Link (with AT32 support), DAPLink, OpenOCD
(AT32F435 target config available in recent builds).

**If FAP is enabled:** Flash readout is locked. Would require glitching or
other invasive techniques to bypass.

## Betaflight AT32 Support

Betaflight has **official AT32F435 support** for flight controllers, which
means the AT32 toolchain, OpenOCD configs, and community knowledge exist.
This is useful context even though the AX12's AT32 runs TX firmware, not
Betaflight — the same debug tools and flash procedures apply.

## Next Steps

1. **Open the AX12** and locate SWD test points (SWDIO, SWCLK) on the MCU
2. **Probe FAP status** — connect via SWD and check if flash readout is locked
3. **Attempt firmware dump** — if unlocked, pull the full flash image
4. **Disassemble** — Cortex-M4 firmware in Ghidra with AT32F435 SVD for
   peripheral register names
5. **Map UMBUS encoding** — correlate disassembled ADC/GPIO routines with
   known UMBUS frame fields to decode remaining unknowns


## SWD Debug Access

The AT32F435 uses FAP (Flash Access Protection), mirroring STM32's RDP:
- **Level 0**: Unprotected. SWD can read all flash freely. Full firmware dump is trivial.
- **Level 1**: Debug reads blocked. Reversible only with full flash erase.
- **Level 2**: Permanent. JTAG/SWD disabled entirely.

### Tool Support
- **J-Link**: Supported via Artery device pack (DFP)
- **OpenOCD**: Artery's fork supports AT32F435 (bundled with AT32 IDE)
- **pyOCD**: Supported via CMSIS pack
- **Artery ICP Programmer**: Free proprietary tool

### Procedure
1. Locate SWD pads on PCB (standard ARM: SWDIO + SWCLK + GND + optional nRST)
2. Connect J-Link or ST-Link clone
3. Check FAP level first
4. If Level 0: dump full flash immediately
5. If Level 1: can connect but reads fail — need voltage glitching (no published AT32-specific bypass)
6. If Level 2: debug interface is permanently disabled

### AX12 Thermal Zones
| Zone | Type | Description |
|------|------|-------------|
| thermal_zone0 | mtktsbattery | Battery: 25.0C (idle) |
| thermal_zone1 | mtktscpu | CPU: 50.6C (under load) |
| thermal_zone2 | mtktspa | Power amplifier: -127C (not present/invalid) |
| thermal_zone3 | mtktspmic | PMIC |
| thermal_zone4 | mtktswmt | WiFi/BT combo chip |
