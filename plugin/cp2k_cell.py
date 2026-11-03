"""Match a selected, versioned CELL file on the trajectory host."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import math
import re

from trajectory import file_version

_step = re.compile(r"(?:^|[,\s])i\s*=\s*(-?\d+)\b")
_units = re.compile(r"\bAx\s*\[([^\]]+)\]", re.I)


@lru_cache(maxsize=2)
def _cells(path: Path, version: str) -> dict[int, str]:
    result: dict[int, str] = {}
    scale = 1.0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                match = _units.search(line)
                if match:
                    unit = match[1].lower()
                    if unit not in {"angstrom", "bohr", "a.u."}:
                        raise ValueError(f"Unsupported CELL length unit: {unit}")
                    scale = 1.0 if unit == "angstrom" else 0.529177210903
                continue
            fields = [float(v.replace("D", "e").replace("d", "e")) for v in line.split()]
            if len(fields) < 11 or not all(map(math.isfinite, fields)) or not fields[0].is_integer():
                raise ValueError("Invalid CP2K CELL row")
            step = int(fields[0])
            if step in result:
                raise ValueError(f"Duplicate CP2K CELL step: {step}")
            result[step] = " ".join(str(v * scale) for v in fields[2:11])
    if version != file_version(path.stat()):
        raise ValueError("CELL changed; reopen both files.")
    return result


def attach_cell(batch: dict, path: Path, version: str) -> None:
    if path.suffix.lower() != ".cell" or file_version(path.stat()) != version:
        raise ValueError("Invalid or changed CP2K CELL file; reopen both files.")
    if not batch.get("text"):
        return
    table = _cells(path, version)
    lines = batch["text"].splitlines(keepends=True)
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        count = int(lines[i])
        header = lines[i + 1]
        match = _step.search(header)
        if not match:
            raise ValueError("Missing CP2K XYZ step (i = ...)")
        step = int(match[1])
        if step not in table:
            raise ValueError(f"No CELL row for CP2K XYZ step {step}")
        lines[i + 1] = f'Lattice="{table[step]}" pbc="T T T" step={step} {header}'
        i += count + 2
    if version != file_version(path.stat()):
        raise ValueError("CELL changed; reopen both files.")
    batch["text"] = "".join(lines)
