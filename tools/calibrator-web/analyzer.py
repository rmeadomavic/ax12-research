"""
analyzer.py — Channel analysis utilities for AX12 radio calibration tool.

Classifies UMBUS protocol channels (33 uint16 + 4 signed int16 gimbals) to help
identify which physical control maps to which channel.
"""


def classify_channels(samples: list[list[int]]) -> dict[int, str]:
    """
    Classify each channel across N frames of channel values.

    Returns a dict mapping channel index -> classification string:
      "jittery"  — high variance, range > 50 (typical of analog gimbals)
      "static"   — range < 50 (switch or control held in place)
      "stepped"  — range > 100 but only a few unique values (<= 6)
                   (typical of 2- or 3-position switches)

    Args:
        samples: List of frames; each frame is a list of channel values.

    Returns:
        Empty dict if samples is empty, otherwise {channel_index: label}.
    """
    if not samples:
        return {}

    num_channels = len(samples[0])
    result: dict[int, str] = {}

    for ch in range(num_channels):
        values = [frame[ch] for frame in samples]
        lo = min(values)
        hi = max(values)
        span = hi - lo
        unique = len(set(values))

        if span < 50:
            label = "static"
        elif unique <= 6 and span > 100:
            label = "stepped"
        else:
            label = "jittery"

        result[ch] = label

    return result


def detect_movement(
    baseline: list[int],
    current: list[int],
    threshold: int = 1000,
) -> list[int]:
    """
    Return indices of channels where absolute change from baseline exceeds threshold.

    Args:
        baseline:  Reference frame (list of channel values).
        current:   Current frame (list of channel values).
        threshold: Minimum absolute delta to count as movement (default 1000).

    Returns:
        Sorted list of channel indices that moved beyond the threshold.
    """
    moved = []
    for i, (b, c) in enumerate(zip(baseline, current)):
        if abs(c - b) > threshold:
            moved.append(i)
    return moved


def count_positions(values: list[int], tolerance: int = 500) -> int:
    """
    Count distinct value clusters in a list of channel samples.

    Clusters are formed by sorting the unique values and counting gaps larger
    than `tolerance` between consecutive values.

    Args:
        values:    List of raw channel values observed over time.
        tolerance: Minimum gap between values to treat them as separate positions.

    Returns:
        Number of distinct position clusters (>= 1 if values is non-empty, 0 if empty).
    """
    if not values:
        return 0

    unique_sorted = sorted(set(values))
    clusters = 1
    for a, b in zip(unique_sorted, unique_sorted[1:]):
        if b - a > tolerance:
            clusters += 1
    return clusters
