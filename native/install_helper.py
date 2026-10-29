"""Build/register the Mac helper and install its user-approved login agent."""
# Configuration
application_name = "Structure Snapshot Saver.app"

from pathlib import Path
import os
import plistlib
import subprocess


def main() -> None:
    root = Path(__file__).resolve().parent
    app = Path.home() / "Applications" / application_name
    contents = app / "Contents"
    executable = contents / "MacOS" / "SnapshotSaver"
    label = "org.structure-viewer.snapshot-saver"
    domain = f"gui/{os.getuid()}"
    agent = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True, check=False)
    executable.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["/usr/bin/xcrun", "clang", "-fobjc-arc", "-fblocks", str(root / "SnapshotSaver.m"), "-o", str(executable), "-framework", "Cocoa", "-framework", "UniformTypeIdentifiers"], check=True)
    info = {"CFBundleName": "Structure Snapshot Saver", "CFBundleIdentifier": label,
            "CFBundleExecutable": "SnapshotSaver", "CFBundlePackageType": "APPL", "CFBundleVersion": "4", "LSUIElement": True}
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(app)], check=True)
    subprocess.run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister", "-f", str(app)], check=True)
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": [str(executable)],
                                    "RunAtLoad": True, "LimitLoadToSessionType": "Aqua", "ProcessType": "Interactive"}))
    subprocess.run(["launchctl", "bootstrap", domain, str(agent)], check=True)
    print(f"Installed helper: {app}\nLogin agent: {agent}")


if __name__ == "__main__":
    main()
