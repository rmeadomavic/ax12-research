#!/usr/bin/env python3
"""
Comprehensive test suite for the UMBUS protocol library.

Tests CRC-8/MAXIM, frame parsing, streaming decoder, encoder,
round-trips, and edge cases — all using captured data so no
hardware is needed.

Run:
    python3 -m pytest tools/test_umbus.py -v
    # or
    python3 tools/test_umbus.py
"""
import json
import os
import struct
import unittest

# Ensure imports work regardless of cwd
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from umbus import (
    CHANNEL_CENTER, CHANNEL_MAX, CHANNEL_MIN, CHANNEL_OFFSET,
    CMD_07_FIXED, CMD_0E_FIXED, CRC8_TABLE, CRC_INIT_VALUES,
    FrameType, FRAME_SIZES, GIMBAL_OFFSET, HEARTBEAT_APP_FIXED,
    HEARTBEAT_MCU_FIXED, NUM_GIMBALS, SOURCE_APP, SOURCE_MCU,
    SWITCH_ALT, SWITCH_HIGH, SYNC_BYTE,
    UMBUSDecoder, UMBUSEncoder, UMBUSFrame,
    compute_checksum, compute_crc8, describe_channel_value,
    parse_strace_hex, verify_checksum,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES_JSON = os.path.join(REPO_ROOT, 'captures', 'frames.json')
TIMED_FRAMES_JSON = os.path.join(REPO_ROOT, 'captures', 'timed-frames.json')


def load_captured_frames():
    """Load parsed frames from captures/frames.json."""
    with open(FRAMES_JSON) as f:
        data = json.load(f)
    return data['frames']


def load_timed_frames():
    """Load timed frames from captures/timed-frames.json."""
    with open(TIMED_FRAMES_JSON) as f:
        return json.load(f)


def hex_to_bytes(h: str) -> bytes:
    return bytes.fromhex(h)


# ===================================================================
# CRC-8/MAXIM Tests
# ===================================================================

class TestCRC8(unittest.TestCase):
    """Test the CRC-8/MAXIM (Dallas 1-Wire) implementation."""

    def test_table_length(self):
        self.assertEqual(len(CRC8_TABLE), 256)

    def test_table_first_entries(self):
        """First byte should be 0 (CRC of 0x00 XOR 0x00)."""
        self.assertEqual(CRC8_TABLE[0], 0x00)

    def test_table_is_bytes(self):
        self.assertIsInstance(CRC8_TABLE, bytes)

    def test_crc_empty(self):
        """CRC of empty data with init=0 should be 0."""
        self.assertEqual(compute_crc8(b'', 0x00), 0x00)

    def test_crc_single_byte_zero(self):
        self.assertEqual(compute_crc8(b'\x00', 0x00), 0x00)

    def test_crc_known_frame(self):
        """Verify CRC against a known CHANNEL_DATA frame from captures."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'CHANNEL_DATA' and f['ok']:
                raw = hex_to_bytes(f['h'])
                # CRC covers bytes[1:-1], init=0x00
                expected_crc = raw[-1]
                computed = compute_crc8(raw[1:-1], 0x00)
                self.assertEqual(computed, expected_crc,
                                 f"CRC mismatch on CHANNEL_DATA frame")
                break

    def test_crc_with_init(self):
        """Verify non-zero init for EXTENDED frames."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'EXTENDED' and f['ok']:
                raw = hex_to_bytes(f['h'])
                expected_crc = raw[-1]
                computed = compute_crc8(raw[1:-1], 0x7F)
                self.assertEqual(computed, expected_crc,
                                 f"CRC mismatch on EXTENDED frame (init=0x7F)")
                break

    def test_crc_elrs_init(self):
        """Verify init=0x32 for ELRS_TELEM frames."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'ELRS_TELEM' and f['ok']:
                raw = hex_to_bytes(f['h'])
                expected_crc = raw[-1]
                computed = compute_crc8(raw[1:-1], 0x32)
                self.assertEqual(computed, expected_crc,
                                 f"CRC mismatch on ELRS_TELEM frame (init=0x32)")
                break

    def test_crc_deterministic(self):
        """Same input always produces same output."""
        data = b'\x57\x10\x02\x04\x01'
        r1 = compute_crc8(data)
        r2 = compute_crc8(data)
        self.assertEqual(r1, r2)

    def test_crc_init_changes_result(self):
        """Different init values should produce different CRCs (usually)."""
        data = b'\x10\x02\x04\x06\x00\x00\x00\x20'
        c0 = compute_crc8(data, 0x00)
        c1 = compute_crc8(data, 0x7F)
        self.assertNotEqual(c0, c1)


# ===================================================================
# Checksum Helpers
# ===================================================================

class TestChecksumHelpers(unittest.TestCase):

    def test_compute_checksum_channel_data(self):
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'CHANNEL_DATA' and f['ok']:
                raw = hex_to_bytes(f['h'])
                self.assertEqual(compute_checksum(raw), raw[-1])
                break

    def test_compute_checksum_extended(self):
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'EXTENDED' and f['ok']:
                raw = hex_to_bytes(f['h'])
                self.assertEqual(compute_checksum(raw), raw[-1])
                break

    def test_verify_checksum_all_captured(self):
        """Verify checksum on every captured frame marked ok=true."""
        frames = load_captured_frames()
        for f in frames:
            if not f['ok']:
                continue
            raw = hex_to_bytes(f['h'])
            self.assertTrue(verify_checksum(raw),
                            f"verify_checksum failed for {f['n']} frame: {f['h'][:20]}...")

    def test_verify_checksum_mcu_heartbeat(self):
        """MCU heartbeat (7B) should always pass (no checksum byte)."""
        self.assertTrue(verify_checksum(HEARTBEAT_MCU_FIXED))

    def test_verify_checksum_short_frame(self):
        """Frames shorter than 3 bytes should fail."""
        self.assertFalse(verify_checksum(b'\xa6'))
        self.assertFalse(verify_checksum(b'\xa6\x08'))
        self.assertFalse(verify_checksum(b''))

    def test_verify_checksum_corrupted(self):
        """Flipping a bit should fail checksum."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'CHANNEL_DATA' and f['ok']:
                raw = bytearray(hex_to_bytes(f['h']))
                raw[10] ^= 0xFF  # corrupt a payload byte
                self.assertFalse(verify_checksum(bytes(raw)))
                break

    def test_crc_init_values_dict(self):
        """Verify CRC_INIT_VALUES has expected entries."""
        self.assertEqual(CRC_INIT_VALUES[FrameType.EXTENDED], 0x7F)
        self.assertEqual(CRC_INIT_VALUES[FrameType.ELRS_TELEM], 0x32)
        self.assertNotIn(FrameType.CHANNEL_DATA, CRC_INIT_VALUES)


# ===================================================================
# UMBUSFrame Parsing
# ===================================================================

class TestUMBUSFrame(unittest.TestCase):

    def _make_frame(self, hex_str: str) -> UMBUSFrame:
        raw = hex_to_bytes(hex_str)
        return UMBUSFrame(frame_type=raw[1], raw=raw,
                          checksum_valid=verify_checksum(raw))

    # --- type_name ---

    def test_type_name_channel_data(self):
        frame = UMBUSFrame(frame_type=0x57, raw=b'\xa6\x57')
        self.assertEqual(frame.type_name, 'CHANNEL_DATA')

    def test_type_name_unknown(self):
        frame = UMBUSFrame(frame_type=0xAB, raw=b'\xa6\xAB')
        self.assertIn('UNKNOWN', frame.type_name)
        self.assertIn('AB', frame.type_name)

    # --- gimbals ---

    def test_gimbals_channel_data(self):
        """Gimbals from a real CHANNEL_DATA frame should match captures."""
        frames = load_captured_frames()
        f = frames[0]  # first frame is CHANNEL_DATA
        self.assertEqual(f['n'], 'CHANNEL_DATA')
        frame = self._make_frame(f['h'])
        gimbals = frame.gimbals
        self.assertIsNotNone(gimbals)
        self.assertEqual(len(gimbals), 4)
        self.assertEqual(gimbals, f['g'])

    def test_gimbals_are_signed(self):
        """Gimbal values should be signed 16-bit."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'CHANNEL_DATA':
                frame = self._make_frame(f['h'])
                for g in frame.gimbals:
                    self.assertGreaterEqual(g, -32768)
                    self.assertLessEqual(g, 32767)
                break

    def test_gimbals_none_for_non_channel(self):
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'ELRS_TELEM':
                frame = self._make_frame(f['h'])
                self.assertIsNone(frame.gimbals)
                break

    # --- channels ---

    def test_channels_channel_data(self):
        """Channels from a real frame should match captures."""
        frames = load_captured_frames()
        f = frames[0]
        frame = self._make_frame(f['h'])
        channels = frame.channels
        self.assertIsNotNone(channels)
        self.assertEqual(channels, f['ch'])

    def test_channels_count(self):
        """Should have 32 output channels + possibly extra values."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'CHANNEL_DATA':
                frame = self._make_frame(f['h'])
                # channels parsed from offset 18 to end-3, in 2-byte steps
                self.assertGreaterEqual(len(frame.channels), 30)
                break

    def test_channels_none_for_heartbeat(self):
        frame = UMBUSFrame(frame_type=0x08, raw=HEARTBEAT_MCU_FIXED)
        self.assertIsNone(frame.channels)

    # --- source ---

    def test_source_mcu(self):
        """CHANNEL_DATA frames are MCU→App (header byte 3 = 0x02)."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'CHANNEL_DATA':
                frame = self._make_frame(f['h'])
                self.assertEqual(frame.source, 'MCU→App')
                break

    def test_source_extended_special(self):
        """EXTENDED (0x10) has reversed header 02 04 but is MCU→App."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'EXTENDED':
                frame = self._make_frame(f['h'])
                self.assertEqual(frame.source, 'MCU→App')
                break

    def test_source_app_heartbeat(self):
        frame = UMBUSFrame(frame_type=0x08, raw=HEARTBEAT_APP_FIXED)
        self.assertEqual(frame.source, 'App→MCU')

    def test_source_app_keepalive(self):
        frame = UMBUSFrame(frame_type=0x07, raw=CMD_07_FIXED)
        self.assertEqual(frame.source, 'App→MCU')

    def test_source_app_poll(self):
        frame = UMBUSFrame(frame_type=0x0E, raw=CMD_0E_FIXED)
        self.assertEqual(frame.source, 'App→MCU')

    def test_source_none_for_short(self):
        frame = UMBUSFrame(frame_type=0x57, raw=b'\xa6\x57\x10')
        self.assertIsNone(frame.source)

    # --- elrs_telemetry ---

    def test_elrs_telemetry_parsed(self):
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'ELRS_TELEM':
                frame = self._make_frame(f['h'])
                elrs = frame.elrs_telemetry
                self.assertIsNotNone(elrs)
                self.assertIn('crsf_addr', elrs)
                self.assertIn('timing_us', elrs)
                self.assertIn('link_status', elrs)
                self.assertIn('link_valid', elrs)
                self.assertIn('seq', elrs)
                # Known CRSF constants
                self.assertEqual(elrs['crsf_type'], 0x3A)
                self.assertEqual(elrs['sub_cmd'], 0x10)
                break

    def test_elrs_telemetry_none_for_other(self):
        frame = UMBUSFrame(frame_type=0x57, raw=b'\xa6' + b'\x57' + b'\x00' * 85)
        self.assertIsNone(frame.elrs_telemetry)

    # --- extended_telemetry ---

    def test_extended_telemetry_parsed(self):
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'EXTENDED':
                frame = self._make_frame(f['h'])
                ext = frame.extended_telemetry
                self.assertIsNotNone(ext)
                self.assertIn('descriptor', ext)
                self.assertIn('sub_index', ext)
                self.assertIn('value', ext)
                break

    def test_extended_telemetry_none_for_other(self):
        frame = UMBUSFrame(frame_type=0x57, raw=b'\xa6' + b'\x57' + b'\x00' * 85)
        self.assertIsNone(frame.extended_telemetry)

    # --- all_values ---

    def test_all_values(self):
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'CHANNEL_DATA':
                frame = self._make_frame(f['h'])
                vals = frame.all_values
                self.assertIsNotNone(vals)
                # all_values covers bytes 6 to end-1 in 2-byte steps
                self.assertGreater(len(vals), NUM_GIMBALS)
                break

    # --- hexdump ---

    def test_hexdump_format(self):
        frame = UMBUSFrame(frame_type=0x08, raw=HEARTBEAT_MCU_FIXED)
        hd = frame.hexdump()
        self.assertIn('a6', hd)
        self.assertIn('08', hd)

    # --- summary ---

    def test_summary_channel_data(self):
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'CHANNEL_DATA':
                frame = self._make_frame(f['h'])
                s = frame.summary()
                self.assertIn('CHANNEL_DATA', s)
                self.assertIn('Gimbals', s)
                self.assertIn('Channels', s)
                break

    def test_summary_heartbeat_mcu(self):
        frame = UMBUSFrame(frame_type=0x08, raw=HEARTBEAT_MCU_FIXED)
        s = frame.summary()
        self.assertIn('MCU heartbeat', s)

    def test_summary_heartbeat_app(self):
        frame = UMBUSFrame(frame_type=0x08, raw=HEARTBEAT_APP_FIXED)
        s = frame.summary()
        self.assertIn('App heartbeat', s)

    def test_summary_keepalive(self):
        frame = UMBUSFrame(frame_type=0x07, raw=CMD_07_FIXED)
        s = frame.summary()
        self.assertIn('Keep-alive', s)

    def test_summary_poll(self):
        frame = UMBUSFrame(frame_type=0x0E, raw=CMD_0E_FIXED)
        s = frame.summary()
        self.assertIn('Poll', s)

    # --- repr ---

    def test_repr(self):
        frame = UMBUSFrame(frame_type=0x57, raw=b'\xa6' + b'\x57' + b'\x00' * 85)
        r = repr(frame)
        self.assertIn('CHANNEL_DATA', r)
        self.assertIn('87B', r)


# ===================================================================
# Constants & Fixed Frames
# ===================================================================

class TestConstants(unittest.TestCase):

    def test_sync_byte(self):
        self.assertEqual(SYNC_BYTE, 0xA6)

    def test_frame_sizes(self):
        self.assertEqual(FRAME_SIZES[FrameType.CHANNEL_DATA], 87)
        self.assertEqual(FRAME_SIZES[FrameType.ELRS_TELEM], 21)
        self.assertEqual(FRAME_SIZES[FrameType.CMD_07], 7)
        self.assertEqual(FRAME_SIZES[FrameType.CMD_0C], 12)
        self.assertEqual(FRAME_SIZES[FrameType.CMD_0E], 14)
        self.assertEqual(FRAME_SIZES[FrameType.EXTENDED], 18)

    def test_channel_constants(self):
        self.assertEqual(CHANNEL_CENTER, 0x8000)
        self.assertEqual(CHANNEL_MIN, 0x0000)
        self.assertEqual(CHANNEL_MAX, 0xFFFF)
        self.assertEqual(SWITCH_HIGH, 0xFE0C)
        self.assertEqual(SWITCH_ALT, 0xFF9C)

    def test_heartbeat_mcu_fixed(self):
        self.assertEqual(len(HEARTBEAT_MCU_FIXED), 7)
        self.assertEqual(HEARTBEAT_MCU_FIXED[0], SYNC_BYTE)
        self.assertEqual(HEARTBEAT_MCU_FIXED[1], 0x08)

    def test_heartbeat_app_fixed(self):
        self.assertEqual(len(HEARTBEAT_APP_FIXED), 8)
        self.assertEqual(HEARTBEAT_APP_FIXED[0], SYNC_BYTE)
        self.assertEqual(HEARTBEAT_APP_FIXED[1], 0x08)
        self.assertEqual(HEARTBEAT_APP_FIXED[2], 0x35)

    def test_cmd_0e_fixed(self):
        self.assertEqual(len(CMD_0E_FIXED), 14)
        self.assertEqual(CMD_0E_FIXED[0], SYNC_BYTE)
        self.assertEqual(CMD_0E_FIXED[1], 0x0E)

    def test_cmd_07_fixed(self):
        self.assertEqual(len(CMD_07_FIXED), 7)
        self.assertEqual(CMD_07_FIXED[0], SYNC_BYTE)
        self.assertEqual(CMD_07_FIXED[1], 0x07)

    def test_fixed_frames_checksums(self):
        """All fixed App→MCU frames should have valid checksums."""
        self.assertTrue(verify_checksum(HEARTBEAT_APP_FIXED))
        self.assertTrue(verify_checksum(CMD_0E_FIXED))
        self.assertTrue(verify_checksum(CMD_07_FIXED))

    def test_frame_type_enum_values(self):
        self.assertEqual(FrameType.CHANNEL_DATA, 0x57)
        self.assertEqual(FrameType.HEARTBEAT_MCU, 0x08)
        self.assertEqual(FrameType.EXTENDED, 0x10)
        self.assertEqual(FrameType.ELRS_TELEM, 0x15)
        self.assertEqual(FrameType.CMD_07, 0x07)
        self.assertEqual(FrameType.CMD_0C, 0x0C)
        self.assertEqual(FrameType.CMD_0E, 0x0E)
        self.assertEqual(FrameType.IDLE, 0x77)


# ===================================================================
# Streaming Decoder
# ===================================================================

class TestUMBUSDecoder(unittest.TestCase):

    def test_decode_single_frame(self):
        """Decode a single CHANNEL_DATA frame."""
        frames = load_captured_frames()
        f = frames[0]
        raw = hex_to_bytes(f['h'])

        decoder = UMBUSDecoder()
        result = list(decoder.feed(raw))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].frame_type, FrameType.CHANNEL_DATA)
        self.assertTrue(result[0].checksum_valid)

    def test_decode_multiple_frames(self):
        """Concatenate several frames and decode them all."""
        frames = load_captured_frames()
        blob = b''
        count = 0
        for f in frames[:20]:
            blob += hex_to_bytes(f['h'])
            count += 1

        decoder = UMBUSDecoder()
        result = list(decoder.feed(blob))
        self.assertEqual(len(result), count)

    def test_decode_all_captured(self):
        """Decode every frame from captures/frames.json."""
        frames = load_captured_frames()
        blob = b''.join(hex_to_bytes(f['h']) for f in frames)

        decoder = UMBUSDecoder()
        result = list(decoder.feed(blob))
        self.assertEqual(len(result), len(frames))

        # Verify type distribution
        from collections import Counter
        types = Counter(fr.type_name for fr in result)
        self.assertEqual(types['CHANNEL_DATA'], 247)
        self.assertEqual(types['ELRS_TELEM'], 50)
        self.assertEqual(types['HEARTBEAT_MCU'], 40)
        self.assertEqual(types['EXTENDED'], 30)

    def test_decode_chunked(self):
        """Feed data one byte at a time — should still decode correctly."""
        frames = load_captured_frames()
        raw = hex_to_bytes(frames[0]['h'])

        decoder = UMBUSDecoder()
        result = []
        for byte in raw:
            result.extend(decoder.feed(bytes([byte])))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].frame_type, FrameType.CHANNEL_DATA)

    def test_decode_chunked_random_sizes(self):
        """Feed data in random-sized chunks."""
        import random
        random.seed(42)  # deterministic
        frames = load_captured_frames()
        blob = b''.join(hex_to_bytes(f['h']) for f in frames[:50])

        decoder = UMBUSDecoder()
        result = []
        pos = 0
        while pos < len(blob):
            chunk_size = random.randint(1, 30)
            chunk = blob[pos:pos + chunk_size]
            result.extend(decoder.feed(chunk))
            pos += chunk_size
        self.assertEqual(len(result), 50)

    def test_decode_with_garbage_prefix(self):
        """Garbage bytes before sync should be skipped."""
        frames = load_captured_frames()
        raw = hex_to_bytes(frames[0]['h'])
        garbage = b'\x00\x01\x02\x03\xFF\xFE'

        decoder = UMBUSDecoder()
        result = list(decoder.feed(garbage + raw))
        self.assertEqual(len(result), 1)
        self.assertEqual(decoder.bytes_skipped, len(garbage))

    def test_decode_with_garbage_between(self):
        """Garbage between valid frames should be skipped."""
        frames = load_captured_frames()
        raw1 = hex_to_bytes(frames[0]['h'])
        raw2 = hex_to_bytes(frames[1]['h'])
        garbage = b'\x00\xFF\x01\x02'

        decoder = UMBUSDecoder()
        result = list(decoder.feed(raw1 + garbage + raw2))
        self.assertEqual(len(result), 2)

    def test_stats(self):
        frames = load_captured_frames()
        blob = b''.join(hex_to_bytes(f['h']) for f in frames[:10])

        decoder = UMBUSDecoder()
        list(decoder.feed(blob))  # consume
        stats = decoder.stats
        self.assertEqual(stats['frames_decoded'], 10)
        self.assertEqual(stats['buffer_size'], 0)

    def test_reset(self):
        frames = load_captured_frames()
        raw = hex_to_bytes(frames[0]['h'])

        decoder = UMBUSDecoder()
        list(decoder.feed(raw))
        self.assertEqual(decoder.frames_decoded, 1)

        decoder.reset()
        self.assertEqual(decoder.frames_decoded, 0)
        self.assertEqual(decoder.bytes_skipped, 0)
        self.assertEqual(decoder.frames_bad_checksum, 0)

    def test_heartbeat_disambiguation(self):
        """Decoder should handle 7B MCU vs 8B App heartbeats."""
        decoder = UMBUSDecoder()

        # MCU heartbeat (7B)
        result = list(decoder.feed(HEARTBEAT_MCU_FIXED))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].frame_type, 0x08)
        self.assertEqual(len(result[0].raw), 7)

        # App heartbeat (8B)
        result = list(decoder.feed(HEARTBEAT_APP_FIXED))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].frame_type, 0x08)
        self.assertEqual(len(result[0].raw), 8)

    def test_back_to_back_heartbeats(self):
        """MCU heartbeat immediately followed by App heartbeat."""
        decoder = UMBUSDecoder()
        result = list(decoder.feed(HEARTBEAT_MCU_FIXED + HEARTBEAT_APP_FIXED))
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0].raw), 7)
        self.assertEqual(len(result[1].raw), 8)

    def test_incomplete_frame_buffered(self):
        """Partial frame should be buffered, completed on next feed."""
        frames = load_captured_frames()
        raw = hex_to_bytes(frames[0]['h'])
        half = len(raw) // 2

        decoder = UMBUSDecoder()
        result1 = list(decoder.feed(raw[:half]))
        self.assertEqual(len(result1), 0)

        result2 = list(decoder.feed(raw[half:]))
        self.assertEqual(len(result2), 1)

    def test_bad_checksum_counted(self):
        """Corrupted frame should still decode but flag bad checksum."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'CHANNEL_DATA':
                raw = bytearray(hex_to_bytes(f['h']))
                raw[-1] ^= 0xFF  # corrupt checksum byte
                decoder = UMBUSDecoder()
                result = list(decoder.feed(bytes(raw)))
                self.assertEqual(len(result), 1)
                self.assertFalse(result[0].checksum_valid)
                self.assertEqual(decoder.frames_bad_checksum, 1)
                break

    def test_timed_frames_decode(self):
        """Decode all frames from timed-frames.json."""
        timed = load_timed_frames()
        blob = b''.join(hex_to_bytes(entry[2]) for entry in timed)
        decoder = UMBUSDecoder()
        result = list(decoder.feed(blob))
        self.assertEqual(len(result), len(timed))


# ===================================================================
# Encoder
# ===================================================================

class TestUMBUSEncoder(unittest.TestCase):

    def test_heartbeat_app(self):
        frame = UMBUSEncoder.heartbeat_app()
        self.assertEqual(frame, HEARTBEAT_APP_FIXED)
        self.assertTrue(verify_checksum(frame))

    def test_keepalive(self):
        frame = UMBUSEncoder.keepalive()
        self.assertEqual(frame, CMD_07_FIXED)
        self.assertTrue(verify_checksum(frame))

    def test_poll(self):
        frame = UMBUSEncoder.poll()
        self.assertEqual(frame, CMD_0E_FIXED)
        self.assertTrue(verify_checksum(frame))

    def test_roundtrip_heartbeat(self):
        """Encode then decode an App heartbeat."""
        frame_bytes = UMBUSEncoder.heartbeat_app()
        decoder = UMBUSDecoder()
        result = list(decoder.feed(frame_bytes))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].frame_type, 0x08)
        self.assertEqual(result[0].source, 'App→MCU')

    def test_roundtrip_keepalive(self):
        frame_bytes = UMBUSEncoder.keepalive()
        decoder = UMBUSDecoder()
        result = list(decoder.feed(frame_bytes))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].frame_type, FrameType.CMD_07)

    def test_roundtrip_poll(self):
        frame_bytes = UMBUSEncoder.poll()
        decoder = UMBUSDecoder()
        result = list(decoder.feed(frame_bytes))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].frame_type, FrameType.CMD_0E)

    def test_roundtrip_all_app_frames(self):
        """All encoder outputs should round-trip through the decoder."""
        decoder = UMBUSDecoder()
        blob = (UMBUSEncoder.heartbeat_app() +
                UMBUSEncoder.keepalive() +
                UMBUSEncoder.poll())
        result = list(decoder.feed(blob))
        self.assertEqual(len(result), 3)
        types = [r.frame_type for r in result]
        self.assertIn(0x08, types)
        self.assertIn(0x07, types)
        self.assertIn(0x0E, types)

    # --- channel_data ---

    def test_channel_data_defaults(self):
        """Default channel_data frame should be 87 bytes with valid checksum."""
        frame = UMBUSEncoder.channel_data()
        self.assertEqual(len(frame), 87)
        self.assertEqual(frame[0], SYNC_BYTE)
        self.assertEqual(frame[1], FrameType.CHANNEL_DATA)
        self.assertTrue(verify_checksum(frame))

    def test_channel_data_roundtrip(self):
        """Encode then decode channel data."""
        gimbals = [100, -200, 300, -400]
        channels = [CHANNEL_CENTER] * 32
        channels[0] = 0
        channels[5] = SWITCH_HIGH
        frame_bytes = UMBUSEncoder.channel_data(gimbals=gimbals, channels=channels, seq=42)

        decoder = UMBUSDecoder()
        result = list(decoder.feed(frame_bytes))
        self.assertEqual(len(result), 1)
        f = result[0]
        self.assertEqual(f.frame_type, FrameType.CHANNEL_DATA)
        self.assertTrue(f.checksum_valid)
        self.assertEqual(f.gimbals, gimbals)
        self.assertEqual(f.channels[0], 0)
        self.assertEqual(f.channels[5], SWITCH_HIGH)

    def test_channel_data_gimbal_clamping(self):
        """Gimbal values should be clamped to s16 range."""
        frame = UMBUSEncoder.channel_data(gimbals=[99999, -99999, 0, 0])
        decoder = UMBUSDecoder()
        result = list(decoder.feed(frame))
        self.assertEqual(result[0].gimbals[0], 32767)
        self.assertEqual(result[0].gimbals[1], -32768)

    def test_channel_data_seq(self):
        """Sequence counter should be embedded in byte 83."""
        frame = UMBUSEncoder.channel_data(seq=0xAB)
        self.assertEqual(frame[83], 0xAB)

    def test_channel_data_partial_channels(self):
        """Fewer than 32 channels should be padded with CENTER."""
        frame = UMBUSEncoder.channel_data(channels=[0, 65535])
        decoder = UMBUSDecoder()
        result = list(decoder.feed(frame))
        ch = result[0].channels
        self.assertEqual(ch[0], 0)
        self.assertEqual(ch[1], 65535)
        # Channels 2-31 should be CENTER (ch[32] spans unknown/seq bytes)
        for v in ch[2:32]:
            self.assertEqual(v, CHANNEL_CENTER)

    # --- heartbeat_mcu ---

    def test_heartbeat_mcu(self):
        frame = UMBUSEncoder.heartbeat_mcu()
        self.assertEqual(frame, HEARTBEAT_MCU_FIXED)
        self.assertEqual(len(frame), 7)

    def test_heartbeat_mcu_roundtrip(self):
        decoder = UMBUSDecoder()
        result = list(decoder.feed(UMBUSEncoder.heartbeat_mcu()))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].frame_type, FrameType.HEARTBEAT_MCU)

    # --- extended_telemetry ---

    def test_extended_telemetry_size(self):
        frame = UMBUSEncoder.extended_telemetry()
        self.assertEqual(len(frame), 18)
        self.assertTrue(verify_checksum(frame))

    def test_extended_telemetry_roundtrip(self):
        frame_bytes = UMBUSEncoder.extended_telemetry(sub_index=1, value=0x1234)
        decoder = UMBUSDecoder()
        result = list(decoder.feed(frame_bytes))
        self.assertEqual(len(result), 1)
        f = result[0]
        self.assertEqual(f.frame_type, FrameType.EXTENDED)
        self.assertTrue(f.checksum_valid)
        ext = f.extended_telemetry
        self.assertEqual(ext['sub_index'], 1)
        self.assertEqual(ext['value'], 0x1234)

    def test_extended_telemetry_source(self):
        frame_bytes = UMBUSEncoder.extended_telemetry()
        decoder = UMBUSDecoder()
        result = list(decoder.feed(frame_bytes))
        self.assertEqual(result[0].source, 'MCU→App')

    # --- elrs_telemetry ---

    def test_elrs_telemetry_size(self):
        frame = UMBUSEncoder.elrs_telemetry()
        self.assertEqual(len(frame), 21)
        self.assertTrue(verify_checksum(frame))

    def test_elrs_telemetry_roundtrip(self):
        frame_bytes = UMBUSEncoder.elrs_telemetry(timing_us=20000, link_status=0, seq=5)
        decoder = UMBUSDecoder()
        result = list(decoder.feed(frame_bytes))
        self.assertEqual(len(result), 1)
        f = result[0]
        self.assertEqual(f.frame_type, FrameType.ELRS_TELEM)
        self.assertTrue(f.checksum_valid)
        elrs = f.elrs_telemetry
        self.assertEqual(elrs['timing_us'], 20000)
        self.assertEqual(elrs['seq'], 5)
        self.assertEqual(elrs['crsf_type'], 0x3A)
        self.assertEqual(elrs['sub_cmd'], 0x10)

    def test_elrs_telemetry_invalid_link(self):
        frame_bytes = UMBUSEncoder.elrs_telemetry(link_status=0xFFFF)
        decoder = UMBUSDecoder()
        result = list(decoder.feed(frame_bytes))
        elrs = result[0].elrs_telemetry
        self.assertFalse(elrs['link_valid'])

    # --- mixed traffic roundtrip ---

    def test_full_traffic_roundtrip(self):
        """Simulate a realistic burst of mixed UMBUS traffic."""
        blob = b''
        blob += UMBUSEncoder.heartbeat_mcu()
        for i in range(5):
            blob += UMBUSEncoder.channel_data(gimbals=[i, -i, i*2, -i*2], seq=i)
        blob += UMBUSEncoder.elrs_telemetry(timing_us=20000, seq=1)
        blob += UMBUSEncoder.heartbeat_app()
        blob += UMBUSEncoder.poll()
        blob += UMBUSEncoder.extended_telemetry(sub_index=0, value=100)
        blob += UMBUSEncoder.extended_telemetry(sub_index=1, value=200)
        blob += UMBUSEncoder.extended_telemetry(sub_index=2, value=300)
        blob += UMBUSEncoder.keepalive()

        decoder = UMBUSDecoder()
        result = list(decoder.feed(blob))
        self.assertEqual(len(result), 13)  # 1 + 5 + 1 + 1 + 1 + 3 + 1
        self.assertEqual(decoder.frames_bad_checksum, 0)

        # Check types
        from collections import Counter
        types = Counter(r.type_name for r in result)
        self.assertEqual(types['CHANNEL_DATA'], 5)
        self.assertEqual(types['HEARTBEAT_MCU'], 2)  # MCU + App both type 0x08
        self.assertEqual(types['ELRS_TELEM'], 1)
        self.assertEqual(types['EXTENDED'], 3)
        self.assertEqual(types['CMD_0E'], 1)
        self.assertEqual(types['CMD_07'], 1)


# ===================================================================
# Utility Functions
# ===================================================================

class TestUtilities(unittest.TestCase):

    def test_describe_channel_center(self):
        self.assertEqual(describe_channel_value(CHANNEL_CENTER), "CENTER")

    def test_describe_channel_min(self):
        self.assertEqual(describe_channel_value(CHANNEL_MIN), "MIN")

    def test_describe_channel_max(self):
        self.assertEqual(describe_channel_value(CHANNEL_MAX), "MAX")

    def test_describe_switch_high(self):
        self.assertEqual(describe_channel_value(SWITCH_HIGH), "SW_HIGH")

    def test_describe_switch_alt(self):
        self.assertEqual(describe_channel_value(SWITCH_ALT), "SW_ALT")

    def test_describe_channel_arbitrary(self):
        desc = describe_channel_value(40000)
        self.assertIn('40000', desc)
        self.assertIn('+', desc)  # positive percentage
        self.assertIn('%', desc)

    def test_describe_channel_below_center(self):
        desc = describe_channel_value(16384)
        self.assertIn('16384', desc)
        self.assertIn('-', desc)  # negative percentage
        self.assertIn('%', desc)

    def test_parse_strace_hex_escaped(self):
        line = r'read(103, "\xa6\x57\x10\x02\x04\x01", 4096) = 6'
        result = parse_strace_hex(line)
        self.assertIsNotNone(result)
        self.assertEqual(result, bytes([0xa6, 0x57, 0x10, 0x02, 0x04, 0x01]))

    def test_parse_strace_hex_dump(self):
        line = '| 00000  a6 57 10 02 04 01  .W.... |'
        result = parse_strace_hex(line)
        self.assertIsNotNone(result)
        # Should contain the hex bytes (may also pick up offset digits)
        self.assertIn(0xa6, result)
        self.assertIn(0x57, result)

    def test_parse_strace_hex_no_data(self):
        result = parse_strace_hex("nothing useful here")
        self.assertIsNone(result)


# ===================================================================
# Integration: Full Capture Validation
# ===================================================================

class TestCaptureIntegration(unittest.TestCase):
    """Validate the full captured dataset against expected properties."""

    def test_all_frames_have_sync_byte(self):
        frames = load_captured_frames()
        for f in frames:
            raw = hex_to_bytes(f['h'])
            self.assertEqual(raw[0], SYNC_BYTE,
                             f"Frame {f['n']} missing sync byte")

    def test_frame_sizes_match(self):
        """Every frame's raw length should match its declared size."""
        frames = load_captured_frames()
        for f in frames:
            raw = hex_to_bytes(f['h'])
            self.assertEqual(len(raw), f['s'],
                             f"Size mismatch for {f['n']}: {len(raw)} != {f['s']}")

    def test_frame_type_matches_second_byte(self):
        frames = load_captured_frames()
        for f in frames:
            raw = hex_to_bytes(f['h'])
            ft = raw[1]
            # type byte should decode to the named type
            try:
                expected_name = FrameType(ft).name
            except ValueError:
                expected_name = f"UNKNOWN_0x{ft:02X}"
            self.assertEqual(f['n'], expected_name,
                             f"Type name mismatch: {f['n']} != {expected_name}")

    def test_channel_data_gimbal_consistency(self):
        """All CHANNEL_DATA frames should have 4 gimbals."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'CHANNEL_DATA':
                self.assertEqual(len(f['g']), 4)

    def test_checksum_success_rate(self):
        """At least 99% of frames should have valid checksums (per docs)."""
        frames = load_captured_frames()
        ok_count = sum(1 for f in frames if f['ok'])
        rate = ok_count / len(frames) * 100
        self.assertGreaterEqual(rate, 99.0,
                                f"Checksum success rate {rate:.1f}% < 99%")

    def test_elrs_frames_have_crsf_type(self):
        """All ELRS frames should have CRSF_FRAMETYPE_HANDSET = 0x3A."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'ELRS_TELEM':
                raw = hex_to_bytes(f['h'])
                frame = UMBUSFrame(frame_type=raw[1], raw=raw, checksum_valid=True)
                elrs = frame.elrs_telemetry
                if elrs:
                    self.assertEqual(elrs['crsf_type'], 0x3A)

    def test_extended_sub_indices_range(self):
        """Extended telemetry sub_index should be 0, 1, or 2."""
        frames = load_captured_frames()
        for f in frames:
            if f['n'] == 'EXTENDED':
                raw = hex_to_bytes(f['h'])
                frame = UMBUSFrame(frame_type=raw[1], raw=raw, checksum_valid=True)
                ext = frame.extended_telemetry
                if ext:
                    self.assertIn(ext['sub_index'], [0, 1, 2],
                                  f"Unexpected sub_index: {ext['sub_index']}")

    def test_timing_consistency(self):
        """Timed frames should have monotonically increasing timestamps."""
        timed = load_timed_frames()
        timestamps = [entry[0] for entry in timed]
        for i in range(1, len(timestamps)):
            self.assertGreaterEqual(timestamps[i], timestamps[i - 1],
                                    f"Non-monotonic timestamp at index {i}")


if __name__ == '__main__':
    unittest.main()
