# AX12 Research

Hardware reverse engineering project for the RadioMaster AX12 transmitter.

## Device

- Android 9, MediaTek MT8788 SoC, AT32 coprocessor MCU
- Root access via `su 0` (factory userdebug build, no exploit required)
- UMBUS protocol over /dev/ttyS0 at 921600 baud, 8 frame types

## Repo

- Published at github.com/rmeadomavic/ax12-research, branch `main`
- Structure: `docs/`, `tools/`, `captures/`, `device-tree/`
- Native `.so` and `.apk` files are gitignored -- do not commit them

## Development Rules

- All Python scripts require root: `su 0 python3 script.py`
- Python tools use stdlib only -- no external dependencies
- Preserve existing dataclass/enum patterns when editing tools
- Never read /dev/ttyS0 directly -- use strace to monitor serial traffic
  (direct reads steal bytes from the app and corrupt its state)

## Serial Monitoring

```
su 0 strace -e read,write -p <pid> -x -s 512 2>&1 | grep ttyS0
```

Attach to the process that owns the serial port. Do not open the port
from a second process.
