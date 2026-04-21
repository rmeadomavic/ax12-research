"""
Utility functions for UMBUS data handling.

Helpers for parsing hex data from strace output and describing
channel values in human-readable terms.
"""

import re
from typing import Optional

from umbus.constants import (
    CHANNEL_CENTER,
    CHANNEL_MAX,
    CHANNEL_MIN,
    SWITCH_ALT,
    SWITCH_HIGH,
)


def parse_strace_hex(line: str) -> Optional[bytes]:
    """Parse hex data from strace output lines.

    Handles two formats::

        # Escaped string format:
        read(103, "\\\\xa6\\\\x57\\\\x10\\\\x02...", 4096) = 87

        # Hex dump format:
        | 00000  a6 57 10 02 04 01 ...  |

    Args:
        line: A single line of strace output.

    Returns:
        Extracted bytes, or ``None`` if no hex data was found.
    """
    # Try strace escaped string format
    if "\\x" in line:
        hex_bytes = re.findall(r"\\x([0-9a-fA-F]{2})", line)
        if hex_bytes:
            return bytes(int(h, 16) for h in hex_bytes)

    # Try hex dump format
    line = line.strip()
    if line.startswith("|"):
        line = line.strip("|").strip()
    parts = line.split()
    hex_bytes_list = []
    for p in parts:
        if len(p) == 2:
            try:
                hex_bytes_list.append(int(p, 16))
            except ValueError:
                continue
    if hex_bytes_list:
        return bytes(hex_bytes_list)

    return None


def describe_channel_value(value: int) -> str:
    """Describe a channel value in human-readable terms.

    Args:
        value: Raw 16-bit channel value.

    Returns:
        A string like ``"CENTER"``, ``"SW_HIGH"``, or
        ``"34567 (+5.5%)"`` showing the percentage offset from center.
    """
    if value == CHANNEL_CENTER:
        return "CENTER"
    elif value == SWITCH_HIGH:
        return "SW_HIGH"
    elif value == SWITCH_ALT:
        return "SW_ALT"
    elif value == CHANNEL_MIN:
        return "MIN"
    elif value == CHANNEL_MAX:
        return "MAX"
    else:
        pct = (value - CHANNEL_CENTER) / CHANNEL_CENTER * 100
        return f"{value} ({pct:+.1f}%)"
