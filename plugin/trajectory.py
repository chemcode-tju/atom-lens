"""Bounded XYZ reads from the file selected by the native host."""

from pathlib import Path
from typing import Any, BinaryIO
import hashlib
import os
import stat
from ase_trajectory import read_batch


def file_version(info: Any) -> str:
    """Detect replacement, truncation and in-place writes between requests."""
    signature = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    return hashlib.sha256(repr(signature).encode()).hexdigest()


def read_line(stream: BinaryIO, remaining: int) -> bytes:
    line = stream.readline(remaining + 1)
    if len(line) > remaining:
        raise ValueError("单帧超过 8 MiB 分段预览上限，请使用完整文件模式。")
    return line


def read_frames(params: dict[str, Any]) -> dict[str, Any]:
    """Read complete frames only; the UI cannot nominate a filesystem path."""
    host_path = params.get("_meta", {}).get("openai/resource", {}).get("path")
    if not isinstance(host_path, str) or not Path(host_path).is_absolute():
        return {"supported": False, "reason": "host-path-unavailable"}
    path = Path(host_path)
    if path.suffix.lower() not in {".xyz", ".extxyz", ".traj"}:
        raise ValueError("分段读取支持 XYZ/extxyz/ASE traj。")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("只能读取普通结构文件。")
    arguments = params.get("arguments", {})
    offset = arguments.get("offset", 0)
    frame_limit = arguments.get("frameLimit", 32)
    if type(offset) is not int or offset < 0:
        raise ValueError("无效文件偏移。")
    if type(frame_limit) is not int or not 1 <= frame_limit <= 32:
        raise ValueError("每次读取帧数必须为 1–32。")
    blocks: list[bytes] = []
    frame_count = 0
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("只能读取普通结构文件。")
        version = file_version(info)
        if offset > info.st_size or (offset and arguments.get("version") != version):
            raise ValueError("加载期间文件已改变；请重新打开，避免混合不同版本的帧。")
        if path.suffix.lower() == ".traj":
            batch = read_batch(stream, offset, frame_limit)
            if file_version(os.fstat(stream.fileno())) != version or file_version(path.stat()) != version:
                raise ValueError("读取期间文件已改变，请重新打开。")
            return {**batch, "version": version}
        stream.seek(offset)
        size = 0
        while frame_count < frame_limit and size < 262144:
            frame = bytearray()
            while True:
                line = read_line(stream, 8388608 - len(frame))
                frame.extend(line)
                if line.strip() or not line:
                    break
            if not line:
                blocks.append(bytes(frame))
                break
            if not line.strip().isdigit():
                raise ValueError(f"字节 {stream.tell() - len(line)} 处不是原子数。")
            atom_count = int(line.strip())
            if not 1 <= atom_count <= 100000:
                raise ValueError("原子数必须在 1–100000 范围内。")
            for row in range(atom_count + 1):
                line = read_line(stream, 8388608 - len(frame))
                if not line or (row > 0 and not line.strip()):
                    raise ValueError("轨迹末尾存在不完整帧；请等待写入完成后重新打开。")
                frame.extend(line)
            blocks.append(bytes(frame))
            size += len(frame)
            frame_count += 1
        next_offset = stream.tell()
        if file_version(os.fstat(stream.fileno())) != version or file_version(path.stat()) != version:
            raise ValueError("读取期间文件已改变，请重新打开。")
    return {"supported": True, "text": b"".join(blocks).decode("utf-8"),
            "frameCount": frame_count, "nextOffset": next_offset,
            "totalBytes": info.st_size, "eof": next_offset == info.st_size,
            "version": version}
