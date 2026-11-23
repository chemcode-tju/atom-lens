"""Install the Codex plugin on a Mac or Linux server, without pip or sudo."""
from __future__ import annotations

# Configuration
codex_executable = ""

from pathlib import Path
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile


def codex_candidates(home: Path) -> list[Path]:
    """Find the CLI, including desktop bundles and remote Codex installations."""
    candidates = [Path(codex_executable).expanduser()] if codex_executable else []
    if executable := shutil.which("codex"):
        candidates.append(Path(executable))
    for applications in (Path("/Applications"), Path.home() / "Applications"):
        for app in ("ChatGPT.app", "Codex.app"):
            resources = applications / app / "Contents/Resources"
            candidates.extend([resources / "codex-cli/bin/codex", resources / "codex"])
    remote = [home / "bin/codex", *home.glob("bin/*/codex")]
    candidates.extend(sorted((path for path in remote if path.is_file()),
                             key=lambda path: path.stat().st_mtime, reverse=True))
    return list(dict.fromkeys(candidates))


def find_codex(home: Path) -> Path:
    for candidate in codex_candidates(home):
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        try:
            result = subprocess.run([str(candidate), "plugin", "add", "--help"],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode == 0:
                return candidate.absolute()
        except (OSError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError("找不到支持插件安装的 Codex CLI。请先更新 Codex；服务器上先连接一次 Codex 远程聊天。\n"
                       "如果 CLI 在其他目录，在 install.py 顶部的 codex_executable 填入其完整路径。")


def prepare_package(source: Path, staged: Path, python: Path) -> None:
    """Copy runtime files and bind this host's interpreter in the installed copy."""
    shutil.copytree(source / "plugin", staged / "plugin",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    catalog = staged / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    shutil.copy2(source / ".agents/plugins/marketplace.json", catalog)
    config_path = staged / "plugin/.mcp.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    server = config["mcpServers"]["structure-viewer"]
    server["command"] = str(python)
    if "-B" not in server["args"]:
        server["args"].insert(0, "-B")
    environment = server.setdefault("env", {})
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in ("STRUCTURE_VIEWER_ASE_PYTHON", "STRUCTURE_VIEWER_MDA_PYTHON",
                "STRUCTURE_VIEWER_GMX", "STRUCTURE_VIEWER_FFMPEG", "GMXLIB"):
        if os.environ.get(key):
            environment[key] = os.environ[key]
    for key, program in (("STRUCTURE_VIEWER_FFMPEG", "ffmpeg"), ("STRUCTURE_VIEWER_GMX", "gmx")):
        if key not in environment and (executable := shutil.which(program)):
            environment[key] = executable
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (staged / ".structure-viewer-managed").write_text("1\n", encoding="utf-8")


def check_server(package: Path, python: Path) -> None:
    """Check MCP discovery and the complete UI before changing an existing installation."""
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "resources/read",
         "params": {"uri": "ui://structure-viewer/editor.html"}},
    ]
    environment = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([str(python), "-B", str(package / "plugin/server.py")], env=environment,
                            input="".join(json.dumps(item) + "\n" for item in requests),
                            text=True, encoding="utf-8", capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError(f"插件自检失败：{result.stderr.strip()}")
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    if len(replies) != 3 or any("error" in item for item in replies):
        raise RuntimeError("插件自检失败：MCP 服务或界面资源未能完整加载。")
    if "open_structure_path" not in {item["name"] for item in replies[1]["result"]["tools"]}:
        raise RuntimeError("插件缺少结构打开入口。")
    if "/*__" in replies[2]["result"]["contents"][0]["text"]:
        raise RuntimeError("插件界面资源不完整，请重新下载完整仓库。")


def run_codex(codex: Path, home: Path, arguments: list[str]) -> str:
    result = subprocess.run([str(codex), *arguments],
                            env={**os.environ, "CODEX_HOME": str(home)},
                            text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f"Codex 注册失败：{result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def previous_marketplace(codex: Path, home: Path, package: Path) -> str | None:
    """Allow migration only from a local marketplace containing this single plugin."""
    listing = json.loads(run_codex(codex, home, ["plugin", "marketplace", "list", "--json"]))
    for entry in listing["marketplaces"]:
        if entry["name"] != "atomic-structure-tools" or Path(entry["root"]) == package:
            continue
        source = entry.get("marketplaceSource") or {}
        if source.get("sourceType") == "local":
            catalog = Path(entry["root"]) / ".agents/plugins/marketplace.json"
            data = json.loads(catalog.read_text(encoding="utf-8"))
            if [item["name"] for item in data["plugins"]] == ["structure-viewer"]:
                return source["source"]
        raise RuntimeError("已有同名市场包含其他来源或插件，未自动替换。请先检查 atomic-structure-tools 市场。")
    return None


def register_plugin(codex: Path, package: Path, home: Path) -> None:
    previous = previous_marketplace(codex, home, package)
    if previous:
        run_codex(codex, home, ["plugin", "marketplace", "remove", "atomic-structure-tools"])
    try:
        run_codex(codex, home, ["plugin", "marketplace", "add", str(package)])
        run_codex(codex, home, ["plugin", "add", "structure-viewer@atomic-structure-tools"])
    except Exception:
        if previous:
            try:
                run_codex(codex, home, ["plugin", "marketplace", "remove", "atomic-structure-tools"])
                run_codex(codex, home, ["plugin", "marketplace", "add", previous])
                run_codex(codex, home, ["plugin", "add", "structure-viewer@atomic-structure-tools"])
            except (RuntimeError, subprocess.SubprocessError) as error:
                print(f"旧市场自动恢复未完成，请从原源码目录重新安装：{error}", file=sys.stderr)
        raise


def install(source: Path, codex: Path, home: Path, python: Path) -> Path:
    """Replace only an installer-owned package; restore its previous files on failure."""
    home.mkdir(parents=True, exist_ok=True)
    target = home / "structure-viewer-source"
    if target.is_symlink() or (target.exists() and not (target / ".structure-viewer-managed").is_file()):
        raise RuntimeError(f"安装位置已有非本安装器管理的内容，未修改：{target}")
    with tempfile.TemporaryDirectory(prefix=".structure-viewer-install-", dir=home) as temporary:
        staged = Path(temporary) / "package"
        backup = Path(temporary) / "previous"
        prepare_package(source, staged, python)
        check_server(staged, python)
        if target.exists():
            target.rename(backup)
        try:
            staged.rename(target)
            register_plugin(codex, target, home)
        except Exception:
            if target.exists():
                target.rename(staged)
            if backup.exists():
                backup.rename(target)
            # The CLI may already have registered the marketplace. Retrying is safe;
            # never rewrite the user's complete Codex configuration as a rollback.
            raise
    return target


def main() -> None:
    if platform.system() not in {"Darwin", "Linux"}:
        raise RuntimeError("本版本支持 Mac 桌面与 Linux 服务器上的 Codex 插件安装。")
    if sys.version_info < (3, 9):
        raise RuntimeError("需要 Python 3.9 或更新版本。")
    source = Path(__file__).resolve().parent
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().absolute()
    # Preserve virtualenv symlinks: resolve() would discard that environment.
    python = Path(sys.executable).absolute()
    codex = find_codex(home)
    print(f"Atom Lens 安装\nPython：{python}\nCodex：{codex}", flush=True)
    target = install(source, codex, home, python)
    print(f"\n安装完成：{target}\n请重新打开查看器；远程使用时重新连接对应的 Codex 聊天。")
    print("可以对 Codex 说：请用 Atom Lens 打开结构文件，文件路径是……")
    print("基础查看无需额外 Python 包；可选格式和动画依赖见 README。")
    if platform.system() == "Darwin":
        print("远程导出到 Mac 可另装保存助手：python3 native/install_helper.py")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"\n安装未完成：{error}", file=sys.stderr)
        sys.exit(1)
