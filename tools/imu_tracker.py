#!/usr/bin/env python3
"""
imu_tracker.py - IMU-based head tracking / motion sensing for RadioMaster AX12

Reads accelerometer, gyroscope, and magnetometer data from the AX12's ICM-42607
IMU and provides real-time orientation tracking with complementary filtering.

Architecture:
  sensor_reader (C binary) -> stdout JSON lines -> imu_tracker.py (Python)

  The C binary uses Android's NDK ASensorManager API to read the ICM-42607.
  Python handles filtering, calibration, display, and higher-level tracking.

Hardware:
  - ICM-42607 accelerometer (125Hz) + gyroscope (10-400Hz) on i2c bus 1 @ 0x10
  - Magnetometer (5-50Hz)
  - SoC: MT6771/MT8788, managed via MTK SCP (sensor co-processor)

KNOWN ISSUE (firmware V1.1, 2026.3.23):
  The MTK sensor HAL expects sysfs control nodes at /sys/class/sensor/m_acc_misc/
  and device nodes at /dev/m_acc_misc. These are NOT created on the current AX12
  firmware, so sensor batch/enable operations fail with EPERM. The hardware is
  functional (ICM-42607 detected on i2c), but the kernel-HAL bridge is broken.
  Run `python3 imu_tracker.py --diagnose` to see full details.

Usage:
  python3 imu_tracker.py                    # Live display, 10 seconds
  python3 imu_tracker.py --duration 0       # Run forever
  python3 imu_tracker.py --rate 50          # 50Hz sample rate
  python3 imu_tracker.py --json             # JSON output only (for piping)
  python3 imu_tracker.py --motion           # Motion detection mode
  python3 imu_tracker.py --calibrate        # Calibrate zero position
  python3 imu_tracker.py --diagnose         # Full sensor hardware diagnostics

Requires: sensor_reader binary (auto-compiled from sensor_reader.c)
"""

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Path constants
SCRIPT_DIR = Path(__file__).parent.resolve()
SENSOR_READER_SRC = SCRIPT_DIR / "sensor_reader.c"
SENSOR_READER_BIN = SCRIPT_DIR / "sensor_reader"
SENSOR_READER_DEX = SCRIPT_DIR / "SensorReader.dex"
CALIBRATION_FILE = SCRIPT_DIR / "imu_calibration.json"


def compile_sensor_reader():
    """Compile the native sensor reader if needed."""
    if SENSOR_READER_BIN.exists():
        if SENSOR_READER_SRC.exists():
            if SENSOR_READER_BIN.stat().st_mtime >= SENSOR_READER_SRC.stat().st_mtime:
                return True
        else:
            return True

    if not SENSOR_READER_SRC.exists():
        print("ERROR: sensor_reader.c not found at " + str(SENSOR_READER_SRC), file=sys.stderr)
        return False

    print("Compiling sensor_reader...", file=sys.stderr)
    result = subprocess.run(
        ["clang", "-O2", "-o", str(SENSOR_READER_BIN),
         str(SENSOR_READER_SRC), "-landroid", "-llog", "-lm", "-ldl"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Compilation failed:\n{result.stderr}", file=sys.stderr)
        return False
    os.chmod(SENSOR_READER_BIN, 0o755)
    print("Compiled successfully.", file=sys.stderr)
    return True


def load_calibration():
    """Load calibration offsets from file."""
    if CALIBRATION_FILE.exists():
        try:
            with open(CALIBRATION_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"pitch_offset": 0.0, "roll_offset": 0.0, "heading_offset": 0.0}


def save_calibration(cal):
    """Save calibration offsets to file."""
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(cal, f, indent=2)
    print(f"Calibration saved to {CALIBRATION_FILE}", file=sys.stderr)


def run_cmd(cmd, timeout=10):
    """Run a shell command and return stdout."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def diagnose_sensors():
    """Run comprehensive sensor diagnostics."""
    print("=" * 65)
    print("  AX12 IMU Sensor Diagnostics")
    print("  ICM-42607 on MT6771/MT8788 (MediaTek)")
    print("=" * 65)
    print()

    # 1. Hardware detection
    print("[1] Hardware Detection (I2C)")
    print("-" * 40)

    i2c_name = run_cmd("cat /sys/bus/i2c/devices/1-0010/name 2>/dev/null")
    if i2c_name:
        print(f"  i2c bus 1, addr 0x10: {i2c_name}")
    else:
        print("  i2c device 1-0010: NOT FOUND")

    # Check i2c driver binding
    accel_drv = run_cmd("ls /sys/bus/i2c/drivers/ICM42607_ACCEL/ 2>/dev/null")
    gyro_drv = run_cmd("ls /sys/bus/i2c/drivers/ICM42607_GYRO/ 2>/dev/null")
    print(f"  ICM42607_ACCEL driver: {'loaded' if accel_drv else 'NOT FOUND'}")
    print(f"  ICM42607_GYRO driver:  {'loaded' if gyro_drv else 'NOT FOUND'}")

    # Device tree
    dt = run_cmd("ls /sys/firmware/devicetree/base/i2c@11011000/icm42607_a@10 2>/dev/null")
    print(f"  Device tree entry:     {'present' if dt else 'NOT FOUND'}")
    print()

    # 2. Kernel configuration
    print("[2] Kernel Configuration")
    print("-" * 40)
    for key in ["CUSTOM_KERNEL_ACCELEROMETER", "CUSTOM_KERNEL_GYROSCOPE",
                "CUSTOM_KERNEL_MAGNETOMETER", "MTK_SENSOR_SUPPORT",
                "MTK_SENSORS_1_0", "MTK_ICM42607_A", "MTK_ICM42607_G",
                "I2C_CHARDEV"]:
        val = run_cmd(f"su 0 sh -c 'zcat /proc/config.gz | grep CONFIG_{key}='")
        if not val:
            val = run_cmd(f"su 0 sh -c 'zcat /proc/config.gz | grep CONFIG_{key}'")
        status = val.split("=")[-1] if "=" in val else ("not set" if val else "not found")
        print(f"  CONFIG_{key}: {status}")
    print()

    # 3. MTK Sensor HAL paths (the critical check)
    print("[3] MTK Sensor HAL Paths (CRITICAL)")
    print("-" * 40)
    hal_paths = {
        "/dev/m_acc_misc": "Accelerometer device",
        "/dev/m_gyro_misc": "Gyroscope device",
        "/dev/m_mag_misc": "Magnetometer device",
        "/dev/sensorlist": "Sensor list device",
        "/sys/class/sensor/m_acc_misc/": "Accel sysfs control",
        "/sys/class/sensor/m_gyro_misc/": "Gyro sysfs control",
        "/sys/class/sensor/m_mag_misc/": "Mag sysfs control",
    }
    all_missing = True
    for path, desc in hal_paths.items():
        exists = run_cmd(f"su 0 ls {path} 2>/dev/null")
        status = "FOUND" if exists else "MISSING"
        if exists:
            all_missing = False
        print(f"  {path}: {status}  ({desc})")

    if all_missing:
        print()
        print("  *** ALL HAL PATHS MISSING ***")
        print("  The MTK sensor driver did not create the device nodes")
        print("  required by the HAL. This is a firmware/kernel issue.")
        print("  The ICM-42607 hardware is present but inaccessible.")
    print()

    # 4. Android SensorService
    print("[4] Android SensorService")
    print("-" * 40)
    svc = run_cmd("su 0 dumpsys sensorservice 2>/dev/null | head -20")
    if svc:
        for line in svc.split("\n"):
            if any(k in line.lower() for k in ["sensor list", "total", "running",
                                                 "active sensor", "active conn"]):
                print(f"  {line.strip()}")
    events = run_cmd("su 0 dumpsys sensorservice 2>/dev/null | grep -A1 'Recent Sensor events'")
    has_events = events and ":" in events.split("\n")[-1] if events else False
    print(f"  Recent sensor events: {'YES' if has_events else 'NONE'}")
    print()

    # 5. Sensor HAL library
    print("[5] Sensor HAL Library")
    print("-" * 40)
    hal_so = run_cmd("ls /vendor/lib64/hw/sensors.mt6771.so 2>/dev/null")
    print(f"  sensors.mt6771.so: {'present' if hal_so else 'NOT FOUND'}")
    hidl = run_cmd("ls /vendor/lib64/hw/android.hardware.sensors@1.0-impl-mediatek.so 2>/dev/null")
    print(f"  HIDL sensors impl: {'present' if hidl else 'NOT FOUND'}")
    print()

    # 6. SCP (Sensor Co-Processor)
    print("[6] SCP (Sensor Co-Processor)")
    print("-" * 40)
    scp = run_cmd("ls -la /dev/scp 2>/dev/null")
    print(f"  /dev/scp: {scp if scp else 'NOT FOUND'}")
    print()

    # 7. Summary and recommendations
    print("[7] Summary")
    print("=" * 65)
    if all_missing:
        print("  STATUS: SENSORS NOT FUNCTIONAL")
        print()
        print("  The ICM-42607 IMU hardware is physically present and detected")
        print("  on I2C bus 1 (address 0x10), and the kernel drivers are compiled")
        print("  in (CONFIG_MTK_ICM42607_A=y, CONFIG_MTK_ICM42607_G=y).")
        print()
        print("  However, the MTK sensor middleware layer that creates the device")
        print("  nodes (/dev/m_acc_misc) and sysfs control paths")
        print("  (/sys/class/sensor/m_acc_misc/) required by the sensor HAL")
        print("  (sensors.mt6771.so) is NOT functioning.")
        print()
        print("  This means no Android app -- including this tool -- can read")
        print("  sensor data through the standard Android SensorManager API.")
        print()
        print("  Additionally, CONFIG_I2C_CHARDEV is not set, so direct I2C")
        print("  userspace access (/dev/i2c-*) is also unavailable.")
        print()
        print("  POSSIBLE FIXES:")
        print("  1. RadioMaster firmware update that fixes the sensor driver")
        print("     initialization (most likely path)")
        print("  2. Custom kernel with CONFIG_I2C_CHARDEV=y to enable direct")
        print("     I2C access to the ICM-42607")
        print("  3. Magisk module to load a patched sensor driver")
    else:
        print("  STATUS: Some HAL paths exist - sensors may be partially working")
        print("  Try: python3 imu_tracker.py --duration 5")


class IMUTracker:
    """Real-time IMU tracking with complementary filter."""

    def __init__(self, rate_hz=25, duration_sec=10, calibration=None):
        self.rate_hz = rate_hz
        self.duration_sec = duration_sec
        self.calibration = calibration or load_calibration()
        self.process = None
        self.running = False

        # Complementary filter state
        self.filtered_pitch = 0.0
        self.filtered_roll = 0.0
        self.alpha = 0.98  # gyro weight (higher = more gyro, less accel drift)
        self.last_t = None

        # Motion detection
        self.motion_threshold = 0.5  # rad/s total gyro magnitude
        self.in_motion = False

    def start(self):
        """Start the native sensor reader subprocess."""
        if not compile_sensor_reader():
            return False

        cmd = [str(SENSOR_READER_BIN), str(self.duration_sec), str(self.rate_hz)]
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1
            )
        except OSError as e:
            print(f"ERROR: Cannot start sensor_reader: {e}", file=sys.stderr)
            return False

        self.running = True

        # Check for early exit (sensor enable failure returns exit code 2)
        time.sleep(0.5)
        if self.process.poll() is not None:
            stderr = self.process.stderr.read()
            if self.process.returncode == 2:
                print("\nSensor activation failed. The MTK sensor HAL is not functional.", file=sys.stderr)
                print("Run: python3 imu_tracker.py --diagnose", file=sys.stderr)
                print("\nDiagnostic output:", file=sys.stderr)
                print(stderr, file=sys.stderr)
                self.running = False
                return False
            elif self.process.returncode != 0:
                print(f"sensor_reader exited with code {self.process.returncode}", file=sys.stderr)
                print(stderr, file=sys.stderr)
                self.running = False
                return False

        return True

    def stop(self):
        """Stop the sensor reader."""
        self.running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def read_sample(self):
        """Read one sample from the sensor reader. Returns dict or None."""
        if not self.process or self.process.poll() is not None:
            self.running = False
            return None

        line = self.process.stdout.readline()
        if not line:
            return None

        try:
            data = json.loads(line.strip())
        except json.JSONDecodeError:
            return None

        # Skip header
        if data.get("type") == "header":
            return data

        # Apply complementary filter
        t = data.get("t", 0)
        if self.last_t is not None and "gyro" in data:
            dt = t - self.last_t
            if 0 < dt < 1.0:
                gx, gy, gz = data["gyro"]
                accel_pitch = data.get("pitch", 0)
                accel_roll = data.get("roll", 0)

                gyro_pitch = self.filtered_pitch + gy * dt * (180.0 / math.pi)
                gyro_roll = self.filtered_roll + gx * dt * (180.0 / math.pi)

                self.filtered_pitch = self.alpha * gyro_pitch + (1 - self.alpha) * accel_pitch
                self.filtered_roll = self.alpha * gyro_roll + (1 - self.alpha) * accel_roll
            else:
                self.filtered_pitch = data.get("pitch", 0)
                self.filtered_roll = data.get("roll", 0)
        else:
            self.filtered_pitch = data.get("pitch", 0)
            self.filtered_roll = data.get("roll", 0)
        self.last_t = t

        # Apply calibration offsets
        cal_pitch = self.filtered_pitch - self.calibration.get("pitch_offset", 0)
        cal_roll = self.filtered_roll - self.calibration.get("roll_offset", 0)
        raw_heading = data.get("heading", 0)
        cal_heading = (raw_heading - self.calibration.get("heading_offset", 0)) % 360.0

        # Motion detection from gyro magnitude
        if "gyro" in data:
            gx, gy, gz = data["gyro"]
            gyro_mag = math.sqrt(gx*gx + gy*gy + gz*gz)
            self.in_motion = gyro_mag > self.motion_threshold
        else:
            gyro_mag = 0

        # Augmented output
        data["filtered_pitch"] = round(cal_pitch, 2)
        data["filtered_roll"] = round(cal_roll, 2)
        data["cal_heading"] = round(cal_heading, 1)
        data["motion"] = self.in_motion
        data["gyro_magnitude"] = round(gyro_mag, 4)

        return data


def display_live(tracker, json_only=False, motion_mode=False):
    """Live terminal display of IMU data."""
    sample_count = 0
    motion_events = 0

    if not json_only:
        print("\033[2J\033[H", end="")  # Clear screen
        print("=" * 60)
        print("  AX12 IMU Head Tracker")
        print("  ICM-42607 Accelerometer + Gyroscope + Magnetometer")
        print("=" * 60)
        print("\nWaiting for sensor data...\n")

    while tracker.running:
        sample = tracker.read_sample()
        if sample is None:
            if not tracker.running:
                break
            continue

        if sample.get("type") == "header":
            if not json_only:
                sensors = sample.get("sensors", {})
                print(f"  Sensors: accel={sensors.get('accel', '?')} "
                      f"gyro={sensors.get('gyro', '?')} "
                      f"mag={sensors.get('mag', '?')}")
                print(f"  Rate: {sample.get('rate_hz', '?')}Hz")
                if sample.get("chip"):
                    print(f"  Chip: {sample['chip']} (WHO_AM_I={sample.get('who_am_i', '?')})")
                print()
            continue

        sample_count += 1

        if json_only:
            print(json.dumps(sample))
            sys.stdout.flush()
            continue

        if motion_mode:
            if sample.get("motion"):
                motion_events += 1
                print(f"  MOTION #{motion_events:4d} | "
                      f"pitch={sample['filtered_pitch']:+7.1f} "
                      f"roll={sample['filtered_roll']:+7.1f} "
                      f"heading={sample['cal_heading']:5.1f} | "
                      f"gyro_mag={sample['gyro_magnitude']:.3f} rad/s")
            continue

        # Live updating display
        t = sample.get("t", 0)
        accel = sample.get("accel", [0, 0, 0])
        gyro = sample.get("gyro", [0, 0, 0])
        mag = sample.get("mag", [0, 0, 0])

        if sample_count > 1:
            print(f"\033[14A", end="")

        motion_str = "MOVING" if sample.get("motion") else "STILL "
        print(f"  Time: {t:8.2f}s  Sample: {sample_count:6d}        ")
        print(f"  {motion_str}  (threshold: {tracker.motion_threshold:.2f} rad/s)")
        print()
        print(f"  ---- Orientation (filtered) ----")
        pitch = sample["filtered_pitch"]
        roll = sample["filtered_roll"]
        heading = sample["cal_heading"]
        pitch_icon = "[^^^]" if pitch > 15 else "[vvv]" if pitch < -15 else "[ = ]"
        roll_icon = "[ / ]" if roll > 15 else "[ \\ ]" if roll < -15 else "[ | ]"
        compass = "N" if heading < 45 or heading > 315 else "E" if heading < 135 else "S" if heading < 225 else "W"
        print(f"  Pitch: {pitch:+8.2f} deg  {pitch_icon}")
        print(f"  Roll:  {roll:+8.2f} deg  {roll_icon}")
        print(f"  Heading: {heading:6.1f} deg  ({compass})")
        print()
        print(f"  ---- Raw Sensors ----")
        print(f"  Accel: X={accel[0]:+7.3f}  Y={accel[1]:+7.3f}  Z={accel[2]:+7.3f} m/s2")
        print(f"  Gyro:  X={gyro[0]:+7.4f}  Y={gyro[1]:+7.4f}  Z={gyro[2]:+7.4f} rad/s")
        print(f"  Mag:   X={mag[0]:+7.1f}  Y={mag[1]:+7.1f}  Z={mag[2]:+7.1f} uT")
        temp = sample.get("temp")
        temp_str = f"  Temp:  {temp:.1f} C" if temp else ""
        print(f"  Gyro magnitude: {sample['gyro_magnitude']:.4f} rad/s  {temp_str}          ")

    if not json_only:
        print(f"\n  Done. {sample_count} samples collected.")
        if motion_mode:
            print(f"  Motion events: {motion_events}")


def calibrate(tracker):
    """Calibrate zero position by averaging readings for 3 seconds."""
    print("Calibration Mode", file=sys.stderr)
    print("Place the AX12 flat on a level surface.", file=sys.stderr)
    print("Collecting samples for 3 seconds...", file=sys.stderr)

    pitches = []
    rolls = []
    headings = []

    tracker.duration_sec = 3
    if not tracker.start():
        return

    while tracker.running:
        sample = tracker.read_sample()
        if sample is None:
            if not tracker.running:
                break
            continue
        if sample.get("type") == "header":
            continue
        pitches.append(sample.get("pitch", 0))
        rolls.append(sample.get("roll", 0))
        headings.append(sample.get("heading", 0))

    tracker.stop()

    if not pitches:
        print("ERROR: No samples collected", file=sys.stderr)
        return

    cal = {
        "pitch_offset": sum(pitches) / len(pitches),
        "roll_offset": sum(rolls) / len(rolls),
        "heading_offset": sum(headings) / len(headings),
        "samples": len(pitches),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    save_calibration(cal)
    print(f"\nCalibration ({len(pitches)} samples):", file=sys.stderr)
    print(f"  Pitch offset: {cal['pitch_offset']:.2f} deg", file=sys.stderr)
    print(f"  Roll offset:  {cal['roll_offset']:.2f} deg", file=sys.stderr)
    print(f"  Heading offset: {cal['heading_offset']:.1f} deg", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="AX12 IMU Head Tracker - real-time orientation from ICM-42607",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s                      Live display for 10 seconds
  %(prog)s -d 0 -r 50           Continuous at 50Hz
  %(prog)s --json | jq .pitch   Stream pitch values
  %(prog)s --motion -t 0.3      Sensitive motion detection
  %(prog)s --diagnose           Debug sensor issues
"""
    )
    parser.add_argument("--duration", "-d", type=int, default=10,
                        help="Duration in seconds (0=continuous, default=10)")
    parser.add_argument("--rate", "-r", type=int, default=25,
                        help="Sample rate in Hz (default=25)")
    parser.add_argument("--json", "-j", action="store_true",
                        help="JSON-only output (no terminal UI)")
    parser.add_argument("--motion", "-m", action="store_true",
                        help="Motion detection mode")
    parser.add_argument("--threshold", "-t", type=float, default=0.5,
                        help="Motion threshold in rad/s (default=0.5)")
    parser.add_argument("--calibrate", "-c", action="store_true",
                        help="Calibrate zero position")
    parser.add_argument("--no-filter", action="store_true",
                        help="Disable complementary filter")
    parser.add_argument("--diagnose", action="store_true",
                        help="Run sensor diagnostics and exit")
    args = parser.parse_args()

    if args.diagnose:
        diagnose_sensors()
        return

    tracker = IMUTracker(rate_hz=args.rate, duration_sec=args.duration)
    tracker.motion_threshold = args.threshold
    if args.no_filter:
        tracker.alpha = 0.0

    if args.calibrate:
        calibrate(tracker)
        return

    def cleanup(sig, frame):
        tracker.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    if not tracker.start():
        sys.exit(1)

    try:
        display_live(tracker, json_only=args.json, motion_mode=args.motion)
    finally:
        tracker.stop()


if __name__ == "__main__":
    main()
