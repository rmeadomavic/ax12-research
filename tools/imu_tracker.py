#!/usr/bin/env python3
"""
imu_tracker.py - IMU-based head tracking / motion sensing for RadioMaster AX12

Reads accelerometer, gyroscope, and magnetometer data from the AX12's ICM-42607
IMU via a native C sensor reader (Android NDK ASensorManager API).

Features:
  - Real-time orientation (pitch, roll, heading)
  - Gyroscope angular rates
  - Motion detection with configurable threshold
  - JSON line output for piping to other tools
  - Live terminal display mode
  - Complementary filter for stable orientation

Hardware:
  - ICM-42607 accelerometer (125Hz) + gyroscope (10-400Hz)
  - Magnetometer (5-50Hz)
  - All accessed via Android SensorManager framework

Usage:
  python3 imu_tracker.py                    # Live display, 10 seconds
  python3 imu_tracker.py --duration 0       # Run forever
  python3 imu_tracker.py --rate 50          # 50Hz sample rate
  python3 imu_tracker.py --json             # JSON output only (for piping)
  python3 imu_tracker.py --motion           # Motion detection mode
  python3 imu_tracker.py --calibrate        # Calibrate zero position

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
CALIBRATION_FILE = SCRIPT_DIR / "imu_calibration.json"


def compile_sensor_reader():
    """Compile the native sensor reader if not already built."""
    if SENSOR_READER_BIN.exists():
        # Check if source is newer than binary
        if SENSOR_READER_SRC.exists():
            src_mtime = SENSOR_READER_SRC.stat().st_mtime
            bin_mtime = SENSOR_READER_BIN.stat().st_mtime
            if bin_mtime >= src_mtime:
                return True
        else:
            return True

    if not SENSOR_READER_SRC.exists():
        print("ERROR: sensor_reader.c not found", file=sys.stderr)
        return False

    print("Compiling sensor_reader...", file=sys.stderr)
    result = subprocess.run(
        ["clang", "-O2", "-o", str(SENSOR_READER_BIN),
         str(SENSOR_READER_SRC), "-landroid", "-llog", "-lm"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Compilation failed:\n{result.stderr}", file=sys.stderr)
        return False
    # Make executable
    os.chmod(SENSOR_READER_BIN, 0o755)
    print("Compiled successfully.", file=sys.stderr)
    return True


def load_calibration():
    """Load calibration offsets."""
    if CALIBRATION_FILE.exists():
        try:
            with open(CALIBRATION_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"pitch_offset": 0.0, "roll_offset": 0.0, "heading_offset": 0.0}


def save_calibration(cal):
    """Save calibration offsets."""
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(cal, f, indent=2)
    print(f"Calibration saved to {CALIBRATION_FILE}", file=sys.stderr)


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
        self.alpha = 0.98  # gyro weight (higher = more gyro, less accel)
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
            if 0 < dt < 1.0:  # sanity check
                gx, gy, gz = data["gyro"]
                accel_pitch = data.get("pitch", 0)
                accel_roll = data.get("roll", 0)

                # Integrate gyro
                gyro_pitch = self.filtered_pitch + gy * dt * (180.0 / math.pi)
                gyro_roll = self.filtered_roll + gx * dt * (180.0 / math.pi)

                # Complementary filter: blend gyro (fast) with accel (stable)
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
        cal_pitch = self.filtered_pitch - self.calibration["pitch_offset"]
        cal_roll = self.filtered_roll - self.calibration["roll_offset"]
        raw_heading = data.get("heading", 0)
        cal_heading = (raw_heading - self.calibration["heading_offset"]) % 360.0

        # Motion detection
        if "gyro" in data:
            gx, gy, gz = data["gyro"]
            gyro_mag = math.sqrt(gx*gx + gy*gy + gz*gz)
            self.in_motion = gyro_mag > self.motion_threshold
        else:
            gyro_mag = 0

        # Augmented data
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
        print("  AX12 IMU Head Tracker - RadioMaster AX12")
        print("  ICM-42607 Accelerometer + Gyroscope + Magnetometer")
        print("=" * 60)
        print("\nStarting sensor reader...\n")

    while tracker.running:
        sample = tracker.read_sample()
        if sample is None:
            if not tracker.running:
                break
            continue

        if sample.get("type") == "header":
            if not json_only:
                print(f"  Sensors active: {json.dumps(sample.get('sensors', {}))}")
                print(f"  Sample rate: {sample.get('rate_hz', '?')}Hz")
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

        # Move cursor up and overwrite
        if sample_count > 1:
            print(f"\033[14A", end="")

        print(f"  Time: {t:8.2f}s  Sample: {sample_count:6d}        ")
        print(f"  {'MOVING' if sample['motion'] else 'STILL ':6s}  "
              f"(threshold: {tracker.motion_threshold:.2f} rad/s)")
        print()
        print(f"  ---- Orientation (filtered) ----")
        print(f"  Pitch: {sample['filtered_pitch']:+8.2f} deg  "
              f"{'[^^^]' if sample['filtered_pitch'] > 15 else '[vvv]' if sample['filtered_pitch'] < -15 else '[ = ]'}")
        print(f"  Roll:  {sample['filtered_roll']:+8.2f} deg  "
              f"{'[ / ]' if sample['filtered_roll'] > 15 else '[ \\ ]' if sample['filtered_roll'] < -15 else '[ | ]'}")
        print(f"  Heading: {sample['cal_heading']:6.1f} deg  "
              f"({'N' if sample['cal_heading'] < 45 or sample['cal_heading'] > 315 else 'E' if sample['cal_heading'] < 135 else 'S' if sample['cal_heading'] < 225 else 'W'})")
        print()
        print(f"  ---- Raw Sensors ----")
        print(f"  Accel: X={accel[0]:+7.3f}  Y={accel[1]:+7.3f}  Z={accel[2]:+7.3f} m/s2")
        print(f"  Gyro:  X={gyro[0]:+7.4f}  Y={gyro[1]:+7.4f}  Z={gyro[2]:+7.4f} rad/s")
        print(f"  Mag:   X={mag[0]:+7.1f}  Y={mag[1]:+7.1f}  Z={mag[2]:+7.1f} uT")
        print(f"  Gyro magnitude: {sample['gyro_magnitude']:.4f} rad/s             ")

    if not json_only:
        print(f"\n  Done. {sample_count} samples collected.")
        if motion_mode:
            print(f"  Motion events detected: {motion_events}")


def calibrate(tracker):
    """Calibrate zero position by averaging readings for 3 seconds."""
    print("Calibration Mode", file=sys.stderr)
    print("Place the AX12 flat on a level surface.", file=sys.stderr)
    print("Collecting samples for 3 seconds...", file=sys.stderr)

    pitches = []
    rolls = []
    headings = []

    # Override duration to 3 seconds for calibration
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
        print("ERROR: No samples collected during calibration", file=sys.stderr)
        return

    cal = {
        "pitch_offset": sum(pitches) / len(pitches),
        "roll_offset": sum(rolls) / len(rolls),
        "heading_offset": sum(headings) / len(headings),
        "samples": len(pitches),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
    }

    save_calibration(cal)
    print(f"\nCalibration complete ({len(pitches)} samples):", file=sys.stderr)
    print(f"  Pitch offset: {cal['pitch_offset']:.2f} deg", file=sys.stderr)
    print(f"  Roll offset:  {cal['roll_offset']:.2f} deg", file=sys.stderr)
    print(f"  Heading offset: {cal['heading_offset']:.1f} deg", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="AX12 IMU Head Tracker - real-time orientation from ICM-42607"
    )
    parser.add_argument("--duration", "-d", type=int, default=10,
                        help="Duration in seconds (0=continuous, default=10)")
    parser.add_argument("--rate", "-r", type=int, default=25,
                        help="Sample rate in Hz (default=25)")
    parser.add_argument("--json", "-j", action="store_true",
                        help="JSON-only output (no terminal graphics)")
    parser.add_argument("--motion", "-m", action="store_true",
                        help="Motion detection mode - only print when moving")
    parser.add_argument("--threshold", "-t", type=float, default=0.5,
                        help="Motion detection threshold in rad/s (default=0.5)")
    parser.add_argument("--calibrate", "-c", action="store_true",
                        help="Calibrate zero position")
    parser.add_argument("--no-filter", action="store_true",
                        help="Disable complementary filter (raw accel angles)")
    args = parser.parse_args()

    tracker = IMUTracker(
        rate_hz=args.rate,
        duration_sec=args.duration
    )
    tracker.motion_threshold = args.threshold

    if args.no_filter:
        tracker.alpha = 0.0  # Pure accelerometer

    if args.calibrate:
        calibrate(tracker)
        return

    # Setup signal handler for clean exit
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
