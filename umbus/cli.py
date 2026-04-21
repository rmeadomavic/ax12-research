"""
Command-line interface for decoding UMBUS data.

Installed as ``umbus-decode`` when the package is pip-installed::

    umbus-decode capture.bin          # decode a binary file
    umbus-decode -                    # decode from stdin
    cat raw.bin | umbus-decode -      # pipe binary data

On a rooted AX12::

    umbus-decode --live               # read directly from /dev/ttyS0
"""

import os
import sys

from umbus.decoder import UMBUSDecoder


def main() -> None:
    """Entry point for the ``umbus-decode`` CLI."""
    if len(sys.argv) < 2:
        print("Usage: umbus-decode <file.bin | - | --live>")
        print()
        print("Decode UMBUS frames from binary data.")
        print()
        print("  file.bin   Read frames from a binary file")
        print("  -          Read binary data from stdin")
        print("  --live     Read from /dev/ttyS0 (requires root on AX12)")
        sys.exit(1)

    decoder = UMBUSDecoder()

    if sys.argv[1] == "--live":
        _live_mode(decoder)
    elif sys.argv[1] == "-":
        data = sys.stdin.buffer.read()
        for frame in decoder.feed(data):
            print(frame.summary())
            print()
    else:
        with open(sys.argv[1], "rb") as f:
            data = f.read()
        for frame in decoder.feed(data):
            print(frame.summary())
            print()

    print(f"--- Stats: {decoder.stats}")


def _live_mode(decoder: UMBUSDecoder) -> None:
    """Read frames from /dev/ttyS0 in non-blocking mode."""
    import time

    fd = os.open("/dev/ttyS0", os.O_RDONLY | os.O_NONBLOCK)
    try:
        print("Reading from /dev/ttyS0... (Ctrl+C to stop)")
        while True:
            try:
                data = os.read(fd, 4096)
                for frame in decoder.feed(data):
                    print(frame.summary())
                    print()
            except BlockingIOError:
                time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        os.close(fd)
