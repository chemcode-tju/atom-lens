"""Cross-check ASE ULM and snapshot writes; fixtures are generated in temporary dirs."""
from pathlib import Path
import base64
import json
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
from trajectory import read_frames
from snapshot import save_snapshot


def fixture(path: Path) -> None:
    """A minimal two-frame ULM with different per-frame atomic-number headers."""
    data = bytearray(b"- of Ulm" + b"ASE-Trajectory".ljust(16))
    data.extend(struct.pack("<qqq", 3, 2, 48))
    data.extend(bytes(16))
    offsets = []
    for number in [8, 1]:
        numbers = len(data)
        data.extend(struct.pack("<q", number))
        positions = len(data)
        data.extend(struct.pack("<ddd", -1.5, 2.0, 3.25))
        meta = {"numbers.": {"ndarray": [[1], "int64", numbers]},
                "positions.": {"ndarray": [[1, 3], "float64", positions]},
                "cell": [[8, 0, 0], [1, 9, 0], [0, 0, 10]], "pbc": [True, False, True]}
        encoded = json.dumps(meta).encode()
        offsets.append(len(data))
        data.extend(struct.pack("<q", len(encoded)) + encoded)
    data[48:64] = struct.pack("<qq", *offsets)
    path.write_bytes(data)


class FeatureTests(unittest.TestCase):
    def test_binary_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.traj"
            fixture(path)
            params = {"_meta": {"openai/resource": {"path": str(path)}}, "arguments": {"frameLimit": 1}}
            first = read_frames(params)
            self.assertIn("O -1.5 2.0 3.25", first["text"])
            self.assertFalse(first["eof"])
            params["arguments"].update(offset=1, version=first["version"])
            second = read_frames(params)
            self.assertIn("H -1.5 2.0 3.25", second["text"])
            self.assertTrue(second["eof"])
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaises(ValueError):
                read_frames(params)

    def test_snapshot_directory_and_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            params = {"_meta": {"openai/resource": {"path": str(Path(temporary) / "test.xyz")}},
                      "arguments": {"name": "frame.png", "data": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()}}
            first = save_snapshot(params)
            second = save_snapshot(params)
            self.assertNotEqual(first["path"], second["path"])
            self.assertEqual(Path(first["path"]).parent.name, "structure-snapshots")
            params["arguments"]["name"] = "../escape.png"
            with self.assertRaises(ValueError):
                save_snapshot(params)
            params["arguments"]["name"] = "mismatch.pdf"
            with self.assertRaises(ValueError):
                save_snapshot(params)


if __name__ == "__main__":
    unittest.main()
