# Roadmap

Open research targets, by priority.

## High Priority

- **Non-idle captures** — All current data is from idle state. Need captures during binding, flying, trainer mode, and model switching.
- **App-to-MCU command semantics** — The app sends on types 0x0E, 0x0C, 0x08, and 0x07. Payload semantics are poorly understood.
- **ELRS telemetry field mapping** — Type 0x15 carries RSSI, LQ, SNR, TX power. Byte-to-field mapping incomplete. Needs controlled RF experiments.
- **Config sync protocol** — How does the app push model config to the MCU? The native library has `UMBUS_Fill`, `UMBUS_StartPack`, `UMBUS_EndPack` for multi-frame transfers.

## Medium Priority

- **Extended telemetry (0x10)** — Frame structure identified, most payload fields unknown. Likely carries battery voltage and system status.
- **0x57 unknown bytes** — Channel data mapped, but bytes 4-5, 14-17, and trailing bytes remain unidentified in the 87-byte frame.
- **Gimbal calibration** — MCU-side calibration process (center/endpoint storage, dead zones) is undocumented.
- **Firmware update protocol** — Update mechanism for MCU and ELRS backpack is unanalyzed.
- **Model file format (.rcm)** — Header, config, and endpoint sections substantially decoded. Remaining unknowns: helicopter swash parameters, DeltaWing/Heli `0xAA` block, endpoint limit semantics.

## Low Priority

- **Header byte encoding** — Bytes 2-3 encode source/destination routing. Encoding scheme not fully understood.
- **PWM output mapping** — Logical-to-physical channel mapping and module bay pin assignments.
- **Native library decompilation** — Targeted Ghidra analysis of UMBUS engine functions.

## In Progress

- **USB OTG host mode** — Sysfs toggle found and responsive. Needs physical testing with USB-C OTG adapter.
- **Trainer host mode** — Wireless buddy box via EdgeTX trainer system. Investigation scripts prepared, needs on-device execution.

## Future

- **ATAK integration** — Tactical UAV controller leveraging the built-in GCS, IMU, and map engine.
- **Python package** — Package `umbus.py` as a pip-installable library.
- **Lua widgets** — Custom on-device dashboards via LVGL bindings.
