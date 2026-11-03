"""Check native and path-based links with real dump and companion reads."""
from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "plugin"))
import server


def call(name: str, args: dict, path: Path | None = None) -> dict:
    params = {"name": name, "arguments": args}
    if path:
        params["_meta"] = {"openai/resource": {"path": str(path)}}
    return server.dispatch("tools/call", params)["structuredContent"]


class TrajectoryLinkTests(unittest.TestCase):
    def test_link_roundtrip(self) -> None:
        self.assertIn(".svtraj", server.tool_descriptor()["_meta"]["openai/ui"]["entrypoints"][0]["extensions"])
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for source in (root / "examples/lammps").iterdir():
                shutil.copy(source, directory)
            args = {"path": str(directory / "water.dump"), "companions": [str(directory / name) for name in ("system.data", "log.lammps")]}
            result = call("create_lammps_link", args)
            self.assertEqual(result, call("create_lammps_link", args))
            link = Path(result["path"])
            ref = call("open_structure_path", {"path": str(link)})["file"]
            for resolved in (call("resolve_lammps_link", {}, link), call("resolve_lammps_link", {"token": ref["token"]})):
                dump = resolved["file"]
                self.assertEqual(len(dump["companions"]), 2)
                binding = {"token": dump["token"]}
                version = call("structure_import", {**binding, "action": "stat"})["version"]
                first = call("structure_import", {**binding, "action": "frames", "version":version, "format":"lammps-dump-text"})
                self.assertFalse(first["eof"])
                self.assertIn("ITEM: ATOMS id type", first["text"])

    def test_untrusted_members_and_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dump = base / "water.dump"
            dump.touch()
            args = {"path": str(dump), "companions": []}
            link = Path(call("create_lammps_link", args)["path"])
            (base / "alias.data").symlink_to(dump)
            for member in ["../log.lammps", "/etc/passwd", "secrets.txt", "missing.data", "alias.data"]:
                link.write_text(json.dumps(dict(version=1,dump=dump.name,companions=[member])))
                with self.assertRaises(ValueError):
                    call("resolve_lammps_link", {}, link)
            contents = link.read_bytes()
            with self.assertRaises(ValueError):
                call("create_lammps_link", args)
            self.assertEqual(link.read_bytes(), contents)


if __name__ == "__main__":
    unittest.main()
