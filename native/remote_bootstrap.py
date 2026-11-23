"""Read one installation request from stdin; use only the user's managed backend."""
from __future__ import annotations

# Configuration
backend_directory = "~/.local/share/atom-lens/backend"

from pathlib import Path
import base64
import hashlib
import importlib.util
import io
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile


def find_codex() -> str:
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    candidates = [shutil.which("codex"), str(home / "bin/codex")]
    candidates.extend(str(path) for path in home.glob("bin/*/codex"))
    if platform.system() == "Darwin":
        for directory in (Path("/Applications"), Path.home() / "Applications"):
            for name in ("Codex.app", "ChatGPT.app"):
                resources = directory / name / "Contents/Resources"
                candidates.extend(str(resources / name) for name in ("codex-cli/bin/codex", "codex"))
    for executable in dict.fromkeys(candidates):
        if not executable or not Path(executable).is_file():
            continue
        try:
            result = subprocess.run([executable, "plugin", "add", "--help"], capture_output=True, timeout=10)
            if result.returncode == 0:
                return executable
        except (OSError, subprocess.TimeoutExpired):
            continue
    return ""


def codex_plugin_installed(executable: str) -> bool | None:
    """Read the current registry. An unavailable CLI is an unknown result."""
    if not executable:
        return None
    try:
        result = subprocess.run([executable, "plugin", "list", "--marketplace", "atomic-structure-tools", "--json"],
                                capture_output=True, text=True, timeout=8, check=True)
        installed = json.loads(result.stdout)["installed"]
        if not isinstance(installed, list):
            return None
        return any(item.get("pluginId") == "structure-viewer@atomic-structure-tools" for item in installed)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        return None


def check() -> dict:
    target = Path(backend_directory).expanduser()
    version = ""
    manifest = target / "plugin/.codex-plugin/plugin.json"
    if (target / ".atom-lens-managed").is_file() and manifest.is_file():
        version = json.loads(manifest.read_text())["version"]
    reader = target / "plugin/md_import.py"
    codex = find_codex()
    return {"python": sys.executable, "pythonVersion": platform.python_version(),
            "system": platform.system(), "architecture": platform.machine(),
            "codex": codex, "codexInstalled": codex_plugin_installed(codex), "backend": str(target), "version": version,
            "trajectoryReaderHash": hashlib.sha256(reader.read_bytes()).hexdigest() if version and reader.is_file() else ""}


def unpack(request: dict, destination: Path) -> None:
    payload = base64.b64decode(request["bundle"], validate=True)
    if len(payload) > 32 * 1048576 or hashlib.sha256(payload).hexdigest() != request["sha256"]:
        raise ValueError("安装包校验失败")
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        total = 0
        for entry in bundle.infolist():
            path = Path(entry.filename)
            total += entry.file_size
            if path.is_absolute() or ".." in path.parts or "archive" in path.parts or total > 128 * 1048576:
                raise ValueError("无效的安装包路径或大小")
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("安装包不能包含符号链接")
        bundle.extractall(destination)


def install(request: dict) -> dict:
    target = Path(backend_directory).expanduser()
    if target.is_symlink() or (target.exists() and not (target / ".atom-lens-managed").is_file()):
        raise ValueError(f"目录已有非本应用管理的内容，未修改：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=target.parent) as temporary:
        staged = Path(temporary) / "package"
        staged.mkdir()
        unpack(request, staged)
        spec = importlib.util.spec_from_file_location("atomlens_installer", staged / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.check_server(staged, Path(sys.executable))
        codex = installer.find_codex(Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")) if request.get("codex") else None
        (staged / ".atom-lens-managed").write_text("1\n")
        backup = Path(temporary) / "previous"
        if target.exists():
            target.rename(backup)
        try:
            staged.rename(target)
            if codex:
                home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
                installer.install(target, codex, home, Path(sys.executable))
        except Exception:
            target.rename(staged)
            if backup.exists():
                backup.rename(target)
            raise
    result = check()
    if codex:
        result["codexInstalled"] = True
    return result


def main() -> None:
    if sys.version_info < (3, 9):
        raise RuntimeError("服务器需要 Python 3.9+；可在连接设置中指定已有 Python 的绝对路径")
    request = json.load(sys.stdin)
    if request.get("action") == "check":
        result = check()
    elif request.get("action") == "install":
        result = install(request)
    else:
        raise ValueError("未知安装操作")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
