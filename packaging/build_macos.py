"""Build the standalone Mac viewer with optional local and remote Codex plugins."""
from __future__ import annotations

# Configuration
target_architecture = "arm64"
preview_revision = 12
python_download_url = "https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.11.18%2B20261026-aarch64-apple-darwin-install_only_stripped.tar.gz"
python_sha256 = "f3e1cd83a7f1d70e58b0d69102c18bd6867d2f973068dc5cbfd5822e445c66df"
signing_identity = "-"

from pathlib import Path
import hashlib
import json
import os
import platform
import plistlib
import posixpath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def runtime_archive(cache: Path) -> Path:
    """Download the pinned official archive and verify it before extraction."""
    archive = cache / f"python-macos-{target_architecture}.tar.gz"
    if not archive.exists():
        pending = archive.with_suffix(".download")
        with urllib.request.urlopen(python_download_url, timeout=120) as source, pending.open("wb") as output:
            shutil.copyfileobj(source, output)
        pending.rename(archive)
    with archive.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    if digest.hexdigest() != python_sha256:
        raise ValueError(f"Python archive checksum mismatch; remove and download again: {archive}")
    return archive


def extract_runtime(archive: Path, resources: Path) -> None:
    """Keep the official runtime, shared libraries and their included license texts."""
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if not member.name.startswith("python/") or ".." in Path(member.name).parts:
                raise ValueError(f"Unexpected archive path: {member.name}")
            if member.issym() or member.islnk():
                parent = posixpath.dirname(member.name) if member.issym() else ""
                target = posixpath.normpath(posixpath.join(parent, member.linkname))
                if not target.startswith("python/"):
                    raise ValueError(f"Unexpected archive link: {member.name}")
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise ValueError(f"Unsupported archive entry: {member.name}")
        bundle.extractall(resources)


def create_icon(image: Path, small_image: Path, contents: Path, staging: Path) -> None:
    """Use heavier atom orbits at 16/32 pt so the icon survives downsampling."""
    iconset = staging / "AtomLens.iconset"
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            suffix = "@2x" if scale == 2 else ""
            destination = iconset / f"icon_{size}x{size}{suffix}.png"
            source = small_image if size <= 32 else image
            subprocess.run(["sips", "-z", str(size * scale), str(size * scale), str(source),
                            "--out", str(destination)], stdout=subprocess.DEVNULL, check=True)
    run(["iconutil", "-c", "icns", str(iconset), "-o", str(contents / "Resources/AtomLens.icns")])


def compile_program(source: Path, destination: Path, extra_framework: str = "") -> None:
    command = ["xcrun", "clang", "-arch", target_architecture, "-mmacosx-version-min=12.0",
               "-fobjc-arc", "-fblocks", str(source), "-o", str(destination), "-framework", "Cocoa"]
    if extra_framework:
        command.extend(["-framework", extra_framework])
    run(command)


def populate_app(root: Path, app: Path, archive: Path, staging: Path) -> None:
    contents = app / "Contents"
    resources = contents / "Resources"
    (contents / "MacOS").mkdir(parents=True)
    resources.mkdir()
    extract_runtime(archive, resources)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "archive")
    shutil.copytree(root / "plugin", resources / "plugin", ignore=ignore)
    catalog = resources / ".agents/plugins/marketplace.json"
    catalog.parent.mkdir(parents=True)
    shutil.copy2(root / ".agents/plugins/marketplace.json", catalog)
    shutil.copy2(root / "install.py", resources / "install.py")
    shutil.copy2(root / "LICENSE", resources / "LICENSE")
    native = resources / "native"
    native.mkdir()
    for filename in ("install_helper.py", "connection.py", "broker.py", "desktop_host.py", "desktop_backend.py",
                     "desktop_worker.py", "desktop_profiles.py", "remote_bootstrap.py", "desktop.html"):
        shutil.copy2(root / "native" / filename, native / filename)
    (resources / "examples").mkdir()
    shutil.copy2(root / "examples/water.xyz", resources / "examples/water.xyz")
    run(["xcrun", "clang", "-arch", target_architecture, "-mmacosx-version-min=12.0", "-fobjc-arc", "-fblocks",
         str(root / "native/Desktop.m"), str(root / "native/Installer.m"), "-o", str(contents / "MacOS/AtomLens"),
         "-framework", "Cocoa", "-framework", "WebKit"])
    compile_program(root / "native/SnapshotSaver.m", native / "SnapshotSaver", "UniformTypeIdentifiers")
    create_icon(root / "design/app-icon.png", root / "design/app-icon-small.png", contents, staging)
    manifest = json.loads((root / "plugin/.codex-plugin/plugin.json").read_text())
    info = {"CFBundleName": "Atom Lens", "CFBundleDisplayName": "Atom Lens",
            "CFBundleIdentifier": "org.atom-lens.installer", "CFBundleExecutable": "AtomLens",
            "CFBundlePackageType": "APPL", "CFBundleShortVersionString": manifest["version"],
            "CFBundleVersion": manifest["version"], "AtomLensPreviewRevision": preview_revision,
            "CFBundleIconFile": "AtomLens",
            "LSMinimumSystemVersion": "12.0", "NSHighResolutionCapable": True,
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
            "CFBundleDocumentTypes": [{"CFBundleTypeName": "Atomic structures", "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate", "CFBundleTypeExtensions": ["xyz", "extxyz", "traj", "vasp", "gro", "lammpstrj", "dump", "trr", "xtc", "cif", "pdb", "svtraj"]}]}
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    (resources / "RUNTIME-NOTICE.txt").write_text(
        f"Atom Lens preview revision: {preview_revision}\n"
        f"Python runtime: python-build-standalone (Astral)\n{python_download_url}\n"
        f"SHA256: {python_sha256}\nAll bundled Python licenses are retained under python/.\n"
        "Atom Lens: MIT (LICENSE). 3Dmol: plugin/web/vendor/LICENSE-3Dmol.txt.\n"
        "Mol* XTC decoder: MIT (plugin/web/vendor/LICENSE-Molstar.txt).\n",
        encoding="utf-8")
    # Check the actual bundled resources before producing a distributable artifact.
    probe = f"import sys; sys.path.insert(0, {str(native)!r}); from desktop_backend import runtime_bundle; runtime_bundle()"
    run([str(resources / "python/bin/python3"), "-I", "-B", "-c", probe])
    # Ad-hoc signing is for local review. Distribution signing/notarization is a separate release step.
    run(["codesign", "--force", "--deep", "--sign", signing_identity, str(app)])
    run(["codesign", "--verify", "--deep", "--strict", str(app)])


def main() -> None:
    if platform.system() != "Darwin" or platform.machine() != target_architecture:
        raise SystemExit("Build this package on a Mac matching the configured runtime architecture.")
    root = Path(__file__).resolve().parents[1]
    output = root / "dist" / f"macos-{target_architecture}"
    output.mkdir(parents=True, exist_ok=True)
    cache = root / "dist/build-cache"
    cache.mkdir(parents=True, exist_ok=True)
    archive = runtime_archive(cache)
    with tempfile.TemporaryDirectory(prefix="atomlens-build-", dir=output) as temporary:
        staging = Path(temporary)
        image_root = staging / "image"
        image_root.mkdir()
        app = image_root / "Atom Lens.app"
        populate_app(root, app, archive, staging)
        (image_root / "Applications").symlink_to("/Applications")
        (image_root / "安装说明.txt").write_text(
            "1. 将 Atom Lens 拖到 Applications。\n2. 从 Applications 打开 Atom Lens。\n"
            "3. 在查看器顶部的服务器图标中打开本地文件或连接服务器。\n"
            "可选：从同一菜单打开“Codex 插件”；服务器面板可勾选远程 Codex 插件。\n\n"
            "独立查看无需 Codex。请保留应用，它包含运行环境。\n"
            "此本地预览包尚未使用 Developer ID 签名或经 Apple 公证，不作为正式 Release 发布。\n",
            encoding="utf-8")
        version = json.loads((root / "plugin/.codex-plugin/plugin.json").read_text())["version"]
        dmg_name = f"Atom-Lens-{version}-macOS-{target_architecture}-preview-{preview_revision}.dmg"
        dmg = staging / dmg_name
        run(["hdiutil", "create", "-volname", "Atom Lens", "-srcfolder", str(image_root),
             "-format", "UDZO", "-ov", str(dmg)])
        # Replace only these generated artifacts, never the working repository or user installations.
        destination = output / app.name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(app), destination)
        os.replace(dmg, output / dmg_name)
        checksum = hashlib.sha256((output / dmg_name).read_bytes()).hexdigest()
        (output / "SHA256SUMS.txt").write_text(f"{checksum}  {dmg_name}\n")
    print(f"Built: {output / dmg_name}\nApp preview: {output / 'Atom Lens.app'}")


if __name__ == "__main__":
    main()
