# Host / Trainer Mode

## What It Is

The **Host** option in the AX12 radio settings is the **wireless trainer (buddy box) host/master mode** -- an EdgeTX-derived feature for instructor/student flight training.

In trainer mode, two radios are linked so that an instructor ("host" / "master" / "coach") can monitor and override a student ("pupil" / "slave") who is learning to fly. The host radio maintains authority over the aircraft and can instantly take back control.

| Role | Also called | Function |
|------|-------------|----------|
| **Host** | Master, Coach, Instructor | Has final authority. Receives student input and mixes it into channel output. Can override at any time via a trainer switch. |
| **Pupil** | Slave, Student | Sends stick/switch input to the host. Does not directly control the aircraft. |

## Evidence from Codebase

The host option has not yet been fully reverse-engineered at the protocol level. Here is what we know from static analysis:

### Flyshark App (`docs/software/flyshark-app.md`)

- **AUX Serial Modes** include "SBUS Trainer" -- this is the transport used for wired trainer connections via the top USB-C port (labeled "Trainer port" in hardware-map.md:242).
- **RcSetSystem** settings page exists but its individual options are not enumerated. The host/trainer toggle almost certainly lives here.

### Lua API (`docs/software/lua-api.md`)

- `getTrainerStatus()` -- Returns trainer port status. Exists as an inferred API function (not yet confirmed at runtime).
- `CHAR_TRAINER` -- UI constant for trainer-related display elements.
- `getGeneralSettings()` -- Returns general settings table. In EdgeTX, this includes `trainerMode` and trainer channel configuration.

### Native Library (`docs/software/native-lib-analysis.md`)

- 266,670 strings in the .so library. A targeted search for trainer/host strings has not yet been performed. The `search-host-strings.sh` script (see below) will extract all relevant strings.
- `STR_AUX_SERIAL_MODE` / `STR_AUX2_SERIAL_MODE` -- AUX serial mode labels (includes SBUS Trainer).

### EdgeTX Heritage

The AX12 firmware is derived from EdgeTX/OpenTX. In EdgeTX, trainer mode is configured under **Radio Setup > Trainer** and includes:

| Setting | Values | Purpose |
|---------|--------|---------|
| Mode | Off / Master SBUS / Master CPPM / Master Battery / Slave | Role selection |
| Channel range | CH1-CH4 through CH1-CH16 | Which channels the student controls |
| PPM multiplier | 0-100% | Student input scaling per channel |
| Cal | Per-channel calibration | Calibrate student stick ranges |

The AX12's implementation likely mirrors this structure, adapted for SBUS transport over the USB-C trainer port and potentially wireless trainer via ELRS/CRSF.

## Physical Setup

### Wired Trainer (SBUS)

```
Host AX12 (USB-C data port) ←── SBUS cable ──→ Pupil radio (trainer port)
```

- Uses the top USB-C port in its default gadget/device role (not USB OTG host mode)
- AUX Serial Mode must be set to "SBUS Trainer"
- SBUS is inverted serial at 100kbps, 8E2

### Wireless Trainer (potential)

ELRS supports wireless trainer mode where the pupil radio transmits stick data over the RF link. The backpack's ESP-NOW wireless switch input (documented in `docs/hardware/elrs-backpack.md`) could also serve as a trainer input pathway. This has not been confirmed on the AX12.

## Protocol Effects (Unknown -- Needs Capture)

When the host option is toggled, we expect changes in:

| Frame | Current idle value | Expected change |
|-------|-------------------|-----------------|
| **0x0C (Config/State)** | `02 81 01 08 00 00` | Byte 4 (`01`) or byte 5 (`08`) may encode trainer mode |
| **0x0E (Poll)** | `02 06 4B 01 00 00 00` | May change poll flags |
| **0x57 (Channel Data)** | 33 channels @ 25 Hz | Trainer channels may appear or modify existing channels |
| **New frame types** | None expected | One-shot config sync command possible |

## Investigation Procedure

### Step 1: Native Library Strings (5 min)

Run the search script on the AX12 to extract all trainer/host-related strings:

```bash
su 0 bash ~/ax12-research/scripts/search-host-strings.sh
```

Results written to `/sdcard/AX12LUA/host-strings-report.txt`. This reveals the exact UI labels, enum values, and function names.

### Step 2: Lua API Probe (10 min)

Copy the probe script and run it from the Tools menu:

```bash
su 0 cp ~/ax12-research/scripts/trainer-probe.lua /sdcard/AX12LUA/SCRIPTS/TOOLS/
```

1. With host **OFF**: Run the script from Tools menu. Save output.
2. Toggle host **ON** in the radio settings.
3. Run the script again. Save output.
4. Diff the two result files:

```bash
diff /sdcard/AX12LUA/trainer-probe-results-off.txt /sdcard/AX12LUA/trainer-probe-results-on.txt
```

(Rename the output file between runs, or the second run overwrites the first.)

### Step 3: Protocol Capture (15 min)

Capture UMBUS frames before, during, and after toggling the host option:

```bash
# Find the Flyshark process
PID=$(su 0 pgrep -f Flyshark | head -1)

# Capture with host OFF (10 seconds)
su 0 timeout 10 strace -tt -e read,write -x -s 512 -p $PID 2>&1 > /sdcard/host-off.strace

# Start capture, then toggle host ON in the UI during capture
su 0 timeout 30 strace -tt -e read,write -x -s 512 -p $PID 2>&1 > /sdcard/host-toggle.strace

# Capture with host ON (10 seconds)
su 0 timeout 10 strace -tt -e read,write -x -s 512 -p $PID 2>&1 > /sdcard/host-on.strace
```

Parse the captures:

```bash
su 0 python3 ~/ax12-research/tools/strace-parser.py /sdcard/host-off.strace > /sdcard/host-off-frames.txt
su 0 python3 ~/ax12-research/tools/strace-parser.py /sdcard/host-toggle.strace > /sdcard/host-toggle-frames.txt
su 0 python3 ~/ax12-research/tools/strace-parser.py /sdcard/host-on.strace > /sdcard/host-on-frames.txt
```

Compare the 0x0C frame payloads between host-off and host-on to identify which bytes encode the trainer mode.

### Step 4: Settings File Monitor (optional)

Watch for file writes when the setting is changed:

```bash
# Start watching, then toggle the host option
su 0 strace -tt -e trace=openat,write,rename -p $PID 2>&1 | grep -i 'settings\|config\|trainer\|rcCfg'
```

This may reveal the Qt INI file or binary config that persists the trainer mode setting.

## Results

> **Status: Investigation prepared, awaiting on-device execution.**
>
> The probe scripts and search tools are ready. Run Steps 1-3 on the
> AX12 device and commit the result files to complete this investigation.

## See Also

- [Flyshark App Analysis](flyshark-app.md) -- App architecture, AUX Serial Modes, settings pages
- [Lua API Reference](lua-api.md) -- `getTrainerStatus()`, `CHAR_TRAINER`
- [USB OTG Host Mode](../hardware/hardware-map.md#usb-otg-host-mode) -- Separate feature (USB-C role switching, not trainer mode)
- [ELRS Backpack](../hardware/elrs-backpack.md) -- Wireless switch input via ESP-NOW
- [ROADMAP](../../ROADMAP.md) -- Trainer mode listed as high-priority research gap
