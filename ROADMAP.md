# Roadmap

Remaining research targets and open questions, organized by priority.

## High Priority

These are the biggest gaps in our understanding of the AX12.

- **Non-idle captures** — All current protocol data comes from idle-state strace sessions. Need captures during binding, flying, trainer mode, model switching, and firmware update to observe command sequences and state transitions.
- **App-to-MCU command protocol** — The app sends frames on types 0x0E, 0x0C, 0x08, and 0x07, but the payload semantics are poorly understood. What triggers changes in these frames? How does the app command channel output, mode changes, or binding?
- **ELRS telemetry field identification** — Type 0x15 frames carry ELRS RF telemetry (RSSI, LQ, SNR, TX power), but individual byte-to-field mapping is incomplete. Needs controlled experiments with known RF conditions.
- **Config sync protocol** — How does the app push model configuration, channel maps, and mixer settings to the MCU? The native library has `UMBUS_Fill`, `UMBUS_StartPack`, `UMBUS_EndPack` — these likely handle multi-frame config transfers.

## Medium Priority

Partially understood or less critical research areas.

- **Extended telemetry (type 0x10)** — Frame structure identified but most payload fields are unknown. Uses CRC init 0x7F. Appears to carry battery voltage and system status.
- **Unknown bytes in 0x57 frames** — Channel data and gimbal axes are mapped, but several bytes in the 87-byte frame remain unidentified (bytes 4-5, 14-17, and trailing bytes after channel data).
- **Gimbal calibration protocol** — The calibrator tool maps axes via live observation, but the MCU-side calibration process (center/endpoint storage, dead zone) is undocumented.
- **Firmware update protocol** — `QSharkFwControl` manages MCU and ELRS backpack updates. The update mechanism (frame type, transfer protocol, verification) is unanalyzed.
- **Model file format (.rcm)** — Substantially decoded. Header (magic, timestamps, name, icon, model type), config section (trims, rates, rate/expo curves with signed curve points), and variable-length endpoint section (mixer entries with weights/offsets, endpoint definitions with travel/subtrim/limits) all mapped. Remaining unknowns: 16-byte `0xAA` block in DeltaWing/Helicopter configs, helicopter swash parameters at 0x208, exact semantics of endpoint limit u16le[4] values, and the config sync protocol to MCU.

## Low Priority

Edge cases and deeper analysis that would complete the picture.

- **Header byte encoding** — Bytes 2-3 encode source/destination routing, but the encoding scheme (bitmask? lookup table?) is not fully understood.
- ~~**Heartbeat checksum anomaly**~~ — **RESOLVED.** All app->MCU frames (0x08, 0x0E, 0x0C, 0x07) use standard CRC-8/MAXIM init=0x00. Verified from strace capture of steady-state serial I/O.
- **PWM output mapping** — How do the 33 logical channels map to physical PWM outputs on the MCU? External module bay pin assignments are unknown.
- **Native library decompilation** — The 25MB .so has 13,000+ dynamic symbols. Current analysis uses strings/readelf only. Targeted Ghidra decompilation of UMBUS engine functions would accelerate protocol understanding.

## In Progress

Active work with partial results.

- **USB OTG host mode** — Sysfs toggle found: `device_host_gpio_attr` is world-writable, MUSB cmode and dual-role port mode are switchable from userspace. No custom kernel needed. **Needs physical testing** with a USB-C OTG adapter and connected device to confirm full enumeration, VBUS sourcing, and data transfer. See [hardware-map.md USB OTG section](docs/hardware/hardware-map.md#usb-otg-host-mode).
- **Trainer host mode** — The "Host" option in radio settings is the wireless trainer (buddy box) host/master mode, derived from EdgeTX's trainer system. Investigation scripts prepared: `scripts/trainer-probe.lua` (Lua API probe) and `scripts/search-host-strings.sh` (native library string search). **Needs on-device execution** to capture protocol-level changes when the setting is toggled, and to enumerate the full RcSetSystem settings page. See [host-trainer-mode.md](docs/software/host-trainer-mode.md).

## Recently Resolved

- **MCU standalone operation** — Confirmed the AT32 MCU broadcasts all 4 frame types (0x57 channel, 0x08 heartbeat, 0x15 ELRS, 0x10 extended) at full documented rates even when the Flyshark app is NOT running. The MCU operates completely autonomously.
- **App->MCU frame CRCs** — All use CRC-8/MAXIM init=0x00. No heartbeat anomaly exists. Frame batching confirmed: 0x08+0x0C+0x0E written as single 34-byte burst, 0x07+0x0E as 21-byte burst.
- **App->MCU idle payloads decoded** — 0x0E: 02064B01000000, 0x0C: 028101080000, 0x08: 050180, 0x07: FF01. All static during idle state.
- **I2C device map complete** — 28 devices across 7 buses. IT66121 HDMI transmitter identified at bus 1 addr 0x4C.

## Future

Longer-term projects that build on the research.

- ~~**Custom kernel / USB OTG**~~ — Moved to **In Progress** (see below).
- **ATAK plugin** — The AX12 has a functional GCS with IMU and map engine. An ATAK (Android Team Awareness Kit) integration could turn it into a tactical UAV controller.
- **Python package** — Package `umbus.py` and the analysis tools as a pip-installable library for broader community use.
- **Lua tools and widgets** — Build custom Lua scripts leveraging the LVGL bindings for on-device dashboards, telemetry overlays, and protocol diagnostics.
