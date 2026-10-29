"""Exercise the real SSH stdio protocol with a local subprocess and private temp queue."""
from pathlib import Path
import base64
import json
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

plugin = Path(__file__).resolve().parents[1] / "plugin"
sys.path.insert(0, str(plugin))
from local_export import prepare_local_snapshot, snapshot_save_status


class QueueTests(unittest.TestCase):
    def test_cancel_ack_and_disconnect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            code = f"import sys;sys.path.insert(0,{str(plugin)!r});import snapshot_queue;from pathlib import Path;snapshot_queue.export_folder=lambda:Path({temporary!r});snapshot_queue.poll_interval=0.05;snapshot_queue.watch()"
            process = subprocess.Popen([sys.executable, "-u", "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(json.loads(process.stdout.readline()), {"kind": "ready"})
                with patch("local_export.export_folder", return_value=folder):
                    request = prepare_local_snapshot({"name": "test.png", "language": "en", "data": base64.b64encode(b"\x89PNG\r\n\x1a\ntest").decode()})
                    payload = json.loads(process.stdout.readline())
                    self.assertEqual(payload["id"], request["id"])
                    self.assertEqual(payload["kind"], "snapshot")
                    self.assertEqual(payload["language"], "en")
                    self.assertEqual(snapshot_save_status(request)["status"], "choosing")
                    process.stdin.write(json.dumps({**request, "status": "cancelled"}) + "\n")
                    process.stdin.flush()
                    deadline = time.monotonic() + 3
                    while snapshot_save_status(request)["status"] != "cancelled" and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertEqual(snapshot_save_status(request)["status"], "cancelled")
                    (folder / f"{request['id']}.status").write_text("pending")
                    (folder / "helper-heartbeat").unlink()
                    self.assertEqual(snapshot_save_status(request)["status"], "disconnected")
                process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=3)


if __name__ == "__main__":
    unittest.main()
