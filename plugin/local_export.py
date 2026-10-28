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
    from snapshot import validate_name
    import tempfile
    validate_name(name)
    with tempfile.TemporaryDirectory(prefix="structure-stage-") as temporary:
        path = Path(temporary) / name
        path.write_bytes(base64.b64decode(encoded, validate=True))
        return prepare_local_file(path, name)


def prepare_local_file(path: Path, name: str) -> dict[str, str]:
    from snapshot import validate_file
    validate_file(path, name)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
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
