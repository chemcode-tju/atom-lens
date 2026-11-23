"""Index standard XTC headers without decompressing or copying trajectories."""
from __future__ import annotations

import math
import struct
from typing import Any, BinaryIO

from file_snapshot import IncompleteFrame


def read_xtc_index(stream: BinaryIO, offset: int, index_only: bool, frozen: bool, frame_limit: int = 64) -> dict[str, Any]:
    """Skip compressed payloads; ignore an unfinished final frame in snapshots."""
    stream.seek(0, 2)
    end = stream.tell()
    frames: list[dict[str, Any]] = []
    if type(frame_limit) is not int or frame_limit < 1:
        raise ValueError("无效 XTC 索引批次大小")
    for _ in range(min(frame_limit, 64) if index_only else 1):
        if offset == end:
            break
        stream.seek(offset)
        header = stream.read(min(92, end - offset))
        try:
            if len(header) < 56:
                raise IncompleteFrame("XTC 帧头不完整")
            magic, count, step, time = struct.unpack_from(">iiif", header)
            if magic != 1995:
                raise ValueError(f"不支持的 XTC 标识 {magic}（字节 {offset}）")
            if not 1 <= count <= 1_000_000 or struct.unpack_from(">i", header, 52)[0] != count:
                raise ValueError("XTC 原子数无效或超过 1,000,000")
            if not math.isfinite(time):
                raise ValueError("XTC 时间无效")
            if count <= 9:
                length = 56 + count * 12
            else:
                if len(header) < 92:
                    raise IncompleteFrame("XTC 压缩帧头不完整")
                size = struct.unpack_from(">i", header, 88)[0]
                if not 0 < size <= count * 32:
                    raise ValueError("XTC 压缩数据长度无效")
                length = 92 + (size + 3) // 4 * 4
            if offset + length > end:
                raise IncompleteFrame("XTC 坐标帧不完整")
        except IncompleteFrame:
            if not frozen:
                raise
            offset = end
            break
        frames.append(dict(offset=offset, end=offset + length, n=count, step=step, time=time))
        offset += length
    return dict(frames=frames, nextOffset=offset, eof=offset == end)
