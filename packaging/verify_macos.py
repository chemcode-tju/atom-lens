"""Verify a relocated Mac bundle and real Codex registration in temporary folders."""
from __future__ import annotations

# Configuration
target_architecture = "arm64"

from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request


def verify_signature(app: Path) -> None:
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)


def verify_deployment(app: Path, folder: Path) -> None:
    """Build and install the SSH payload using only the relocated app's resources."""
    resources = app / "Contents/Resources"
    environment = {**os.environ, "CODEX_HOME": str(folder / "deployment codex home"),
                   "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
    probe = f"""
import base64, hashlib, sys
from pathlib import Path
sys.path.insert(0, {str(resources / 'native')!r})
from desktop_backend import RPCClient, runtime_bundle
import remote_bootstrap
payload = runtime_bundle()
target = Path({str(folder / 'deployment backend')!r})
remote_bootstrap.backend_directory = str(target)
request = {{'bundle': base64.b64encode(payload).decode(), 'sha256': hashlib.sha256(payload).hexdigest(), 'codex': False}}
for _ in range(2):
    result = remote_bootstrap.install(request)
    assert result['version'] and not result['codexInstalled'], result
assert (target / 'LICENSE').read_bytes() == Path({str(resources / 'LICENSE')!r}).read_bytes()
client = RPCClient([sys.executable, '-B', '-u', str(target / 'native/desktop_worker.py')])
try:
    client.call('initialize')
    opened = client.call('tools/call', {{'name': 'open_structure_path', 'arguments': {{'path': str(target / 'examples/water.xyz')}}}})
    frames = client.call('tools/call', {{'name': 'read_trajectory_frames', 'arguments': {{'token': opened['structuredContent']['file']['token'], 'frameLimit': 2}}}})
    assert frames['structuredContent']['frameCount'] == 2, frames
finally:
    client.close()
assert not Path({environment['CODEX_HOME']!r}).exists()
print('Relocated app deployment payload: license, fresh install, reinstall and two-frame worker passed.')
"""
    subprocess.run([str(resources / "python/bin/python3"), "-I", "-B", "-c", probe],
                   env=environment, cwd=folder, check=True, timeout=90)


def verify_runtime(root: Path, app: Path, folder: Path) -> None:
    """Exercise the installed cache without a Python or Codex executable on PATH."""
    resources = app / "Contents/Resources"
    python = resources / "python/bin/python3"
    home = folder / "codex home"
    environment = {**os.environ, "CODEX_HOME": str(home), "PATH": "/usr/bin:/bin",
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    host = subprocess.Popen([str(python), "-I", "-B", "-u", str(resources / "native/desktop_host.py")],
                            env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    try:
        address = host.stdout.readline().strip()
        assert address.startswith("http://127.0.0.1:"), host.stderr.read() if host.poll() is not None else address
        def desktop_request(route: str, payload: dict) -> dict:
            request = urllib.request.Request(address + route, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "X-Atom-Lens": "desktop"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        state = desktop_request("state", {})
        opened = desktop_request("rpc", {"session": state["session"], "method": "tools/call", "params": {
            "name": "open_structure_path", "arguments": {"path": str(resources / "examples/water.xyz")}}})
        frames = desktop_request("rpc", {"session": state["session"], "method": "tools/call", "params": {
            "name": "read_trajectory_frames", "arguments": {"token": opened["structuredContent"]["file"]["token"], "frameLimit": 2}}})
        assert frames["structuredContent"]["frameCount"] == 2
        assert not home.exists(), "Standalone viewer must not install or configure Codex"
    finally:
        host.stdin.close()
        host.wait(timeout=15)
        host.stdout.close()
        host.stderr.close()
    print("Relocated standalone host opened two frames without creating Codex configuration.")
    for _ in range(2):
        subprocess.run([str(python), "-I", "-B", str(resources / "install.py")],
                       env=environment, check=True, capture_output=True, text=True, timeout=90)
    version = json.loads((resources / "plugin/.codex-plugin/plugin.json").read_text())["version"]
    cached = home / "plugins/cache/atomic-structure-tools/structure-viewer" / version
    config = json.loads((cached / ".mcp.json").read_text())["mcpServers"]["structure-viewer"]
    assert config["command"] == str(python), config["command"]
    probe = f"""
import sys, ssl, ctypes, fcntl
sys.path.insert(0, {str(cached)!r})
import server
opened = server.dispatch('tools/call', {{'name': 'open_structure_path', 'arguments': {{'path': {str(root / 'examples/water.xyz')!r}}}}})
token = opened['structuredContent']['file']['token']
frames = server.dispatch('tools/call', {{'name': 'read_trajectory_frames', 'arguments': {{'token': token, 'frameLimit': 2}}}})['structuredContent']
assert frames['frameCount'] == 2, frames
sys.path.insert(0, {str(resources / 'native')!r})
import connection, broker
print('Relocated runtime: SSL/ctypes/fcntl, cached viewer, two frames and helper imports passed.')
"""
    subprocess.run([str(python), "-E", "-s", "-B", "-c", probe], env=environment,
                   cwd=folder, check=True, timeout=30)
    ssh_config = folder / "test ssh config"
    ssh_config.write_text("Host test-host\n  HostName example.invalid\n")
    result = subprocess.run([str(python), "-E", "-s", "-B", str(resources / "native/connection.py")],
                            input=json.dumps({"action": "aliases", "config": str(ssh_config)}),
                            env=environment, text=True, capture_output=True, check=True, timeout=30)
    assert json.loads(result.stdout) == ["test-host"]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "dist" / f"macos-{target_architecture}" / "Atom Lens.app"
    verify_signature(source)
    with tempfile.TemporaryDirectory(prefix="atom lens relocation ") as directory:
        folder = Path(directory)
        app = folder / "Applications/Atom Lens.app"
        shutil.copytree(source, app, symlinks=True)
        verify_signature(app)
        verify_deployment(app, folder)
        verify_runtime(root, app, folder)
        verify_signature(app)
    print("First install, reinstall, relocation and unchanged app signature passed.")


if __name__ == "__main__":
    main()
