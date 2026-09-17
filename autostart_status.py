"""查询/解析自启动项状态，供 autostart.bat 调用。"""

import os
import re
import sys


def startup_dir():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(
        appdata,
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )


def entry_path():
    return os.path.join(startup_dir(), "ClipboardSync.vbs")


def legacy_paths():
    d = startup_dir()
    return [
        os.path.join(d, "ClipboardSync Client.vbs"),
        os.path.join(d, "ClipboardSync Server.vbs"),
        os.path.join(d, "start_client.vbs"),
    ]


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def detect():
    path = entry_path()
    if not os.path.isfile(path):
        return {"installed": False, "role": "none", "ip": "", "entry": path}

    text = read_text(path)
    if "tray_server.py" in text:
        return {"installed": True, "role": "server", "ip": "", "entry": path}
    if "tray_client.py" in text:
        m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", text)
        ip = m.group(1) if m else ""
        return {"installed": True, "role": "client", "ip": ip, "entry": path}
    return {"installed": True, "role": "unknown", "ip": "", "entry": path}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    info = detect()

    if cmd == "status":
        if not info["installed"]:
            print("ROLE:none")
            print("IP:")
            for p in legacy_paths():
                if os.path.isfile(p):
                    print(f"OLD:{p}")
            return
        print(f"ROLE:{info['role']}")
        print(f"IP:{info['ip']}")
        return

    if cmd == "legacy":
        for p in legacy_paths():
            if os.path.isfile(p):
                print(p)
        return

    print(f"UNKNOWN_CMD:{cmd}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
