"""Build/register the Mac helper and install its user-approved login agent."""
# Configuration
application_name = "Structure Snapshot Saver.app"

from pathlib import Path
import os
import plistlib
import shutil
import tempfile
import subprocess


def main() -> None:
    root = Path(__file__).resolve().parent
    app = Path.home() / "Applications" / application_name
    label = "org.structure-viewer.snapshot-saver"
    domain = f"gui/{os.getuid()}"
    agent = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    app.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=app.parent) as staging:
        staged = Path(staging) / application_name
        contents = staged / "Contents"
        executable = contents / "MacOS/SnapshotSaver"
        executable.parent.mkdir(parents=True)
        resources = contents / "Resources"
        resources.mkdir()
        for filename in ("connection.py", "broker.py"):
            shutil.copy2(root / filename, resources)
        for filename in ("snapshot_queue.py", "local_export.py"):
            shutil.copy2(root.parent / "plugin" / filename, resources)
        subprocess.run(["/usr/bin/xcrun", "clang", "-fobjc-arc", "-fblocks", str(root / "SnapshotSaver.m"), "-o", str(executable), "-framework", "Cocoa", "-framework", "UniformTypeIdentifiers"], check=True)
        info = {"CFBundleName": "Structure Snapshot Saver", "CFBundleIdentifier": label,
                "CFBundleExecutable": executable.name, "CFBundlePackageType": "APPL", "CFBundleVersion": "6", "LSUIElement": True}
        (contents / "Info.plist").write_bytes(plistlib.dumps(info))
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(staged)], check=True)
        agent.parent.mkdir(parents=True, exist_ok=True)
        program = app / "Contents/MacOS/SnapshotSaver"
        new_agent = plistlib.dumps({"Label": label, "ProgramArguments": [str(program)],
                                   "RunAtLoad": True, "LimitLoadToSessionType": "Aqua"})
        backup = Path(staging) / "previous.app"
        old_agent = agent.read_bytes() if agent.exists() else None
        subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True, check=False)
        if app.exists():
            app.rename(backup)
        try:
            staged.rename(app)
            subprocess.run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister", "-f", str(app)], check=True)
            agent.write_bytes(new_agent)
            subprocess.run(["launchctl", "bootstrap", domain, str(agent)], check=True)
        except Exception:
            if app.exists():
                app.rename(staged)
            if backup.exists():
                backup.rename(app)
            if old_agent is None:
                agent.unlink(missing_ok=True)
            else:
                agent.write_bytes(old_agent)
                subprocess.run(["launchctl", "bootstrap", domain, str(agent)], check=False)
            raise
    print(f"Installed helper: {app}\nLogin agent: {agent}\n菜单栏 → 结构快照 → 服务器")


if __name__ == "__main__":
    main()
