"""Validate skipped XTC payloads and snapshot boundaries against real encoding."""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
from xtc_index import read_xtc_index
from md_import import read_md_index, import_selected


class XtcIndexTests(unittest.TestCase):
    def test_snapshot_freezes_xtc_while_writer_appends(self) -> None:
        fixture = json.loads((Path(__file__).parent / "fixtures/xtc-reference.json").read_text())["fixtures"][1]
        parts = [base64.b64decode(frame["data"]) for frame in fixture["frames"]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "growing.xtc"
            path.write_bytes(parts[0] + parts[1][:24])
            resource = {"openai/resource": {"path": str(path)}}
            version = import_selected({"_meta": resource, "arguments": {"action": "stat"}})["version"]
            with path.open("ab") as stream:
                stream.write(parts[1][24:])
            arguments = dict(action="frames", format="xtc", offset=0, indexOnly=True, version=version)
            old = import_selected({"_meta": resource, "arguments": arguments})
            self.assertEqual(len(old["frames"]), 1)
            arguments["version"] = import_selected({"_meta": resource, "arguments": {"action": "stat"}})["version"]
            new = import_selected({"_meta": resource, "arguments": arguments})
            self.assertEqual(len(new["frames"]), 2)

    def test_reference_headers_and_incomplete_tails(self) -> None:
        fixtures = json.loads((Path(__file__).parent / "fixtures/xtc-reference.json").read_text())["fixtures"]
        for fixture in fixtures:
            parts = [base64.b64decode(frame["data"]) for frame in fixture["frames"]]
            stream = io.BytesIO(b"".join(parts))
            first = read_md_index(stream, "xtc", 0, False)
            self.assertEqual(len(first["frames"]), 1)
            self.assertFalse(first["eof"])
            last = read_xtc_index(stream, first["nextOffset"], True, False)
            self.assertEqual([frame["step"] for frame in last["frames"]], [1, 2])
            self.assertEqual(last["frames"][1]["n"], fixture["atoms"])
            self.assertTrue(last["eof"])
            bounded = read_xtc_index(io.BytesIO(parts[0] * 100), 0, True, False)
            self.assertEqual(len(bounded["frames"]), 64)
            self.assertFalse(bounded["eof"])
            playing = read_xtc_index(io.BytesIO(parts[0] * 100), 0, True, False, 16)
            self.assertEqual(len(playing["frames"]), 16)
            for tail in [parts[1][:24], parts[1][:-3]]:
                stream = io.BytesIO(parts[0] + tail)
                with self.assertRaisesRegex(ValueError, "不完整"):
                    read_xtc_index(stream, 0, True, False)
                frozen = read_xtc_index(stream, 0, True, True)
                self.assertEqual(len(frozen["frames"]), 1)
                self.assertTrue(frozen["eof"])


if __name__ == "__main__":
    unittest.main()
