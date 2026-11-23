"""User-facing directory imports, pairing ambiguity and bounded metadata reads."""
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
import server
import structure_discovery as discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def open(self, path: Path, companions: list[str] | None = None) -> dict:
        return server.dispatch("tools/call", {"name": "open_structure_path", "arguments": {
            "path": str(path), "companions": companions or []}})["structuredContent"]

    def dump(self, name: str = "run/traj.lammpstrj") -> Path:
        return self.write(name, "ITEM: TIMESTEP\n0\nITEM: NUMBER OF ATOMS\n2\n"
                          "ITEM: BOX BOUNDS pp pp ff\n0 10\n0 10\n0 20\n"
                          "ITEM: ATOMS id type x y z\n1 1 0 0 0\n2 2 1 1 1\n")

    def data(self, name: str, mass: float = 107.8682) -> Path:
        return self.write(name, f"LAMMPS data file via write_data, units = real\n\n2 atoms\n2 atom types\n"
                          f"\nMasses\n\n1 {mass}\n2 1.008\n\nAtoms # full\n\n1 1 1 0 0 0 0\n2 1 2 0 1 1 1\n")

    def test_continuation_directory_resolves_provenance_and_reads_frames(self) -> None:
        dump = self.dump()
        data = self.data("continue/final.data")
        restart = self.write("continue/final.restart", "binary not parsed")
        self.write("run/provenance.json", json.dumps({"source_restart": str(restart)}))
        self.write("run/input.in", "include settings.in\ndump run all custom 10 traj.lammpstrj id type x y z\n")
        self.write("run/settings.in", "units real\nboundary p p f\nshell touch forbidden\n")
        self.write("run/log.lammps", "irrelevant log\n" * 100000)
        before = dump.read_bytes()
        file = self.open(dump.parent)["file"]
        self.assertEqual(file["path"], str(dump))
        self.assertEqual(file["companions"][0]["path"], str(data))
        text = "\n".join(item["metadataText"] for item in file["companions"])
        self.assertIn("units real", text)
        self.assertIn("boundary p p f", text)
        self.assertIn("1 107.8682", text)
        self.assertNotIn("shell", text)
        self.assertLess(len(text), 1000)
        snapshot = server.dispatch("tools/call", {"name": "structure_import", "arguments": {
            "action": "stat", "token": file["token"]}})["structuredContent"]
        batch = server.dispatch("tools/call", {"name": "structure_import", "arguments": {
            "action": "frames", "token": file["token"], "version": snapshot["version"],
            "format": "lammps-dump-text", "offset": 0}})["structuredContent"]
        self.assertIn("ITEM: ATOMS", batch["text"])
        self.assertEqual(dump.read_bytes(), before)
        self.assertFalse((self.root / "forbidden").exists())

    def test_multiple_trajectories_are_choices_not_concatenated(self) -> None:
        self.dump("run/a.dump")
        self.dump("run/b.dump")
        self.data("run/system.data")
        result = self.open(self.root / "run")
        self.assertNotIn("file", result)
        self.assertEqual(len(result["choices"]), 2)
        self.assertTrue(all(len(choice["file"]["companions"]) == 1 for choice in result["choices"]))

    def test_conflicting_mass_tables_require_a_choice(self) -> None:
        dump = self.dump()
        self.data("run/silver.data")
        self.data("run/carbon.data", 12.011)
        self.assertEqual(len(self.open(dump)["choices"]), 2)
        self.write("run/input.in", "read_data silver.data\ndump d all custom 1 traj.lammpstrj id type x y z\n")
        self.assertIn("silver.data", self.open(dump)["file"]["companions"][0]["path"])

    def test_parent_data_copies_collapse_but_atom_count_mismatch_does_not_pair(self) -> None:
        dump = self.dump()
        self.data("a.data")
        self.data("b.data")
        self.assertIn("file", self.open(dump))
        self.write("run/wrong.data", "3 atoms\n2 atom types\nMasses\n1 12\n2 1\n")
        self.assertNotIn("wrong.data", self.open(dump)["file"]["companions"][0]["path"])

    def test_archive_and_symlink_to_archive_are_not_read(self) -> None:
        self.write("run/water.xyz", "1\n\nO 0 0 0\n")
        hidden = self.write("run/archive/old.xyz", "not a structure")
        (self.root / "run/old.xyz").symlink_to(hidden)
        self.assertEqual(self.open(self.root / "run")["file"]["name"], "water.xyz")
        with self.assertRaisesRegex(ValueError, "archive"):
            self.open(hidden)

    def test_cp2k_pair_uses_project_name(self) -> None:
        self.write("run/sim-pos-1.xyz", "1\n i = 0, time = 0\nH 0 0 0\n")
        self.write("run/sim-vel-1.xyz", "1\n i = 0, time = 0\nH 0 0 0\n")
        self.write("run/sim-frc-1.xyz", "1\n i = 0, time = 0\nH 0 0 0\n")
        self.write("run/POSCAR.xyz", "1\ninitial static geometry\nH 0 0 0\n")
        self.write("run/POSCAR", "Initial geometry is separately openable")
        self.write("run/sim-1.cell", "0 0 10 0 0 0 10 0 0 0 10 1000\n")
        self.write("run/unrelated.cell", "0 0 20 0 0 0 20 0 0 0 20 8000\n")
        file = self.open(self.root / "run")["file"]
        self.assertEqual(file["companions"][0]["name"], "sim-1.cell")
        direct = self.open(self.root / "run/sim-pos-1.xyz")["file"]
        self.assertEqual(direct["companions"][0]["name"], "sim-1.cell")

    def test_self_contained_file_does_not_require_parent_directory_access(self) -> None:
        for name, text in (("water.xyz", "1\nwater\nO 0 0 0\n"),
                           ("run.extxyz", "1\nProperties=species:S:1:pos:R:3\nO 0 0 0\n"),
                           ("POSCAR", "static structure"), ("water.pdb", "static structure")):
            with self.subTest(name=name):
                path = self.write(name, text)
                with patch.object(discovery, "files_in", side_effect=PermissionError("directory not selected")):
                    file = self.open(path)["file"]
                self.assertEqual(file["path"], str(path))
                self.assertEqual(file["companions"], [])

    def test_gromacs_pair_and_missing_topology(self) -> None:
        trr = self.write("run/md.trr", "binary validated by TRR decoder")
        self.write("run/conf.gro", "static structure")
        with self.assertRaisesRegex(ValueError, "缺少 TPR"):
            self.open(trr.parent)
        self.write("run/md.tpr", "topology validated by topology worker")
        self.write("run/old.tpr", "another topology")
        for index in range(40):
            self.write(f"run/step{index}b.pdb", "Diagnostic snapshot")
        file = self.open(trr.parent)["file"]
        self.assertEqual(file["name"], "md.trr")
        self.assertEqual(file["companions"][0]["name"], "md.tpr")
        self.write("gro/conf.gro", "title\n1\n")
        self.write("gro/topol.top", "[ molecules ]\nWater 1\n")
        self.assertEqual(self.open(self.root / "gro")["file"]["companions"][0]["name"], "topol.top")

    def test_xtc_pairs_with_gro_then_prefers_matching_tpr(self) -> None:
        self.write("run/md.xtc", "binary")
        self.write("run/conf.gro", "static structure")
        file = self.open(self.root / "run")["file"]
        self.assertEqual(file["name"], "md.xtc")
        self.assertEqual(file["companions"][0]["name"], "conf.gro")
        self.write("run/md.tpr", "binary topology")
        file = self.open(self.root / "run")["file"]
        self.assertEqual(file["companions"][0]["name"], "md.tpr")

    def test_metadata_scan_is_bounded_and_explicit_override_is_preserved(self) -> None:
        dump = self.dump()
        data = self.data("run/system.data")
        with data.open("ab") as stream:
            stream.seek(20 * 1048576)
            stream.write(b"\n")
        with patch.object(discovery, "metadata_limit", 256):
            self.assertLess(len(self.open(dump)["file"]["companions"][0]["metadataText"]), 256)
        override = self.data("manual.data", 12.011)
        file = self.open(dump, [str(override)])["file"]
        self.assertEqual(file["companions"][0]["path"], str(override))
        self.assertNotIn("metadataText", file["companions"][0])
        with self.assertRaises(ValueError):
            self.open(dump, ["relative.data"])


if __name__ == "__main__":
    unittest.main()
