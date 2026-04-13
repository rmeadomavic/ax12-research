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
- **Model file format (.rcm)** — Files are flat binary structs with known load/save functions in the native library, but the field layout is not yet decoded.

## Low Priority

Edge cases and deeper analysis that would complete the picture.

- **Header byte encoding** — Bytes 2-3 encode source/destination routing, but the encoding scheme (bitmask? lookup table?) is not fully understood.
- **Heartbeat checksum anomaly** — App-originated 0x08 frames use a non-standard checksum. May be a different CRC init value or a different algorithm entirely.
- **PWM output mapping** — How do the 33 logical channels map to physical PWM outputs on the MCU? External module bay pin assignments are unknown.
- **Native library decompilation** — The 25MB .so has 13,000+ dynamic symbols. Current analysis uses strings/readelf only. Targeted Ghidra decompilation of UMBUS engine functions would accelerate protocol understanding.

## Future

Longer-term projects that build on the research.

- **Custom kernel / USB OTG** — The MT8788 supports USB OTG but it is disabled in the stock kernel config. A custom kernel could enable USB host mode on the DSC port, opening gamepad/HID input and external peripherals.
- **ATAK plugin** — The AX12 has a functional GCS with IMU and map engine. An ATAK (Android Team Awareness Kit) integration could turn it into a tactical UAV controller.
- **Python package** — Package `umbus.py` and the analysis tools as a pip-installable library for broader community use.
- **Lua tools and widgets** — Build custom Lua scripts leveraging the LVGL bindings for on-device dashboards, telemetry overlays, and protocol diagnostics.
