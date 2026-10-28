"""SSH stdio queue: no TCP listener; native helper acknowledges each save."""
# Configuration
poll_interval = 2
request_lifetime = 600

from pathlib import Path
import fcntl
import json
import re
import select
import sys
import time
import threading

from local_export import export_folder


def watch() -> None:
    folder = export_folder()
    lock = (folder / "helper.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for claimed in folder.glob("*.claimed"):
        state = claimed.with_suffix(".status")
        if state.exists() and state.read_text() == "choosing":
            state.write_text("error")
    # Continue the connection heartbeat even while SSH sends a large export.
    def heartbeat() -> None:
        while True:
            (folder / "helper-heartbeat").touch()
            time.sleep(poll_interval)
    threading.Thread(target=heartbeat, daemon=True).start()
    pending: str | None = None
    (folder / "helper-heartbeat").touch()
    print(json.dumps({"kind": "ready"}), flush=True)
    while True:
        (folder / "helper-heartbeat").touch()
        readable, _, _ = select.select([sys.stdin], [], [], poll_interval)
        if readable:
            line = sys.stdin.readline(4096)
            if not line:
                return
            reply = json.loads(line)
            if pending and reply.get("id") == pending and reply.get("status") in {"saved", "cancelled", "error"}:
                (folder / f"{pending}.status").write_text(reply["status"])
                pending = None
        if pending:
            continue
        for request in sorted(folder.glob("*.request"), key=lambda path: path.stat().st_mtime):
            identifier = request.stem
            if not re.fullmatch(r"[0-9a-f-]{36}", identifier):
                continue
            if time.time() - request.stat().st_mtime > request_lifetime:
                (folder / f"{identifier}.status").write_text("expired")
                request.unlink()
                continue
            # Only one registered Mac helper is expected for this SSH account.
            request.rename(request.with_suffix(".claimed"))
            payload = json.loads(request.with_suffix(".json").read_text())
            payload["kind"] = "snapshot"
            (folder / f"{identifier}.status").write_text("choosing")
            pending = identifier
            print(json.dumps(payload), flush=True)
            break


def main() -> None:
    try:
        watch()
    except (BrokenPipeError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
