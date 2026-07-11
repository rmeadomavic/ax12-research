#!/usr/bin/env python3
"""Smoke test for the installable ``umbus`` package (repo-root ``umbus/``).

``tools/test_umbus.py`` exercises the single-file ``tools/umbus.py`` module. The
pip-packaged ``umbus/`` package — exposed as the ``umbus-decode`` console script
in ``pyproject.toml`` — had no tests at all. This adds a minimal smoke test that
imports the package and decodes one known-good captured frame, mirroring
``TestUMBUSDecoder.test_decode_single_frame`` in ``test_umbus.py``.

Both libraries claim the top-level name ``umbus``. Once ``tools/test_umbus.py``
imports ``tools/umbus.py`` it owns that name in ``sys.modules`` for the rest of
the process, so we isolate the import here: put the repo root ahead of ``tools/``
on ``sys.path`` and load the package fresh, restoring global state afterward so
sibling tests are unaffected.
"""

import json
import os
import sys
import unittest
from contextlib import contextmanager

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES_JSON = os.path.join(REPO_ROOT, "captures", "frames.json")


@contextmanager
def import_umbus_package():
    """Import the repo-root ``umbus/`` package, shadowing ``tools/umbus.py``."""
    saved_path = list(sys.path)
    saved_modules = {
        name: mod
        for name, mod in sys.modules.items()
        if name == "umbus" or name.startswith("umbus.")
    }
    for name in saved_modules:
        del sys.modules[name]
    sys.path.insert(0, REPO_ROOT)
    try:
        import umbus  # repo-root package, not tools/umbus.py

        yield umbus
    finally:
        sys.path[:] = saved_path
        for name in [n for n in sys.modules if n == "umbus" or n.startswith("umbus.")]:
            del sys.modules[name]
        sys.modules.update(saved_modules)


class TestUmbusPackageSmoke(unittest.TestCase):
    def test_decode_single_known_frame(self):
        """Package decodes the first captured CHANNEL_DATA frame with a valid checksum."""
        with open(FRAMES_JSON) as f:
            frames = json.load(f)["frames"]
        raw = bytes.fromhex(frames[0]["h"])

        with import_umbus_package() as umbus:
            # Guard: make sure we loaded the package, not tools/umbus.py.
            self.assertTrue(
                os.path.abspath(umbus.__file__).startswith(
                    os.path.join(REPO_ROOT, "umbus") + os.sep
                ),
                f"expected repo-root umbus/ package, got {umbus.__file__}",
            )
            decoder = umbus.UMBUSDecoder()
            result = list(decoder.feed(raw))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].frame_type, umbus.FrameType.CHANNEL_DATA)
            self.assertTrue(result[0].checksum_valid)


if __name__ == "__main__":
    unittest.main()
