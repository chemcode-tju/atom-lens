"""Read modern ASE ULM trajectories without importing ASE or executing pickle data."""
from typing import Any, BinaryIO
import json
import math
import struct

symbols = "X H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split()


def read_at(stream: BinaryIO, offset: int, size: int) -> bytes:
    if offset < 0 or size < 0 or size > 8388608:
        raise ValueError("无效或过大的 ASE 轨迹数据块")
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("ASE 轨迹不完整")
    return data


def metadata(stream: BinaryIO, table: int, index: int) -> dict[str, Any]:
    offset = struct.unpack("<q", read_at(stream, table + index * 8, 8))[0]
    size = struct.unpack("<q", read_at(stream, offset, 8))[0]
    return json.loads(read_at(stream, offset + 8, size))


def array(stream: BinaryIO, data: dict[str, Any], key: str) -> list[Any]:
    shape, dtype, offset = data[f"{key}."]["ndarray"]
    formats = {"int64": "q", "int32": "i", "float64": "d", "float32": "f"}
    if dtype not in formats or not shape or any(type(n) is not int or n < 0 for n in shape):
        raise ValueError(f"不支持的 ASE 数组类型：{key} {dtype}")
    count = math.prod(shape)
    fmt = ("<" if data.get("_little_endian", True) else ">") + formats[dtype]
    values = [item[0] for item in struct.iter_unpack(fmt, read_at(stream, offset, count * struct.calcsize(fmt)))]
    if len(shape) == 1:
        return values
    if len(shape) != 2:
        raise ValueError("ASE 结构数组维度无效")
    return [values[i:i + shape[1]] for i in range(0, count, shape[1])]


def read_batch(stream: BinaryIO, start: int, limit: int, index_only: bool = False) -> dict[str, Any]:
    """Use ULM's offset table for bounded frame access; ignore calculator payloads."""
    header = read_at(stream, 0, 48)
    if header[:8] not in {b"- of Ulm", b"AFFormat"} or header[8:24].strip() != b"ASE-Trajectory":
        raise ValueError("需要现代 ASE .traj 文件；不读取旧版 pickle 轨迹")
    version, count, table = struct.unpack("<qqq", header[24:])
    if version not in {1, 2, 3} or count < 1 or start >= count:
        raise ValueError("ASE 轨迹版本或帧号无效")
    if index_only:
        # ULM already stores a frame index. Do not read any position arrays.
        return {"supported": True, "text": "", "frameCount": 0, "offsets": [],
                "nextOffset": count, "totalFrames": count, "eof": True, "readOnly": True}
    first = metadata(stream, table, 0)
    blocks: list[str] = []
    size = 0
    for index in range(start, min(count, start + limit)):
        data = metadata(stream, table, index)
        header_data = data if "numbers." in data else first
        numbers = array(stream, header_data, "numbers")
        positions = array(stream, data, "positions")
        masses = array(stream, header_data, "masses") if "masses." in header_data else None
        if masses is not None and (len(masses) != len(numbers) or any(not math.isfinite(m) or m <= 0 for m in masses)):
            raise ValueError("ASE 原子质量无效")
        cell = data.get("cell", [[0.0] * 3 for _ in range(3)])
        pbc = header_data.get("pbc", [False] * 3)
        if not 1 <= len(numbers) <= 1000000 or len(numbers) != len(positions):
            raise ValueError("ASE 原子数与坐标不一致")
        if len(cell) != 3 or any(len(row) != 3 for row in cell) or len(pbc) != 3:
            raise ValueError("ASE 晶胞或周期边界无效")
        lattice = " ".join(str(v) for row in cell for v in row)
        periodic = " ".join("T" if value else "F" for value in pbc)
        properties = "species:S:1:pos:R:3" + (":mass:R:1" if masses is not None else "")
        rows = [str(len(numbers)), f'Lattice="{lattice}" Properties={properties} pbc="{periodic}"']
        for atom_index, (number, position) in enumerate(zip(numbers, positions)):
            if type(number) is not int or not 1 <= number < len(symbols) or len(position) != 3 or not all(math.isfinite(v) for v in position):
                raise ValueError("ASE 元素或坐标无效")
            rows.append(f"{symbols[number]} {' '.join(str(v) for v in position)}" + (f" {masses[atom_index]}" if masses is not None else ""))
        block = "\n".join(rows) + "\n"
        blocks.append(block)
        size += len(block)
        if size >= 262144:
            break
    next_index = start + len(blocks)
    return {"supported": True, "text": "".join(blocks), "frameCount": len(blocks),
            "offsets": list(range(start, next_index)), "nextOffset": next_index, "totalFrames": count, "eof": next_index == count, "readOnly": True}
