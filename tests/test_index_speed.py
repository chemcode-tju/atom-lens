"""Check byte-identical random access across batch boundaries and paired remote reads."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"plugin"))
from trajectory import read_frames, file_version
from cp2k_cell import attach_cell


class IndexTests(unittest.TestCase):
    def test_boundary_and_partial_tail(self) -> None:
        frame = b"2\r\n\r\nC " + b"0 " * 16000 + b"\r\nH 1 2 3\r\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"a.xyz"
            path.write_bytes(frame * 600 + b"2\n\nH 0 0 0\n")
            version = file_version(path.stat())
            offset = 0
            indices = []
            while offset < len(frame)*600:
                batch = read_frames({"_meta":{"openai/resource":{"path":str(path)}},
                                     "arguments":{"offset":offset,"version":version,"indexOnly":True,"frameLimit":4096}})
                indices.extend(batch["offsets"])
                offset = batch["nextOffset"]
            self.assertEqual(indices, list(range(0, len(frame)*600, len(frame))))
            with self.assertRaisesRegex(ValueError, "不完整"):
                read_frames({"_meta":{"openai/resource":{"path":str(path)}},
                             "arguments":{"offset":offset,"version":version,"indexOnly":True}})

    def test_cached_cell_is_keyed_by_step_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"run.cell"
            path.write_text("9 0 3 0 0 0 4 0 0 0 5\n7 0 2 0 0 0 4 0 0 0 5\n")
            version = file_version(path.stat())
            text = "1\ni = 7, time = 0\nH 0 0 0\n1\ni = 9, time = 1\nHe 1 0 0"
            batch = {"text":text}
            attach_cell(batch,path,version)
            self.assertIn('Lattice="2.0', batch["text"].splitlines()[1])
            self.assertIn('Lattice="3.0', batch["text"].splitlines()[4])
            with self.assertRaisesRegex(ValueError,"No CELL row"):
                attach_cell({"text":text.replace("i = 7","i = 3")},path,version)
            path.write_text(path.read_text()+"7 0 2 0 0 0 4 0 0 0 5\n")
            with self.assertRaisesRegex(ValueError,"changed"):
                attach_cell({"text":text},path,version)
            with self.assertRaisesRegex(ValueError,"Duplicate"):
                attach_cell({"text":text},path,file_version(path.stat()))


if __name__ == "__main__":
    unittest.main()
