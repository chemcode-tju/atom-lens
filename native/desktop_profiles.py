"""Persist independent desktop SSH profiles without storing credentials."""
from __future__ import annotations

# Configuration
maximum_profiles = 100

from pathlib import Path, PurePosixPath
from typing import Any
from contextlib import contextmanager
from collections.abc import Iterator
import json
import os
import re
import sys
import tempfile
import uuid


def valid_directory(value: object, *, remote: bool = False) -> bool:
    if not isinstance(value, str) or not value or len(value) > 4096 or "\0" in value:
        return False
    path = PurePosixPath(value) if remote else Path(value)
    return path.is_absolute() and "archive" not in path.parts


def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate editable fields while leaving SSH files and remote hosts untouched."""
    if not isinstance(profile, dict):
        raise ValueError("无效的服务器配置")
    values: dict[str, Any] = {}
    for key, default, limit in (("host", "", 255), ("name", "", 80),
                                ("config", "~/.ssh/config", 4096), ("python", "python3", 4096)):
        value = profile.get(key, default)
        if not isinstance(value, str) or len(value) > limit or any(ord(char) < 32 for char in value):
            raise ValueError(f"服务器配置字段无效：{key}")
        values[key] = value.strip() or default
    if not re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]*", values["host"]):
        raise ValueError("请选择 SSH Host 别名或填写 user@host")
    config = Path(values["config"]).expanduser()
    if not config.is_absolute():
        raise ValueError("SSH 配置文件须使用绝对路径")
    if values["python"].startswith("-"):
        raise ValueError("无效的 Python 路径")
    values["config"] = str(config)
    values["name"] = values["name"] or values["host"]
    values["codex"] = profile.get("codex", False)
    if not isinstance(values["codex"], bool):
        raise ValueError("无效的 Codex 安装选项")
    return values


class ProfileStore:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            if sys.platform == "win32":
                base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
            else:
                base = Path.home() / "Library/Application Support"
            path = base / "Atom Lens/servers.json"
        self.path = path

    def read(self) -> dict[str, Any]:
        if sys.platform == "win32":
            # Windows readers can prevent the atomic replacement while the file is open.
            with self.locked():
                return self.read_unlocked()
        return self.read_unlocked()

    def read_unlocked(self) -> dict[str, Any]:
        if self.path.is_symlink():
            raise ValueError("服务器配置文件不能是符号链接")
        if not self.path.exists():
            return {"version": 1, "profiles": [], "lastConnected": None}
        try:
            if self.path.stat().st_size > 1048576:
                raise ValueError("配置文件过大")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("profiles"), list):
                raise ValueError("配置文件格式不受支持")
            if len(data["profiles"]) > maximum_profiles:
                raise ValueError("服务器配置过多")
            profiles = []
            for item in data["profiles"]:
                profile = {"id": str(uuid.UUID(item["id"])), **normalize_profile(item)}
                if type(item.get("codexInstalled")) is bool:
                    profile["codexInstalled"] = item["codexInstalled"]
                if valid_directory(item.get("lastDirectory"), remote=True):
                    profile["lastDirectory"] = item["lastDirectory"]
                profiles.append(profile)
            if len({item["id"] for item in profiles}) != len(profiles):
                raise ValueError("服务器标识重复")
            last = data.get("lastConnected")
            local_directory = data.get("lastDirectory")
            data = {"version": 1, "profiles": profiles,
                    "lastConnected": last if any(item["id"] == last for item in profiles) else None}
            if valid_directory(local_directory):
                data["lastDirectory"] = local_directory
            return data
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"无法读取服务器列表，原文件未修改：{self.path}") from error

    def list(self) -> list[dict[str, Any]]:
        return self.read()["profiles"]

    def last_connected(self) -> dict[str, Any] | None:
        data = self.read()
        return next((item for item in data["profiles"] if item["id"] == data["lastConnected"]), None)

    @staticmethod
    def location_record(data: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
        if profile is None:
            return data
        return next((item for item in data["profiles"] if all(
            item[key] == profile.get(key) for key in ("id", "host", "config", "python")
        )), {})

    def directory(self, profile: dict[str, Any] | None) -> str | None:
        return self.location_record(self.read(), profile).get("lastDirectory")

    def remember_directory(self, profile: dict[str, Any] | None, directory: str) -> None:
        if not valid_directory(directory, remote=profile is not None):
            return
        with self.locked():
            data = self.read_unlocked()
            record = self.location_record(data, profile)
            if record and record.get("lastDirectory") != directory:
                record["lastDirectory"] = directory
                self.write(data)

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Serialize read-modify-write across app instances, with an atomic JSON swap."""
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "r+b", buffering=0) as lock:
            if sys.platform == "win32":
                import msvcrt

                # A Windows byte-range lock may extend beyond the end of the lock file.
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def write(self, data: dict[str, Any]) -> None:
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as output:
                temporary_path = Path(output.name)
                json.dump(data, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            temporary_path.replace(self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def save(self, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_profile(profile)
        identifier = profile.get("id")
        with self.locked():
            data = self.read_unlocked()
            profiles = data["profiles"]
            if identifier:
                previous = next((item for item in profiles if item["id"] == identifier), None)
                if previous is None:
                    raise ValueError("此服务器配置已移除，请作为新配置保存")
            elif len(profiles) >= maximum_profiles:
                raise ValueError(f"最多保存 {maximum_profiles} 个服务器配置")
            saved = {"id": identifier or uuid.uuid4().hex, **normalized}
            # UUIDs use one canonical spelling when reloaded.
            saved["id"] = str(uuid.UUID(saved["id"]))
            if identifier:
                if all(previous[key] == saved[key] for key in ("host", "config", "python")):
                    for key in ("codexInstalled", "lastDirectory"):
                        if key in previous:
                            saved[key] = previous[key]
                elif data["lastConnected"] == identifier:
                    data["lastConnected"] = None
                profiles = [saved if item["id"] == identifier else item for item in profiles]
            else:
                profiles.append(saved)
            data["profiles"] = profiles
            self.write(data)
        return saved

    def remove(self, identifier: str) -> None:
        with self.locked():
            data = self.read_unlocked()
            profiles = data["profiles"]
            remaining = [item for item in profiles if item["id"] != identifier]
            if len(remaining) == len(profiles):
                raise ValueError("此服务器配置已移除")
            data["profiles"] = remaining
            if data["lastConnected"] == identifier:
                data["lastConnected"] = None
            self.write(data)

    def record(self, profile: dict[str, Any], installed: bool | None = None, *, connected: bool = False) -> None:
        identifier = profile.get("id")
        if not identifier:
            return
        with self.locked():
            data = self.read_unlocked()
            saved = next((item for item in data["profiles"] if item["id"] == identifier), None)
            if not saved or any(saved[key] != profile[key] for key in ("host", "config", "python")):
                return
            status_changed = type(installed) is bool and saved.get("codexInstalled") != installed
            connection_changed = connected and data["lastConnected"] != identifier
            if not status_changed and not connection_changed:
                return
            if type(installed) is bool:
                saved["codexInstalled"] = installed
            if connected:
                data["lastConnected"] = identifier
            self.write(data)

    def forget_connection(self, identifier: str | None) -> None:
        if not identifier:
            return
        with self.locked():
            data = self.read_unlocked()
            if data["lastConnected"] == identifier:
                data["lastConnected"] = None
                self.write(data)
