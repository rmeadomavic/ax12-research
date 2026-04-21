# Captures

Raw serial capture data from UMBUS protocol monitoring sessions. All captures were recorded passively via `strace` on the Flyshark app — no bytes were injected or stolen from the serial link.

## Files

| File | Description |
|------|-------------|
| `idle-strace.txt` | Truncated strace log from idle state |
| `idle-strace-full.txt` | Full strace log (~10 seconds idle) |
| `idle-raw-10s.bin` | Raw binary capture of serial traffic |
| `frames.json` | Parsed UMBUS frames (JSON) |
| `timed-frames.json` | Timestamped parsed frames (JSON) |
| `jitter-debug.txt` | Frame timing jitter debug output |
| `jitter-test.txt` | Frame timing test results |

## Capture Methodology

1. Identify the process holding `/dev/ttyS0`: `su 0 ls -la /proc/*/fd/* 2>/dev/null | grep ttyS0`
2. Attach strace: `su 0 strace -e read,write -p <pid> -x -s 512 2>&1 | grep ttyS0`
3. Parse with `tools/strace-parser.py` to extract UMBUS frames

## Adding New Captures

Name files descriptively: `<state>-<duration>-<date>.txt` (e.g., `binding-30s-20260415.txt`). Include firmware version and radio state in commit messages. See [CONTRIBUTING.md](../CONTRIBUTING.md) for full guidelines.
