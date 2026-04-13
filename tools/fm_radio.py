#!/usr/bin/env python3
"""
FM Radio controller for MT6631 on AX12 (MT8788).
Uses /dev/fm with the MTK WCN ioctl interface (magic 0xf5).

Discovered via strace of the stock FM Radio app:
  - Open /dev/fm
  - IOWR(0xf5, 0x00, 8) = POWERUP   (struct: err, band, space, hilo, freq_le16, pad, pad)
  - IOWR(0xf5, 0x01, 8) = TUNE/DOWN (same struct)
  - IOWR(0xf5, 0x0d, 8) = STATUS    (returns 8 bytes status)
  - IOWR(0xf5, 0x28, 8) = HW_INFO   (returns chip ID in first 2 bytes LE)

Struct fm_tune_parm (8 bytes):
  uint8_t  err;     # 0 = OK
  uint8_t  band;    # 0 = 87.5-108MHz
  uint8_t  space;   # 2 = 100kHz spacing
  uint8_t  hilo;    # 0 = auto
  uint16_t freq;    # frequency * 10, little-endian (e.g. 1000 = 100.0 MHz)
  uint8_t  pad[2];  # padding to 8 bytes
"""

import struct
import fcntl
import os
import sys
import signal
import time

# --- ioctl number calculation ---
def _IOWR(type, nr, size):
    return (3 << 30) | (size << 16) | (type << 8) | nr

# --- FM ioctl definitions (0xf5 magic, 8-byte struct) ---
FM_MAGIC = 0xf5
FM_PARM_SIZE = 8

FM_IOCTL_POWERUP   = _IOWR(FM_MAGIC, 0x00, FM_PARM_SIZE)
FM_IOCTL_POWERDOWN = _IOWR(FM_MAGIC, 0x01, FM_PARM_SIZE)
FM_IOCTL_TUNE      = _IOWR(FM_MAGIC, 0x02, FM_PARM_SIZE)  # needs testing
FM_IOCTL_SEEK      = _IOWR(FM_MAGIC, 0x03, FM_PARM_SIZE)
FM_IOCTL_SETVOL    = _IOWR(FM_MAGIC, 0x04, FM_PARM_SIZE)
FM_IOCTL_GETVOL    = _IOWR(FM_MAGIC, 0x05, FM_PARM_SIZE)
FM_IOCTL_MUTE      = _IOWR(FM_MAGIC, 0x06, FM_PARM_SIZE)
FM_IOCTL_GETRSSI   = _IOWR(FM_MAGIC, 0x07, FM_PARM_SIZE)
FM_IOCTL_STATUS    = _IOWR(FM_MAGIC, 0x0d, FM_PARM_SIZE)
FM_IOCTL_HWINFO    = _IOWR(FM_MAGIC, 0x28, FM_PARM_SIZE)

# Also try the 0x6d magic ioctls as fallback (traditional MTK FM)
FM_MAGIC_LEGACY = 0x6d

DEV_FM = "/dev/fm"


def pack_tune_parm(freq, band=0, space=2, hilo=0):
    """Pack struct fm_tune_parm (8 bytes).
    freq: frequency * 10 (e.g., 1000 for 100.0 MHz)
    """
    return struct.pack('<BBBBHBB', 0, band, space, hilo, freq, 0, 0)


def unpack_tune_parm(data):
    """Unpack struct fm_tune_parm (8 bytes)."""
    err, band, space, hilo, freq, _, _ = struct.unpack('<BBBBHBB', data[:8])
    return {'err': err, 'band': band, 'space': space, 'hilo': hilo, 'freq': freq}


def freq_str(freq_val):
    return f"{freq_val / 10:.1f}"


class FMRadio:
    def __init__(self):
        self.fd = None
        self.powered = False
        self.current_freq = 0

    def open(self):
        # Set SELinux context for FM access
        try:
            with open('/proc/self/attr/current', 'w') as f:
                f.write('u:r:platform_app:s0:c512,c768')
        except Exception:
            pass
        self.fd = os.open(DEV_FM, os.O_RDWR)
        print(f"[+] Opened {DEV_FM} (fd={self.fd})")

    def close(self):
        if self.fd is not None:
            if self.powered:
                self.powerdown()
            os.close(self.fd)
            self.fd = None

    def _ioctl(self, cmd, data=None):
        """Do an ioctl, return result bytes or None on failure."""
        if data is None:
            data = b'\x00' * FM_PARM_SIZE
        buf = bytearray(data)
        try:
            fcntl.ioctl(self.fd, cmd, buf)
            return bytes(buf)
        except OSError as e:
            return None

    def hw_info(self):
        result = self._ioctl(FM_IOCTL_HWINFO)
        if result:
            chip_id = struct.unpack('<H', result[:2])[0]
            print(f"[+] Chip ID: 0x{chip_id:04X} (MT{chip_id})")
            return chip_id
        print("[-] Failed to get HW info")
        return None

    def powerup(self, freq_mhz=100.0):
        freq = int(freq_mhz * 10)
        parm = pack_tune_parm(freq)
        print(f"[*] Powering up at {freq_str(freq)} MHz...")
        result = self._ioctl(FM_IOCTL_POWERUP, parm)
        if result:
            parsed = unpack_tune_parm(result)
            if parsed['err'] == 0:
                self.powered = True
                self.current_freq = parsed['freq']
                print(f"[+] FM powered up at {freq_str(parsed['freq'])} MHz")
                return True
            else:
                print(f"[-] Powerup error: {parsed['err']}")
        else:
            print("[-] Powerup ioctl failed")
        return False

    def powerdown(self):
        print("[*] Powering down...")
        parm = pack_tune_parm(self.current_freq or 1000)
        result = self._ioctl(FM_IOCTL_POWERDOWN, parm)
        self.powered = False
        if result:
            print("[+] Powered down")
        return result is not None

    def tune(self, freq_mhz):
        freq = int(freq_mhz * 10)
        parm = pack_tune_parm(freq)
        print(f"[*] Tuning to {freq_str(freq)} MHz...")
        # Try multiple possible tune ioctl numbers
        for nr in [0x02, 0x08, 0x01]:
            cmd = _IOWR(FM_MAGIC, nr, FM_PARM_SIZE)
            result = self._ioctl(cmd, parm)
            if result:
                parsed = unpack_tune_parm(result)
                if parsed['err'] == 0:
                    self.current_freq = parsed['freq']
                    print(f"[+] Tuned to {freq_str(parsed['freq'])} MHz (nr=0x{nr:02x})")
                    return True
        # Last resort: powerup to new freq
        print("[*] Tune ioctls failed, trying powerup to new freq...")
        return self.powerup(freq_mhz)

    def get_rssi(self):
        result = self._ioctl(FM_IOCTL_GETRSSI)
        if result:
            rssi = struct.unpack('<i', result[:4])[0]
            print(f"[+] RSSI: {rssi}")
            return rssi
        # Try alternate
        for nr in [0x07, 0x0a, 0x0b]:
            cmd = _IOWR(FM_MAGIC, nr, FM_PARM_SIZE)
            result = self._ioctl(cmd)
            if result:
                rssi = struct.unpack('<i', result[:4])[0]
                if rssi != 0:
                    print(f"[+] RSSI (nr=0x{nr:02x}): {rssi}")
                    return rssi
        return None

    def get_status(self):
        result = self._ioctl(FM_IOCTL_STATUS)
        if result:
            print(f"[+] Status: {result.hex()}")
        return result

    def probe_ioctls(self):
        """Probe all ioctl NR values 0x00-0x30 to discover the interface."""
        print("\n[*] Probing 0xf5 ioctls (nr 0x00 - 0x30)...")
        parm = pack_tune_parm(1000)  # 100.0 MHz
        for nr in range(0x31):
            cmd = _IOWR(FM_MAGIC, nr, FM_PARM_SIZE)
            buf = bytearray(parm)
            try:
                fcntl.ioctl(self.fd, cmd, buf)
                result = bytes(buf)
                print(f"  [+] nr=0x{nr:02x}: {result.hex()}")
            except OSError as e:
                errno_val = e.errno
                if errno_val == 1:  # EPERM
                    pass  # silently skip
                elif errno_val == 25:  # ENOTTY
                    pass  # not recognized
                else:
                    print(f"  [-] nr=0x{nr:02x}: errno={errno_val} ({e.strerror})")


def setup_audio_routing():
    """Configure audio mixer for FM playback through speaker."""
    import subprocess
    commands = [
        # Enable FM I2S path
        ("tinymix", "Audio_I2S1_Setting", "On"),
        ("tinymix", "Audio_i2s0_hd_Switch", "On"),
        # Set FM volume
        ("tinymix", "Audio FM I2S Volume", "65536"),
    ]
    for cmd in commands:
        try:
            subprocess.run(["su", "0"] + list(cmd), capture_output=True, timeout=5)
        except Exception:
            pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description='AX12 FM Radio (MT6631)')
    parser.add_argument('command', choices=['probe', 'listen', 'powerup', 'tune',
                                            'info', 'scan', 'status'],
                        help='Command')
    parser.add_argument('-f', '--freq', type=float, default=100.0,
                        help='Frequency in MHz (default: 100.0)')
    args = parser.parse_args()

    fm = FMRadio()
    try:
        fm.open()

        if args.command == 'probe':
            fm.hw_info()
            fm.probe_ioctls()

        elif args.command == 'info':
            fm.hw_info()
            fm.get_status()

        elif args.command == 'status':
            fm.get_status()

        elif args.command == 'powerup':
            fm.powerup(args.freq)
            fm.get_rssi()
            fm.get_status()
            print(f"\n[*] FM is on at {freq_str(fm.current_freq)} MHz")
            print("[*] Keeping device open (Ctrl+C to stop)...")
            try:
                while True:
                    time.sleep(5)
                    fm.get_status()
            except KeyboardInterrupt:
                print("\n[*] Shutting down...")

        elif args.command == 'listen':
            setup_audio_routing()
            if fm.powerup(args.freq):
                fm.get_rssi()
                print(f"\n[*] Listening to {freq_str(fm.current_freq)} MHz")
                print("[*] Press Ctrl+C to stop")
                try:
                    while True:
                        time.sleep(10)
                except KeyboardInterrupt:
                    print("\n[*] Shutting down...")

        elif args.command == 'tune':
            fm.powerup(args.freq)
            fm.get_rssi()

        elif args.command == 'scan':
            if not fm.powerup(87.5):
                print("[-] Can't power up, aborting scan")
                return
            print("\n[*] Scanning FM band (87.5 - 108.0 MHz)...")
            stations = []
            for f10 in range(875, 1081, 5):  # 500 kHz steps for speed
                freq_mhz = f10 / 10
                parm = pack_tune_parm(f10)
                result = fm._ioctl(FM_IOCTL_POWERUP, parm)
                if result:
                    parsed = unpack_tune_parm(result)
                    if parsed['err'] == 0:
                        rssi_result = fm._ioctl(FM_IOCTL_GETRSSI)
                        rssi = 0
                        if rssi_result:
                            rssi = struct.unpack('<i', rssi_result[:4])[0]
                        if rssi > -100 and rssi != 0:
                            stations.append((freq_mhz, rssi))
                            print(f"  {freq_mhz:6.1f} MHz  RSSI: {rssi}")
                time.sleep(0.05)
            print(f"\n[+] Found {len(stations)} potential stations")
            for freq, rssi in sorted(stations, key=lambda x: -x[1])[:10]:
                print(f"  {freq:6.1f} MHz  RSSI: {rssi}")

    finally:
        fm.close()


if __name__ == '__main__':
    main()
