# Contributing

Thanks for your interest in the AX12 reverse-engineering project! This is a
community research effort — contributions of captures, protocol findings,
tooling improvements, and documentation are all welcome.

## What We Need

- **Captures from different states** — binding, flying, different model
  configurations, trainer mode, DSC port activity
- **DSC port loopback testing** — does the external module bay speak UMBUS?
- **ELRS telemetry field identification** — mapping raw bytes to sensor values
- **Bootloader unlock attempts** — fastboot, MediaTek SP Flash Tool, etc.
- **Lua script testing** — confirming which API functions are live vs. dead stubs
- **New API discoveries** — undocumented LVGL bindings, shared memory usage

## How to Contribute Captures

1. Follow the [capture session guide](docs/guides/capture-session-guide.md) to
   record a strace session.
2. Run `tools/strace-parser.py` to extract frames from the raw log.
3. Name your files descriptively:
   `<state>-<duration>-<date>.txt` (e.g., `binding-30s-20260415.txt`)
4. Include metadata in your PR description:
   - Flyshark app version (Settings → About)
   - Firmware version
   - Model configuration (number of channels, ELRS packet rate, etc.)
   - What was happening on the radio during the capture

## Code Style

- **Python 3.13, stdlib only** — no pip on the target device
- **Dataclass/enum patterns** — follow the conventions in `tools/umbus.py`
- **Docstrings on public functions** — one-line summary, then details
- **Type hints** — use them consistently

## Reporting Protocol Findings

- Open an issue with the raw hex frame dumps
- Include the frame type byte and your interpretation
- Note the firmware version and Flyshark app version
- Screenshots of the [protocol dashboard](dashboard/index.html) can help
  provide visual context

## Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b my-finding`)
3. Commit with a descriptive message explaining *what you found*, not just
   what you changed
4. Open a pull request against `main`

## License

By contributing, you agree that your contributions will be licensed under the
MIT License that covers this project.
