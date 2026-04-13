# MAVLink Telemetry over ELRS on the AX12

End-to-end setup for full ArduPilot telemetry on the RadioMaster AX12
using ELRS MAVLink mode. After this guide you will have live flight data,
parameter editing, and mission upload — either on the AX12 itself via QGC
or on a laptop over WiFi.

## Prerequisites

- RadioMaster AX12 with ELRS internal module (stock)
- ELRS TX and RX firmware **3.5.0 or later** (MAVLink link mode requires it)
- RX must be **ESP-based** (e.g. RP1/RP2/RP3, EP1/EP2, BetaFPV Nano) —
  STM-based receivers lack the bandwidth for MAVLink packets
- ArduPilot flight controller (Copter 4.4+, Plane 4.4+, or Rover 4.4+)
- A free UART on the FC connected to the ELRS receiver's TX/RX pins

## Step 1: ArduPilot Parameters

Connect to your FC with Mission Planner or QGC and set these parameters.
Replace `n` with your UART number (e.g. `SERIAL2` if the RX is on UART2).

**Required:**

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `SERIALn_PROTOCOL` | `2` | MAVLink 2 |
| `SERIALn_BAUD` | `460` | 460800 baud (match ELRS backpack rate) |
| `RSSI_TYPE` | `5` | Read RSSI from MAVLink (enables LQ/RSSI in OSD) |

**Stream rates** — keep these low. ELRS bandwidth is limited (~250 B/s at
500 Hz packet rate). Overloading the link causes packet loss, not faster
updates.

| Parameter | Value |
|-----------|-------|
| `SRn_EXTRA1` | `1` |
| `SRn_EXTRA2` | `1` |
| `SRn_EXTRA3` | `1` |
| `SRn_POSITION` | `1` |
| `SRn_RC_CHAN` | `1` |
| `SRn_EXT_STAT` | `1` |
| `SRn_ADSB` | `0` |
| `SRn_PARAMS` | `0` |
| `SRn_RAW_CTRL` | `0` |

Replace `n` in `SRn_` with the stream number matching your serial port
(e.g. `SR2_` for `SERIAL2`). Reboot the FC after saving.

## Step 2: ELRS Configuration

1. Power on the AX12 and connect to the model
2. Open the **ELRS Lua script** (System menu > ELRS Lua)
3. Set **Link Mode** to `MAVLink`
4. Scroll down and select **Save & Reboot**
5. **Power cycle the receiver** — the RX must reboot to enter MAVLink mode.
   A simple reconnect is not enough; pull RX power or reboot the FC

The TX module and RX negotiate the link mode on bind. Both sides must be
running 3.5.0+ or the MAVLink option will not appear.

## Step 3A: QGroundControl on the AX12

The AX12 has a dedicated MAVLink serial port at `/dev/ttyS1` (460800 baud).
ELRS telemetry data arrives here directly, bypassing the UMBUS protocol
entirely.

1. Install the **RadioMaster custom QGC build**:
   - GitHub: `github.com/Radiomaster-RC/qgroundcontrol`, release v5.0.8+
   - Install the APK via ADB or download directly on the AX12
2. Open QGC > Application Settings > Comm Links > Add
3. Configure:
   - Type: **Serial**
   - Device: `/dev/ttyS1`
   - Baud Rate: **460800**
4. Connect — you should see the vehicle appear within a few seconds

If QGC cannot open the port, it may need root. Launch from Termux:

```
su 0 am start -n org.mavlink.qgroundcontrol/org.mavlink.qgroundcontrol.QGCActivity
```

Or grant the serial port world-readable access:

```
su 0 chmod 666 /dev/ttyS1
```

## Step 3B: WiFi Alternative (Laptop GCS)

If you prefer to run your GCS on a laptop instead of the AX12 screen:

1. Enable **TX Backpack** WiFi in the ELRS Lua script
2. The TX Backpack creates a WiFi AP — connect your laptop to it
3. Open QGC/Mission Planner on the laptop
4. Add a UDP link on port **14550** (the Backpack forwards MAVLink there)

This gives you a full-size screen and keyboard for mission planning while
the AX12 handles the RF link. Latency adds ~5-15 ms over the WiFi hop.

## CRSF vs MAVLink: When to Use Each

| | CRSF (default) | MAVLink |
|---|---|---|
| **What you get** | Basic telemetry: RSSI, LQ, voltage, GPS, attitude | Full GCS: parameters, missions, logs, fence, rally |
| **On-device display** | Yaapu telemetry script (built into Flyshark) | QGroundControl |
| **Bandwidth** | Minimal — fits in standard CRSF frames | Needs dedicated link bandwidth |
| **FC configuration** | None (CRSF is default ELRS protocol) | Requires UART + stream rate setup |
| **Best for** | FPV flying, quick checks, LOS flying | Mission planning, tuning, autonomous ops |

**Rule of thumb:** Use CRSF for flying, switch to MAVLink when you need to
talk to the FC (tune PIDs, upload waypoints, review logs). You can switch
between modes in the ELRS Lua script without rebinding.

## Troubleshooting

**No vehicle appears in QGC:**
- Verify the UART number — `SERIALn` must match the physical UART the ELRS
  RX is wired to. Check with `SERIALn_PROTOCOL` readback in Mission Planner
- Confirm the RX LED shows solid (bound) not blinking (searching)
- Check that ELRS Lua shows Link Mode = MAVLink, not CRSF

**Data appears but drops frequently:**
- Lower stream rates — `SRn_EXTRA1/2/3` and `SRn_POSITION` at 1 Hz is the
  safe starting point. Only increase once the link is stable
- Use a DMA-capable UART on the FC. Non-DMA UARTs drop bytes at 460800.
  Check your FC's documentation — typically UART1 and UART2 are DMA-capable

**QGC says "serial port busy":**
- Another process has ttyS1 open. Check with:
  ```
  su 0 ls -la /proc/*/fd/* 2>/dev/null | grep ttyS1
  ```
- Kill the conflicting process or use the WiFi path instead

**ELRS Lua does not show MAVLink option:**
- TX and/or RX firmware is below 3.5.0. Flash both sides to 3.5.0+
- STM-based RX does not support MAVLink mode — swap to an ESP-based RX

**Parameters won't save / missions won't upload:**
- Set `SRn_PARAMS` to `10` temporarily during parameter-heavy sessions,
  then set it back to `0` for flight. Param transfer is slow at rate 0
  but it works — rate 10 just speeds it up

**WiFi Backpack not creating AP:**
- Backpack firmware must also be 3.5.0+. Update via ELRS Configurator
- Some Backpack versions need a power cycle after enabling WiFi mode
