"""
serial_reader.py — Read UMBUS frames from the AX12's serial port and maintain
a shared state dict that the UI can poll.

Two operating modes:

  exclusive  — Kill the RC app, configure /dev/ttyS0 via stty, open the port
               directly with os.open/os.read.  Gives the cleanest data but
               takes the transmitter offline for the duration.

  strace     — Attach strace to the running RC app PID and parse the hex bytes
               from its read() syscalls.  RC app keeps running; data arrives at
               the same rate but with syscall overhead.

Both modes feed raw bytes into UMBUSDecoder and update LATEST on every valid
CHANNEL_DATA frame.

NOTE: This module is only useful when deployed on the AX12 (Android/Termux)
      where the umbus library and /dev/ttyS0 are present.
"""

import codecs
import os
import re
import subprocess
import threading
import time

# ---------------------------------------------------------------------------
# umbus import — will only succeed on the AX12 target device
# ---------------------------------------------------------------------------
UMBUSDecoder = None
FrameType = None
try:
    from umbus import UMBUSDecoder, FrameType
except ImportError:
    try:
        # On AX12, umbus lives inside the ax12-research tools directory
        import sys as _sys
        _sys.path.insert(0, os.path.expanduser("~/ax12-research"))
        _sys.path.insert(0, os.path.expanduser("~/ax12-research/tools"))
        from umbus import UMBUSDecoder, FrameType
    except ImportError:
        try:
            from tools.umbus import UMBUSDecoder, FrameType
        except ImportError:
            print("WARNING: umbus library not found. Serial reader will not work.")

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

LATEST: dict = {
    "gimbals": [0, 0, 0, 0],
    "channels": [32768] * 33,
    "fps": 0.0,
    "crc_errors": 0,
    "connected": False,
}

_lock = threading.Lock()

# ---------------------------------------------------------------------------
# State accessors
# ---------------------------------------------------------------------------

def get_latest() -> dict:
    """Return a thread-safe shallow copy of LATEST."""
    with _lock:
        return dict(LATEST)


# ---------------------------------------------------------------------------
# Spike rejection filter
# ---------------------------------------------------------------------------

_SPIKE_THRESHOLD = 1000
_prev_gimbals = [0, 0, 0, 0]
_prev_valid = False


def update_latest(gimbals, channels):
    """Thread-safe update of LATEST with spike rejection filter."""
    global _prev_gimbals, _prev_valid
    if _prev_valid:
        for i in range(min(len(gimbals), len(_prev_gimbals))):
            if abs(gimbals[i] - _prev_gimbals[i]) > _SPIKE_THRESHOLD:
                return
    _prev_gimbals = list(gimbals)
    _prev_valid = True
    with _lock:
        LATEST["gimbals"] = list(gimbals)
        LATEST["channels"] = list(channels)
        LATEST["connected"] = True


# ---------------------------------------------------------------------------
# Internal FPS / CRC helpers (called only from reader threads)
# ---------------------------------------------------------------------------

def _record_frame(decoder_frame, frame_count_state: dict) -> None:
    """
    Called once per decoded frame (inside a reader thread).

    Updates fps/crc_errors in LATEST.  frame_count_state is a mutable dict
    owned by the calling thread that persists between calls:
        {"count": int, "window_start": float}
    """
    with _lock:
        if not decoder_frame.checksum_valid:
            LATEST["crc_errors"] += 1

    # FPS: count frames in the current 1-second window
    now = time.monotonic()
    frame_count_state["count"] += 1
    elapsed = now - frame_count_state["window_start"]
    if elapsed >= 1.0:
        fps = frame_count_state["count"] / elapsed
        with _lock:
            LATEST["fps"] = round(fps, 1)
        frame_count_state["count"] = 0
        frame_count_state["window_start"] = now


# ---------------------------------------------------------------------------
# Exclusive mode
# ---------------------------------------------------------------------------

def start_exclusive(port: str = "/dev/ttyS0", baud: int = 921600) -> threading.Thread:
    """
    Kill the RC app, configure the serial port, and start a reader thread that
    owns /dev/ttyS0 exclusively.

    Returns a started daemon thread.
    """

    def _run() -> None:
        try:
            # --- stop RC app -----------------------------------------------
            os.system("su 0 am force-stop com.radiomaster.ax12")

            # --- open port and configure termios in-process ------------------
            # We must configure termios AFTER opening the fd, not before via
            # stty.  BusyBox stty opens/closes the device, which triggers
            # hupcl (termios reset on last close), so settings are lost by
            # the time we os.open() the port again.
            import fcntl
            import termios

            fd = os.open(port, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)

            # Set fully raw mode via termios (cfmakeraw equivalent)
            attrs = termios.tcgetattr(fd)
            # attrs: [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
            attrs[0] = 0          # iflag: clear ALL input processing
            attrs[1] = 0          # oflag: clear ALL output processing
            attrs[2] &= ~(termios.CSIZE | termios.PARENB)
            attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[3] = 0          # lflag: clear ALL local processing
            attrs[6][termios.VMIN] = 1    # block until at least 1 byte
            attrs[6][termios.VTIME] = 0
            # Set baud rate
            baud_const = getattr(termios, f"B{baud}", None)
            if baud_const is not None:
                attrs[4] = baud_const   # ispeed
                attrs[5] = baud_const   # ospeed
            termios.tcsetattr(fd, termios.TCSANOW, attrs)

            # Switch to blocking I/O after open
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)

            decoder = UMBUSDecoder()
            fps_state: dict = {"count": 0, "window_start": time.monotonic()}

            with _lock:
                LATEST["connected"] = True

            # --- read loop -------------------------------------------------
            while True:
                data = os.read(fd, 256)
                if not data:
                    continue

                for frame in decoder.feed(data):
                    _record_frame(frame, fps_state)
                    if frame.frame_type == FrameType.CHANNEL_DATA:
                        if frame.gimbals is not None and frame.channels is not None:
                            update_latest(frame.gimbals, frame.channels)

        except Exception as exc:  # noqa: BLE001
            with _lock:
                LATEST["connected"] = False
            # Re-raise so the thread's exception is visible in logs
            raise RuntimeError(f"exclusive reader failed: {exc}") from exc

    t = threading.Thread(target=_run, name="serial-exclusive", daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Strace mode
# ---------------------------------------------------------------------------

# Matches:  read(25, "\xa6\x57...", 256) = 87
# Group 1 captures everything between the first pair of double-quotes.
_STRACE_RE = re.compile(r'read\(\d+,\s*"((?:[^"\\]|\\.)*)",\s*\d+\)\s*=\s*\d+')


def _parse_strace_bytes(line: str) -> bytes | None:
    """
    Extract raw bytes from a single strace output line.

    Returns bytes if the line is a read() syscall that contains UMBUS-looking
    data (i.e. at least one escaped byte), otherwise None.

    Strace encodes non-printable bytes as \\xNN.  Printable ASCII is left
    as-is.  We decode via 'unicode_escape' then re-encode as latin-1 to get
    the original byte values.
    """
    m = _STRACE_RE.search(line)
    if m is None:
        return None

    raw_str = m.group(1)

    # Only bother decoding if the line carries binary data
    if r"\x" not in raw_str:
        return None

    try:
        # unicode_escape turns \xNN sequences into the corresponding unicode
        # code points (U+0000–U+00FF).  latin-1 maps those back to raw bytes.
        decoded = raw_str.encode("raw_unicode_escape").decode("unicode_escape")
        return decoded.encode("latin-1")
    except (UnicodeDecodeError, ValueError):
        return None


def start_strace(pid: int | None = None) -> threading.Thread:
    """
    Attach strace to the RC app and parse UMBUS frames from its read() calls.

    If *pid* is None, the RC app PID is located automatically via pidof.
    Returns a started daemon thread.
    """

    def _run() -> None:
        try:
            # --- find PID --------------------------------------------------
            target_pid = pid
            if target_pid is None:
                result = subprocess.run(
                    ["su", "0", "pidof", "com.radiomaster.ax12"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                pids = result.stdout.strip().split()
                if not pids:
                    raise RuntimeError("RC app (com.radiomaster.ax12) is not running")
                target_pid = int(pids[0])

            # --- launch strace ---------------------------------------------
            proc = subprocess.Popen(
                [
                    "su", "0",
                    "strace",
                    "-p", str(target_pid),
                    "-e", "read",
                    "-x",          # print all strings in hex
                    "-s", "256",   # capture up to 256 bytes per syscall
                ],
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                text=True,
                errors="replace",
            )

            decoder = UMBUSDecoder()
            fps_state: dict = {"count": 0, "window_start": time.monotonic()}

            with _lock:
                LATEST["connected"] = True

            # --- parse loop ------------------------------------------------
            for line in proc.stderr:
                raw = _parse_strace_bytes(line)
                if raw is None:
                    continue

                for frame in decoder.feed(raw):
                    _record_frame(frame, fps_state)
                    if frame.frame_type == FrameType.CHANNEL_DATA:
                        if frame.gimbals is not None and frame.channels is not None:
                            update_latest(frame.gimbals, frame.channels)

            # strace exited (process killed / detached)
            proc.wait()

        except Exception as exc:  # noqa: BLE001
            with _lock:
                LATEST["connected"] = False
            raise RuntimeError(f"strace reader failed: {exc}") from exc

    t = threading.Thread(target=_run, name="serial-strace", daemon=True)
    t.start()
    return t
