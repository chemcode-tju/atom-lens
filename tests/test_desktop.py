"""Exercise real desktop transport, host isolation, exports and private HTTP access."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import base64
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "native"))
from desktop_backend import DesktopSessions, RPCClient, runtime_bundle, ssh_command
from desktop_host import DesktopHost
import remote_bootstrap

png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6ZQAAAABJRU5ErkJggg==")


class DesktopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sessions = DesktopSessions()
        self.addCleanup(self.sessions.close)

    def call(self, name: str, arguments: dict) -> dict:
        return self.sessions.call(self.sessions.identifier, "tools/call", {"name": name, "arguments": arguments})["structuredContent"]

    def test_real_backend_reuses_local_session_and_tokens(self) -> None:
        opened = self.call("open_structure_path", {"path": str(root / "examples/water.xyz")})
        result = self.call("read_trajectory_frames", {"token": opened["file"]["token"], "frameLimit": 2})
        self.assertEqual(result["frameCount"], 2)
        old = self.sessions.identifier
        self.sessions.connect({})
        self.assertEqual(self.sessions.identifier, old)
        self.assertEqual(self.call("read_trajectory_frames", {"token": opened["file"]["token"], "frameLimit": 2})["frameCount"], 2)

    def test_index_does_not_block_foreground_rpc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            started = Path(directory) / "index-started"
            program = f"""
from pathlib import Path
import sys
import threading
sys.path.insert(0, {str(root / 'native')!r})
import desktop_worker
release = threading.Event()
def dispatch(method, params):
    if desktop_worker.is_trajectory_index(method, params):
        Path({str(started)!r}).touch()
        if not release.wait(3):
            raise RuntimeError('Foreground did not run while indexing')
        return {{'offsets': [0]}}
    release.set()
    return {{'foreground': True}}
desktop_worker.dispatch = dispatch
desktop_worker.main()
"""
            client = RPCClient([sys.executable, "-B", "-u", "-c", program])
            try:
                with ThreadPoolExecutor(1) as executor:
                    pending = executor.submit(client.call, "tools/call", {"name": "read_trajectory_frames", "arguments": {"indexOnly": True}})
                    for _ in range(200):
                        if started.exists():
                            break
                        threading.Event().wait(0.01)
                    self.assertTrue(started.exists())
                    self.assertEqual(client.call("ping"), {"foreground": True})
                    self.assertEqual(pending.result(), {"offsets": [0]})
            finally:
                client.close()

    def test_retained_workers_isolate_tokens_and_disconnect_explicitly(self) -> None:
        local_id = self.sessions.identifier
        local_client = self.sessions.client
        worker_command = [sys.executable, "-B", "-u", str(root / "native/desktop_worker.py")]
        # Real separate workers, but no network or modifications to real servers.
        with patch("desktop_backend.bootstrap", return_value={"version": "test", "python": "python3"}), \
             patch("desktop_backend.RPCClient", side_effect=lambda command: RPCClient(worker_command)):
            first = self.sessions.connect({"host": "server-one"})["session"]
            opened = self.call("open_structure_path", {"path": str(root / "examples/water.xyz")})
            second = self.sessions.connect({"host": "server-two"})["session"]
            self.sessions.connect({})
            self.assertEqual(self.sessions.identifier, local_id)
            self.assertIs(self.sessions.client, local_client)
            args = {"name": "read_trajectory_frames", "arguments": {"token": opened["file"]["token"], "frameLimit": 2}}
            self.assertEqual(self.sessions.call(first, "tools/call", args)["structuredContent"]["frameCount"], 2)
            with self.assertRaisesRegex(RuntimeError, "失效"):
                self.sessions.call(second, "tools/call", args)
            self.assertEqual(self.sessions.connect({"host": "server-one"})["session"], first)
            self.sessions.disconnect(first)
            self.assertEqual(self.sessions.identifier, local_id)
            with self.assertRaisesRegex(ValueError, "关闭"):
                self.sessions.call(first, "ping", {})
            self.assertEqual(len(self.sessions.state()["connections"]), 2)
            self.sessions.activate(second)
            self.sessions.client.close()
            with patch("desktop_backend.bootstrap", side_effect=RuntimeError("offline")):
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    self.sessions.connect({"host": "server-two"})
            self.assertEqual(self.sessions.state()["session"], second, "Failed reconnect must leave a valid state")
            replacement = self.sessions.connect({"host": "server-two"})["session"]
            self.assertNotEqual(replacement, second)
            with self.assertRaisesRegex(ValueError, "关闭"):
                self.sessions.call(second, "ping", {})

    def test_export_transport_preserves_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "image.png").write_bytes(b"existing")
            job = self.call("structure_media_export", {"action": "begin", "kind": "image", "name": "image.png"})
            self.call("structure_media_export", {"action": "append", "id": job["id"], "chunk": 0,
                      "last": True, "data": base64.b64encode(png).decode()})
            result = self.call("structure_media_export", {"action": "save", "id": job["id"],
                               "destination": "native", "directory": str(folder)})
            self.assertEqual(Path(result["path"]).read_bytes(), png)
            self.assertEqual((folder / "image.png").read_bytes(), b"existing")
            self.call("structure_media_export", {"action": "cancel", "id": job["id"]})
            with self.assertRaisesRegex(RuntimeError, "不存在"):
                self.sessions.client.call("atomlens/export-read", {"id": job["id"]})

    def test_directory_listing_is_explicit_and_paged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for index in range(205):
                (folder / f"file-{index:03d}.xyz").touch()
            page = self.sessions.client.call("atomlens/list-directory", {"path": temporary})
            self.assertEqual(len(page["entries"]), 200)
            next_page = self.sessions.client.call("atomlens/list-directory", {"path": temporary, "offset": page["next"]})
            self.assertEqual(len(next_page["entries"]), 5)
            self.assertIsNone(next_page["next"])

    def test_ssh_host_cannot_inject_flags_or_commands(self) -> None:
        for host in ["-oProxyCommand=evil", "nd3; touch file", "$(whoami)"]:
            with self.assertRaises(ValueError):
                ssh_command({"host": host})


class DeploymentTests(unittest.TestCase):
    def test_install_reinstall_and_refuse_unmanaged_content(self) -> None:
        payload = runtime_bundle()
        request = {"bundle": base64.b64encode(payload).decode(), "sha256": hashlib.sha256(payload).hexdigest(), "codex": False}
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "backend"
            with patch.object(remote_bootstrap, "backend_directory", str(target)), patch.object(remote_bootstrap, "find_codex", return_value=""):
                first = remote_bootstrap.install(request)
                self.assertIsNone(first["codexInstalled"])
                self.assertTrue((target / "native/desktop_worker.py").is_file())
                (target / "obsolete.txt").write_text("old")
                remote_bootstrap.install(request)
                self.assertFalse((target / "obsolete.txt").exists())
                (target / ".atom-lens-managed").unlink()
                with self.assertRaisesRegex(ValueError, "非本应用"):
                    remote_bootstrap.install(request)

    def test_bundle_integrity_and_path_traversal(self) -> None:
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as bundle:
            bundle.writestr("../escaped", "bad")
        payload = data.getvalue()
        request = {"bundle": base64.b64encode(payload).decode(), "sha256": hashlib.sha256(payload).hexdigest()}
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "路径"):
                remote_bootstrap.unpack(request, Path(temporary))
            request["sha256"] = "wrong"
            with self.assertRaisesRegex(ValueError, "校验"):
                remote_bootstrap.unpack(request, Path(temporary))


class DesktopHTTPTests(unittest.TestCase):
    def test_private_host_rejects_missing_secret_and_foreign_origin(self) -> None:
        host = DesktopHost()
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        try:
            def post(url: str, origin: str) -> dict:
                request = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json",
                    "X-Atom-Lens": "desktop", "Origin": origin})
                with urllib.request.urlopen(request) as result:
                    return json.load(result)
            correct = f"{host.origin}/{host.secret}/state"
            self.assertIn("session", post(correct, host.origin))
            for url, origin in [(host.origin + "/state", host.origin), (correct, "https://example.com")]:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    post(url, origin)
                self.assertEqual(error.exception.code, 403)
        finally:
            host.shutdown()
            host.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
