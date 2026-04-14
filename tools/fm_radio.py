#!/usr/bin/env python3
"""
FM Radio controller for MT6631 on RadioMaster AX12 (MT8788).
Uses /dev/fm with the MTK WCN ioctl interface (magic 0xf5).

Requires root: su 0 python3 fm_radio.py <command> [options]

Discovered ioctl map (from kernel module strings + probing):
  nr=0x00  POWERUP       struct fm_tune_parm (8 bytes)
  nr=0x01  POWERDOWN     struct fm_tune_parm (8 bytes)
  nr=0x02  TUNE          struct fm_tune_parm (8 bytes)
  nr=0x04  SETVOL        uint32_t volume (in 8-byte buf)
  nr=0x05  GETVOL        uint32_t volume (in 8-byte buf)
  nr=0x06  MUTE          uint32_t mute (in 8-byte buf)
  nr=0x07  GETRSSI       int16_t rssi (in 8-byte buf)
  nr=0x0a  GETCHIPID     uint16_t chipid (in 8-byte buf)
  nr=0x0b  GETMONOSTERO  uint16_t mono/stereo
  nr=0x0d  GET_STATUS    8 bytes status
  nr=0x0e  RDS_ONOFF     uint32_t on/off
  nr=0x0f  RDS_SUPPORT   uint32_t supported
  nr=0x10  GETGOODBCNT   uint32_t count
  nr=0x11  GETBADBNT     uint32_t count
  nr=0x13  IS_FM_POWERED_UP  uint32_t powered
  nr=0x28  GET_HW_INFO   uint16_t chipid + hw info
  nr=0x29  GET_I2S_INFO  i2s config

struct fm_tune_parm (8 bytes):
  uint8_t  err;     # 0 = OK
  uint8_t  band;    # 0 = 87.5-108MHz (US/EU), 1 = 76-90MHz (JP), 2 = 76-108MHz
  uint8_t  space;   # 0 = 50kHz, 1 = 100kHz, 2 = 200kHz
  uint8_t  hilo;    # 0 = auto side injection
  uint16_t freq;    # frequency * 10, LE (e.g. 1011 = 101.1 MHz)
  uint8_t  pad[2];  # padding

Audio routing (tinymix on mt-snd-card):
  Audio_I2S1_Setting     -> On  (FM I2S data path)
  Audio_i2s0_hd_Switch   -> On  (I2S HD mode)
  Audio FM I2S Volume    -> 0-524288 (65536 = reasonable default)
  Audio Mrgrx Volume     -> 0-524288 (merger Rx for FM)
  Speaker_Amp_Switch     -> On  (internal speaker)
  Ext_Speaker_Amp_Switch -> On  (external speaker amp if present)

Note: MT6631 FM typically uses headphone cable as antenna.
      Audio can be routed to speaker even without headphones,
      but signal reception improves dramatically with them.
"""

import struct
import fcntl
import os
import sys
import subprocess
import time
import argparse

# ============================================================
# ioctl helpers
# ============================================================

def _IOWR(magic, nr, size):
    """Linux _IOWR macro: direction=3 (read+write)."""
    return (3 << 30) | (size << 16) | (magic << 8) | nr

FM_MAGIC = 0xf5
FM_PARM_SIZE = 8

# ioctl command numbers
FM_IOCTL_POWERUP      = _IOWR(FM_MAGIC, 0x00, FM_PARM_SIZE)
FM_IOCTL_POWERDOWN    = _IOWR(FM_MAGIC, 0x01, FM_PARM_SIZE)
FM_IOCTL_TUNE         = _IOWR(FM_MAGIC, 0x02, FM_PARM_SIZE)
FM_IOCTL_SEEK         = _IOWR(FM_MAGIC, 0x03, FM_PARM_SIZE)
FM_IOCTL_SETVOL       = _IOWR(FM_MAGIC, 0x04, FM_PARM_SIZE)
FM_IOCTL_GETVOL       = _IOWR(FM_MAGIC, 0x05, FM_PARM_SIZE)
FM_IOCTL_MUTE         = _IOWR(FM_MAGIC, 0x06, FM_PARM_SIZE)
FM_IOCTL_GETRSSI      = _IOWR(FM_MAGIC, 0x07, FM_PARM_SIZE)
FM_IOCTL_GETCHIPID    = _IOWR(FM_MAGIC, 0x0a, FM_PARM_SIZE)
FM_IOCTL_GETMONOSTEREO = _IOWR(FM_MAGIC, 0x0b, FM_PARM_SIZE)
FM_IOCTL_GET_STATUS   = _IOWR(FM_MAGIC, 0x0d, FM_PARM_SIZE)
FM_IOCTL_RDS_ONOFF    = _IOWR(FM_MAGIC, 0x0e, FM_PARM_SIZE)
FM_IOCTL_RDS_SUPPORT  = _IOWR(FM_MAGIC, 0x0f, FM_PARM_SIZE)
FM_IOCTL_GETGOODBCNT  = _IOWR(FM_MAGIC, 0x10, FM_PARM_SIZE)
FM_IOCTL_GETBADBNT    = _IOWR(FM_MAGIC, 0x11, FM_PARM_SIZE)
FM_IOCTL_IS_POWERED   = _IOWR(FM_MAGIC, 0x13, FM_PARM_SIZE)
FM_IOCTL_GET_HW_INFO  = _IOWR(FM_MAGIC, 0x28, FM_PARM_SIZE)
FM_IOCTL_GET_I2S_INFO = _IOWR(FM_MAGIC, 0x29, FM_PARM_SIZE)

DEV_FM = "/dev/fm"

# Band limits (freq * 10)
BAND_US_EU = (875, 1080)   # 87.5 - 108.0 MHz
BAND_JP    = (760, 900)    # 76.0 - 90.0 MHz
BAND_WIDE  = (760, 1080)   # 76.0 - 108.0 MHz

# Scan thresholds
RSSI_THRESHOLD = -105  # Stations above this RSSI are "found"
SEEK_STEP = 1          # 100kHz steps (freq*10 increment of 1)


def pack_tune_parm(freq, band=0, space=1, hilo=0):
    """Pack struct fm_tune_parm (8 bytes).
    freq: frequency * 10 (e.g., 1011 for 101.1 MHz)
    band: 0=US/EU(87.5-108), 1=JP(76-90), 2=wide(76-108)
    space: 0=50kHz, 1=100kHz, 2=200kHz
    """
    return struct.pack('<BBBBHBB', 0, band, space, hilo, freq, 0, 0)


def unpack_tune_parm(data):
    """Unpack struct fm_tune_parm (8 bytes)."""
    err, band, space, hilo, freq, p1, p2 = struct.unpack('<BBBBHBB', data[:8])
    return {'err': err, 'band': band, 'space': space, 'hilo': hilo, 'freq': freq}


def freq_to_str(freq_val):
    """Convert freq*10 to display string."""
    return "%.1f" % (freq_val / 10.0)


def p(msg):
    """Print with immediate flush."""
    sys.stdout.write(str(msg) + "\n")
    sys.stdout.flush()


# ============================================================
# FMRadio class
# ============================================================

class FMRadio:
    """MT6631 FM Radio controller via /dev/fm ioctls."""

    def __init__(self):
        self.fd = None
        self.powered = False
        self.current_freq = 0
        self.chip_id = 0
        self.band = BAND_US_EU

    def open(self):
        """Open /dev/fm device."""
        self.fd = os.open(DEV_FM, os.O_RDWR)
        p("[+] Opened %s (fd=%d)" % (DEV_FM, self.fd))

    def close(self):
        """Close device, powering down if needed."""
        if self.fd is not None:
            if self.powered:
                self.powerdown()
            os.close(self.fd)
            self.fd = None

    def _ioctl(self, cmd, data=None):
        """Execute ioctl, return result bytes or None on failure."""
        if data is None:
            data = b'\x00' * FM_PARM_SIZE
        buf = bytearray(data)
        try:
            fcntl.ioctl(self.fd, cmd, buf)
            return bytes(buf)
        except OSError:
            return None

    def _ioctl_or_raise(self, cmd, data=None):
        """Execute ioctl, raise on failure."""
        if data is None:
            data = b'\x00' * FM_PARM_SIZE
        buf = bytearray(data)
        fcntl.ioctl(self.fd, cmd, buf)
        return bytes(buf)

    # --- Core operations ---

    def hw_info(self):
        """Get hardware info (chip ID)."""
        result = self._ioctl(FM_IOCTL_GET_HW_INFO)
        if result:
            self.chip_id = struct.unpack('<H', result[:2])[0]
            p("[+] Chip: MT%d (0x%04X)" % (self.chip_id, self.chip_id))
            return self.chip_id
        p("[-] Failed to get HW info")
        return None

    def powerup(self, freq_mhz=100.0):
        """Power up FM receiver at given frequency."""
        freq = int(freq_mhz * 10)
        parm = pack_tune_parm(freq)
        p("[*] Powering up at %s MHz..." % freq_to_str(freq))
        result = self._ioctl(FM_IOCTL_POWERUP, parm)
        if result:
            parsed = unpack_tune_parm(result)
            if parsed['err'] == 0:
                self.powered = True
                self.current_freq = parsed['freq']
                p("[+] FM powered up at %s MHz" % freq_to_str(self.current_freq))
                return True
            else:
                p("[-] Powerup error: %d" % parsed['err'])
        else:
            p("[-] Powerup ioctl failed")
        return False

    def powerdown(self):
        """Power down FM receiver."""
        p("[*] Powering down...")
        parm = pack_tune_parm(self.current_freq or 1000)
        result = self._ioctl(FM_IOCTL_POWERDOWN, parm)
        self.powered = False
        if result:
            p("[+] Powered down")
        return result is not None

    def tune(self, freq_mhz):
        """Tune to a specific frequency (FM must be powered up)."""
        freq = int(freq_mhz * 10)
        parm = pack_tune_parm(freq)
        result = self._ioctl(FM_IOCTL_TUNE, parm)
        if result:
            parsed = unpack_tune_parm(result)
            if parsed['err'] == 0:
                self.current_freq = parsed['freq']
                return True
        # If tune fails, try powerdown + powerup cycle
        self._ioctl(FM_IOCTL_POWERDOWN, pack_tune_parm(self.current_freq or 1000))
        result = self._ioctl(FM_IOCTL_POWERUP, parm)
        if result:
            parsed = unpack_tune_parm(result)
            if parsed['err'] == 0:
                self.current_freq = parsed['freq']
                self.powered = True
                return True
        return False

    def get_rssi(self):
        """Get current signal strength (RSSI)."""
        result = self._ioctl(FM_IOCTL_GETRSSI)
        if result:
            rssi = struct.unpack('<h', result[:2])[0]
            return rssi
        return None

    def get_volume(self):
        """Get current volume level."""
        result = self._ioctl(FM_IOCTL_GETVOL)
        if result:
            vol = struct.unpack('<I', result[:4])[0]
            return vol
        return None

    def set_volume(self, vol):
        """Set volume (0-15 typical for MT6631)."""
        buf = struct.pack('<I', vol) + b'\x00' * 4
        result = self._ioctl(FM_IOCTL_SETVOL, buf)
        return result is not None

    def mute(self, on=True):
        """Mute or unmute."""
        buf = struct.pack('<I', 1 if on else 0) + b'\x00' * 4
        result = self._ioctl(FM_IOCTL_MUTE, buf)
        return result is not None

    def is_stereo(self):
        """Check if current station is stereo."""
        result = self._ioctl(FM_IOCTL_GETMONOSTEREO)
        if result:
            val = struct.unpack('<H', result[:2])[0]
            return val != 0
        return None

    def is_powered(self):
        """Check if FM is currently powered up."""
        result = self._ioctl(FM_IOCTL_IS_POWERED)
        if result:
            val = struct.unpack('<I', result[:4])[0]
            return val != 0
        return None

    def get_status(self):
        """Get FM status register."""
        result = self._ioctl(FM_IOCTL_GET_STATUS)
        if result:
            return result.hex()
        return None

    def rds_supported(self):
        """Check if RDS is supported."""
        result = self._ioctl(FM_IOCTL_RDS_SUPPORT)
        if result:
            val = struct.unpack('<I', result[:4])[0]
            return val != 0
        return None

    def rds_onoff(self, on=True):
        """Enable/disable RDS."""
        buf = struct.pack('<I', 1 if on else 0) + b'\x00' * 4
        result = self._ioctl(FM_IOCTL_RDS_ONOFF, buf)
        return result is not None

    def get_i2s_info(self):
        """Get I2S configuration info."""
        result = self._ioctl(FM_IOCTL_GET_I2S_INFO)
        if result:
            return result.hex()
        return None

    # --- Software seek/scan ---

    def seek(self, direction=1, threshold=RSSI_THRESHOLD):
        """Software seek: find next station with RSSI above threshold.
        direction: 1=up, -1=down
        Returns freq_mhz or None if wrapped around without finding.
        """
        if not self.powered:
            p("[-] FM not powered up")
            return None

        start = self.current_freq
        freq = start
        lo, hi = self.band
        step = SEEK_STEP * direction

        while True:
            freq += step
            # Wrap around
            if freq > hi:
                freq = lo
            elif freq < lo:
                freq = hi

            # Tune and check RSSI
            if self.tune(freq / 10.0):
                rssi = self.get_rssi()
                if rssi is not None and rssi > threshold:
                    p("[+] Found station at %s MHz (RSSI=%d)" %
                      (freq_to_str(freq), rssi))
                    self.current_freq = freq
                    return freq / 10.0

            # Wrapped all the way around
            if freq == start:
                p("[-] No stations found")
                return None

            time.sleep(0.02)  # Brief delay between tunes

    def scan_band(self, threshold=RSSI_THRESHOLD, step_khz=100):
        """Scan entire band, return list of (freq_mhz, rssi, stereo)."""
        lo, hi = self.band
        step = step_khz // 10  # Convert kHz step to freq*10 units
        stations = []

        p("[*] Scanning %s - %s MHz (step=%dkHz, threshold=%d)..." %
          (freq_to_str(lo), freq_to_str(hi), step_khz, threshold))

        for freq in range(lo, hi + 1, step):
            if self.tune(freq / 10.0):
                time.sleep(0.05)  # Let tuner settle
                rssi = self.get_rssi()
                stereo = self.is_stereo()
                if rssi is not None and rssi > threshold:
                    marker = "S" if stereo else "M"
                    stations.append((freq / 10.0, rssi, stereo))
                    p("  %6.1f MHz  RSSI: %4d  [%s]" %
                      (freq / 10.0, rssi, marker))

        p("[+] Found %d stations" % len(stations))
        return stations

    # --- ioctl probe ---

    def probe_ioctls(self):
        """Probe all ioctl NR values to discover the interface."""
        p("\n[*] Probing 0xf5 ioctls (nr 0x00 - 0x30)...")
        parm = pack_tune_parm(1000)
        for nr in range(0x31):
            cmd = _IOWR(FM_MAGIC, nr, FM_PARM_SIZE)
            buf = bytearray(parm)
            try:
                fcntl.ioctl(self.fd, cmd, buf)
                result = bytes(buf)
                p("  [+] nr=0x%02x: %s" % (nr, result.hex()))
            except OSError as e:
                if e.errno not in (1, 25):  # Skip EPERM, ENOTTY
                    p("  [-] nr=0x%02x: errno=%d (%s)" %
                      (nr, e.errno, e.strerror))


# ============================================================
# Audio routing
# ============================================================

def setup_audio(speaker=True, volume=65536):
    """Configure ALSA mixer for FM playback."""
    p("[*] Configuring audio routing...")
    cmds = [
        ("Audio_I2S1_Setting", "On"),
        ("Audio_i2s0_hd_Switch", "On"),
        ("Audio FM I2S Volume", str(volume)),
        ("Audio Mrgrx Volume", str(volume)),
    ]
    if speaker:
        cmds.append(("Speaker_Amp_Switch", "On"))

    ok = True
    for name, val in cmds:
        try:
            r = subprocess.run(["tinymix", name, val],
                             capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                p("  [+] %s = %s" % (name, val))
            else:
                p("  [-] %s: %s" % (name, r.stderr.strip()))
                ok = False
        except Exception as e:
            p("  [-] %s: %s" % (name, e))
            ok = False
    return ok


def teardown_audio():
    """Disable FM audio path."""
    p("[*] Tearing down audio...")
    for name, val in [("Audio_I2S1_Setting", "Off"),
                      ("Speaker_Amp_Switch", "Off")]:
        try:
            subprocess.run(["tinymix", name, val],
                         capture_output=True, timeout=5)
        except Exception:
            pass


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='AX12 FM Radio (MT6631)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  info      Show chip info and FM status
  probe     Probe all ioctl numbers
  powerup   Power up FM at frequency (use with -f)
  tune      Tune to frequency (use with -f)
  listen    Power up + audio routing + keep alive (Ctrl+C to stop)
  seek      Seek next station up/down (use with --down)
  scan      Scan entire FM band for stations
  off       Power down FM radio

Examples:
  fm_radio.py listen -f 101.1
  fm_radio.py scan
  fm_radio.py tune -f 98.7
  fm_radio.py seek
  fm_radio.py seek --down
  fm_radio.py off
""")
    parser.add_argument('command',
                       choices=['info', 'probe', 'powerup', 'tune', 'listen',
                               'seek', 'scan', 'off', 'status'],
                       help='Command to execute')
    parser.add_argument('-f', '--freq', type=float, default=101.1,
                       help='Frequency in MHz (default: 101.1)')
    parser.add_argument('-v', '--volume', type=int, default=65536,
                       help='FM I2S volume 0-524288 (default: 65536)')
    parser.add_argument('--down', action='store_true',
                       help='Seek downward instead of up')
    parser.add_argument('--threshold', type=int, default=RSSI_THRESHOLD,
                       help='RSSI threshold for seek/scan (default: %d)' %
                       RSSI_THRESHOLD)
    parser.add_argument('--step', type=int, default=100,
                       help='Scan step in kHz (default: 100)')
    parser.add_argument('--no-speaker', action='store_true',
                       help='Do not enable speaker amp')
    args = parser.parse_args()

    fm = FMRadio()
    try:
        fm.open()

        if args.command == 'info':
            fm.hw_info()
            powered = fm.is_powered()
            p("[*] Powered: %s" % ("Yes" if powered else "No"))
            status = fm.get_status()
            p("[*] Status: %s" % status)
            i2s = fm.get_i2s_info()
            p("[*] I2S info: %s" % i2s)
            rds = fm.rds_supported()
            p("[*] RDS supported: %s" % rds)
            vol = fm.get_volume()
            p("[*] Volume: %s" % vol)

        elif args.command == 'probe':
            fm.hw_info()
            fm.probe_ioctls()

        elif args.command == 'status':
            powered = fm.is_powered()
            if powered:
                rssi = fm.get_rssi()
                stereo = fm.is_stereo()
                status = fm.get_status()
                vol = fm.get_volume()
                p("[+] FM is ON")
                p("    RSSI: %s" % rssi)
                p("    Stereo: %s" % stereo)
                p("    Volume: %s" % vol)
                p("    Status: %s" % status)
            else:
                p("[*] FM is OFF")

        elif args.command == 'powerup':
            fm.powerup(args.freq)
            rssi = fm.get_rssi()
            p("[*] RSSI: %s" % rssi)

        elif args.command == 'tune':
            # Always powerdown first then powerup at new freq.
            # The tune ioctl only works on the fd that did powerup,
            # and since we open a new fd each invocation, we must
            # cycle power to change frequency.
            if fm.is_powered():
                fm.powered = True
                fm.powerdown()
            fm.powerup(args.freq)
            rssi = fm.get_rssi()
            stereo = fm.is_stereo()
            p("[*] RSSI: %s  Stereo: %s" % (rssi, stereo))

        elif args.command == 'listen':
            # Ensure clean state
            if fm.is_powered():
                fm.powered = True
                fm.powerdown()
            setup_audio(speaker=not args.no_speaker, volume=args.volume)
            if fm.powerup(args.freq):
                fm.hw_info()
                rssi = fm.get_rssi()
                stereo = fm.is_stereo()
                p("")
                p("=" * 40)
                p("  FM Radio: %s MHz" % freq_to_str(fm.current_freq))
                p("  RSSI: %s  Stereo: %s" %
                  (rssi, "Yes" if stereo else "No"))
                if fm.chip_id:
                    p("  Chip: MT%d" % fm.chip_id)
                p("=" * 40)
                p("  Press Ctrl+C to stop")
                p("")
                try:
                    while True:
                        time.sleep(5)
                        rssi = fm.get_rssi()
                        stereo = fm.is_stereo()
                        sys.stdout.write(
                            "\r  %s MHz | RSSI: %4s | %s   " %
                            (freq_to_str(fm.current_freq),
                             rssi,
                             "Stereo" if stereo else "Mono"))
                        sys.stdout.flush()
                except KeyboardInterrupt:
                    p("\n[*] Stopping...")
                    teardown_audio()
            return

        elif args.command == 'seek':
            if not fm.is_powered():
                fm.powerup(args.freq)
            else:
                fm.powered = True
                fm.current_freq = int(args.freq * 10)
            direction = -1 if args.down else 1
            found = fm.seek(direction=direction,
                          threshold=args.threshold)
            if found:
                rssi = fm.get_rssi()
                stereo = fm.is_stereo()
                p("[+] %s MHz  RSSI: %s  Stereo: %s" %
                  (found, rssi, stereo))

        elif args.command == 'scan':
            if not fm.powerup(87.5):
                p("[-] Cannot power up FM")
                return
            stations = fm.scan_band(threshold=args.threshold,
                                   step_khz=args.step)
            if stations:
                p("\n[+] Station list (sorted by signal strength):")
                for freq, rssi, stereo in sorted(stations,
                                                  key=lambda x: -x[1]):
                    marker = "Stereo" if stereo else "Mono"
                    p("  %6.1f MHz  RSSI: %4d  %s" %
                      (freq, rssi, marker))

        elif args.command == 'off':
            fm.powered = True  # Force powerdown attempt
            fm.powerdown()
            teardown_audio()
            p("[+] FM radio off")
            return

    except KeyboardInterrupt:
        p("\n[*] Interrupted")
    except OSError as e:
        p("[-] OS error: %s" % e)
        p("    Make sure you are running as root (su 0)")
    finally:
        if fm.fd is not None:
            if fm.powered and args.command not in ('listen', 'off'):
                # Keep powered for non-listen commands so state persists
                os.close(fm.fd)
                fm.fd = None
            else:
                fm.close()


if __name__ == '__main__':
    main()
