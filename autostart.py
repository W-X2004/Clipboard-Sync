"""Clipboard Sync 开机自启动管理（命令行菜单）。"""

from __future__ import annotations

import os
import re
import sys
import time


def project_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def startup_dir() -> str:
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(
        appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )


def entry_path() -> str:
    return os.path.join(startup_dir(), "ClipboardSync.vbs")


def legacy_paths() -> list[str]:
    d = startup_dir()
    return [
        os.path.join(d, "ClipboardSync Client.vbs"),
        os.path.join(d, "ClipboardSync Server.vbs"),
        os.path.join(d, "start_client.vbs"),
    ]


def read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def detect() -> dict:
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


def write_vbs(command: str) -> bool:
    """写入启动 VBS。command 例如 pythonw "C:\\...\\tray_server.py" """
    content = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run "{command}", 0, False\n'
    )
    try:
        os.makedirs(startup_dir(), exist_ok=True)
        with open(entry_path(), "w", encoding="utf-8", newline="\r\n") as f:
            f.write(content)
        return os.path.isfile(entry_path())
    except OSError as e:
        print(f"[ERROR] 写入失败: {e}")
        return False


def cleanup_old() -> None:
    for p in legacy_paths():
        if os.path.isfile(p):
            try:
                os.remove(p)
                print(f"  [清理] 已删除旧项: {os.path.basename(p)}")
            except OSError as e:
                print(f"  [清理失败] {os.path.basename(p)}: {e}")


def pause() -> None:
    try:
        input("\n按回车键继续...")
    except EOFError:
        pass


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def show_status() -> None:
    info = detect()
    print(f"  项目目录: {project_dir()}")
    print(f"  启动目录: {startup_dir()}")
    print()
    if not info["installed"]:
        print("  当前自启动项: 未安装")
        for p in legacy_paths():
            if os.path.isfile(p):
                print(f"  [提示] 发现旧文件: {os.path.basename(p)}")
        return

    role = info["role"]
    if role == "server":
        print("  当前自启动项: 服务端")
        print(f"  启动脚本    : {info['entry']}")
        print("  启动命令    : pythonw tray_server.py")
    elif role == "client":
        ip = info["ip"] or "未知"
        print("  当前自启动项: 客户端")
        print(f"  服务端 IP   : {ip}")
        print(f"  启动脚本    : {info['entry']}")
        print(f"  启动命令    : pythonw tray_client.py {ip}")
    else:
        print("  当前自启动项: 文件存在但无法识别")
        print(f"  启动脚本    : {info['entry']}")


def install_server() -> None:
    clear()
    print("=" * 40)
    print("  安装服务端自启动")
    print("=" * 40)
    print()
    cleanup_old()
    py = sys.executable
    # prefer pythonw for silent start
    pythonw = os.path.join(os.path.dirname(py), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = py
    server = os.path.join(project_dir(), "tray_server.py")
    cmd = f'"{pythonw}" "{server}"'
    if write_vbs(cmd):
        print()
        print("[OK] 服务端自启动已安装")
        print("     开机登录后自动运行 tray_server.py")
    else:
        print()
        print("[ERROR] 安装失败，请检查启动目录权限")
    pause()


def install_client() -> None:
    clear()
    print("=" * 40)
    print("  安装客户端自启动")
    print("=" * 40)
    print()
    try:
        server_ip = input("请输入服务端 IP（例如 192.168.0.1）: ").strip()
    except EOFError:
        server_ip = ""

    if not server_ip:
        print("[ERROR] IP 不能为空")
        pause()
        return

    cleanup_old()
    py = sys.executable
    pythonw = os.path.join(os.path.dirname(py), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = py
    client = os.path.join(project_dir(), "tray_client.py")
    cmd = f'"{pythonw}" "{client}" {server_ip}'
    if write_vbs(cmd):
        print()
        print("[OK] 客户端自启动已安装")
        print(f"     服务端 IP: {server_ip}")
        print("     开机登录后自动运行 tray_client.py")
    else:
        print()
        print("[ERROR] 安装失败，请检查启动目录权限")
    pause()


def uninstall() -> None:
    clear()
    print("=" * 40)
    print("  卸载自启动")
    print("=" * 40)
    print()
    removed = False
    path = entry_path()
    if os.path.isfile(path):
        try:
            os.remove(path)
            print("  [删除] ClipboardSync.vbs")
            removed = True
        except OSError as e:
            print(f"  [删除失败] {e}")
    cleanup_old()
    if removed:
        print("  [OK] 自启动已全部卸载")
    else:
        print("  [INFO] 没有找到已安装的自启动项")
    pause()


def main() -> None:
    if os.name == "nt":
        # 让中文在 cmd 窗口正常显示
        os.system("chcp 65001 >nul")

    while True:
        clear()
        print("=" * 40)
        print("  Clipboard Sync 自启动管理")
        print("=" * 40)
        print()
        show_status()
        print()
        print("-" * 40)
        print("  1. 安装服务端自启动")
        print("  2. 安装客户端自启动")
        print("  3. 卸载自启动（含清理旧项）")
        print("  4. 刷新状态")
        print("  0. 退出")
        print("-" * 40)
        print()
        try:
            choice = input("请选择 [0-4]: ").strip()
        except EOFError:
            return

        if choice == "1":
            install_server()
        elif choice == "2":
            install_client()
        elif choice == "3":
            uninstall()
        elif choice == "4":
            continue
        elif choice == "0":
            return
        else:
            print()
            print("[ERROR] 无效选项，请输入 0-4")
            pause()


if __name__ == "__main__":
    main()
