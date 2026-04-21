"""
Streaming UMBUS frame decoder.

Feed raw bytes from any source (serial port, file, strace output) and
iterate over decoded frames. The decoder maintains an internal buffer
and handles partial reads, sync recovery, and checksum validation.
"""

from typing import Iterator

from umbus.constants import SYNC_BYTE
from umbus.crc import verify_checksum
from umbus.frame import FRAME_SIZES, UMBUSFrame


class UMBUSDecoder:
    """Streaming UMBUS frame decoder.

    Feed raw bytes and iterate over decoded frames::

        decoder = UMBUSDecoder()
        for frame in decoder.feed(data):
            print(frame.summary())

    The decoder automatically:

    - Scans for sync bytes (``0xA6``)
    - Determines frame length from the type byte
    - Validates CRC-8/MAXIM checksums
    - Tracks decode statistics
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.frames_decoded: int = 0
        self.frames_bad_checksum: int = 0
        self.bytes_skipped: int = 0

    def feed(self, data: bytes) -> Iterator[UMBUSFrame]:
        """Feed raw bytes and yield decoded frames.

        Args:
            data: Raw bytes to decode. May contain partial frames;
                  leftover bytes are buffered for the next call.

        Yields:
            :class:`~umbus.frame.UMBUSFrame` instances for each
            complete frame found in the data.
        """
        self._buf.extend(data)

        while True:
            # Find sync byte
            sync_idx = self._buf.find(bytes([SYNC_BYTE]))
            if sync_idx < 0:
                self.bytes_skipped += len(self._buf)
                self._buf.clear()
                return

            if sync_idx > 0:
                self.bytes_skipped += sync_idx
                del self._buf[:sync_idx]

            # Need at least 2 bytes (sync + type)
            if len(self._buf) < 2:
                return

            frame_type = self._buf[1]

            # Determine frame size
            # Special case: 0x08 can be 7B (MCU) or 8B (App), disambiguate
            if frame_type == 0x08 and len(self._buf) >= 4:
                if self._buf[2] == 0x35:  # App heartbeat header
                    frame_size = 8
                else:
                    frame_size = 7  # MCU heartbeat
            else:
                frame_size = FRAME_SIZES.get(frame_type)

            if frame_size is None:
                # Unknown frame type: the type byte IS the total length
                frame_size = frame_type
                if frame_size < 3 or frame_size > 256:
                    del self._buf[0]
                    self.bytes_skipped += 1
                    continue

            # Wait for full frame
            if len(self._buf) < frame_size:
                return

            raw = bytes(self._buf[:frame_size])
            del self._buf[:frame_size]

            # Verify checksum
            chk_valid = verify_checksum(raw)
            if not chk_valid:
                self.frames_bad_checksum += 1

            frame = UMBUSFrame(
                frame_type=frame_type,
                raw=raw,
                checksum_valid=chk_valid,
            )
            self.frames_decoded += 1
            yield frame

    def reset(self) -> None:
        """Reset decoder state, clearing the buffer and all counters."""
        self._buf.clear()
        self.frames_decoded = 0
        self.frames_bad_checksum = 0
        self.bytes_skipped = 0

    @property
    def stats(self) -> dict:
        """Current decoder statistics.

        Returns:
            Dict with ``frames_decoded``, ``frames_bad_checksum``,
            ``bytes_skipped``, and ``buffer_size``.
        """
        return {
            "frames_decoded": self.frames_decoded,
            "frames_bad_checksum": self.frames_bad_checksum,
            "bytes_skipped": self.bytes_skipped,
            "buffer_size": len(self._buf),
        }
