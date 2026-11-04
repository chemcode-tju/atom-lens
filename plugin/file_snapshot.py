"""Bounded, append-tolerant file views; keep hashes, never full trajectories."""
from __future__ import annotations

# Configuration
block_size = 262144
maximum_snapshots = 256

from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator
import hashlib
import io
import os
import secrets
import stat


class IncompleteFrame(ValueError):
    """The fixed read boundary cuts a frame that has not finished writing."""


class FileSnapshot:
    """Freeze a byte boundary and verify blocks again when they are revisited.

    Assumes writers append. Blocks not yet visited cannot be proven unchanged
    without copying/scanning the whole file up front. Indexed blocks are hashed.
    """

    def __init__(self, path: Path, info: Any) -> None:
        self.path = path
        self.size = info.st_size
        self.identity = (info.st_dev, info.st_ino)
        self.modified = (info.st_mtime_ns, info.st_ctime_ns)
        self.hashes: dict[int, bytes] = {}
        self.version = f"snapshot:{secrets.token_urlsafe(24)}"
        self.invalid = False

    def validate(self, info: Any) -> None:
        changed = (info.st_mtime_ns, info.st_ctime_ns) != self.modified
        if (self.invalid or (info.st_dev, info.st_ino) != self.identity
                or info.st_size < self.size or (info.st_size == self.size and changed)):
            self.invalid = True
            raise ValueError("文件已改变（替换、截短或改写）；请重新打开。")

    def block(self, stream: BinaryIO, start: int) -> bytes:
        stream.seek(start)
        data = stream.read(min(block_size, self.size - start))
        digest = hashlib.sha256(data).digest()
        previous = self.hashes.setdefault(start, digest)
        if len(data) != min(block_size, self.size - start) or digest != previous:
            self.invalid = True
            raise ValueError("已读取的文件内容已改变；请重新打开。")
        return data


class SnapshotReader(io.RawIOBase):
    """Seekable raw reader capped at the opening size, even while appending."""

    def __init__(self, stream: BinaryIO, snapshot: FileSnapshot) -> None:
        self.stream = stream
        self.snapshot = snapshot
        self.position = 0
        self.block_start = -1
        self.data = b""

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        position = offset + (self.position if whence == 1 else self.snapshot.size if whence == 2 else 0)
        if whence not in (0, 1, 2) or position < 0:
            raise ValueError("无效文件偏移。")
        self.position = position
        return position

    def readinto(self, output: Any) -> int:
        if self.position >= self.snapshot.size:
            return 0
        start = self.position // block_size * block_size
        if start != self.block_start:
            self.data = self.snapshot.block(self.stream, start)
            self.block_start = start
        begin = self.position - start
        count = min(len(output), len(self.data) - begin)
        output[:count] = self.data[begin:begin + count]
        self.position += count
        return count


_snapshots: OrderedDict[str, FileSnapshot] = OrderedDict()


def is_snapshot(version: str | None) -> bool:
    return isinstance(version, str) and version.startswith("snapshot:")


@contextmanager
def open_snapshot(path: Path, version: str | None = None) -> Iterator[tuple[BinaryIO, FileSnapshot]]:
    """Open a stable prefix, with an opaque session token bound to its path."""
    path = path.resolve()
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as physical:
        info = os.fstat(physical.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("只能读取普通结构文件。")
        if version is None:
            snapshot = FileSnapshot(path, info)
            _snapshots[snapshot.version] = snapshot
            while len(_snapshots) > maximum_snapshots:
                _snapshots.popitem(last=False)
        else:
            snapshot = _snapshots.get(version)
            if snapshot is None or snapshot.path != path:
                raise ValueError("文件读取会话已改变或失效；请重新打开。")
            _snapshots.move_to_end(version)
        snapshot.validate(info)
        snapshot.validate(path.stat())
        # Pin the boundary; hash interior blocks as indexing visits them.
        if snapshot.size:
            snapshot.block(physical, 0)
            snapshot.block(physical, (snapshot.size - 1) // block_size * block_size)
        with io.BufferedReader(SnapshotReader(physical, snapshot), buffer_size=65536) as stream:
            yield stream, snapshot
        snapshot.validate(os.fstat(physical.fileno()))
        snapshot.validate(path.stat())
