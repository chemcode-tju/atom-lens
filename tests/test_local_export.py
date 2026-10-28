"""Validate the bounded nd3-to-Mac snapshot staging boundary."""
from pathlib import Path
import base64
import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
from local_export import prepare_local_snapshot, export_folder, snapshot_save_status


class LocalExportTests(unittest.TestCase):
    def test_stage_and_expire_only_snapshot_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch("local_export.Path.home", return_value=Path(temporary)):
            arguments = {"name": "构型.png", "data": base64.b64encode(b"\x89PNG\r\n\x1a\ntest").decode()}
            (export_folder() / "helper-heartbeat").touch()
            first = prepare_local_snapshot(arguments)
            folder = Path(temporary) / ".cache/structure-viewer/exports"
            target = folder / f"{first['id']}.json"
            self.assertEqual(json.loads(target.read_text()), {**arguments, "id": first["id"]})
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            os.utime(target, (time.time() - 90000,) * 2)
            unrelated = folder / "keep.json"
            unrelated.write_text("keep")
            os.utime(unrelated, (time.time() - 90000,) * 2)
            second = prepare_local_snapshot(arguments)
            self.assertNotEqual(first, second)
            self.assertFalse(target.exists())
            self.assertTrue(unrelated.exists())

    def test_offline_helper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch("local_export.Path.home", return_value=Path(temporary)):
            with self.assertRaisesRegex(ValueError, "未连接"):
                prepare_local_snapshot({"name": "a.png", "data": base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()})

    def test_reject_invalid_name_content_and_size(self) -> None:
        for arguments in [
            {"name": "../image.png", "data": ""}, {"name": None, "data": ""},
            {"name": "image.png", "data": "not-base64"},
            {"name": "image.pdf", "data": base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()},
            {"name": "image.png", "data": "a" * (24 * 1048576 + 1)},
        ]:
            with self.subTest(arguments=arguments["name"]), self.assertRaises(ValueError):
                prepare_local_snapshot(arguments)


if __name__ == "__main__":
    unittest.main()
