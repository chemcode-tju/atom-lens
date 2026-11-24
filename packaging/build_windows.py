"""Cross-build the standalone Windows x64 setup with NSIS and pinned runtimes."""
from __future__ import annotations

# Configuration
release_version = "0.0.0"
preview_revision = 1
electron_version = "45.4.1"
electron_sha256 = "2ba6223afa9121f42831fefe92c434334907540165294fc56697449d12e7cfe9"
python_build = "20261026"
python_version = "3.11.18"
python_sha256 = "67215a7bf1643e33d01b17ee3f1e91a8b0b39163746855ee02594bf0608f68b4"

from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download(path: Path, url: str, expected: str) -> Path:
    """Keep verified downloads in the build cache for reproducible offline rebuilds."""
    if path.is_file() and sha256(path) == expected:
        return path
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
    try:
        with urllib.request.urlopen(url, timeout=120) as source, temporary.open("wb") as output:
            shutil.copyfileobj(source, output)
        if sha256(temporary) != expected:
            raise ValueError(f"Download checksum mismatch: {url}")
        temporary.replace(path)
        return path
    finally:
        temporary.unlink(missing_ok=True)


def populate_application(root: Path, app: Path, python_archive: Path) -> None:
    resources = app / "resources"
    viewer = resources / "atom-lens"
    viewer.mkdir(parents=True)
    with tarfile.open(python_archive) as bundle:
        bundle.extractall(viewer, filter="data")
    if not (viewer / "python/python.exe").is_file():
        raise ValueError("The bundled Python executable is missing")

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "archive")
    shutil.copytree(root / "plugin", viewer / "plugin", ignore=ignore)
    for filename in ("LICENSE", "install.py", ".agents/plugins/marketplace.json", "examples/water.xyz",
                     "native/connection.py", "native/desktop_host.py", "native/desktop_backend.py",
                     "native/desktop_worker.py", "native/desktop_profiles.py", "native/remote_bootstrap.py",
                     "native/desktop.html"):
        destination = viewer / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / filename, destination)

    shell = resources / "app"
    shell.mkdir()
    for filename in ("main.cjs", "preload.cjs"):
        shutil.copy2(root / "native/windows" / filename, shell)
    shutil.copy2(root / "native/windows/AtomLens.ico", viewer)
    manifest = {"name": "atom-lens", "productName": "Atom Lens", "version": release_version, "main": "main.cjs"}
    (shell / "package.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (viewer / "RUNTIME-NOTICE.txt").write_text(
        f"Atom Lens {release_version} Windows preview {preview_revision}\n"
        f"Electron {electron_version}. See LICENSE and LICENSES.chromium.html in the app directory.\n"
        f"Python {python_version} (Astral python-build-standalone {python_build}). "
        "See the notices in the python directory.\n"
        "Atom Lens: MIT (LICENSE). Third-party viewer licenses are in plugin/web/vendor.\n",
        encoding="utf-8")


def main() -> None:
    compiler = shutil.which("makensis")
    if not compiler:
        raise SystemExit("Install NSIS 3 and make makensis available on PATH.")
    root = Path(__file__).resolve().parents[1]
    output = root / "dist/windows-x64"
    cache = root / "dist/build-cache"
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    electron_name = f"electron-v{electron_version}-win32-x64.zip"
    electron = download(cache / electron_name,
                        f"https://github.com/electron/electron/releases/download/v{electron_version}/{electron_name}",
                        electron_sha256)
    python_name = f"cpython-{python_version}%2B{python_build}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
    python = download(cache / f"python-windows-x64-{python_build}.tar.gz",
                      f"https://github.com/astral-sh/python-build-standalone/releases/download/{python_build}/{python_name}",
                      python_sha256)

    name = f"Atom-Lens-{release_version}-Windows-x64-preview-{preview_revision}-Setup.exe"
    with tempfile.TemporaryDirectory(prefix="atomlens-windows-") as temporary:
        staging = Path(temporary)
        app = staging / "app"
        with zipfile.ZipFile(electron) as bundle:
            bundle.extractall(app)
        (app / "electron.exe").rename(app / "AtomLens.exe")
        (app / "resources/default_app.asar").unlink()
        populate_application(root, app, python)
        switch = "/" if sys.platform == "win32" else "-"
        installer = staging / name
        subprocess.run([compiler, f"{switch}DAPP_DIRECTORY={app}", f"{switch}DOUTPUT_FILE={installer}",
                        f"{switch}DRELEASE_VERSION={release_version}", str(root / "packaging/windows.nsi")],
                       cwd=staging, check=True)
        pending = output / f"{name}.pending"
        shutil.copyfile(installer, pending)
        os.replace(pending, output / name)
    (output / "SHA256SUMS.txt").write_text(f"{sha256(output / name)}  {name}\n", encoding="utf-8")
    print(f"Built: {output / name}")


if __name__ == "__main__":
    main()
