#!/data/data/com.termux/files/usr/bin/python3
"""
AX12 Live Serial Monitor

Real-time visualization of UMBUS channel data from /dev/ttyS0.
Uses the umbus.py library for frame parsing.

Run with:  su 0 /data/data/com.termux/files/usr/bin/python3 ~/ax12-research/tools/monitor.py

WARNING: Do NOT run this while the RadioMaster app is also reading ttyS0.
         Two readers on the same serial port will corrupt both data streams.
         Use strace on the app process instead for non-destructive monitoring.
"""
import os
import sys
import time

# Add tools directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from umbus import UMBUSDecoder, FrameType, CHANNEL_CENTER

SERIAL_PORT = '/dev/ttyS0'

def main():
    fd = os.open(SERIAL_PORT, os.O_RDONLY | os.O_NONBLOCK)
    decoder = UMBUSDecoder()
    baseline = None
    frame_count = 0

    sys.stdout.write("\033[2J\033[?25l")  # clear screen, hide cursor

    try:
        while True:
            try:
                data = os.read(fd, 4096)
            except BlockingIOError:
                time.sleep(0.005)
                continue

            latest_frame = None
            for frame in decoder.feed(data):
                if frame.frame_type in (FrameType.CHANNEL_DATA, FrameType.IDLE):
                    latest_frame = frame
                    frame_count += 1

            if latest_frame is None:
                continue

            vals = latest_frame.all_values
            if vals is None:
                continue

            if baseline is None:
                baseline = list(vals)

            # Render
            out = "\033[H"
            out += f"  AX12 SERIAL MONITOR  |  frame #{frame_count}  |  Ctrl+C quit\n"
            out += f"  Decoded: {decoder.frames_decoded}  Skip: {decoder.bytes_skipped}B\n\n"

            # Show gimbals separately
            gimbals = latest_frame.gimbals
            if gimbals:
                out += "  GIMBALS (signed):\n"
                for i, g in enumerate(gimbals):
                    bar_w = 20
                    norm = max(0, min(bar_w, int((g + 600) / 1200 * bar_w)))
                    bar = "░" * norm + "█" + "░" * (bar_w - norm - 1)
                    color = "\033[1;32m" if abs(g) > 50 else "\033[0;37m"
                    out += f"    {color}G{i} [{bar}] {g:>+6d}\033[0m\n"
                out += "\n"

            # Show channels
            out += "  CHANNELS (unsigned):\n"
            for i, v in enumerate(vals):
                delta = v - baseline[i]
                bar_w = 16
                norm = max(0, min(bar_w, int(v / 65536 * bar_w)))
                bar = "█" * norm + "░" * (bar_w - norm)

                if abs(delta) > 1000:
                    color = "\033[1;31m"  # red — big move
                elif abs(delta) > 100:
                    color = "\033[1;33m"  # yellow
                elif abs(delta) > 10:
                    color = "\033[0;36m"  # cyan
                else:
                    color = "\033[0;37m"  # dim

                out += f"    {color}[{i:>2d}] [{bar}] {v:>5d}  Δ{delta:>+6d}\033[0m\n"

            sys.stdout.write(out)
            sys.stdout.flush()
            time.sleep(0.03)

    except KeyboardInterrupt:
        pass
    finally:
        os.close(fd)
        sys.stdout.write("\033[?25h\n")
        print(f"\nStats: {decoder.stats}")


if __name__ == '__main__':
    main()
