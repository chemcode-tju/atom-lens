"""Exercise runtime packaging and failed updates without changing the user's Codex."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("viewer_installer", root / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_staged_package_runs_without_source_or_path_python(self) -> None:
        original = (root / "plugin/.mcp.json").read_bytes()
        with tempfile.TemporaryDirectory(prefix="atom lens '") as directory:
            folder = Path(directory)
            python = folder / "selected python"
            python.symlink_to(sys.executable)
            staged = folder / "package"
            with patch.dict(os.environ, {"STRUCTURE_VIEWER_FFMPEG": "/chosen/ffmpeg"}):
                installer.prepare_package(root, staged, python)
            config = json.loads((staged / "plugin/.mcp.json").read_text())
            server = config["mcpServers"]["structure-viewer"]
            self.assertEqual(server["command"], str(python))
            self.assertEqual(server["env"]["STRUCTURE_VIEWER_FFMPEG"], "/chosen/ffmpeg")
            with patch.dict(os.environ, {"PATH": "/nonexistent"}):
                installer.check_server(staged, python)
            self.assertFalse((staged / "tests").exists())
            self.assertFalse(list(staged.rglob("__pycache__")))
        self.assertEqual((root / "plugin/.mcp.json").read_bytes(), original)

    def test_reinstall_refreshes_package_and_failed_registration_restores_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            with patch.object(installer, "register_plugin"):
                target = installer.install(root, Path("codex"), home, Path(sys.executable))
            (target / "obsolete.txt").write_text("old")
            with patch.object(installer, "register_plugin", side_effect=RuntimeError("registration failed")):
                with self.assertRaisesRegex(RuntimeError, "registration failed"):
                    installer.install(root, Path("codex"), home, Path(sys.executable))
            self.assertEqual((target / "obsolete.txt").read_text(), "old")
            with patch.object(installer, "register_plugin"):
                installer.install(root, Path("codex"), home, Path(sys.executable))
            self.assertFalse((target / "obsolete.txt").exists())

    def test_incomplete_bundle_is_rejected_before_registration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory) / "broken"
            installer.prepare_package(root, staged, Path(sys.executable))
            (staged / "plugin/web/app.js").unlink()
            with self.assertRaisesRegex(RuntimeError, "自检失败"):
                installer.check_server(staged, Path(sys.executable))

    def test_unmanaged_destination_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            target = home / "structure-viewer-source"
            target.mkdir()
            (target / "keep.txt").write_text("personal")
            with patch.object(installer, "register_plugin") as register:
                with self.assertRaisesRegex(RuntimeError, "非本安装器"):
                    installer.install(root, Path("codex"), home, Path(sys.executable))
                register.assert_not_called()
            self.assertEqual((target / "keep.txt").read_text(), "personal")

    def test_symlink_destination_is_not_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "structure-viewer-source").symlink_to(home / "missing")
            with self.assertRaisesRegex(RuntimeError, "非本安装器"):
                installer.install(root, Path("codex"), home, Path(sys.executable))

    def test_migration_refuses_a_marketplace_with_other_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / ".agents/plugins/marketplace.json"
            catalog.parent.mkdir(parents=True)
            catalog.write_text(json.dumps({"plugins": [{"name": "structure-viewer"}, {"name": "other"}]}))
            listing = {"marketplaces": [{"name": "atomic-structure-tools", "root": str(root),
                       "marketplaceSource": {"sourceType": "local", "source": str(root)}}]}
            with patch.object(installer, "run_codex", return_value=json.dumps(listing)) as run:
                with self.assertRaisesRegex(RuntimeError, "未自动替换"):
                    installer.register_plugin(Path("codex"), root / "new", root)
                self.assertEqual(run.call_count, 1)  # Read the catalog, without removing it.

    def test_failed_migration_restores_old_marketplace(self) -> None:
        source = "/previous/source"
        with patch.object(installer, "previous_marketplace", return_value=source), \
             patch.object(installer, "run_codex", side_effect=["", "", RuntimeError("install failed"), "", "", ""]) as run:
            with self.assertRaisesRegex(RuntimeError, "install failed"):
                installer.register_plugin(Path("codex"), Path("/new"), Path("/home"))
            self.assertEqual(run.call_args_list[-2].args[2], ["plugin", "marketplace", "add", source])
            self.assertEqual(run.call_args_list[-1].args[2], ["plugin", "add", "structure-viewer@atomic-structure-tools"])


if __name__ == "__main__":
    unittest.main()
