"""Progressive structure reads from the file selected by the native host."""

from pathlib import Path
from typing import Any, BinaryIO
import hashlib
import os
import stat
from ase_trajectory import read_batch
from vasp_trajectory import read_vasp_batch


def file_version(info: Any) -> str:
    """Detect replacement, truncation and in-place writes between requests."""
    signature = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    return hashlib.sha256(repr(signature).encode()).hexdigest()


def read_line(stream: BinaryIO, remaining: int) -> bytes:
    line = stream.readline(remaining + 1)
    if len(line) > remaining:
        raise ValueError("单帧超过 8 MiB 分段预览上限，请使用完整文件模式。")
    return line


def xyz_index(stream: BinaryIO, offset: int, end: int, limit: int) -> dict[str, Any]:
    """Count complete XYZ records within a bounded block, preserving byte offsets."""
    stream.seek(offset)
    data = stream.read(8 * 1048576)
    eof = offset + len(data) == end
    rows = data.split(b"\n")
    # The last item is either a partial line, a final unterminated line,
    # or the empty sentinel produced by a trailing newline.
    if not eof or not rows[-1]:
        rows.pop()
    cursor = offset
    i = 0
    offsets = []
    while i < len(rows) and len(offsets) < limit:
        start = cursor
        while i < len(rows) and not rows[i].strip():
            cursor += len(rows[i]) + 1
            i += 1
        if i == len(rows):
            if not eof:
                cursor = start  # Let the next frame own its leading blank lines.
            break
        count = rows[i].strip()
        if not count.isdigit() or not 1 <= int(count) <= 100000:
            if offsets:
                cursor = start
                break
            raise ValueError(f"字节 {cursor} 处不是有效的原子数。")
        next_frame = i + int(count) + 2
        if next_frame > len(rows):
            if offsets:
                cursor = start
                break
            if not eof:
                raise ValueError("单帧超过 8 MiB 分段预览上限。")
            raise ValueError("轨迹末尾存在不完整帧。")
        atoms = rows[i + 2:next_frame]
        if b"" in atoms or any(map(bytes.isspace, atoms)):
            if offsets:
                cursor = start
                break
            raise ValueError("轨迹末尾存在不完整帧。")
        offsets.append(start)
        cursor += sum(map(len, rows[i:next_frame])) + next_frame - i
        i = next_frame
    cursor = min(cursor, end)
    if not offsets and cursor < end and not eof:
        raise ValueError("单帧超过 8 MiB 分段预览上限。")
    return {"supported": True, "text": "", "frameCount": len(offsets), "offsets": offsets,
            "nextOffset": cursor, "totalBytes": end, "eof": cursor == end}


def read_frames(params: dict[str, Any]) -> dict[str, Any]:
    """Read complete frames only; the UI cannot nominate a filesystem path."""
    host_path = params.get("_meta", {}).get("openai/resource", {}).get("path")
    if not isinstance(host_path, str) or not Path(host_path).is_absolute():
        return {"supported": False, "reason": "host-path-unavailable"}
    path = Path(host_path)
    vasp = path.name.upper() in {"POSCAR", "CONTCAR", "XDATCAR"} or path.suffix.lower() == ".vasp"
    if not vasp and path.suffix.lower() not in {".xyz", ".extxyz", ".traj"}:
        raise ValueError("分段读取支持 XYZ/extxyz/ASE traj 和 VASP。")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("只能读取普通结构文件。")
    arguments = params.get("arguments", {})
    offset = arguments.get("offset", 0)
    frame_limit = arguments.get("frameLimit", 32)
    index_only = arguments.get("indexOnly", False)
    if type(index_only) is not bool:
        raise ValueError("无效索引请求")
    if type(offset) is not int or offset < 0:
        raise ValueError("无效文件偏移。")
    maximum = 4096 if index_only else 32
    if type(frame_limit) is not int or not 1 <= frame_limit <= maximum:
        raise ValueError(f"每次读取帧数必须为 1–{maximum}。")
    blocks: list[bytes] = []
    offsets: list[int] = []
    frame_count = 0
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("只能读取普通结构文件。")
        version = file_version(info)
        if offset > info.st_size or ((offset or arguments.get("version") is not None) and arguments.get("version") != version):
            raise ValueError("加载期间文件已改变；请重新打开，避免混合不同版本的帧。")
        if vasp:
            batch = read_vasp_batch(stream, offset, frame_limit, path.name.upper() == "XDATCAR", index_only, arguments.get("headerOffset", 0))
            if file_version(os.fstat(stream.fileno())) != version or file_version(path.stat()) != version:
                raise ValueError("读取期间文件已改变，请重新打开。")
            return {**batch, "version": version, "totalBytes": info.st_size,
                    "eof": batch["nextOffset"] == info.st_size}
        if path.suffix.lower() == ".traj":
            batch = read_batch(stream, offset, frame_limit, index_only)
            if file_version(os.fstat(stream.fileno())) != version or file_version(path.stat()) != version:
                raise ValueError("读取期间文件已改变，请重新打开。")
            return {**batch, "version": version}
        if index_only:
            batch = xyz_index(stream, offset, info.st_size, frame_limit)
            if file_version(os.fstat(stream.fileno())) != version or file_version(path.stat()) != version:
                raise ValueError("读取期间文件已改变，请重新打开。")
            return {**batch, "version": version}
        stream.seek(offset)
        size = 0
        while frame_count < frame_limit and size < 262144:
            start = stream.tell()
            frame = bytearray()
            frame_size = 0
            while True:
                line = read_line(stream, 8388608 - frame_size)
                frame_size += len(line)
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
                line = read_line(stream, 8388608 - frame_size)
                if not line or (row > 0 and not line.strip()):
                    raise ValueError("轨迹末尾存在不完整帧；请等待写入完成后重新打开。")
                frame_size += len(line)
                frame.extend(line)
            offsets.append(start)
            blocks.append(bytes(frame))
            size += frame_size
            frame_count += 1
        next_offset = stream.tell()
        if file_version(os.fstat(stream.fileno())) != version or file_version(path.stat()) != version:
            raise ValueError("读取期间文件已改变，请重新打开。")
    return {"supported": True, "text": b"".join(blocks).decode("utf-8"),
            "frameCount": frame_count, "offsets": offsets, "nextOffset": next_offset,
            "totalBytes": info.st_size, "eof": next_offset == info.st_size,
            "version": version}
