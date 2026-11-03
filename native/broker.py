"""Route native save requests between independent, active Codex SSH hosts."""
from __future__ import annotations

import ctypes
import json
from pathlib import Path
import re
import shlex
import signal
import struct
import subprocess
import sys
import threading
import time

from connection import read_profiles, settings_path

default_config = str(Path.home() / ".ssh/config")
# Only use queue code already installed on this server by Structure Viewer.
auto_queue = """
from pathlib import Path
import os, re, sys
root=Path(os.getenv('CODEX_HOME') or Path.home()/'.codex')/'plugins/cache/atomic-structure-tools/structure-viewer'
versions=sorted((p for p in root.glob('*') if re.fullmatch(r'\\d+\\.\\d+\\.\\d+', p.name)),key=lambda p:tuple(map(int,p.name.split('.'))),reverse=True)
for version in versions:
    if (version/'snapshot_queue.py').is_file():
        sys.path.insert(0,str(version))
        from snapshot_queue import watch
        watch()
        break
else:
    sys.exit(42)
"""


def process_arguments(pid: int) -> list[str]:
    """Read exact argv from Darwin KERN_PROCARGS2; do not parse environment entries."""
    key = (ctypes.c_int * 3)(1, 49, pid)
    size = ctypes.c_size_t(0)
    sysctl = ctypes.CDLL(None).sysctl
    if sysctl(key, 3, None, ctypes.byref(size), None, 0) or not size.value:
        return []
    data = ctypes.create_string_buffer(size.value)
    if sysctl(key, 3, data, ctypes.byref(size), None, 0):
        return []
    raw = data.raw[:size.value]
    if len(raw)<5 or b"\0" not in raw[4:]:
        return []  # Process exited during inspection.
    count = struct.unpack_from("i", raw)[0]
    start = raw.index(b"\0", 4)
    return [arg.decode(errors="replace") for arg in raw[start:].lstrip(b"\0").split(b"\0", count)[:count]]


def codex_profile(argv: list[str]) -> dict | None:
    """Keep endpoint/auth options only. Never replay tunnels, commands or agent forwarding."""
    keys = {"hostname","port","user","identityfile","identitiesonly","proxyjump","proxycommand",
            "hostkeyalias","userknownhostsfile","globalknownhostsfile","identityagent","certificatefile",
            "addressfamily","controlpath","canonicalizehostname","stricthostkeychecking"}
    options: list[str] = []
    config = default_config
    index = 1
    while index < len(argv) and argv[index].startswith("-"):
        token = argv[index]
        index += 1
        if token == "--":
            break
        flag = token[:2]
        if flag in ("-R","-L","-D","-W","-b","-F","-S","-J","-p","-l","-i","-o"):
            if not token[2:] and index >= len(argv):
                return None
            value = token[2:] or argv[index]
            index += int(not token[2:])
            if flag == "-F":
                config = value
                options.extend([flag,value])
            elif flag in ("-S","-J","-p","-l","-i","-b"):
                options.extend([flag,value])
            elif flag == "-o" and re.split(r"[=\s]+",value,1)[0].lower() in keys:
                options.extend([flag,value])
        elif flag in ("-4","-6"):
            options.append(flag)
        elif not re.fullmatch(r"-[TvqnxNaA]+",token):
            return None
    if index+1 >= len(argv) or "app-server" not in " ".join(argv[index+1:]):
        return None
    host = argv[index]
    if not re.fullmatch(r"[\w.][\w.@:-]*",host):
        return None
    return {"host":host,"config":config,"options":options,"automatic":True}


def active_profiles() -> list[dict]:
    """Inspect only SSH transports descended from a running Codex desktop app."""
    listing = subprocess.check_output(["/bin/ps","-axo","pid=,ppid=,comm="],text=True)
    processes = {}
    for line in listing.splitlines():
        pid, parent, executable = line.strip().split(None, 2)
        processes[int(pid)] = int(parent), executable
    hosts = []
    for pid,(parent,executable) in processes.items():
        if executable != "/usr/bin/ssh":
            continue
        while parent in processes:
            parent, ancestor = processes[parent]
            if ancestor.endswith(("/ChatGPT.app/Contents/MacOS/ChatGPT","/Codex.app/Contents/MacOS/Codex")):
                profile = codex_profile(process_arguments(pid))
                if profile:
                    hosts.append(profile)
                break
    return hosts


def profile_key(profile: dict) -> tuple[str, str]:
    return profile["config"], profile["host"]


def desired_profiles(active: list[dict], saved: list[dict]) -> dict:
    targets = {profile_key(p):p for p in active}
    for p in saved:
        key = profile_key(p)
        # Retain the desktop connection's endpoint and authentication overrides.
        targets[key] = {**targets.get(key,{}),**p,"automatic":False}
    return targets


def worker_command(profile: dict) -> list[str]:
    remote = (shlex.join(["python3","-u",profile["installed"]]) if profile.get("installed")
              else shlex.join(["python3","-u","-c",auto_queue]))
    options = profile.get("options")
    if options is None:
        options = ["-F",profile["config"]]
    return ["/usr/bin/ssh",*options,"-o","BatchMode=yes","-o","ConnectTimeout=12","-o","ServerAliveInterval=15",
            "-o","ServerAliveCountMax=2","-o","ClearAllForwardings=yes","--",profile["host"],remote]


class Broker:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.workers = {}
        self.requests = {}
        self.ready = set()
        self.last_status = None
        self.stop = threading.Event()

    def send(self, message: dict) -> None:
        with self.lock:
            print(json.dumps(message,ensure_ascii=False),flush=True)

    def relay(self, key: tuple, process: subprocess.Popen) -> None:
        try:
            for line in process.stdout:
                message = json.loads(line)
                with self.lock:
                    if message.get("kind") == "ready":
                        self.ready.add(key)
                    elif message.get("kind") == "snapshot":
                        request_key = (*key,message["id"])
                        self.requests[request_key] = process
                        self.send({**message,"route":list(key)})
        except (OSError, ValueError, KeyError):
            pass
        finally:
            with self.lock:
                self.ready.discard(key)
                for request in [k for k,p in self.requests.items() if p is process]:
                    del self.requests[request]
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
            process.wait()
            process.stdin.close()

    def acknowledgments(self) -> None:
        try:
            for line in iter(sys.stdin.buffer.raw.readline,b""):
                reply = json.loads(line)
                route = reply.pop("route",[])
                with self.lock:
                    process = self.requests.pop((*route,reply["id"]),None)
                    if process and process.poll() is None:
                        try:
                            process.stdin.write(json.dumps(reply).encode()+b"\n")
                            process.stdin.flush()
                        except OSError:
                            pass
        finally:
            self.stop.set()

    def run(self) -> None:
        threading.Thread(target=self.acknowledgments,daemon=True).start()
        retry_at = {}
        active = []
        unavailable = set()
        try:
            while not self.stop.is_set():
                try:
                    active = active_profiles()
                except (OSError, subprocess.SubprocessError):
                    pass  # Preserve existing workers through a failed process listing.
                targets = desired_profiles(active,read_profiles(settings_path()))
                with self.lock:
                    for key,(profile,process,reader) in list(self.workers.items()):
                        if profile != targets.get(key) and process.poll() is None and process not in self.requests.values():
                            process.terminate()
                        if not reader.is_alive():
                            del self.workers[key]
                            if process.returncode == 42:
                                unavailable.add(key)
                            delay = 60 if process.returncode == 42 else 5
                            retry_at[key] = time.monotonic()+(delay if profile==targets.get(key) else 0)
                    for key,profile in targets.items():
                        if key in self.workers or time.monotonic()<retry_at.get(key,0):
                            continue
                        process = subprocess.Popen(worker_command(profile),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                                   stderr=subprocess.DEVNULL)
                        reader = threading.Thread(target=self.relay,args=(key,process),daemon=True)
                        self.workers[key] = profile,process,reader
                        reader.start()
                    unavailable.difference_update(self.ready)
                    state = [{k:v for k,v in {**p,"ready":key in self.ready,
                                               "missing":key in unavailable}.items() if k!="options"}
                             for key,p in sorted(targets.items())]
                    if state!=self.last_status:
                        self.send({"kind":"hosts","hosts":state})
                        self.last_status=state
                self.stop.wait(2)
        finally:
            for _,process,_ in self.workers.values():
                if process.poll() is None:
                    process.terminate()
            for _,process,_ in self.workers.values():
                process.wait()


if __name__ == "__main__":
    broker = Broker()
    signal.signal(signal.SIGTERM, lambda *_: broker.stop.set())
    broker.run()
