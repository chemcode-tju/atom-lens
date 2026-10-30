"""Regression tests for large unchanged-name VASP trajectories and progressive I/O."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
from trajectory import read_frames

header = b"Cu O\n1.0\n10 0 0\n0 10 0\n0 0 20\nCu O\n1 1\n"
frame = b"Direct configuration= 1\n0 0 0\n0.5 0.5 0.25\n"


class VaspTrajectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "XDATCAR"

    def read(self, **arguments: object) -> dict:
        return read_frames({"arguments": arguments, "_meta": {"openai/resource": {"path": str(self.path)}}})

    def test_first_frame_precedes_late_error(self) -> None:
        self.path.write_bytes(header + frame + b"broken later frame\n")
        result = self.read(frameLimit=1)
        self.assertEqual(result["format"], "vasp")
        self.assertEqual(result["text"].encode(), header + frame)
        self.assertEqual(result["nextOffset"], len(header + frame))
        self.assertFalse(result["eof"])
        with self.assertRaisesRegex(ValueError, "坐标模式"):
            self.read(offset=result["nextOffset"], version=result["version"])

    def test_over_64_mib_and_final_frame(self) -> None:
        repeat = (65 * 1024 * 1024) // len(frame) + 1
        with self.path.open("wb") as stream:
            stream.write(header)
            block = frame * 4096
            for _ in range(repeat // 4096):
                stream.write(block)
            stream.write(frame * (repeat % 4096))
        first = self.read(frameLimit=1)
        self.assertGreater(first["totalBytes"], 64 * 1024 * 1024)
        self.assertEqual(first["frameCount"], 1)
        last = self.read(offset=len(header) + (repeat - 1) * len(frame), version=first["version"])
        self.assertEqual(last["frameCount"], 1)
        self.assertTrue(last["eof"])
        self.assertEqual(last["text"], first["text"])

    def test_batches_crlf_and_changed_file(self) -> None:
        self.path.write_bytes((header + frame * 65).replace(b"\n", b"\r\n") + b"\r\n")
        first = self.read(frameLimit=1)
        offset, version, count = first["nextOffset"], first["version"], 1
        while True:
            batch = self.read(offset=offset, version=version)
            count += batch["frameCount"]
            offset = batch["nextOffset"]
            if batch["eof"]:
                break
        self.assertEqual(count, 65)
        self.path.write_bytes(header + frame)
        with self.assertRaisesRegex(ValueError, "改变"):
            self.read(offset=first["nextOffset"], version=version)

    def test_poscar_selective_and_truncated_xdatcar(self) -> None:
        self.path = self.path.with_name("POSCAR")
        content = header + b"Selective dynamics\nCartesian\n0 0 0 T T F\n1 2 3 F F F\n"
        self.path.write_bytes(content + b"\nvelocities follow\n")
        batch = self.read(frameLimit=1)
        self.assertEqual(batch["text"].encode(), content)
        self.assertTrue(batch["eof"])
        self.path = self.path.with_name("XDATCAR")
        self.path.write_bytes(header + b"Direct configuration= 1\n0 0 0\n")
        with self.assertRaisesRegex(ValueError, "不完整"):
            self.read(frameLimit=1)

    def test_index_only_offsets_can_refetch_each_frame(self) -> None:
        frames = [f"Direct configuration= {i}\n0 0 0\n0.5 0.5 {i / 100}\n".encode() for i in range(10)]
        self.path.write_bytes(header + b"".join(frames))
        first = self.read(frameLimit=1)
        index = self.read(offset=first["nextOffset"], version=first["version"], indexOnly=True)
        self.assertEqual(index["text"], "")
        self.assertEqual(index["frameCount"], 9)
        for number, offset in enumerate(first["offsets"] + index["offsets"]):
            fetched = self.read(offset=offset, version=first["version"], frameLimit=1)
            self.assertEqual(fetched["text"].encode(), header + frames[number])


if __name__ == "__main__":
    unittest.main()
