"""Read complete VASP frames progressively without a total-file size limit."""
from typing import Any, BinaryIO


def required_line(stream: BinaryIO) -> bytes:
    line = stream.readline()
    if not line:
        raise ValueError("VASP 结构帧不完整，请等待文件写入完成后重新打开。")
    return line


def read_vasp_batch(stream: BinaryIO, offset: int, frame_limit: int, trajectory: bool) -> dict[str, Any]:
    """Repeat the small header in each batch so the browser can reuse its VASP parser."""
    stream.seek(0)
    header = [required_line(stream) for _ in range(7)]
    try:
        counts = [int(value) for value in header[6].split()]
    except ValueError as error:
        raise ValueError("VASP 元素计数无效；需要含元素名的 VASP 5/6 文件。") from error
    if not counts or any(count < 0 for count in counts) or sum(counts) < 1:
        raise ValueError("VASP 元素计数无效。")
    atom_count = sum(counts)
    first_mode = required_line(stream)
    if first_mode.strip().lower().startswith(b"s"):
        header.append(first_mode)
        first_mode = required_line(stream)
    trajectory = trajectory or b"configuration" in first_mode.lower()
    if offset:
        stream.seek(offset)
    else:
        stream.seek(stream.tell() - len(first_mode))
    frames: list[bytes] = []
    size = 0
    while len(frames) < frame_limit and size < 262144:
        mode = stream.readline()
        while mode and not mode.strip():
            mode = stream.readline()
        if not mode:
            break
        if mode.strip()[:1].lower() not in {b"d", b"c", b"k"}:
            raise ValueError("无法识别 VASP 坐标模式；XDATCAR 当前需要固定晶胞。")
        rows = [mode]
        for _ in range(atom_count):
            line = required_line(stream)
            if len(line.split()) < 3:
                raise ValueError("VASP 结构帧坐标不完整。")
            rows.append(line)
        frame = b"".join(rows)
        if not frame.endswith(b"\n"):
            frame += b"\n"
        frames.append(frame)
        size += len(frame)
        if not trajectory:
            # A POSCAR may contain velocities after its one structure frame.
            stream.seek(0, 2)
            break
    return {"supported": True, "format": "vasp",
            "text": (b"".join(header + frames).decode("utf-8") if frames else ""),
            "frameCount": len(frames), "nextOffset": stream.tell()}
