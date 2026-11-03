"""Persistent, portable links to a LAMMPS dump and its explicit metadata files."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import socket
import tempfile
from typing import Any

from path_access import StructurePaths

dump_pattern = re.compile(r"(?:dump(?:[._-].+)?|.+\.(?:dump|lammpstrj|lammps))\Z", re.I)
metadata_pattern = re.compile(r"(?:(?:data|log|in)(?:[._-].+)?|.+\.(?:data|lmp|log|in|inp|lammps))\Z", re.I)
link_size_limit = 16 * 1024


def member(directory: Path, name: str, pattern: re.Pattern) -> Path:
    """Links grant access only to named regular files beside the link itself."""
    if not isinstance(name, str) or Path(name).name != name or not pattern.fullmatch(name):
        raise ValueError("轨迹链接只接受同目录下的 LAMMPS 文件名。")
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"轨迹链接文件缺失或为符号链接：{name}")
    return path


def members(directory: Path, spec: Any) -> tuple[Path, list[Path]]:
    if not isinstance(spec, dict) or set(spec) != {"version", "dump", "companions"} or type(spec["version"]) is not int or spec["version"] != 1:
        raise ValueError("无效的 Structure Viewer 轨迹链接。")
    names = spec["companions"]
    if not isinstance(names, list) or len(names) > 31:
        raise ValueError("轨迹链接最多支持 31 个配套文件。")
    dump = member(directory, spec["dump"], dump_pattern)
    inputs = [member(directory, name, metadata_pattern) for name in names]
    if len({dump, *inputs}) != 1 + len(inputs):
        raise ValueError("轨迹链接包含重复文件。")
    return dump, inputs


def create_link(path: str, companions: list[str]) -> dict[str, str]:
    if not isinstance(path, str) or not Path(path).is_absolute() or not isinstance(companions, list):
        raise ValueError("请输入轨迹和配套文件在当前主机上的绝对路径。")
    dump = Path(path)
    directory = dump.parent.resolve(strict=True)
    if any(not isinstance(p, str) or not Path(p).is_absolute() or Path(p).parent.resolve() != directory for p in companions):
        raise ValueError("生成链接时，轨迹和配套文件必须在同一个目录；跨目录请用按路径打开。")
    spec = dict(version=1, dump=dump.name, companions=sorted(Path(p).name for p in companions))
    members(directory, spec)
    content = (json.dumps(spec, ensure_ascii=False, indent=2) + "\n").encode()
    if len(content) > link_size_limit:
        raise ValueError("轨迹链接过大。")
    digest = hashlib.sha256(content).hexdigest()[:12]
    target = directory / f"view-{digest}.svtraj"
    # Publish a complete file atomically without replacing any existing entry.
    with tempfile.NamedTemporaryFile(dir=directory) as temp:
        temp.write(content)
        temp.flush()
        try:
            os.link(temp.name, target)
        except FileExistsError:
            if target.is_symlink() or not target.is_file() or target.stat().st_size != len(content) or target.read_bytes() != content:
                raise ValueError(f"同名文件已存在：{target}")
    return {"path": str(target), "host": socket.gethostname()}


def resolve_link(selected: StructurePaths, params: dict[str, Any]) -> dict[str, Any]:
    path = params.get("_meta", {}).get("openai/resource", {}).get("path")
    if not isinstance(path, str) or not Path(path).is_absolute():
        raise ValueError("宿主没有提供轨迹链接路径，请在对应主机的查看器中按路径打开。")
    link = Path(path)
    if link.suffix.lower() != ".svtraj" or link.is_symlink() or not link.is_file():
        raise ValueError("无效的 Structure Viewer 轨迹链接。")
    with link.open("rb") as stream:
        content = stream.read(link_size_limit + 1)
    if len(content) > link_size_limit:
        raise ValueError("轨迹链接过大。")
    dump, inputs = members(link.parent, json.loads(content))
    result = selected.open(str(dump))
    result["file"]["companions"] = [selected.open(str(p), companion=True)["file"] for p in inputs]
    return result
