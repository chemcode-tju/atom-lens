"""Exercise installation without a real host or personal SSH configuration."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "native"))
import connection


class HelperConnectionTests(unittest.TestCase):
    def test_aliases_include_patterns_and_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            config = folder / "ssh config"
            extra = folder / "extra.conf"
            config.write_text(f'Include "{extra}"\nHost = user-host *.example !excluded\n')
            extra.write_text(f'Include "{config}"\nHost=second third\nHost *\n')
            self.assertEqual(connection.host_aliases(config), ["second", "third", "user-host"])

    def test_deploy_and_run_in_path_with_shell_characters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "folder with ' quotes; and $" / "queue.pyz"
            config = folder / "config"
            config.touch()
            settings = folder / "connection.json"
            args = {"config": str(config), "host": "test", "queue": str(path)}
            # Execute the actual remote shell command locally in an isolated home.
            with patch.object(connection, "settings_path", return_value=settings), patch.object(
                connection, "ssh_args", return_value=["/bin/sh", "-c"]
            ):
                connection.configure(args, root / "plugin")
                connection.configure(args, root / "plugin")
                worker = subprocess.run([sys.executable, str(path)], env={"HOME": str(folder)},
                                        input=b"", capture_output=True, timeout=5, check=True)
                self.assertIn(b'"kind": "ready"', worker.stdout)
                other = folder / "other.pyz"
                other.write_text("keep")
                saved = settings.read_bytes()
                with self.assertRaises(ValueError):
                    connection.configure(dict(args, queue=str(other)), root / "plugin")
                self.assertEqual(other.read_text(), "keep")
                self.assertEqual(settings.read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
