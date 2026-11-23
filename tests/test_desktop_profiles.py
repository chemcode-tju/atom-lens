"""Verify independent saved profiles and their HTTP boundary without any SSH calls."""
from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "native"))
from desktop_profiles import ProfileStore
from desktop_host import DesktopHost
from desktop_backend import RPCClient


class ProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "settings/servers.json"
        self.store = ProfileStore(self.path)

    def test_multiple_profiles_survive_restart_and_edit_independently(self) -> None:
        first = self.store.save({"host": "nd3", "name": "实验室", "python": "/opt/env/bin/python3", "codex": True})
        second = self.store.save({"host": "user@other", "config": "/tmp/other-config", "password": "must-not-store"})
        restarted = ProfileStore(self.path)
        self.assertEqual(restarted.list(), [first, second])
        edited = restarted.save({**first, "name": "实验室新名称", "python": "/other/python3"})
        self.assertEqual(self.store.list(), [edited, second])
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertNotIn("password", self.path.read_text())
        self.assertNotIn("must-not-store", self.path.read_text())

    def test_remove_only_selected_configuration(self) -> None:
        first = self.store.save({"host": "same", "python": "python3"})
        second = self.store.save({"host": "same", "python": "/env/python3"})
        self.store.remove(first["id"])
        self.assertEqual(self.store.list(), [second])
        with self.assertRaises(ValueError):
            self.store.save(first)
        self.assertEqual(self.store.list(), [second])

    def test_last_connection_and_plugin_status_survive_restart(self) -> None:
        profile = self.store.save({"host": "nd3", "codex": False})
        self.store.record(profile, True, connected=True)
        restarted = ProfileStore(self.path)
        saved = restarted.last_connected()
        self.assertEqual(saved["id"], profile["id"])
        self.assertTrue(saved["codexInstalled"])
        self.assertFalse(saved["codex"], "Install preference is separate from detected status")
        restarted.record(profile)
        self.assertTrue(restarted.last_connected()["codexInstalled"], "An unavailable check preserves known status")
        renamed = restarted.save({**profile, "name": "Lab"})
        self.assertTrue(renamed["codexInstalled"])
        restarted.forget_connection(profile["id"])
        self.assertIsNone(restarted.last_connected())
        self.assertTrue(restarted.list()[0]["codexInstalled"])
        restarted.record(renamed, True, connected=True)
        changed = restarted.save({**renamed, "host": "nd2"})
        self.assertNotIn("codexInstalled", changed)
        self.assertIsNone(restarted.last_connected())

    def test_startup_selects_saved_server_once_and_falls_back_if_unreachable(self) -> None:
        profile = self.store.save({"host": "nd3"})
        self.store.record(profile, connected=True)
        with DesktopHost(self.path) as host, patch("desktop_backend.bootstrap", side_effect=RuntimeError("offline")):
            fallback = host.startup_state()
            self.assertFalse(fallback["remote"])
            self.assertEqual(fallback["startupError"], "offline")
            self.assertEqual(self.store.last_connected()["id"], profile["id"])

        command = [sys.executable, "-B", "-u", str(root / "native/desktop_worker.py")]
        with DesktopHost(self.path) as host, \
             patch("desktop_backend.bootstrap", return_value={"version": "test", "python": "python3"}) as bootstrap, \
             patch("desktop_backend.RPCClient", side_effect=lambda _: RPCClient(command)):
            local = host.sessions.identifier
            initial = host.startup_state()
            self.assertTrue(initial["remote"])
            self.assertEqual(initial["profile"]["id"], profile["id"])
            host.sessions.activate(local)
            self.assertEqual(host.startup_state()["session"], local, "Reloading the UI must respect a manual host change")
            bootstrap.assert_called_once()

    def test_invalid_input_and_corrupt_file_are_not_silently_overwritten(self) -> None:
        self.store.save({"host": "nd3"})
        original = self.path.read_bytes()
        for value in ({"host": "-oProxyCommand=bad"}, {"host": "nd3;bad"},
                      {"host": "nd3", "config": "relative"}, {"host": "nd3", "python": "-bad"}):
            with self.assertRaises(ValueError):
                self.store.save(value)
        self.assertEqual(self.path.read_bytes(), original)
        self.path.write_text("broken JSON")
        with self.assertRaisesRegex(ValueError, "原文件未修改"):
            self.store.save({"host": "nd2"})
        self.assertEqual(self.path.read_text(), "broken JSON")

    def test_concurrent_app_instances_preserve_each_profile(self) -> None:
        def save(index: int) -> None:
            ProfileStore(self.path).save({"host": f"server-{index}"})
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(save, range(12)))
        self.assertEqual({item["host"] for item in self.store.list()}, {f"server-{index}" for index in range(12)})

    def test_profile_http_changes_do_not_switch_the_active_connection(self) -> None:
        host = DesktopHost(self.path)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        def post(route: str, payload: dict, origin: str | None = None) -> dict:
            request = urllib.request.Request(f"{host.origin}/{host.secret}/{route}", data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "X-Atom-Lens": "desktop", "Origin": origin or host.origin})
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)
        try:
            before = post("state", {})
            first = post("profiles", {"action": "save", "profile": {"host": "nd3"}})["saved"]
            post("profiles", {"action": "save", "profile": {"host": "nd2"}})
            self.assertEqual(len(post("profiles", {})["profiles"]), 2)
            with self.assertRaises(urllib.error.HTTPError) as error:
                post("profiles", {"action": "remove", "id": first["id"]}, "https://example.com")
            self.assertEqual(error.exception.code, 403)
            self.assertEqual(len(post("profiles", {})["profiles"]), 2)
            post("profiles", {"action": "remove", "id": first["id"]})
            self.assertEqual(post("state", {}), before)
        finally:
            host.shutdown()
            host.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
