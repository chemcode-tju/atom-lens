"""Read explicitly selected server-side structure paths without renaming files."""

from __future__ import annotations

# Configuration
max_open_files = 256

from pathlib import Path
from typing import Any
import os
import secrets
import socket
import stat

from trajectory import file_version


class StructurePaths:
    """Bind bounded reads to opaque handles for paths selected by the user or agent."""

    def __init__(self) -> None:
        self.files: dict[str, Path] = {}

    def open(self, value: str | None, companion: bool = False) -> dict[str, Any]:
        if not value:
            return {"browser": True, "host": socket.gethostname()}
        if not isinstance(value, str) or not Path(value).expanduser().is_absolute():
            raise ValueError("请输入当前主机上的完整绝对路径。")
        path = Path(value).expanduser()
        name = path.name.lower()
        known_companion = companion and (name in {"in", "log", "data"} or name.startswith(("in.", "log.", "data.", "in_", "log_", "data_", "in-", "log-", "data-")) or path.suffix.lower() in {".in", ".inp", ".init", ".settings", ".log", ".cell", ".tpr", ".top", ".itp"})
        if not known_companion and name not in {"dump", "data"} and not name.startswith(("data.", "dump.", "dump_", "dump-")) and path.name.upper() not in {"POSCAR", "CONTCAR", "XDATCAR"} and path.suffix.lower() not in {".xyz", ".extxyz", ".traj", ".vasp", ".gro", ".lammpstrj", ".dump", ".lammps", ".lmp", ".data", ".pdb", ".cif", ".svtraj", ".trr", ".xtc"}:
            raise ValueError("不支持该结构文件名。")
        try:
            resolved = path.resolve(strict=True)
            if not stat.S_ISREG(resolved.stat().st_mode):
                raise ValueError("只能打开普通结构文件。")
        except FileNotFoundError as error:
            raise ValueError(f"当前主机 {socket.gethostname()} 上没有此文件：{path}") from error
        token = secrets.token_urlsafe(24)
        self.files[token] = resolved
        if len(self.files) > max_open_files:
            del self.files[next(iter(self.files))]
        return {"host": socket.gethostname(), "file": {"name": path.name, "path": str(path),
                "resourceUri": f"structure-viewer://selected/{token}", "token": token}}

    def bind(self, params: dict[str, Any]) -> dict[str, Any]:
        """Only explicit known tokens may replace native host file metadata."""
        token = params.get("arguments", {}).get("token")
        if token is None:
            return params
        if not isinstance(token, str) or token not in self.files:
            raise ValueError("结构文件会话已失效，请重新按路径打开。")
        return {**params, "_meta": {"openai/resource": {"path": str(self.files[token])}}}

    def read_source(self, params: dict[str, Any]) -> dict[str, str]:
        """Compatibility full read; normal VASP viewing uses progressive frame reads."""
        token = params.get("arguments", {}).get("token")
        if not isinstance(token, str) or token not in self.files:
            raise ValueError("结构文件会话已失效，请重新按路径打开。")
        path = self.files[token]
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("只能读取普通结构文件。")
            version = file_version(info)
            data = stream.read()
            if version != file_version(os.fstat(stream.fileno())) or version != file_version(path.stat()):
                raise ValueError("读取时文件已变化，请等待写入完成后重新打开。")
        return {"text": data.decode("utf-8"), "version": version}
