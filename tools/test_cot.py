#!/data/data/com.termux/files/usr/bin/python3
"""
CoT Test Sender — Send a single CoT message to ATAK for display testing.

Sends one CoT XML datagram to localhost:4242 with a hardcoded position
at (0, 0) — null island. Use this to verify ATAK is receiving and
rendering CoT events before running the full bridge.

Usage:
    python3 tools/test_cot.py                  # send to default port
    python3 tools/test_cot.py --port 4243      # custom port

No root required. No serial access.
"""

import argparse
import socket
import time


def iso8601(timestamp: float) -> str:
    t = time.gmtime(timestamp)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", t)


def build_cot(lat: float = 0.0, lon: float = 0.0, alt: float = 100.0,
              uid: str = "ELRS-Drone-1") -> str:
    """Build a minimal CoT event XML string."""
    now = time.time()
    time_str = iso8601(now)
    stale_str = iso8601(now + 30)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<event version="2.0" uid="{uid}" type="a-f-A-M-F-Q" '
        f'time="{time_str}" start="{time_str}" stale="{stale_str}" '
        f'how="m-g">'
        f'<point lat="{lat:.7f}" lon="{lon:.7f}" hae="{alt:.1f}" '
        f'ce="10.0" le="10.0"/>'
        f'<detail>'
        f'<track course="0.0" speed="0.00"/>'
        f'<remarks>TEST | Disarmed | 0.0m/s | {alt:.0f}m MSL</remarks>'
        f'<contact callsign="{uid}"/>'
        f'<__group name="Cyan" role="Team Member"/>'
        f'</detail>'
        f'</event>'
    )


def main():
    parser = argparse.ArgumentParser(description="Send a single test CoT to ATAK")
    parser.add_argument('--host', default='127.0.0.1', help='Target host')
    parser.add_argument('--port', type=int, default=4242, help='Target port')
    parser.add_argument('--uid', default='ELRS-Drone-1', help='CoT UID')
    args = parser.parse_args()

    xml = build_cot(lat=0.0, lon=0.0, alt=100.0, uid=args.uid)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(xml.encode('utf-8'), (args.host, args.port))
    sock.close()

    print(f"[test_cot] Sent CoT to {args.host}:{args.port}")
    print(f"[test_cot] UID: {args.uid}")
    print(f"[test_cot] Position: 0.0, 0.0 (null island) @ 100m")
    print(f"[test_cot] XML ({len(xml)} bytes):")
    print(xml)


if __name__ == '__main__':
    main()
