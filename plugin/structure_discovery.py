"""Bounded, read-only structure discovery shared by desktop and Codex hosts."""
from __future__ import annotations

# Configuration
directory_limit = 2000
candidate_limit = 32
header_limit = 8192
metadata_limit = 1048576
related_parent_limit = 2

from pathlib import Path
from typing import Any
import json
import os
import re
import shlex
import stat
import tempfile

from file_snapshot import binary_read_flags
from path_access import StructurePaths


def safe_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if "archive" in path.parts or "archive" in resolved.parts:
        raise ValueError("不会读取 archive 目录，请选择其他结构目录。")
    return resolved


def prefix(path: Path, limit: int = header_limit) -> str:
    """Never read a trajectory in full, follow a pipe, or enter archive."""
    path = safe_path(path)
    descriptor = os.open(path, binary_read_flags)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("只能读取普通文件。")
        data = stream.read(limit)
        after = os.fstat(stream.fileno())
        if before.st_size == after.st_size and before.st_mtime_ns != after.st_mtime_ns:
            raise ValueError(f"读取时文件已变化：{path}")
        # Drop a partially read line; headers and metadata always use complete rows.
        if len(data) == limit:
            data = data.rsplit(b"\n", 1)[0]
        return data.decode("utf-8", errors="replace")


def files_in(directory: Path) -> list[Path]:
    result = []
    with os.scandir(safe_path(directory)) as entries:
        for index, entry in enumerate(entries):
            if index >= directory_limit:
                raise ValueError("目录超过 2000 项，请选择更具体的目录或直接打开轨迹路径。")
            if entry.name.startswith((".", "#")) or entry.name == "archive" or entry.name.endswith(("~", ".bak")):
                continue
            if entry.is_file() and "archive" not in Path(entry.path).resolve().parts:
                result.append(Path(entry.path))
    return sorted(result, key=lambda path: path.name.casefold())


def format_of(path: Path) -> str | None:
    name, suffix = path.name.lower(), path.suffix.lower()
    direct = {".trr": "GROMACS TRR", ".xtc": "GROMACS XTC", ".gro": "GROMACS GRO",
              ".pdb": "PDB", ".cif": "CIF", ".svtraj": "LAMMPS link", ".traj": "ASE",
              ".xyz": "XYZ", ".extxyz": "XYZ", ".vasp": "VASP"}
    if suffix in direct:
        return direct[suffix]
    if path.name.upper() in {"POSCAR", "CONTCAR", "XDATCAR"}:
        return "VASP"
    if suffix not in {".lammps", ".lmp", ".data", ".dump", ".lammpstrj"} and not name.startswith(("data", "dump")):
        return None
    text = prefix(path)
    if re.search(r"^ITEM: (?:TIMESTEP|UNITS|TIME)", text, re.M):
        return "LAMMPS dump"
    if re.search(r"^\s*\d+\s+atom types\s*$", text, re.M):
        return "LAMMPS data"
    return None


def commands(text: str) -> list[list[str]]:
    """Parse literal metadata only; substitutions and commands are never executed."""
    result = []
    for line in re.sub(r"&\s*\n", " ", text).splitlines():
        try:
            words = shlex.split(line, comments=True)
        except ValueError:
            continue
        if words:
            result.append(words)
    return result


def literal_path(value: str, base: Path) -> Path | None:
    if any(char in value for char in "$*?`\n"):
        return None
    path = Path(value).expanduser()
    path = path if path.is_absolute() else base / path
    try:
        path = safe_path(path)
        return path if path.is_file() else None
    except (OSError, ValueError):
        return None


def metadata_text(path: Path) -> str:
    """Keep only data headers, masses/labels and relevant input commands."""
    text = prefix(path, metadata_limit)
    rows, section = [], ""
    for index, raw in enumerate(text.splitlines()):
        line = raw.split("#", 1)[0].strip()
        if index == 0 and "LAMMPS data file" in raw:
            rows.append(raw)
        elif re.fullmatch(r"\d+\s+(?:atoms|atom types)", line):
            rows.append(raw)
        elif re.match(r"^(?:mass|units|atom_style|boundary|labelmap|dump_modify)\s", line):
            rows.append(raw)
        elif re.match(r"^pair_coeff\s+\*\s+\*\s", line):
            rows.append(raw)
        elif re.fullmatch(r"[A-Za-z][A-Za-z ]*", line):
            section = line
            if section in {"Masses", "Atom Type Labels", "Atoms"}:
                rows.append(raw)
        elif section in {"Masses", "Atom Type Labels"} and re.match(r"^\d+\s", line):
            rows.append(raw)
    return "\n".join(rows) + "\n"


def data_count(text: str) -> int | None:
    match = re.search(r"^\s*(\d+) atoms\s*$", text, re.M)
    return int(match[1]) if match else None


def data_signature(text: str) -> str:
    """Equal mass tables are safe to collapse; differing tables stay selectable."""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip() and not line.startswith("LAMMPS data file"))


def input_metadata(primary: Path, siblings: list[Path]) -> tuple[list[Path], list[Path]]:
    inputs = [path for path in siblings if path.suffix.lower() in {".in", ".inp", ".lammps", ".init"}
              or path.name.lower().startswith(("in.", "input."))]
    parsed = [(path, commands(prefix(path))) for path in inputs if path != primary and format_of(path) is None]
    matching = [(path, rows) for path, rows in parsed
                if any(row[0] == "dump" and len(row) > 5 and Path(row[5]).name == primary.name for row in rows)]
    selected = matching or (parsed if len(parsed) == 1 else [])
    metadata, data, visited = [], [], set()

    def visit(path: Path, depth: int = 0) -> None:
        if path in visited or depth > 4 or len(visited) >= 16:
            return
        visited.add(path)
        metadata.append(path)
        for row in commands(prefix(path, metadata_limit)):
            if len(row) < 2 or row[0] not in {"include", "read_data"}:
                continue
            related = literal_path(row[1], primary.parent)
            if related is None:
                continue
            if row[0] == "include":
                visit(related, depth + 1)
            elif format_of(related) == "LAMMPS data":
                data.append(related)

    for path, _ in selected:
        visit(path)
    if not metadata:
        logs = [path for path in siblings if path.name.lower().startswith("log")
                and path.suffix.lower() in {".log", ".lammps", ""}]
        if len(logs) == 1:
            metadata.append(logs[0])
    return metadata, data


def lammps_options(primary: Path, siblings: list[Path]) -> list[list[Path]]:
    """Prefer explicit run references, then local and nearby compatible data."""
    inputs, explicit = input_metadata(primary, siblings)
    header = prefix(primary)
    count_match = re.search(r"ITEM: NUMBER OF ATOMS\s*\n(\d+)", header)
    count = int(count_match[1]) if count_match else None
    atom_columns = re.search(r"ITEM: ATOMS ([^\n]+)", header)
    if atom_columns and "element" in atom_columns[1].split():
        return [inputs]

    def compatible(paths: list[Path]) -> list[Path]:
        return [path for path in dict.fromkeys(paths) if format_of(path) == "LAMMPS data"
                and (count is None or data_count(prefix(path)) == count)]

    candidates = compatible(explicit)
    if not candidates:
        candidates = compatible(siblings)
    if not candidates:
        # Optional run provenance is a hint, never executable code or a recursive scan.
        provenance = primary.parent / "provenance.json"
        if provenance.is_file() and provenance.stat().st_size <= 65536:
            try:
                info = json.loads(prefix(provenance, 65537))
                paths = []
                for key in ("source_data", "source_restart"):
                    value = info.get(key) if isinstance(info, dict) else None
                    if not isinstance(value, str):
                        continue
                    source = literal_path(value, primary.parent)
                    if source:
                        paths.extend([source] if key == "source_data" else [source.with_suffix(".data")])
                candidates = compatible([path for path in paths if path.is_file()])
            except (ValueError, OSError):
                pass
    directory = primary.parent
    for _ in range(related_parent_limit):
        stops = {Path.home().resolve(), Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve(), Path("/var/tmp").resolve()}
        if candidates or directory.parent in stops or len(directory.parent.parts) < 3 or (directory / ".git").exists():
            break
        directory = directory.parent
        candidates = compatible(files_in(directory))
    # Multiple copies of the same mapping do not require a user choice.
    unique: dict[str, Path] = {}
    for path in candidates:
        text = metadata_text(path)
        if "Masses" in text or "Atom Type Labels" in text:
            unique.setdefault(data_signature(text), path)
    if len(unique) > candidate_limit:
        raise ValueError("找到太多配套 data 文件，请选择更具体的目录。")
    return [[path, *inputs] for path in unique.values()] or [inputs]


def companion_suffix(primary: Path, fmt: str) -> str | None:
    """Identify formats that need sibling files before requesting directory access."""
    suffix = {"GROMACS TRR": ".tpr", "GROMACS XTC": ".tpr", "GROMACS GRO": ".top"}.get(fmt)
    if fmt == "XYZ" and primary.suffix.lower() == ".xyz" and re.search(r"\bi\s*=\s*\d+", prefix(primary).partition("\n")[2].partition("\n")[0]):
        suffix = ".cell"
    return suffix


def paired_options(primary: Path, fmt: str, siblings: list[Path]) -> list[list[Path]]:
    suffix = companion_suffix(primary, fmt)
    if not suffix:
        return [[]]
    candidates = [path for path in siblings if path.suffix.lower() == suffix]
    if not candidates and fmt == "GROMACS XTC":
        candidates = [path for path in siblings if path.suffix.lower() == ".gro"]
    stem = re.sub(r"-pos-\d+$", "", primary.stem)
    matching = [path for path in candidates if path.stem == primary.stem or re.sub(r"-\d+$", "", path.stem) == stem]
    candidates = matching or candidates
    if not candidates and fmt in {"GROMACS TRR", "GROMACS XTC"}:
        needed = "TPR 或 GRO" if fmt == "GROMACS XTC" else "TPR"
        raise ValueError(f"找到 {fmt} 轨迹，但缺少 {needed} 拓扑；请放在同一目录，或在高级选项中指定。")
    return [[path] for path in candidates] or [[]]


def open_selection(selected: StructurePaths, value: str | None, companions: list[str]) -> dict[str, Any]:
    """Resolve a file or directory into one ready-to-open file or explicit choices."""
    if not value:
        return selected.open(value)
    if not isinstance(value, str) or not Path(value).expanduser().is_absolute():
        raise ValueError("请输入当前主机上的完整路径，可使用 ~/。")
    path = safe_path(Path(value))
    if not path.exists():
        return selected.open(value)  # Preserve the established missing-file diagnostic.
    if companions:
        result = selected.open(str(path))
        for item in companions:
            if not isinstance(item, str) or not Path(item).expanduser().is_absolute():
                raise ValueError("配套文件必须使用完整路径，可使用 ~/。")
        result["file"]["companions"] = [selected.open(str(safe_path(Path(item))), companion=True)["file"] for item in companions]
        return result
    is_directory = path.is_dir()
    directory = path if is_directory else path.parent
    if is_directory:
        siblings = files_in(directory)
        entries = [(item, format_of(item)) for item in siblings]
    else:
        fmt = format_of(path)
        # A file-panel selection authorizes the selected file, not necessarily
        # its containing directory. Self-contained formats need no directory scan.
        needs_siblings = fmt == "LAMMPS dump" or (fmt is not None and companion_suffix(path, fmt) is not None)
        siblings = files_in(directory) if needs_siblings else []
        entries = [(path, fmt)]
    entries = [(item, fmt) for item, fmt in entries if fmt]
    if not entries:
        if not path.is_dir():
            return selected.open(str(path))
        raise ValueError("此目录没有找到支持的结构或轨迹文件。")
    if path.is_dir() and any(fmt in {"LAMMPS dump", "GROMACS TRR"} or item.name.upper() == "XDATCAR" for item, fmt in entries):
        # A run directory can contain hundreds of diagnostic PDB snapshots.
        # Keep trajectories as the default; individual snapshots remain directly openable.
        entries = [(item, fmt) for item, fmt in entries if fmt in {"LAMMPS dump", "GROMACS TRR", "GROMACS XTC", "XYZ", "ASE"}
                   or item.name.upper() == "XDATCAR"]
    if path.is_dir() and any(re.search(r"-pos-\d+\.xyz$", item.name, re.I) for item, _ in entries):
        entries = [(item, fmt) for item, fmt in entries if re.search(r"-pos-\d+\.xyz$", item.name, re.I)
                   or fmt in {"LAMMPS dump", "GROMACS TRR", "GROMACS XTC", "ASE"} or item.name.upper() == "XDATCAR"]
    if path.is_dir() and any(fmt in {"GROMACS TRR", "GROMACS XTC"} for _, fmt in entries):
        entries = [(item, fmt) for item, fmt in entries if fmt != "GROMACS GRO"]
    if len(entries) > candidate_limit:
        raise ValueError("目录中有超过 32 个结构，请选择更具体的目录或轨迹路径。")
    choices = []
    for primary, fmt in entries:
        options = lammps_options(primary, siblings) if fmt == "LAMMPS dump" else paired_options(primary, fmt, siblings)
        for paired in options:
            if len(choices) >= candidate_limit:
                raise ValueError("轨迹与配套文件的组合超过 32 组，请选择更具体的路径。")
            file = selected.open(str(primary))["file"]
            if fmt == "LAMMPS dump":
                file["companions"] = [{"name": item.name + ".metadata.in", "path": str(item), "metadataText": metadata_text(item)} for item in paired]
            else:
                file["companions"] = [selected.open(str(item), companion=True)["file"] for item in paired]
            names = "、".join(os.path.relpath(item, directory) if item.parent != directory else item.name for item in paired)
            file["discoveryNote"] = f"自动识别：{fmt}" + (f" · 配套：{names}" if names else "")
            file["directory"] = str(directory)
            label = f"{primary.name} · {fmt}" + (f" ＋ {names}" if names else "")
            choices.append({"label": label, "file": file})
    result = {**selected.open(None), "directory": str(directory)}
    result.pop("browser", None)
    if len(choices) == 1:
        result["file"] = choices[0]["file"]
    else:
        result["choices"] = choices
    return result
