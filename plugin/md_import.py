"""Versioned reads for MD trajectories and file-picker imports on the plugin host."""
from __future__ import annotations

import base64
import json
import os
import stat
import struct
import subprocess
import sys
from pathlib import Path
from itertools import islice
from typing import Any, BinaryIO

from trajectory import file_version
from file_snapshot import IncompleteFrame, is_snapshot, open_snapshot
from xtc_index import read_xtc_index


def read_md_index(stream: BinaryIO, fmt: str, offset: int, index_only: bool, frozen: bool = False, frame_limit: int = 64) -> dict[str, Any]:
    """Walk frame boundaries on the data host. Only requested frames cross MCP."""
    if fmt == "xtc":
        return read_xtc_index(stream, offset, index_only, frozen, frame_limit)
    if fmt == "trr":
        return read_trr_index(stream, offset, frozen, frame_limit)
    if type(frame_limit) is not int or not 1 <= frame_limit <= 4096:
        raise ValueError("无效轨迹索引批次大小")
    stream.seek(offset)
    offsets: list[int] = []
    stream.seek(0, 2)
    end = stream.tell()
    stream.seek(offset)
    text = ""

    def required() -> bytes:
        row = stream.readline()
        if not row or (frozen and not row.endswith(b"\n")):
            raise IncompleteFrame("轨迹末尾存在不完整帧")
        return row

    def item(prefix: bytes) -> bytes:
        row = required().strip()
        if not row.startswith(prefix):
            raise ValueError(f"LAMMPS dump 缺少 {prefix.decode()}")
        return row

    while stream.tell() < end:
        start = stream.tell()
        try:
            title = required().strip()
            if not title and fmt != "gromacs":
                continue
            if fmt == "gromacs":
                count_line = required()
                count = int(count_line)
            elif fmt == "lammps-dump-text":
                while title in (b"ITEM: UNITS", b"ITEM: TIME"):
                    required()
                    title = required().strip()
                if title != b"ITEM: TIMESTEP":
                    raise ValueError("仅支持 LAMMPS atom/custom 文本 dump")
                required()
                label = required().strip()
                while label in (b"ITEM: UNITS", b"ITEM: TIME"):
                    required()
                    label = required().strip()
                if label != b"ITEM: NUMBER OF ATOMS":
                    raise ValueError("dump 缺少 NUMBER OF ATOMS")
                count = int(required())
                item(b"ITEM: BOX BOUNDS")
                for _ in range(3):
                    required()
                item(b"ITEM: ATOMS ")
            else:
                raise ValueError("Unsupported MD format")
            if not 1 <= count <= 1000000:
                raise ValueError("每帧原子数必须为 1–1000000")
            # BufferedReader's iterator skips coordinate lines in C. Reading
            # the last declared row still detects a truncated snapshot tail.
            rows = count + (fmt == "gromacs")
            last = next(islice(stream, rows - 1, rows), b"")
            if not last or (frozen and not last.endswith(b"\n")):
                raise IncompleteFrame("轨迹末尾存在不完整帧")
        except IncompleteFrame:
            if not frozen:
                raise
            stream.seek(end)
            return dict(offsets=offsets, nextOffset=end, eof=True, text=text, incompleteTail=True)
        offsets.append(start)
        if not index_only:
            finish = stream.tell()
            stream.seek(start)
            text = stream.read(finish - start).decode("utf-8")
            break
        if len(offsets) >= frame_limit or stream.tell() - offset >= (2 if frame_limit <= 16 else 32) * 1048576:
            break
    return dict(offsets=offsets, nextOffset=stream.tell(), eof=stream.tell() == end, text=text)


def read_trr_index(stream: BinaryIO, offset: int, frozen: bool, frame_limit: int) -> dict[str, Any]:
    """Send only XDR header metadata and skip coordinate, velocity and force payloads."""
    if type(frame_limit) is not int or not 1 <= frame_limit <= 64:
        raise ValueError("无效 TRR 索引批次大小")
    end = stream.seek(0, 2)
    frames = []
    for _ in range(frame_limit):
        if offset == end:
            break
        stream.seek(offset)
        header = stream.read(84)
        if len(header) < 84:
            if not frozen:
                raise IncompleteFrame("TRR 帧头不完整")
            offset = end
            break
        if struct.unpack_from(">3i", header) != (1993, 13, 12) or header[12:24] != b"GMX_trn_file":
            raise ValueError(f"无效 TRR 帧头（字节 {offset}）")
        sizes = struct.unpack_from(">10i", header, 24)
        count, step = struct.unpack_from(">2i", header, 64)
        ir, energy, box, virial, pressure, top, sym, coords, velocity, force = sizes
        if not 1 <= count <= 1_000_000:
            raise ValueError("TRR 原子数无效或超过 1,000,000")
        width = box / 9 if box else (coords or velocity or force) / (count * 3)
        if (width not in (4, 8) or min(sizes) < 0 or any((ir, energy, top, sym))
                or any(size and size != 9 * width for size in (box, virial, pressure))
                or any(size and size != count * 3 * width for size in (coords, velocity, force))):
            raise ValueError("不支持的 TRR 数据块布局")
        width = int(width)
        start = offset + 76 + 2 * width
        offset = start + sum(sizes)
        if offset > end:
            if not frozen:
                raise IncompleteFrame("TRR 坐标帧不完整")
            offset = end
            break
        if coords:
            frames.append(dict(step=step, width=width, start=start, box=box,
                               coords=start + box + virial + pressure, n=count))
    return dict(frames=frames, nextOffset=offset, eof=offset == end)


def convert_static(args: dict[str, Any]) -> dict[str, str]:
    """Use an existing ASE environment for static CIF, PDB or LAMMPS data."""
    if args.get("format") not in {"lammps-data", "proteindatabank", "cif"}:
        raise ValueError("Unsupported conversion format")
    if not isinstance(args.get("text"), str) or len(args["text"].encode()) > 32 * 1048576:
        raise ValueError("Static structure conversion requires a text file of at most 32 MiB")
    candidates = [os.getenv("STRUCTURE_VIEWER_ASE_PYTHON"), sys.executable,
                  Path(sys.prefix) / "envs/work/bin/python",
                  Path.home() / "miniconda3/envs/work/bin/python",
                  Path.home() / ".conda/envs/work/bin/python",
                  Path.home() / "software/miniconda3/envs/work/bin/python"]
    for executable in dict.fromkeys(str(p) for p in candidates if p and Path(p).is_file()):
        result = subprocess.run([executable, str(Path(__file__).with_name("ase_convert.py"))],
                                input=json.dumps(args), text=True, capture_output=True, timeout=120)
        if result.returncode == 42:
            continue
        if result.returncode:
            raise ValueError(result.stderr.strip() or "Structure conversion failed")
        return {"text": result.stdout}
    raise ValueError("CIF/PDB/LAMMPS data 需要 ASE。请设置 STRUCTURE_VIEWER_ASE_PYTHON 指向已安装 ASE 的 Python。")


def import_selected(params: dict[str, Any]) -> dict[str, Any]:
    args = params["arguments"]
    action = args["action"]
    if action == "topology":
        from gmx_topology import topology_request
        return topology_request(params)
    if action == "convert" and "text" in args:
        return convert_static(args)
    path = params.get("_meta", {}).get("openai/resource", {}).get("path")
    if not isinstance(path, str) or not Path(path).is_absolute():
        return {"supported": False}
    if action == "stat" or is_snapshot(args.get("version")):
        with open_snapshot(Path(path), None if action == "stat" else args["version"]) as (stream, snapshot):
            if action == "stat":
                return {"size": snapshot.size, "version": snapshot.version, "supported": True,
                        "frozen": True, "trrIndex": True}
            offset = args.get("offset", 0)
            if type(offset) is not int or not 0 <= offset <= snapshot.size:
                raise ValueError("无效文件偏移。")
            if action == "frames":
                return read_md_index(stream, args["format"], offset, args.get("indexOnly", False), frozen=True, frame_limit=args.get("frameLimit", 64))
            if action == "range":
                length = args["length"]
                if type(length) is not int or not 0 <= length <= 1048576:
                    raise ValueError("Invalid chunk size")
                stream.seek(offset)
                return {"data": base64.b64encode(stream.read(length)).decode("ascii")}
            if action == "convert":
                if snapshot.size > 32 * 1048576:
                    raise ValueError("Static structure conversion is limited to 32 MiB")
                return convert_static({**args, "text": stream.read().decode("utf-8-sig")})
            raise ValueError("Unsupported import action")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("只能读取普通结构文件。")
        version = file_version(info)
        if action == "stat":
            return {"size": info.st_size, "version": version, "supported": True}
        if args.get("version") != version:
            raise ValueError("加载期间文件已改变；请重新打开，避免混合不同版本的帧。")
        offset = args.get("offset", 0)
        if type(offset) is not int or not 0 <= offset <= info.st_size:
            raise ValueError("无效文件偏移。")
        if action == "frames":
            result = read_md_index(stream, args["format"], offset, args.get("indexOnly", False), frame_limit=args.get("frameLimit", 64))
        elif action == "convert":
            if info.st_size > 32 * 1048576:
                raise ValueError("Static structure conversion is limited to 32 MiB")
            result = convert_static({**args, "text": stream.read().decode("utf-8-sig")})
        elif action == "range":
            length = args["length"]
            if type(length) is not int or not 0 <= length <= 1048576:
                raise ValueError("Invalid chunk size")
            stream.seek(offset)
            result = {"data": base64.b64encode(stream.read(length)).decode("ascii")}
        else:
            raise ValueError("Unsupported import action")
        if file_version(os.fstat(stream.fileno())) != version or file_version(os.stat(path)) != version:
            raise ValueError("读取期间文件已改变，请重新打开。")
        return result
