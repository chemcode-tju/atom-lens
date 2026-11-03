"""Convert supported static formats using ASE in an isolated worker."""
import json
import re
import sys
from io import StringIO

try:
    import numpy as np
    from ase import Atoms
    from ase.data import atomic_numbers
    from ase.io import iread, read
except ImportError:
    sys.exit(42)


def data_frame(text: str, elements: list[str], units: str, atom_style: str) -> Atoms:
    if not elements:
        raise ValueError("LAMMPS data 需要明确提供 type 对应的元素，例如 Cu O H。")
    atoms = read(
        StringIO(text),
        format="lammps-data",
        units=units,
        Z_of_type={index + 1: atomic_numbers[value] for index, value in enumerate(elements)},
        atom_style=None if atom_style == "auto" else atom_style,
    )
    # Conventional data boxes use absolute coordinates; ASE omits xlo/ylo/zlo in celldisp.
    origin = np.asarray(atoms.get_celldisp()).reshape(3).copy()
    for index, axis in enumerate("xyz"):
        match = re.search(rf"^\s*(\S+)\s+\S+\s+{axis}lo\s+{axis}hi\b", text, re.M)
        if match:
            origin[index] = float(match[1])
    atoms.positions -= origin
    return atoms


def frame_text(atoms: Atoms) -> str:
    """Serialize only viewer fields; coordinates/cell in Å and masses in atomic mass units."""
    if not 1 <= len(atoms) <= 100000:
        raise ValueError("每帧原子数必须为 1–100000")
    masses = atoms.get_masses()
    if not all(np.isfinite(values).all() for values in (atoms.positions, atoms.cell, masses)):
        raise ValueError("结构包含非有限坐标、晶胞或质量。")
    if np.any(masses <= 0) or np.any(atoms.numbers == 0):
        raise ValueError("无法识别某些原子的元素或质量，请核对原子名/元素映射。")
    if np.any(atoms.pbc) and np.linalg.matrix_rank(atoms.cell) < sum(atoms.pbc):
        raise ValueError("周期晶胞退化，无法进行 Wrap 或晶胞显示。")
    lattice = " ".join(f"{value:.12g}" for value in np.asarray(atoms.cell).ravel())
    periodic = " ".join("T" if value else "F" for value in atoms.pbc)
    identifiers = atoms.arrays.get("id")
    properties = "species:S:1:pos:R:3:mass:R:1" + (":id:I:1" if identifiers is not None else "")
    lines = [str(len(atoms)), f'Lattice="{lattice}" Properties={properties} pbc="{periodic}"']
    for index, (symbol, position, mass) in enumerate(
        zip(atoms.get_chemical_symbols(), atoms.positions, masses, )
    ):
        coordinates = " ".join(f"{value:.12g}" for value in position)
        identifier = f" {int(identifiers[index])}" if identifiers is not None else ""
        lines.append(f"{symbol} {coordinates} {mass:.12g}{identifier}")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = json.load(sys.stdin)
    fmt = args["format"]
    if fmt == "lammps-data":
        atoms = data_frame(args["text"], args["elements"], args["units"], args["atomStyle"])
        frames = [atoms]
    elif fmt in {"cif", "proteindatabank"}:
        from io import BytesIO
        source = BytesIO(args["text"].encode()) if fmt == "cif" else StringIO(args["text"])
        frames = iread(source, index=":", format=fmt)
    else:
        raise ValueError("Unsupported conversion format")
    size = 0
    for atoms in frames:
        text = frame_text(atoms)
        size += len(text)
        if size > 64 * 1048576:
            raise ValueError("Static conversion exceeds 64 MiB")
        sys.stdout.write(text)
    if not size:
        raise ValueError("没有结构帧")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.exit(str(error))
