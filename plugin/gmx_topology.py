"""Extract ordered atom metadata with GROMACS or an isolated MDAnalysis reader."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def environments() -> list[Path]:
    return [Path(sys.prefix), *[Path.home() / subdir for subdir in (
        "miniconda3/envs/gmx-md", "software/miniconda3/envs/gmx-analysis", ".conda/envs/gmx-analysis")]]


def tpr_metadata(path: Path) -> dict:
    candidates = [os.getenv("STRUCTURE_VIEWER_GMX"), *(p / "bin/gmx" for p in environments()), shutil.which("gmx")]
    executable = next((str(p) for p in candidates if p and Path(p).is_file()), None)
    if not executable:
        raise ValueError("TPR requires GROMACS. Set STRUCTURE_VIEWER_GMX to gmx.")
    result = subprocess.run([executable, "dump", "-sys", "-s", str(path)], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError(f"GROMACS could not read the TPR: {result.stderr[-1500:]}")
    return parse_tpr_dump(result.stdout)


def parse_tpr_dump(text: str) -> dict:
    """Retain ordered source types, atom names and residues from gmx dump -sys."""
    atoms = []
    residue_indices = []
    for match in re.finditer(r"^\s*atom\[\s*(\d+)\]=\{(type=[^\n]+)\}", text, re.M):
        if int(match[1]) != len(atoms):
            raise ValueError("Unexpected TPR atom order")
        fields = dict(re.findall(r"(\w+)\s*=\s*([^,}]+)", match[2]))
        atoms.append(dict(number=int(fields["atomnumber"]), mass=float(fields["m"]),
                          type=fields["type"].strip(), charge=float(fields["q"])))
        residue_indices.append(int(fields["resind"]))
    if not atoms:
        raise ValueError("No atomic metadata in TPR")
    names = {int(m[1]): m[2] for m in re.finditer(r'^\s*atom\[\s*(\d+)\]=\{name="([^"]*)"', text, re.M)}
    types = {int(m[1]): m[2] for m in re.finditer(r'^\s*type\[\s*(\d+)\]=\{name="([^"]*)"', text, re.M)}
    residues = {int(m[1]): (m[2], int(m[3])) for m in re.finditer(r'^\s*residue\[\s*(\d+)\]=\{name="([^"]*)",\s*nr=\s*(-?\d+)', text, re.M)}
    for index, atom in enumerate(atoms):
        if index in names:
            atom["name"] = names[index]
        if index in types:
            atom["typeName"] = types[index]
        if residue_indices[index] in residues:
            atom["residue"], atom["resid"] = residues[residue_indices[index]]
    match = re.search(r"^\s*pbc\s*=\s*(\S+)", text, re.M)
    boundaries = {"xyz": [True]*3, "xy": [True, True, False], "no": [False]*3}
    if not match or match[1].lower() not in boundaries:
        raise ValueError("Unsupported or missing TPR periodic boundary mode")
    return {"atoms": atoms, "pbc": boundaries[match[1].lower()]}


def read_top(path: Path) -> list[dict]:
    import MDAnalysis as mda
    from MDAnalysis.topology import ITPParser
    roots = [Path(sys.prefix)/"share/gromacs/top", *(p/"share/gromacs/top" for p in environments())]
    if os.getenv("GMXLIB"):
        roots.insert(0, Path(os.environ["GMXLIB"]))
    library = next((p.resolve() for p in roots if p.is_dir()), path.parent)
    directory = path.parent.resolve()

    class ScopedIncludes(ITPParser.GmxTopIterator):
        def find_path(self, name):
            if hasattr(name, "name"):  # The already opened root TOP.
                return str(path)
            relative = Path(name)
            if relative.is_absolute() or relative.suffix.lower() != ".itp":
                raise ValueError(f"Unsupported topology include: {name}")
            current = Path(getattr(self.current_file, "name", str(self.current_file))).parent
            for base in (current, library):
                candidate = (base / relative).resolve()
                if (candidate.is_relative_to(directory) or candidate.is_relative_to(library)) and candidate.is_file():
                    return str(candidate)
            raise ValueError(f"Missing topology include {name}. Select its ITP file as well, or open the TOP by path.")
    ITPParser.GmxTopIterator = ScopedIncludes  # Only inside this short-lived worker.
    u = mda.Universe(str(path), topology_format="ITP", include_dir=str(library), infer_system=False)
    return [dict(name=a.name, residue=a.resname, resid=int(a.resid), type=str(a.type),
                 mass=float(a.mass), charge=float(a.charge)) for a in u.atoms]


def metadata(path: Path) -> dict:
    if path.suffix.lower() == ".tpr":
        return tpr_metadata(path)
    if path.suffix.lower() != ".top":
        raise ValueError("Select a TOP or TPR file")
    candidates = [os.getenv("STRUCTURE_VIEWER_MDA_PYTHON"), sys.executable, *(p/"bin/python" for p in environments())]
    for p in candidates:
        if not p or not Path(p).is_file():
            continue
        result = subprocess.run([str(p), __file__], input=str(path), text=True, capture_output=True, timeout=120)
        if result.returncode == 42:
            continue
        if result.returncode:
            raise ValueError(result.stderr.strip().splitlines()[-1])
        return {"atoms": json.loads(result.stdout)}
    raise ValueError("TOP requires MDAnalysis. Set STRUCTURE_VIEWER_MDA_PYTHON to its Python executable.")


def topology_request(params: dict[str, Any]) -> dict:
    args = params["arguments"]
    if args.get("token"):
        path = Path(params["_meta"]["openai/resource"]["path"])
        from trajectory import file_version
        from file_snapshot import is_snapshot, open_snapshot
        version = args.get("version")
        if is_snapshot(version):
            with open_snapshot(path, version) as (_, snapshot):
                if path.stat().st_size != snapshot.size:
                    raise ValueError("Topology changed; reopen it.")
                result = metadata(path)
                if path.stat().st_size != snapshot.size:
                    raise ValueError("Topology changed; reopen it.")
                return result
        if file_version(path.stat()) != version:
            raise ValueError("Topology changed; reopen it.")
        result = metadata(path)
        if file_version(path.stat()) != version:
            raise ValueError("Topology changed; reopen it.")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            primary = None
            for item in args.get("files", []):
                name = item["name"]
                if Path(name).name != name or Path(name).suffix.lower() not in {".tpr", ".top", ".itp"}:
                    raise ValueError("Invalid topology filename")
                candidate = Path(tmp)/name
                with candidate.open("xb") as f:
                    f.write(base64.b64decode(item["data"], validate=True))
                if candidate.suffix.lower() != ".itp":
                    if primary is not None:
                        raise ValueError("Select one topology")
                    primary = candidate
            if primary is None:
                raise ValueError("Missing TOP/TPR")
            result = metadata(primary)
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(read_top(Path(sys.stdin.read())), allow_nan=False))
    except ImportError:
        sys.exit(42)
