"""Local SSH profile discovery and installation for Structure Snapshot Saver."""
# Configuration
default_queue = "~/.local/share/structure-viewer/snapshot-queue.pyz"

import glob
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import zipfile


def settings_path() -> Path:
    return Path.home() / "Library/Application Support/Structure Viewer/connection.json"


def host_aliases(config: Path) -> list[str]:
    """Suggest literal Host aliases. OpenSSH itself resolves the selected host."""
    aliases: set[str] = set()
    visited: set[Path] = set()

    def read(path: Path) -> None:
        path = path.resolve()
        if path in visited or not path.is_file():
            return
        visited.add(path)
        for line in path.read_text().splitlines():
            if not re.match(r"^\s*(Host|Include)(?:\s|=)", line, re.IGNORECASE):
                continue
            tokens = shlex.split(line, comments=True)
            if not tokens:
                continue
            directive, _, value = tokens[0].partition("=")
            values = ([value] if value else []) + tokens[1:]
            if values[:1] == ["="]:
                values.pop(0)
            if directive.lower() == "host":
                aliases.update(item for item in values if re.fullmatch(r"[\w.][\w.-]*", item))
            if directive.lower() == "include":
                for item in values:
                    pattern = Path(item).expanduser()
                    if not pattern.is_absolute():
                        pattern = Path.home() / ".ssh" / pattern
                    for match in sorted(glob.glob(str(pattern))):
                        read(Path(match))
    read(config)
    return sorted(aliases)


def ssh_args(config: str, host: str) -> list[str]:
    path = Path(config).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError("请选择可读取的 SSH 配置文件")
    if not re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.-]*", host):
        raise ValueError("请输入 SSH Host 别名或主机名")
    return ["/usr/bin/ssh", "-F", str(path), "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2", host]


def queue_bundle(source: Path) -> bytes:
    """Ship the queue and its import dependency as one atomic, versioned unit."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.comment = b"Structure Viewer snapshot queue"
        bundle.write(source / "snapshot_queue.py", "__main__.py")
        bundle.write(source / "local_export.py", "local_export.py")
    return buffer.getvalue()


# Executed by the remote Python. Only replace an existing Structure Viewer bundle.
remote_install = """
import os, pathlib, sys, tempfile, zipfile
target = pathlib.Path(sys.argv[1]).expanduser()
if sys.version_info < (3, 9): raise ValueError("Python 3.9+ required")
if not target.is_absolute() or target.suffix != '.pyz': raise ValueError("absolute or ~/... .pyz path required")
target.parent.mkdir(parents=True, exist_ok=True)
if target.is_symlink(): raise ValueError("refusing to replace a symlink")
if target.exists():
    with zipfile.ZipFile(target) as old:
        if old.comment != b'Structure Viewer snapshot queue': raise ValueError("destination belongs to another file")
with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
    temp = pathlib.Path(output.name)
try:
    temp.write_bytes(sys.stdin.buffer.read())
    with zipfile.ZipFile(temp) as bundle:
        if bundle.testzip() or bundle.comment != b'Structure Viewer snapshot queue': raise ValueError("invalid queue bundle")
    temp.replace(target)
finally:
    if temp.exists(): temp.unlink()
print(target)
"""


def configure(request: dict, source: Path) -> dict:
    config = str(Path(request["config"]).expanduser())
    host = request["host"].strip()
    remote_path = request["queue"].strip()
    if not remote_path.startswith(("/", "~/")) or not remote_path.endswith(".pyz") or any(ord(c) < 32 for c in remote_path):
        raise ValueError("远程路径须以 / 或 ~/ 开头，以 .pyz 结尾")
    command = shlex.join(["python3", "-c", remote_install, remote_path])
    result = subprocess.run([*ssh_args(config, host), command], input=queue_bundle(source),
                            capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip() or "SSH 安装失败")
    lines = result.stdout.decode().splitlines()
    absolute = lines[-1] if lines else ""
    if not absolute.startswith("/"):
        raise ValueError("服务器未返回脚本的绝对路径")
    settings = {"host": host, "config": config, "queue": remote_path, "installed": absolute}
    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as temporary:
        json.dump(settings, temporary, ensure_ascii=False)
    Path(temporary.name).replace(target)
    return settings


def main() -> None:
    request = json.load(sys.stdin)
    if request["action"] == "aliases":
        config = Path(request["config"]).expanduser()
        if not config.is_file():
            raise ValueError("找不到 SSH 配置文件")
        result = host_aliases(config)
    elif request["action"] == "install":
        result = configure(request, Path(__file__).resolve().parent)
    else:
        raise ValueError("未知操作")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
