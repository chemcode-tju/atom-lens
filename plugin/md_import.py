"""Versioned reads for MD trajectories and file-picker imports on the plugin host."""
from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, BinaryIO

from trajectory import file_version


def read_md_index(stream: BinaryIO, fmt: str, offset: int, index_only: bool) -> dict[str, Any]:
    """Walk frame boundaries on the data host. Only requested frames cross MCP."""
    stream.seek(offset)
    offsets: list[int] = []
    end = os.fstat(stream.fileno()).st_size
    text = ""

    def required() -> bytes:
        row = stream.readline()
        if not row:
            raise ValueError("轨迹末尾存在不完整帧")
        return row

    def item(prefix: bytes) -> bytes:
        row = required().strip()
        if not row.startswith(prefix):
            raise ValueError(f"LAMMPS dump 缺少 {prefix.decode()}")
        return row

    while stream.tell() < end:
        start = stream.tell()
        title = required().strip()
        if not title and fmt != "gromacs":
            continue
        if fmt == "gromacs":
            count_line = stream.readline()
            if not title and not count_line.strip() and stream.tell() == end:
                break
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
        if not 1 <= count <= 100000:
            raise ValueError("每帧原子数必须为 1–100000")
        for _ in range(count + (fmt == "gromacs")):
            required()
        offsets.append(start)
        if not index_only:
            finish = stream.tell()
            stream.seek(start)
            text = stream.read(finish - start).decode("utf-8")
            break
        if len(offsets) >= 4096 or stream.tell() - offset >= 1048576:
            break
    return dict(offsets=offsets, nextOffset=stream.tell(), eof=stream.tell() == end, text=text)


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
            result = read_md_index(stream, args["format"], offset, args.get("indexOnly", False))
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
