#!/usr/bin/env python3
"""
Test suite for the strace-parser.py module.

Tests hex extraction, syscall record parsing, and frame decoding
from real and synthetic strace output — no hardware needed.

Run:
    python3 -m unittest tools/test_strace_parser.py -v
    # or
    python3 tools/test_strace_parser.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the functions under test (strace-parser.py uses a hyphen, so import manually)
import importlib.util
_parser_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'strace-parser.py')
_spec = importlib.util.spec_from_file_location('strace_parser', _parser_path)
strace_parser = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(strace_parser)

extract_hex_from_strace = strace_parser.extract_hex_from_strace
parse_strace_syscalls = strace_parser.parse_strace_syscalls

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDLE_STRACE = os.path.join(REPO_ROOT, 'captures', 'idle-strace.txt')


# ===================================================================
# extract_hex_from_strace
# ===================================================================

class TestExtractHex(unittest.TestCase):

    def test_hex_dump_format(self):
        """Standard strace hex dump lines should be parsed."""
        text = (
            " | 00000  a6 57 10 02 04 01 03 00  ff ff b8 fe 01 00 f8 ff  .W.............. |\n"
            " | 00010  9c 00 00 80 00 80 00 80  00 80 00 80 00 80 07 00  ................ |"
        )
        result = extract_hex_from_strace(text)
        self.assertEqual(len(result), 32)
        self.assertEqual(result[0], 0xa6)
        self.assertEqual(result[1], 0x57)

    def test_escaped_string_format(self):
        """Strace escaped string format should be parsed."""
        text = r'read(103, "\xa6\x57\x10\x02\x04\x01", 4096) = 6'
        result = extract_hex_from_strace(text)
        self.assertEqual(len(result), 6)
        self.assertEqual(result[0], 0xa6)
        self.assertEqual(result[1], 0x57)

    def test_empty_input(self):
        result = extract_hex_from_strace("")
        self.assertEqual(result, b'')

    def test_no_hex_data(self):
        result = extract_hex_from_strace("just some random text\nnothing here")
        self.assertEqual(result, b'')

    def test_multiline_hex_dump(self):
        """Multi-line hex dump (like a full 87-byte channel frame)."""
        text = (
            " | 00000  a6 57 10 02 04 01 03 00  ff ff b8 fe 01 00 f8 ff  .W.............. |\n"
            " | 00010  9c 00 00 80 00 80 00 80  00 80 00 80 00 80 07 00  ................ |\n"
            " | 00020  7b fe 00 80 00 80 00 80  00 80 00 80 00 80 0c fe  {............... |\n"
            " | 00030  0c fe 00 00 0c fe 00 00  f4 01 00 80 00 80 00 80  ................ |\n"
            " | 00040  00 80 00 80 00 80 00 80  00 80 00 80 0c fe 00 00  ................ |\n"
            " | 00050  00 00 01 00 90 01 80                              .......          |"
        )
        result = extract_hex_from_strace(text)
        self.assertEqual(len(result), 87)
        self.assertEqual(result[0], 0xa6)
        self.assertEqual(result[1], 0x57)

    def test_mixed_formats(self):
        """Mix of escaped strings and hex dumps."""
        text = (
            r'read(94, "\xa6\x08\x10\x02\x04\x03\x00", 32768) = 7' + "\n"
            " | 00000  a6 08 10 02 04 03 00                              .......          |"
        )
        result = extract_hex_from_strace(text)
        # Should get bytes from both lines
        self.assertGreater(len(result), 7)
        self.assertEqual(result[0], 0xa6)


# ===================================================================
# parse_strace_syscalls
# ===================================================================

class TestParseSyscalls(unittest.TestCase):

    SAMPLE_STRACE = (
        '[pid 14372] 07:05:03.963555 read(94, "\\xa6\\x08\\x10\\x02\\x04\\x03\\x00", 32768) = 7\n'
        ' | 00000  a6 08 10 02 04 03 00                              .......          |\n'
        '[pid 14372] 07:05:03.993363 read(94, "\\xa6\\x57\\x10\\x02\\x04\\x01\\x03\\x00", 32768) = 21\n'
        ' | 00000  a6 57 10 02 04 01 03 00  ff ff b8 fe 01 00 f8 ff  .W.............. |\n'
        ' | 00010  9c 00 00 80 00                                    .....            |\n'
    )

    def test_parses_records(self):
        records = parse_strace_syscalls(self.SAMPLE_STRACE)
        self.assertEqual(len(records), 2)

    def test_record_fields(self):
        records = parse_strace_syscalls(self.SAMPLE_STRACE)
        r = records[0]
        self.assertEqual(r['syscall'], 'read')
        self.assertEqual(r['fd'], 94)
        self.assertEqual(r['size'], 7)
        self.assertEqual(r['direction'], 'MCU→App')
        self.assertEqual(r['timestamp'], '07:05:03.963555')

    def test_hex_data_extracted(self):
        records = parse_strace_syscalls(self.SAMPLE_STRACE)
        r = records[0]
        self.assertIn('hex_data', r)
        self.assertIsInstance(r['hex_data'], bytes)
        self.assertGreater(len(r['hex_data']), 0)
        # First byte should be 0xa6 (sync)
        self.assertEqual(r['hex_data'][0], 0xa6)

    def test_write_direction(self):
        text = (
            '[pid 14372] 07:05:04.200000 write(94, "\\xa6\\x0e\\x10\\x04", 32768) = 14\n'
            ' | 00000  a6 0e 10 04 02 02 06 83  df 00 00 00 00 2f        ............./ |\n'
        )
        records = parse_strace_syscalls(text)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['direction'], 'App→MCU')
        self.assertEqual(records[0]['syscall'], 'write')

    def test_empty_input(self):
        records = parse_strace_syscalls("")
        self.assertEqual(len(records), 0)

    def test_no_hex_data(self):
        """Syscall lines without hex dumps produce no records."""
        text = "some random log output\nnot a strace line\n"
        records = parse_strace_syscalls(text)
        self.assertEqual(len(records), 0)

    def test_multiple_reads_writes(self):
        """Interleaved reads and writes."""
        text = (
            '[pid 100] 07:05:04.000000 read(94, "\\xa6\\x08", 1024) = 7\n'
            ' | 00000  a6 08 10 02 04 03 00                              .......          |\n'
            '[pid 100] 07:05:04.100000 write(94, "\\xa6\\x07", 1024) = 7\n'
            ' | 00000  a6 07 2b 04 ff 01 f4                              ..+....          |\n'
            '[pid 100] 07:05:04.200000 read(94, "\\xa6\\x57", 1024) = 87\n'
            ' | 00000  a6 57 10 02 04 01 03 00  ff ff b8 fe 01 00 f8 ff  .W.............. |\n'
            ' | 00010  9c 00 00 80 00                                    .....            |\n'
        )
        records = parse_strace_syscalls(text)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]['direction'], 'MCU→App')
        self.assertEqual(records[1]['direction'], 'App→MCU')
        self.assertEqual(records[2]['direction'], 'MCU→App')


# ===================================================================
# Integration: Real Strace File
# ===================================================================

class TestRealStrace(unittest.TestCase):
    """Test against the actual captured idle-strace.txt file."""

    @unittest.skipUnless(os.path.exists(IDLE_STRACE), "idle-strace.txt not found")
    def test_parse_idle_strace(self):
        with open(IDLE_STRACE) as f:
            text = f.read()
        records = parse_strace_syscalls(text)
        # The idle strace should have many reads on fd 94
        self.assertGreater(len(records), 0)

    @unittest.skipUnless(os.path.exists(IDLE_STRACE), "idle-strace.txt not found")
    def test_idle_strace_has_reads(self):
        with open(IDLE_STRACE) as f:
            text = f.read()
        records = parse_strace_syscalls(text)
        reads = [r for r in records if r['syscall'] == 'read']
        self.assertGreater(len(reads), 0)

    @unittest.skipUnless(os.path.exists(IDLE_STRACE), "idle-strace.txt not found")
    def test_idle_strace_has_serial_data(self):
        """Records from fd 94 should contain UMBUS sync bytes."""
        with open(IDLE_STRACE) as f:
            text = f.read()
        records = parse_strace_syscalls(text)
        serial_records = [r for r in records if r['fd'] == 94]
        if serial_records:
            # At least some should have hex data starting with 0xa6
            has_umbus = any(
                r.get('hex_data', b'') and r['hex_data'][0] == 0xa6
                for r in serial_records
            )
            self.assertTrue(has_umbus, "No UMBUS sync bytes found in fd 94 records")

    @unittest.skipUnless(os.path.exists(IDLE_STRACE), "idle-strace.txt not found")
    def test_idle_strace_decode_frames(self):
        """Decode UMBUS frames from the real strace capture."""
        from umbus import UMBUSDecoder
        with open(IDLE_STRACE) as f:
            text = f.read()
        records = parse_strace_syscalls(text)
        decoder = UMBUSDecoder()
        frame_count = 0
        for r in records:
            data = r.get('hex_data', b'')
            if data:
                for frame in decoder.feed(data):
                    frame_count += 1
        # Should decode at least some frames
        self.assertGreater(frame_count, 0)


if __name__ == '__main__':
    unittest.main()
