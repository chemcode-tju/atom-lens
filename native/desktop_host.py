"""Private loopback host for the Mac window; stdout emits one startup URL."""
from __future__ import annotations

# Configuration
port = 0
max_request_bytes = 48 * 1048576

from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import sys
import threading
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from connection import host_aliases
from desktop_backend import DesktopSessions, bootstrap, root
from desktop_profiles import ProfileStore, normalize_profile
from remote_bootstrap import codex_plugin_installed, find_codex
sys.path.insert(0, str(root / "plugin"))
from server import localization_js, widget_html


class DesktopHost(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, profiles_path: Path | None = None) -> None:
        self.secret = secrets.token_urlsafe(32)
        self.sessions = DesktopSessions()
        self.profiles = ProfileStore(profiles_path)
        self.startup_lock = threading.Lock()
        self.started = False
        self.widget = widget_html().encode()
        self.localizer = localization_js().encode()
        self.theme_script = (root / "plugin/web/theme.js").read_bytes()
        self.theme_style = (root / "plugin/web/theme.css").read_bytes()
        self.shell = (root / "native/desktop.html").read_bytes()
        super().__init__(("127.0.0.1", port), DesktopHandler)
        self.origin = f"http://127.0.0.1:{self.server_port}"

    def startup_state(self) -> dict:
        """Resolve the initial host once, before creating the first viewer."""
        with self.startup_lock:
            if self.started:
                return self.sessions.state()
            self.started = True
            try:
                profile = self.profiles.last_connected()
                if profile:
                    result = self.sessions.connect(profile, reconnect=True)
                    self.profiles.record(result["profile"], result.get("codexInstalled"))
                    return result
            except (ValueError, RuntimeError, OSError) as error:
                return {**self.sessions.state(), "startupError": str(error)}
            return self.sessions.state()

    def server_close(self) -> None:
        self.sessions.close()
        super().server_close()


class DesktopHandler(BaseHTTPRequestHandler):
    server: DesktopHost

    def log_message(self, format: str, *arguments: object) -> None:
        pass  # URLs contain a per-launch secret.

    def route(self) -> str | None:
        prefix = f"/{self.server.secret}/"
        path = urlsplit(self.path).path
        if self.headers.get("Host") != self.server.origin.removeprefix("http://") or not path.startswith(prefix):
            return None
        if self.headers.get("Origin", self.server.origin) != self.server.origin:
            return None
        return path[len(prefix):]

    def reply(self, body: bytes, mime: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'self'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json_reply(self, value: object, status: int = 200) -> None:
        self.reply(json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

    def do_GET(self) -> None:
        route = self.route()
        if route == "":
            self.reply(self.server.shell, "text/html; charset=utf-8")
        elif route == "widget":
            self.reply(self.server.widget, "text/html; charset=utf-8")
        elif route == "i18n.js":
            self.reply(self.server.localizer, "text/javascript; charset=utf-8")
        elif route == "theme.js":
            self.reply(self.server.theme_script, "text/javascript; charset=utf-8")
        elif route == "theme.css":
            self.reply(self.server.theme_style, "text/css; charset=utf-8")
        else:
            self.json_reply({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        route = self.route()
        if route is None or self.headers.get("X-Atom-Lens") != "desktop" or not self.headers.get("Content-Type", "").startswith("application/json"):
            self.json_reply({"error": "Unauthorized"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= max_request_bytes:
                raise ValueError("请求大小无效")
            request = json.loads(self.rfile.read(length))
            sessions = self.server.sessions
            if route == "state":
                result = sessions.state()
            elif route == "startup":
                result = self.server.startup_state()
            elif route == "local-codex":
                result = {"installed": codex_plugin_installed(find_codex())}
            elif route == "profiles":
                action = request.get("action", "list")
                if action == "save":
                    saved = self.server.profiles.save(request["profile"])
                    result = {"saved": saved, "profiles": self.server.profiles.list()}
                elif action == "remove":
                    self.server.profiles.remove(request["id"])
                    result = {"profiles": self.server.profiles.list()}
                elif action == "list":
                    result = {"profiles": self.server.profiles.list()}
                else:
                    raise ValueError("未知服务器列表操作")
            elif route == "hosts":
                path = Path(request.get("config") or "~/.ssh/config").expanduser()
                result = {"hosts": host_aliases(path) if path.is_file() else [], "config": str(path)}
            elif route == "bootstrap":
                if request.get("install", False):
                    sessions.prepare_update(request["profile"])
                result = bootstrap(request["profile"], request.get("install", False), request.get("codex", False))
                self.server.profiles.record({**normalize_profile(request["profile"]), "id": request["profile"].get("id")}, result.get("codexInstalled"))
            elif route == "connect":
                result = sessions.connect(request.get("profile", {}))
                if result["remote"]:
                    self.server.profiles.record(result["profile"], result.get("codexInstalled"), connected=True)
            elif route == "activate":
                result = sessions.activate(request["session"])
                if result["remote"]:
                    self.server.profiles.record(result["profile"], connected=True)
            elif route == "disconnect":
                previous = next((item for item in sessions.state()["connections"] if item["session"] == request["session"]), None)
                result = sessions.disconnect(request["session"])
                if previous and not request.get("updating"):
                    self.server.profiles.forget_connection((previous.get("profile") or {}).get("id"))
            elif route == "rpc":
                method = request["method"]
                if method not in {"initialize", "ping", "tools/call", "resources/read", "resources/subscribe", "resources/unsubscribe", "atomlens/list-directory"}:
                    raise ValueError("不支持的桌面请求")
                result = sessions.call(request["session"], method, request.get("params", {}))
            else:
                self.json_reply({"error": "Not found"}, 404)
                return
            self.json_reply(result)
        except Exception as error:
            self.json_reply({"error": str(error)}, 400)


def main() -> None:
    host = DesktopHost()

    def watch_parent() -> None:
        sys.stdin.buffer.read()
        host.shutdown()

    threading.Thread(target=watch_parent, daemon=True).start()
    print(f"{host.origin}/{host.secret}/", flush=True)
    try:
        host.serve_forever()
    finally:
        host.server_close()


if __name__ == "__main__":
    main()
