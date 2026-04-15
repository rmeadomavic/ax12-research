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

The AT32F435 uses FAP (Flash Access Protection), analogous to STM32's RDP:
- **Level 0**: Unprotected — full flash dump via SWD
- **Level 1**: Debug reads blocked — reversible only with full flash erase
- **Level 2**: Permanent — JTAG/SWD disabled entirely

SWD test points (SWDIO, SWCLK, GND, optional nRST) are expected on the PCB but have not been located yet.

**Tools:** J-Link (via Artery DFP), OpenOCD (Artery's fork), pyOCD (CMSIS pack), Artery ICP Programmer.

**Procedure:**
1. Locate SWD pads on PCB
2. Connect debug probe and check FAP level
3. If Level 0: dump flash immediately
4. If Level 1: voltage glitching required (no published AT32-specific bypass)
5. If Level 2: debug interface permanently disabled

## Betaflight AT32 Support

Betaflight has official AT32F435 support for flight controllers. The same toolchain, OpenOCD configs, and debug procedures apply to the AX12's AT32 even though it runs TX firmware, not Betaflight.

## Next Steps

1. Open the AX12 and locate SWD test points
2. Probe FAP status
3. Attempt firmware dump if unlocked
4. Disassemble in Ghidra with AT32F435 SVD
5. Correlate ADC/GPIO routines with known UMBUS frame fields
