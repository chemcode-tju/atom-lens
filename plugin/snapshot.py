"""Save explicitly requested snapshots beside the host-selected structure file."""
from pathlib import Path
from typing import Any
import base64
import re


def save_snapshot(params: dict[str, Any]) -> dict[str, Any]:
    host_path = params.get("_meta", {}).get("openai/resource", {}).get("path")
    if not isinstance(host_path, str) or not Path(host_path).is_absolute():
        raise ValueError("宿主没有提供结构文件路径，无法确定截图保存位置")
    arguments = params.get("arguments", {})
    name = arguments.get("name", "")
    if not isinstance(name, str) or not re.fullmatch(r"[\w .()\-]{1,100}\.(png|jpeg|pdf)", name) or name.startswith("."):
        raise ValueError("图片名称只能包含字母、数字、空格、下划线、圆括号和短横线")
    encoded = arguments.get("data", "")
    if not isinstance(encoded, str) or len(encoded) > 24 * 1048576:
        raise ValueError("截图超过 18 MiB 上限")
    data = base64.b64decode(encoded, validate=True)
    signatures = {".png": b"\x89PNG\r\n\x1a\n", ".jpeg": b"\xff\xd8\xff", ".pdf": b"%PDF-"}
    if not data.startswith(signatures[Path(name).suffix]):
        raise ValueError("图片内容与扩展名不符")
    parent = Path(host_path).resolve().parent
    directory = parent / "structure-snapshots"
    if directory.is_symlink():
        raise ValueError("截图目录不能是符号链接")
    directory.mkdir(exist_ok=True)
    for number in range(10000):
        target = directory / (name if number == 0 else f"{Path(name).stem}-{number}{Path(name).suffix}")
        try:
            with target.open("xb") as stream:
                stream.write(data)
            return {"path": str(target), "bytes": len(data)}
        except FileExistsError:
            continue
    raise ValueError("同名图片过多，请使用其他文件名")
