#!/usr/bin/env python3
"""
Test suite for the UMBUS traffic simulator.

Verifies frame generation, timing patterns, and decode integrity
without requiring any hardware.

Run:
    python3 -m unittest tools/test_simulator.py -v
"""
import os
import sys
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulator import TrafficGenerator
from umbus import (
    CHANNEL_CENTER, FrameType, SWITCH_HIGH,
    UMBUSDecoder, UMBUSEncoder, verify_checksum,
)


class TestTrafficGenerator(unittest.TestCase):

    def test_generate_returns_frames(self):
        gen = TrafficGenerator()
        frames = gen.generate(duration=1.0)
        self.assertGreater(len(frames), 0)

    def test_all_frames_decode(self):
        """Every generated frame should decode without errors."""
        gen = TrafficGenerator()
        frames = gen.generate(duration=2.0)
        decoder = UMBUSDecoder()
        blob = b''.join(data for _t, data in frames)
        result = list(decoder.feed(blob))
        self.assertEqual(len(result), len(frames))
        self.assertEqual(decoder.frames_bad_checksum, 0)

    def test_all_checksums_valid(self):
        gen = TrafficGenerator()
        frames = gen.generate(duration=1.0)
        for _t, data in frames:
            self.assertTrue(verify_checksum(data),
                            f"Bad checksum: {data[:4].hex()}")

    def test_timestamps_monotonic(self):
        gen = TrafficGenerator()
        frames = gen.generate(duration=5.0)
        for i in range(1, len(frames)):
            self.assertGreaterEqual(frames[i][0], frames[i - 1][0])

    def test_frame_type_distribution(self):
        """Should produce a mix of all frame types."""
        gen = TrafficGenerator()
        frames = gen.generate(duration=5.0)
        decoder = UMBUSDecoder()
        blob = b''.join(data for _t, data in frames)
        result = list(decoder.feed(blob))
        types = Counter(r.type_name for r in result)

        # All expected types should be present
        self.assertIn('CHANNEL_DATA', types)
        self.assertIn('HEARTBEAT_MCU', types)
        self.assertIn('ELRS_TELEM', types)
        self.assertIn('EXTENDED', types)
        self.assertIn('CMD_0E', types)
        self.assertIn('CMD_07', types)

        # Channel data should dominate (25 Hz vs others)
        self.assertGreater(types['CHANNEL_DATA'], types['HEARTBEAT_MCU'])
        self.assertGreater(types['CHANNEL_DATA'], types['ELRS_TELEM'])

    def test_channel_data_rate(self):
        """Should generate roughly 25 CHANNEL_DATA frames per second."""
        gen = TrafficGenerator()
        duration = 4.0
        frames = gen.generate(duration=duration)
        decoder = UMBUSDecoder()
        blob = b''.join(data for _t, data in frames)
        result = list(decoder.feed(blob))
        ch_count = sum(1 for r in result if r.frame_type == FrameType.CHANNEL_DATA)
        rate = ch_count / duration
        # Allow some tolerance (20-30 Hz)
        self.assertGreaterEqual(rate, 20)
        self.assertLessEqual(rate, 30)

    def test_gimbal_pattern_idle(self):
        gen = TrafficGenerator()
        gen.set_gimbal_pattern('idle')
        frames = gen.generate(duration=1.0)
        decoder = UMBUSDecoder()
        blob = b''.join(data for _t, data in frames)
        result = list(decoder.feed(blob))
        ch_frames = [r for r in result if r.frame_type == FrameType.CHANNEL_DATA]
        self.assertGreater(len(ch_frames), 0)
        # Idle gimbals should be small values (drift only)
        for f in ch_frames:
            for g in f.gimbals:
                self.assertLess(abs(g), 500)

    def test_gimbal_pattern_sine(self):
        gen = TrafficGenerator()
        gen.set_gimbal_pattern('sine')
        frames = gen.generate(duration=2.0)
        decoder = UMBUSDecoder()
        blob = b''.join(data for _t, data in frames)
        result = list(decoder.feed(blob))
        ch_frames = [r for r in result if r.frame_type == FrameType.CHANNEL_DATA]
        # Sine pattern should produce larger values
        max_abs = max(abs(g) for f in ch_frames for g in f.gimbals)
        self.assertGreater(max_abs, 100)

    def test_gimbal_pattern_sweep(self):
        gen = TrafficGenerator()
        gen.set_gimbal_pattern('sweep')
        frames = gen.generate(duration=4.0)
        decoder = UMBUSDecoder()
        blob = b''.join(data for _t, data in frames)
        result = list(decoder.feed(blob))
        ch_frames = [r for r in result if r.frame_type == FrameType.CHANNEL_DATA]
        vals = [f.gimbals[0] for f in ch_frames]
        # Sweep should hit both negative and positive
        self.assertTrue(any(v < -100 for v in vals))
        self.assertTrue(any(v > 100 for v in vals))

    def test_elrs_sequence_increments(self):
        gen = TrafficGenerator()
        frames = gen.generate(duration=2.0)
        decoder = UMBUSDecoder()
        blob = b''.join(data for _t, data in frames)
        result = list(decoder.feed(blob))
        elrs_frames = [r for r in result if r.frame_type == FrameType.ELRS_TELEM]
        self.assertGreater(len(elrs_frames), 1)
        seqs = [r.elrs_telemetry['seq'] for r in elrs_frames]
        # Sequence should increment
        for i in range(1, len(seqs)):
            self.assertEqual(seqs[i], seqs[i - 1] + 1)

    def test_extended_sub_indices(self):
        """Extended telemetry should use sub-indices 0, 1, 2."""
        gen = TrafficGenerator()
        frames = gen.generate(duration=3.0)
        decoder = UMBUSDecoder()
        blob = b''.join(data for _t, data in frames)
        result = list(decoder.feed(blob))
        ext_frames = [r for r in result if r.frame_type == FrameType.EXTENDED]
        self.assertGreater(len(ext_frames), 0)
        sub_indices = set(r.extended_telemetry['sub_index'] for r in ext_frames)
        self.assertEqual(sub_indices, {0, 1, 2})

    def test_short_duration(self):
        gen = TrafficGenerator()
        frames = gen.generate(duration=0.1)
        self.assertGreater(len(frames), 0)

    def test_zero_duration(self):
        gen = TrafficGenerator()
        frames = gen.generate(duration=0.0)
        self.assertEqual(len(frames), 0)


if __name__ == '__main__':
    unittest.main()
