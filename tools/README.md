# AX12 Research Tools

Python toolchain for monitoring, capturing, and analyzing UMBUS protocol traffic on the RadioMaster AX12. All tools use stdlib only and run under Termux. Most require root (`su 0`) for serial/hardware access. See [docs/guides/tool-usage.md](../docs/guides/tool-usage.md) for full documentation.

| Tool | Purpose | Usage |
|------|---------|-------|
| `umbus.py` | UMBUS protocol library (frame parsing, CRC, enums) | `import` only — not run directly |
| `strace-parser.py` | Parse UMBUS frames from strace logs | `python3 strace-parser.py captures/raw.log` |
| `monitor.py` | Live TUI channel/gimbal viewer | `su 0 python3 monitor.py` |
| `calibrator.py` | Interactive gimbal and switch mapping | `su 0 python3 calibrator.py` |
| `capture-session.py` | Interactive capture with labeling | `su 0 python3 capture-session.py` (alias: `capture`) |
| `batch-capture.py` | Non-interactive timed capture | `su 0 python3 batch-capture.py --duration 60` |
| `live-mapper.py` | Live control-to-channel mapper | `su 0 python3 live-mapper.py` |
| `live_dashboard.py` | Web dashboard for protocol visualization | `su 0 python3 live_dashboard.py` → `localhost:8081` |
| `umbus_server.py` | SSE server streaming live UMBUS data | `su 0 python3 umbus_server.py` |
| `build-dashboard.py` | Generate static HTML dashboard from captures | `python3 build-dashboard.py captures/session.jsonl` |
| `fm_radio.py` | FM radio controller | `su 0 python3 fm_radio.py` |
| `simulator.py` | Traffic simulator for offline development | `python3 simulator.py` |
| `latency-test.py` | HDMI input latency timer | `su 0 python3 latency-test.py` |
| `cot_bridge.py` | ATAK Cursor-on-Target bridge | `python3 cot_bridge.py` |
| `test_cot.py` | CoT test sender | `python3 test_cot.py` |
| `usb_otg.py` | USB OTG host mode toggle | `su 0 python3 usb_otg.py` |
| `optimize.py` | Performance optimizer | `su 0 python3 optimize.py` |
