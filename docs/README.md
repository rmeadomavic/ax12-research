# Documentation

## Protocol
- [UMBUS Protocol](protocol/umbus-protocol.md) — Frame format, timing, field maps for all 8 types
- [Checksum Investigation](protocol/checksum-investigation.md) — CRC-8/MAXIM algorithm, per-type init values
- [ELRS Telemetry](protocol/elrs-telemetry-analysis.md) — RF link quality frames over UMBUS
- [CRSF Reference](protocol/crsf-reference.md) — Crossfire serial protocol

## Hardware
- [Hardware Map](hardware/hardware-map.md) — Architecture, controls, sensors, peripherals
- [AT32F435 MCU](hardware/at32-mcu.md) — Coprocessor role, specs, SWD access
- [Device Tree](hardware/device-tree.md) — SoC peripherals from decompiled DTS
- [System Audit](hardware/system-audit.md) — Partitions, kernel modules, device nodes
- [ELRS Backpack](hardware/elrs-backpack.md) — ESP backpack, WiFi MAVLink, OTA
- [MT8788 Research](hardware/mt8788-research.md) — Platform internals
- [OpenIPC FPV](hardware/openipc-fpv.md) — FPV ground station research

## Software
- [Native Library](software/native-lib-analysis.md) — 25MB `.so` reverse engineering
- [Lua API](software/lua-api.md) — Lua 5.3 VM, LVGL bindings, EdgeTX API
- [Flyshark App](software/flyshark-app.md) — Qt6/QML architecture, model format
- [Trainer Mode](software/host-trainer-mode.md) — Wireless trainer host investigation

## Guides
- [Getting Started](guides/getting-started.md) — Setup and first capture
- [Root Guide](guides/root-guide.md) — Termux, Tailscale, root access
- [Capture Sessions](guides/capture-session-guide.md) — Recording strace data
- [Tool Usage](guides/tool-usage.md) — All tools with usage examples
- [MAVLink Setup](guides/mavlink-setup.md) — ELRS MAVLink with QGC or ATAK
- [Latency Optimization](guides/latency-optimization.md) — HDMI latency reduction
- [USB OTG Testing](guides/usb-otg-testing.md) — USB host mode via sysfs
- [Security Hardening](guides/security-hardening.md) — Mitigating factory root exposure
