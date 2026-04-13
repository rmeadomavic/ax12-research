# Documentation Index

## Protocol

- **[UMBUS Protocol Specification](protocol/umbus-protocol.md)** — Complete serial protocol: frame formats, timing, field layouts, hex examples
- **[Checksum Investigation](protocol/checksum-investigation.md)** — CRC-8/MAXIM algorithm discovery, per-type init values, verification
- **[ELRS Telemetry Analysis](protocol/elrs-telemetry-analysis.md)** — RF link telemetry framing, CRSF transport over UMBUS
- **[CRSF Protocol Reference](protocol/crsf-reference.md)** — CRSF protocol frame types and CRC

## Hardware

- **[Hardware Map](hardware/hardware-map.md)** — Architecture overview, physical controls, sensors, peripherals, serial ports
- **[Device Tree Analysis](hardware/device-tree.md)** — SoC peripheral map from decompiled device tree source
- **[System Audit](hardware/system-audit.md)** — Partitions, kernel modules, device nodes, sysfs entries
- **[MT8788 Platform Research](hardware/mt8788-research.md)** — MT8788/MT6771 platform research
- **[ELRS Backpack](hardware/elrs-backpack.md)** — ELRS backpack capabilities and WiFi MAVLink

## Software

- **[Native Library Analysis](software/native-lib-analysis.md)** — 25MB `.so` reverse engineering: class hierarchy, APIs, constants
- **[Lua API Reference](software/lua-api.md)** — Lua 5.3 VM overview, EdgeTX API surface, LVGL bindings, dead stubs
- **[Flyshark App Analysis](software/flyshark-app.md)** — Flyshark app architecture analysis

## Guides

- **[Root & Setup Guide](guides/root-guide.md)** — Install Termux, get root access, set up development environment
- **[Capture Session Guide](guides/capture-session-guide.md)** — How to record and parse UMBUS traffic via strace
- **[Latency Optimization](guides/latency-optimization.md)** — HDMI latency reduction guide
- **[Tool Usage](guides/tool-usage.md)** — All tools with usage examples
