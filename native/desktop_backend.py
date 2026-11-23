"""Desktop session transport and SSH deployment, independent of Codex."""
from __future__ import annotations

# Configuration
rpc_timeout_seconds = 180
reconnect_timeout_seconds = 20

from pathlib import Path
from typing import Any
from collections import deque
import base64
import hashlib
import io
import json
import os
import queue
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "plugin"))
from snapshot import save_file
from trajectory import is_trajectory_index
from desktop_profiles import normalize_profile


def ssh_command(profile: dict[str, Any]) -> list[str]:
    host = str(profile.get("host", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]*", host):
        raise ValueError("请选择 SSH Host 别名或填写 user@host")
    config = Path(profile.get("config") or "~/.ssh/config").expanduser()
    if not config.is_absolute():
        raise ValueError("SSH 配置文件须使用绝对路径")
    if not config.is_file() and config != Path.home() / ".ssh/config":
        raise ValueError("找不到所选 SSH 配置文件")
    return ["/usr/bin/ssh", "-F", str(config) if config.is_file() else "/dev/null",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=2", "-o", "ClearAllForwardings=yes", "--", host]


def remote_python(profile: dict[str, Any]) -> str:
    value = str(profile.get("python") or "python3").strip()
    if not value or value.startswith("-") or any(ord(char) < 32 for char in value):
        raise ValueError("无效的 Python 路径")
    return value


def runtime_bundle(source: Path = root) -> bytes:
    """Transfer only program files and a tiny fixture; no trajectories or SSH secrets."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        for directory, folders, filenames in os.walk(source / "plugin"):
            folders[:] = sorted(name for name in folders if name not in {"archive", "__pycache__"})
            for name in sorted(filenames):
                path = Path(directory) / name
                if not path.is_symlink() and path.suffix != ".pyc" and path.name != ".DS_Store":
                    bundle.write(path, str(path.relative_to(source)))
        for name in ("LICENSE", "install.py", ".agents/plugins/marketplace.json", "native/desktop_worker.py", "examples/water.xyz"):
            bundle.write(source / name, name)
    return output.getvalue()


def bootstrap(profile: dict[str, Any], install: bool = False, codex: bool = False,
              *, timeout: int = rpc_timeout_seconds) -> dict[str, Any]:
    request: dict[str, Any] = {"action": "install" if install else "check", "codex": codex}
    if install:
        payload = runtime_bundle()
        request.update(bundle=base64.b64encode(payload).decode("ascii"), sha256=hashlib.sha256(payload).hexdigest())
    program = (root / "native/remote_bootstrap.py").read_text()
    command = shlex.join([remote_python(profile), "-B", "-c", program])
    try:
        result = subprocess.run([*ssh_command(profile), command], input=json.dumps(request),
                                text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("服务器连接超时") from error
    if result.returncode:
        message = result.stderr.strip()[-4000:] or "SSH 操作未完成"
        raise RuntimeError(f"{message}\n请确认此主机已能通过 SSH 密钥或 SSH agent 登录；首次连接需先确认主机指纹。")
    try:
        state = json.loads(result.stdout.strip().splitlines()[-1])
        reader_hash = hashlib.sha256((root / "plugin/md_import.py").read_bytes()).hexdigest()
        state["trajectoryUpdateAvailable"] = bool(state["version"] and state.get("trajectoryReaderHash") != reader_hash)
        return state
    except (ValueError, IndexError) as error:
        raise RuntimeError("服务器没有返回有效检查结果，请检查登录脚本是否改写了标准输出") from error


class RPCClient:
    """Keep one foreground request and one background index in flight per worker."""

    def __init__(self, command: list[str]) -> None:
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding="utf-8", env=environment)
        self.replies: dict[int, queue.Queue] = {}
        self.errors: deque[str] = deque(maxlen=20)
        self.foreground = threading.Lock()
        self.background = threading.Lock()
        self.send_lock = threading.Lock()
        self.disconnected = threading.Event()
        self.sequence = 0
        threading.Thread(target=self.read_replies, daemon=True).start()
        threading.Thread(target=self.read_errors, daemon=True).start()

    def read_replies(self) -> None:
        try:
            while line := self.process.stdout.readline(64 * 1048576):
                if not line.endswith("\n"):
                    raise ValueError("后端返回的数据过大")
                response = json.loads(line)
                with self.send_lock:
                    reply = self.replies.get(response.get("id"))
                    if reply is not None:
                        reply.put(response)
        except Exception as error:
            self.errors.append(str(error))
        finally:
            with self.send_lock:
                self.disconnected.set()
                for reply in self.replies.values():
                    reply.put(None)

    def read_errors(self) -> None:
        try:
            for line in iter(lambda: self.process.stderr.readline(4096), ""):
                self.errors.append(line.strip())
        except (ValueError, OSError):
            pass  # The owner is closing a terminated process.

    def call(self, method: str, params: dict[str, Any] | None = None, *, timeout: int = rpc_timeout_seconds) -> dict[str, Any]:
        arguments = params or {}
        lock = self.background if is_trajectory_index(method, arguments) else self.foreground
        with lock:
            identifier = None
            try:
                with self.send_lock:
                    if self.process.poll() is not None or self.disconnected.is_set():
                        raise RuntimeError("连接已断开，请重新连接服务器或切回本地。" + "\n".join(self.errors))
                    self.sequence += 1
                    identifier = self.sequence
                    reply = self.replies[identifier] = queue.Queue()
                    self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": identifier,
                                                         "method": method, "params": arguments}) + "\n")
                    self.process.stdin.flush()
                response = reply.get(timeout=timeout)
                if response is None:
                    raise RuntimeError("后端连接中断：" + "\n".join(self.errors))
            except (queue.Empty, OSError, ValueError) as error:
                self.close()
                raise RuntimeError("后端响应超时或连接中断，请重新连接") from error
            finally:
                if identifier is not None:
                    with self.send_lock:
                        self.replies.pop(identifier, None)
            if "error" in response:
                raise RuntimeError(response["error"]["message"])
            return response["result"]

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream and not stream.closed:
                stream.close()


class DesktopSessions:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.connect_lock = threading.RLock()
        self.connections: dict[str, dict[str, Any]] = {}
        self.identifier = ""
        self.connect({})

    @property
    def client(self) -> RPCClient:
        return self.connections[self.identifier]["client"]

    @staticmethod
    def connection_key(profile: dict[str, Any]) -> tuple[str, str, str]:
        return (profile.get("host", ""), profile.get("config", ""), profile.get("python", ""))

    def connect(self, profile: dict[str, Any], *, reconnect: bool = False) -> dict[str, Any]:
        """Reuse a live worker so switching views preserves its file tokens."""
        with self.connect_lock:
            return self.connect_or_reuse(profile, reconnect=reconnect)

    def connect_or_reuse(self, profile: dict[str, Any], *, reconnect: bool) -> dict[str, Any]:
        remote = bool(profile.get("host"))
        profile_id = profile.get("id")
        profile = normalize_profile(profile) if remote else {}
        if remote and profile_id:
            profile["id"] = profile_id
        key = self.connection_key(profile)
        replaced = None
        with self.lock:
            for identifier, connection in list(self.connections.items()):
                if connection["key"] != key:
                    continue
                if connection["client"].process.poll() is None:
                    self.identifier = identifier
                    connection["profile"] = dict(profile) if remote else None
                    return self.state()
                connection["client"].close()
                replaced = identifier
            if remote and replaced is None and sum(item["remote"] for item in self.connections.values()) >= 4:
                raise ValueError("已保留 4 台服务器连接，请先断开一台再连接新服务器")
        if remote:
            result = bootstrap(profile, timeout=reconnect_timeout_seconds) if reconnect else bootstrap(profile)
            if not result["version"]:
                raise ValueError("服务器尚未安装 Atom Lens 后端，请先点击“安装／更新”")
            program = "from pathlib import Path; import runpy; runpy.run_path(str(Path.home()/'.local/share/atom-lens/backend/native/desktop_worker.py'), run_name='__main__')"
            command = [*ssh_command(profile), shlex.join([result["python"], "-B", "-u", "-c", program])]
        else:
            command = [sys.executable, "-B", "-u", str(root / "native/desktop_worker.py")]
        candidate = RPCClient(command)
        try:
            capabilities = candidate.call("initialize", timeout=reconnect_timeout_seconds if reconnect else rpc_timeout_seconds)
        except Exception:
            candidate.close()
            raise
        with self.lock:
            if replaced is not None:
                del self.connections[replaced]
            identifier = uuid.uuid4().hex
            self.identifier = identifier
            self.connections[identifier] = {
                "session": identifier, "client": candidate, "key": key,
                "host": profile["host"] if remote else "本地 Mac", "remote": remote,
                "profile": dict(profile) if remote else None,
                "concurrentIndex": capabilities.get("atomLensConcurrentIndex") is True,
            }
            if remote and type(result.get("codexInstalled")) is bool:
                self.connections[identifier]["codexInstalled"] = result["codexInstalled"]
            return self.state()

    def state(self) -> dict[str, Any]:
        with self.lock:
            items = [{key: value for key, value in item.items() if key not in {"client", "key"}}
                     for item in self.connections.values()]
            active = next(item for item in items if item["session"] == self.identifier)
            return {**active, "connections": items}

    def activate(self, identifier: str) -> dict[str, Any]:
        with self.lock:
            if identifier not in self.connections:
                raise ValueError("连接已关闭，请重新连接服务器")
            self.identifier = identifier
            return self.state()

    def disconnect(self, identifier: str) -> dict[str, Any]:
        with self.connect_lock:
            with self.lock:
                item = self.connections.get(identifier)
                if item and not item["remote"]:
                    raise ValueError("本地 Mac 会话无需断开")
                if item:
                    del self.connections[identifier]
                    if self.identifier == identifier:
                        self.identifier = next(key for key, value in self.connections.items() if not value["remote"])
            if item:
                item["client"].close()
            return self.state()

    def prepare_update(self, profile: dict[str, Any]) -> None:
        """Close only workers whose backend is about to be replaced."""
        profile = normalize_profile(profile)
        with self.connect_lock:
            identifiers = [key for key, item in self.connections.items() if item["remote"]
                           and item["profile"]["host"] == profile["host"]
                           and item["profile"]["config"] == profile["config"]]
            for identifier in identifiers:
                self.disconnect(identifier)

    def call(self, identifier: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            connection = self.connections.get(identifier)
            if not connection:
                raise ValueError("连接已关闭，请重新打开文件")
            client = connection["client"]
        # An inactive server's slow request must not block the local worker.
        if method == "tools/call" and params.get("name") == "structure_media_export":
            arguments = params.get("arguments", {})
            if arguments.get("action") == "save" and arguments.get("destination") == "native":
                return {"structuredContent": self.save_to_mac(arguments, client), "content": []}
        result = client.call(method, params)
        if method == "tools/call" and params.get("name") == "snapshot_context":
            result["structuredContent"]["desktopPicker"] = True
        return result

    def save_to_mac(self, arguments: dict[str, Any], client: RPCClient) -> dict[str, Any]:
        directory = arguments.get("directory", "")
        if not directory or not Path(directory).is_absolute():
            raise ValueError("请先选择 Mac 上的保存目录")
        with tempfile.TemporaryDirectory(prefix="atomlens-export-") as temporary:
            part = client.call("atomlens/export-read", {"id": arguments["id"], "offset": 0})
            from snapshot import validate_name
            validate_name(part["name"])
            output = Path(temporary) / part["name"]
            with output.open("wb") as stream:
                while True:
                    stream.write(base64.b64decode(part["data"], validate=True))
                    if part["next"] == part["size"]:
                        break
                    if not part["data"]:
                        raise ValueError("导出传输中断")
                    part = client.call("atomlens/export-read", {"id": arguments["id"], "offset": part["next"]})
            return save_file(output, output.name, {"arguments": {"destination": "server", "directory": directory}})

    def close(self) -> None:
        with self.connect_lock:
            with self.lock:
                clients = [item["client"] for item in self.connections.values()]
                self.connections.clear()
            for client in clients:
                client.close()
