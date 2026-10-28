"""User-directed snapshot destinations; structure files remain read-only."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import base64
import platform
import re
import socket
import subprocess
import shutil
import tempfile


def snapshot_context(params: dict[str, Any]) -> dict[str, Any]:
    """Describe the plugin host separately from the Mac rendering the view."""
    host_path = params.get("_meta", {}).get("openai/resource", {}).get("path")
    directory = str(Path(host_path).resolve().parent) if isinstance(host_path, str) and Path(host_path).is_absolute() else ""
    return {"host": socket.gethostname(), "nativePicker": platform.system() == "Darwin", "directory": directory}


def choose_mac_directory(default_directory: str) -> Path | None:
    """Use the macOS folder chooser; pass paths as arguments, never script text."""
    default = Path(default_directory) if default_directory else Path.home() / "Documents"
    if not default.is_dir():
        default = Path.home()
    script = '''on run argv
try
    set chosenFolder to choose folder with prompt "保存结构快照到…" default location (POSIX file (item 1 of argv))
    return POSIX path of chosenFolder
on error number -128
    return ""
end try
end run'''
    result = subprocess.run(["/usr/bin/osascript", "-e", script, str(default)], capture_output=True, text=True, timeout=600, check=False)
    if result.returncode:
        raise ValueError(f"无法打开 Mac 保存窗口：{result.stderr.strip()}")
    return Path(result.stdout.strip()) if result.stdout.strip() else None


def validate_name(name: str) -> None:
    if not isinstance(name, str) or not re.fullmatch(r"[\w .()\-]{1,100}\.(png|jpeg|pdf|gif|mov|mp4)", name) or name.startswith("."):
        raise ValueError("文件名称只能包含字母、数字、空格、下划线、圆括号和短横线")


def validate_file(path: Path, name: str) -> None:
    validate_name(name)
    with path.open("rb") as stream:
        header = stream.read(16)
    suffix = Path(name).suffix
    signatures = {".png": b"\x89PNG\r\n\x1a\n", ".jpeg": b"\xff\xd8\xff", ".pdf": b"%PDF-", ".gif": b"GIF8"}
    valid = header.startswith(signatures[suffix]) if suffix in signatures else header[4:8] == b"ftyp"
    if not valid:
        raise ValueError("文件内容与扩展名不符")


def save_file(source: Path, name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Save a staged export without copying the complete file into memory."""
    validate_file(source, name)
    arguments = params.get("arguments", {})
    context = snapshot_context(params)
    destination = arguments.get("destination", "server")
    if destination == "native":
        if not context["nativePicker"]:
            raise ValueError("服务器不能打开 Mac 文件夹窗口，请选择保存到本地 Mac")
        directory = choose_mac_directory(context["directory"])
        if directory is None:
            return {"cancelled": True}
    elif destination == "server":
        value = arguments.get("directory") or context["directory"]
        if not isinstance(value, str) or not value or not Path(value).expanduser().is_absolute():
            raise ValueError("请指定保存目录的完整绝对路径")
        directory = Path(value).expanduser()
    else:
        raise ValueError("未知的快照保存位置")
    if not directory.is_dir():
        raise ValueError(f"保存目录不存在：{directory}")
    # Exclusive creation avoids overwriting a structure, previous image or symlink.
    for number in range(10000):
        target = directory / (name if number == 0 else f"{Path(name).stem}-{number}{Path(name).suffix}")
        try:
            with target.open("xb") as stream:
                with source.open("rb") as incoming:
                    shutil.copyfileobj(incoming, stream, length=1024 * 1024)
            return {"path": str(target), "bytes": target.stat().st_size}
        except FileExistsError:
            continue
    raise ValueError("同名图片过多，请使用其他文件名")


def save_snapshot(params: dict[str, Any]) -> dict[str, Any]:
    """Compatibility route for earlier viewers; current exports use chunked uploads."""
    arguments = params.get("arguments", {})
    name = arguments.get("name", "")
    validate_name(name)
    with tempfile.TemporaryDirectory(prefix="structure-snapshot-") as temporary:
        source = Path(temporary) / name
        source.write_bytes(base64.b64decode(arguments.get("data", ""), validate=True))
        return save_file(source, name, params)
