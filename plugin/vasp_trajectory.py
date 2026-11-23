"""Read complete VASP frames progressively without a total-file size limit."""
from typing import Any, BinaryIO
from file_snapshot import IncompleteFrame


def required_line(stream: BinaryIO) -> bytes:
    line = stream.readline()
    if not line:
        raise IncompleteFrame("VASP 结构帧不完整，请等待文件写入完成后重新打开。")
    return line


def read_header(stream: BinaryIO, offset: int) -> tuple[list[bytes], int, bytes, int]:
    stream.seek(offset)
    header = [required_line(stream) for _ in range(7)]
    try:
        counts = [int(value) for value in header[6].split()]
    except ValueError as error:
        raise ValueError("VASP 元素计数无效；需要含元素名的 VASP 5/6 文件。") from error
    if not counts or min(counts) < 0 or not 1 <= sum(counts) <= 1000000:
        raise ValueError("VASP 元素计数无效。")
    mode = required_line(stream)
    if mode.strip().lower().startswith(b"s"):
        header.append(mode)
        mode = required_line(stream)
    return header, sum(counts), mode, stream.tell() - len(mode)


def read_vasp_batch(stream: BinaryIO, offset: int, frame_limit: int, trajectory: bool,
                    index_only: bool = False, header_offset: int = 0, frozen: bool = False) -> dict[str, Any]:
    """Keep the offset of each frame's cell header for random access."""
    if type(header_offset) is not int or not 0 <= header_offset <= offset:
        raise ValueError("无效文件偏移。")
    header, atom_count, first_mode, first_position = read_header(stream, header_offset)
    trajectory = trajectory or b"configuration" in first_mode.lower()
    stream.seek(offset or first_position)
    header_offsets: list[int] = []
    frames: list[bytes] = []
    offsets: list[int] = []
    size = 0
    # Larger idle batches amortize SSH round trips. Playing clients request
    # at most 16 index entries and keep each background read short.
    byte_budget = (2 if frame_limit <= 16 else 32) * 1048576 if index_only else 262144
    while len(offsets) < frame_limit and size < byte_budget:
        start = stream.tell()
        try:
            mode = stream.readline()
            while mode and not mode.strip():
                mode = stream.readline()
            if not mode:
                break
            mode_offset = stream.tell() - len(mode)
            word = mode.strip().lower().split()[0]
            if trajectory and mode_offset != first_position and word not in {b"direct", b"cartesian", b"d", b"c", b"k", b"kartesian"}:
                # A data batch has one header. End it before the cell changes.
                if frames:
                    stream.seek(mode_offset)
                    break
                header_offset = mode_offset
                try:
                    header, atom_count, mode, first_position = read_header(stream, header_offset)
                except IncompleteFrame:
                    raise
                except ValueError as error:
                    raise ValueError("无法识别 VASP 坐标模式或轨迹头部") from error
                start = first_position
            if mode.strip()[:1].lower() not in {b"d", b"c", b"k"}:
                raise ValueError("无法识别 VASP 坐标模式")
            rows = [] if index_only else [mode]
            frame_size = len(mode)
            for _ in range(atom_count):
                line = required_line(stream)
                if len(line.split(None, 3)) < 3:
                    if line.endswith(b"\n"):
                        raise ValueError("VASP 结构帧坐标不完整。")
                    raise IncompleteFrame("VASP 结构帧坐标不完整。")
                frame_size += len(line)
                if not index_only:
                    rows.append(line)
        except IncompleteFrame:
            if not frozen:
                raise
            stream.seek(0, 2)
            break
        header_offsets.append(header_offset)
        offsets.append(start)
        if not index_only:
            frame = b"".join(rows)
            if not frame.endswith(b"\n"):
                frame += b"\n"
            frames.append(frame)
        size += frame_size
        if not trajectory:
            # A POSCAR may contain velocities after its one structure frame.
            stream.seek(0, 2)
            break
    return {"supported": True, "format": "vasp",
            "text": (b"".join(header + frames).decode("utf-8") if frames else ""),
            "frameCount": len(offsets), "offsets": offsets, "headerOffsets": header_offsets, "nextOffset": stream.tell()}
