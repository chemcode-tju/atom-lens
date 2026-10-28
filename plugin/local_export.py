"""Private snapshot queue shared by the viewer and the user's Mac helper."""
from pathlib import Path
from typing import Any
import base64
import json
import os
import re
import time
import uuid


def export_folder() -> Path:
    folder = Path.home() / ".cache/structure-viewer/exports"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def helper_connected(folder: Path) -> bool:
    try:
        return time.time() - (folder / "helper-heartbeat").stat().st_mtime < 15
    except FileNotFoundError:
        return False


def prepare_local_snapshot(arguments: dict[str, Any]) -> dict[str, str]:
    name, encoded = arguments.get("name", ""), arguments.get("data", "")
    if not isinstance(name, str) or not re.fullmatch(r"[\w .()\-]{1,100}\.(png|jpeg|pdf)", name) or name.startswith("."):
        raise ValueError("无效图片文件名")
    if not isinstance(encoded, str) or len(encoded) > 24 * 1048576:
        raise ValueError("截图超过 18 MiB 上限")
    data = base64.b64decode(encoded, validate=True)
    signatures = {".png": b"\x89PNG\r\n\x1a\n", ".jpeg": b"\xff\xd8\xff", ".pdf": b"%PDF-"}
    if not data.startswith(signatures[Path(name).suffix]):
        raise ValueError("图片内容与格式不符")
    folder = export_folder()
    if not helper_connected(folder):
        raise ValueError("Mac 保存助手未连接，请在 Mac 打开 Structure Snapshot Saver 后重试")
    for path in folder.iterdir():
        if re.fullmatch(r"[0-9a-f-]{36}\.(json|request|claimed|status)", path.name) and path.lstat().st_mtime < time.time() - 86400:
            path.unlink()
    identifier = str(uuid.uuid4())
    target = folder / f"{identifier}.json"
    with target.open("x") as stream:
        os.chmod(target, 0o600)
        json.dump({"id": identifier, "name": name, "data": encoded}, stream)
    (folder / f"{identifier}.status").write_text("pending")
    (folder / f"{identifier}.request").touch()
    return {"id": identifier}


def snapshot_save_status(arguments: dict[str, Any]) -> dict[str, str]:
    identifier = str(uuid.UUID(arguments.get("id", "")))
    folder = export_folder()
    path = folder / f"{identifier}.status"
    if not path.is_file():
        raise ValueError("快照请求不存在或已过期")
    status = path.read_text()
    if status in {"pending", "choosing"} and not helper_connected(folder):
        status = "disconnected"
    return {"status": status}
