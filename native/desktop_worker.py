"""Shared viewer backend with desktop-only directory and bounded export transport."""
from __future__ import annotations

# Configuration
directory_scan_limit = 2000
directory_page_size = 200

from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor
import base64
import json
import os
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
import server
from trajectory import is_trajectory_index


def directory_page(arguments: dict[str, Any]) -> dict[str, Any]:
    path = Path(arguments.get("path") or "~").expanduser()
    if not path.is_absolute() or "archive" in path.parts or "archive" in path.resolve().parts or not path.is_dir():
        raise ValueError("请输入服务器上可读取目录的绝对路径")
    offset = int(arguments.get("offset", 0))
    if offset < 0 or offset >= directory_scan_limit:
        raise ValueError("目录页码超出范围")
    entries = []
    truncated = False
    with os.scandir(path) as listing:
        for index, entry in enumerate(listing):
            if index >= directory_scan_limit:
                truncated = True
                break
            if entry.name.startswith(".") or entry.name == "archive":
                continue
            try:
                directory = entry.is_dir()
                if directory or entry.is_file():
                    entries.append({"name": entry.name, "directory": directory,
                                    "path": str(path / entry.name)})
            except OSError:
                continue
    entries.sort(key=lambda item: (not item["directory"], item["name"].casefold()))
    return {"path": str(path), "parent": str(path.parent),
            "entries": entries[offset:offset + directory_page_size],
            "next": offset + directory_page_size if offset + directory_page_size < len(entries) else None,
            "truncated": truncated}


def export_read(arguments: dict[str, Any]) -> dict[str, Any]:
    job = server.media_exports.get(arguments)
    if server.media_exports.status(arguments)["state"] != "ready":
        raise ValueError("导出尚未完成")
    path = job["folder"] / job["name"]
    offset = int(arguments.get("offset", 0))
    if offset < 0 or offset > path.stat().st_size:
        raise ValueError("无效的导出读取位置")
    with path.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(1048576)
    return {"name": job["name"], "size": path.stat().st_size,
            "data": base64.b64encode(data).decode("ascii"), "next": offset + len(data)}


def dispatch(method: str, params: dict[str, Any]) -> dict[str, Any]:
    if method == "initialize":
        return {**server.dispatch(method, params), "atomLensConcurrentIndex": True}
    if method == "atomlens/list-directory":
        return directory_page(params)
    if method == "atomlens/export-read":
        return export_read(params)
    return server.dispatch(method, params)


def main() -> None:
    output_lock = threading.Lock()

    def reply(request: dict[str, Any]) -> None:
        try:
            response = {"result": dispatch(request["method"], request.get("params", {}))}
        except Exception as error:
            response = {"error": {"code": -32000, "message": str(error)}}
        line = json.dumps({"jsonrpc": "2.0", "id": request["id"], **response}, ensure_ascii=False)
        with output_lock:
            print(line, flush=True)

    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="trajectory-index") as indexer:
            for line in sys.stdin:
                try:
                    request = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(request, dict) or "id" not in request:
                    continue
                if is_trajectory_index(request.get("method"), request.get("params", {})):
                    indexer.submit(reply, request)
                else:
                    reply(request)
    finally:
        server.media_exports.close()


if __name__ == "__main__":
    main()
