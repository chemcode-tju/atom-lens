"""Test real incremental I/O, version checks and raw-byte preservation."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
from trajectory import read_frames


class TrajectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "trajectory.extxyz"

    def read(self, **arguments: object) -> dict:
        return read_frames({"arguments": arguments,
                            "_meta": {"openai/resource": {"path": str(self.path)}}})

    def test_first_frame_does_not_scan_the_rest(self) -> None:
        first = b"1\nProperties=species:S:1:pos:R:3\nH 0 0 0\n"
        self.path.write_bytes(first + b"broken later frame\n")
        result = self.read(frameLimit=1)
        self.assertEqual(result["text"].encode(), first)
        self.assertEqual(result["nextOffset"], len(first))
        self.assertFalse(result["eof"])
        with self.assertRaisesRegex(ValueError, "原子数"):
            self.read(offset=result["nextOffset"], version=result["version"])

    def test_batches_preserve_crlf_unicode_and_missing_final_newline(self) -> None:
        raw = ("1\r\n注释\r\nH 0 0 0\r\n\r\n" * 65 + "1\n\nHe 1 2 3").encode()
        self.path.write_bytes(raw)
        offset, version, count = 0, None, 0
        chunks = []
        while True:
            result = self.read(offset=offset, version=version, frameLimit=1 if offset == 0 else 32)
            chunks.append(result["text"].encode())
            count += result["frameCount"]
            offset, version = result["nextOffset"], result["version"]
            if result["eof"]:
                break
        self.assertEqual(count, 66)
        self.assertEqual(b"".join(chunks), raw)

    def test_changed_file_rejects_continuation(self) -> None:
        self.path.write_text("1\n\nH 0 0 0\n" * 2)
        result = self.read(frameLimit=1)
        self.path.write_text("1\n\nO 0 0 0\n" * 3)
        with self.assertRaisesRegex(ValueError, "改变"):
            self.read(offset=result["nextOffset"], version=result["version"])

    def test_partial_frame_and_invalid_cursor(self) -> None:
        self.path.write_text("2\n\nH 0 0 0\n")
        with self.assertRaisesRegex(ValueError, "不完整"):
            self.read()
        with self.assertRaisesRegex(ValueError, "偏移"):
            self.read(offset=-1)

    def test_ui_cannot_supply_path(self) -> None:
        result = read_frames({"arguments": {"path": str(self.path)}})
        self.assertFalse(result["supported"])


if __name__ == "__main__":
    unittest.main()
