# QGroundControl on AX12

The AX12 can run QGroundControl as a full ground control station using the MAVLink WiFi bridge.

## Prerequisites

- Rooted AX12 with Termux
- ELRS Backpack firmware 1.5.0+ (enables WiFi MAVLink forwarding)
- QGroundControl APK installed on the AX12

## Install QGC

RadioMaster provides a pre-built QGC APK:
1. Download from RadioMaster's QGC fork releases
2. Install: `su 0 pm install qgroundcontrol.apk`

Or use the community build:
```bash
wget -O ~/downloads/qgc.apk 'https://github.com/Radiomaster-RC/qgroundcontrol/releases/latest/download/QGroundControl.apk'
su 0 pm install ~/downloads/qgc.apk
```

## Connect via MAVLink Bridge

### Option A: ELRS Backpack WiFi (Recommended)

1. Connect AX12 to the ELRS Backpack WiFi AP (`ExpressLRS TX` or similar)
2. Start the bridge:
   ```bash
   python3 tools/mavlink_bridge.py bridge
   ```
3. In QGC: Settings > Comm Links > Add > TCP > Host: 127.0.0.1 > Port: 5760
4. Connect. You should see the vehicle appear.

### Option B: Serial (via ttyS1)

1. Ensure no other app is using ttyS1
2. Start serial bridge:
   ```bash
   su 0 python3 tools/mavlink_bridge.py serial
   ```
3. In QGC: Same TCP connection as above

## Test Without Hardware

Use the bridge test mode to verify QGC connects:
```bash
python3 tools/mavlink_bridge.py test --duration 300
```
This generates a synthetic quadcopter orbiting at 50m AGL in LOITER mode.
Open QGC and connect to TCP 127.0.0.1:5760 -- you should see the vehicle on the map.

## Monitor MAVLink Traffic

```bash
python3 tools/mavlink_bridge.py monitor
```
Shows decoded message types, rates, vehicle state without forwarding.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No vehicle in QGC | Check bridge is running, verify TCP connection in QGC comm links |
| Connection drops | Check WiFi stability, ELRS Backpack may need power cycle |
| High latency | Use monitor mode to check message rates, verify Backpack WiFi signal |
| Wrong vehicle type | Bridge auto-detects from HEARTBEAT. Check ELRS firmware version. |
