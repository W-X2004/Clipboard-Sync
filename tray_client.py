"""
剪贴板同步客户端 - 系统托盘版
在系统托盘运行，不占用命令行窗口
"""

import socket
import struct
import time
import threading
import sys
import os
import logging
import ctypes

# 配置日志
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'client.log')

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger('PIL').setLevel(logging.WARNING)

try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image, ImageDraw
    logger.info("pystray and PIL imported successfully")
except ImportError as e:
    logger.error(f"Failed to import dependencies: {e}")
    print("Please install dependencies first:")
    print("pip install pystray pillow")
    sys.exit(1)


def send_msg(sock, text):
    """发送带 4 字节长度前缀的消息，避免粘包/半包"""
    payload = text.encode('utf-8')
    sock.sendall(struct.pack('>I', len(payload)) + payload)


def recv_msg(sock, timeout=0.3):
    """接收一条完整消息；超时或对端关闭返回 None"""
    sock.settimeout(timeout)
    try:
        header = _recv_exact(sock, 4)
        if header is None:
            return None
        length = struct.unpack('>I', header)[0]
        if length == 0 or length > 16 * 1024 * 1024:
            return None
        payload = _recv_exact(sock, length)
        if payload is None:
            return None
        return payload.decode('utf-8')
    except socket.timeout:
        return None
    except Exception as e:
        logger.debug(f"recv_msg error: {e}")
        return None


def _recv_exact(sock, n):
    """精确接收 n 字节；对端关闭返回 None"""
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


class Clipboard:
    """剪贴板操作"""

    def copy(self, text):
        if text is None:
            return False
        try:
            import pyperclip
            pyperclip.copy(text)
            return True
        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")
            return False

    def paste(self):
        try:
            import pyperclip
            content = pyperclip.paste()
            return content if content else ""
        except Exception as e:
            logger.debug(f"Error reading clipboard: {e}")
            return ""


def _make_circle_icon(fill, outline, letter, letter_xy=(20, 18)):
    """绘制透明背景圆形托盘图标（RGBA）"""
    size = 64
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([4, 4, 60, 60], fill=fill, outline=outline, width=3)
    dc.text(letter_xy, letter, fill=(255, 255, 255, 255))
    return image


class ClipboardSyncClient:
    """剪贴板同步客户端"""

    def __init__(self, server_host, server_port=12345):
        self.server_host = server_host
        self.server_port = server_port
        self.client = None
        self.is_running = False
        self.is_connected = False
        self.last_content = ""
        self.clipboard = Clipboard()
        self.icon = None
        self.thread = None
        self._lock = threading.Lock()
        self._desired_icon_state = None  # 上次成功应用的状态
        # 预生成图标，避免每次创建
        self._img_connected = _make_circle_icon(
            (30, 144, 255, 255), (0, 90, 200, 255), "C"
        )
        self._img_disconnected = _make_circle_icon(
            (128, 128, 128, 255), (80, 80, 80, 255), "X", (22, 18)
        )
        logger.info(f"Client initialized: {server_host}:{server_port}")

    def create_image(self):
        return self._img_connected

    def create_disconnected_image(self):
        return self._img_disconnected

    def _tray_ready(self):
        """
        托盘真正可刷新条件：run() 已启动 且 visible=True。

        pystray 源码行为：icon.icon 赋值只有在 self.visible 为 True 时
        才会调用 NIM_MODIFY。仅判断 _running 会在 setup 线程把 visible
        置 True 之前就改图标，导致改的是 Python 侧镜像，托盘仍显示初始灰图标。
        """
        if not self.icon:
            return False
        return bool(getattr(self.icon, '_running', False)) and bool(
            getattr(self.icon, 'visible', False)
        )

    def _icon_for_state(self):
        if self.is_connected:
            return (
                self._img_connected,
                "Clipboard Sync - Client (Connected)",
                "blue (connected)",
            )
        return (
            self._img_disconnected,
            "Clipboard Sync - Client (Disconnected)",
            "gray (disconnected)",
        )

    def update_icon(self, force=False):
        """
        更新托盘图标。

        只有托盘 visible 后才会真正写入 Shell；否则仅记录期望状态，
        由 icon_watchdog 在就绪后补刷。
        """
        if not self.icon:
            return False

        want_connected = bool(self.is_connected)
        img, title, label = self._icon_for_state()

        with self._lock:
            if not self._tray_ready():
                self._desired_icon_state = want_connected
                logger.debug("Tray not ready yet, icon update deferred")
                return False

            try:
                # 重新赋值 icon，触发 pystray 的 NIM_MODIFY
                self.icon.icon = img
                self.icon.title = title
                prev = self._desired_icon_state
                self._desired_icon_state = want_connected
                if prev != want_connected:
                    logger.info("Icon updated: %s", label)
                else:
                    logger.debug("Icon re-applied: %s", label)
                return True
            except Exception as e:
                logger.error(f"Error updating icon: {e}")
                return False

    def icon_watchdog(self):
        """托盘 visible 后补刷图标；状态变化或缓存异常时强制重刷"""
        waited = 0.0
        while self.is_running and not self._tray_ready() and waited < 15:
            time.sleep(0.05)
            waited += 0.05

        if not self.is_running:
            return

        self.update_icon(force=True)
        logger.info("Icon watchdog: initial refresh applied")

        last = bool(self.is_connected)
        stale = 0
        while self.is_running:
            time.sleep(1)
            cur = bool(self.is_connected)
            if last != cur or self._desired_icon_state != cur or not self._tray_ready():
                self.update_icon(force=True)
                last = cur
                stale = 0
            else:
                stale += 1
                # 每 8 秒强制重刷，对抗 Windows 托盘图标缓存
                if stale >= 8:
                    self.update_icon(force=True)
                    stale = 0

    def sync_clipboard(self):
        """同步剪贴板内容（双向）"""
        logger.info("Clipboard sync thread started")
        last_received_content = ""

        # 等待托盘就绪再连接，避免 connect 成功瞬间 update 被丢弃
        waited = 0.0
        while self.is_running and not self._tray_ready() and waited < 10:
            time.sleep(0.05)
            waited += 0.05

        while self.is_running:
            try:
                if not self.is_connected:
                    self.connect_to_server()
                    time.sleep(1)
                    continue

                current_content = self.clipboard.paste()

                if current_content and current_content != self.last_content:
                    try:
                        send_msg(self.client, current_content)
                        self.last_content = current_content
                        preview = current_content[:50] + ("..." if len(current_content) > 50 else "")
                        logger.info(f"Clipboard sent to server: {preview}")
                    except Exception as e:
                        logger.error(f"Error sending data: {e}")
                        self.is_connected = False
                        self.update_icon(force=True)
                        continue

                data = recv_msg(self.client, timeout=0.3)
                if data is None:
                    # None = 超时；对端关闭由 _recv_exact 返回 None 的空 chunk 处理
                    # 再用一次 0 超时探活
                    try:
                        self.client.settimeout(0.05)
                        probe = self.client.recv(1, socket.MSG_PEEK)
                        if probe == b'':
                            raise ConnectionError("server closed")
                    except socket.timeout:
                        pass
                    except Exception as e:
                        logger.error(f"Connection lost: {e}")
                        self.is_connected = False
                        self.update_icon(force=True)
                elif data != last_received_content:
                    self.clipboard.copy(data)
                    self.last_content = data  # 防止回声
                    last_received_content = data
                    preview = data[:50] + ("..." if len(data) > 50 else "")
                    logger.info(f"Clipboard received from server: {preview}")

                time.sleep(0.15)

            except Exception as e:
                logger.error(f"Sync error: {e}")
                self.is_connected = False
                self.update_icon(force=True)
                time.sleep(1)

    def connect_to_server(self):
        """连接到服务端"""
        try:
            logger.info(f"Connecting to server {self.server_host}:{self.server_port}...")
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.settimeout(5)
            self.client.connect((self.server_host, self.server_port))

            response = recv_msg(self.client, timeout=5)
            if response == "CONNECTED":
                self.is_connected = True
                self.update_icon(force=True)
                logger.info("Connected to server successfully")
                return True
            logger.error(f"Unexpected handshake: {response!r}")
            self.is_connected = False
            self.update_icon(force=True)
            return False

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.is_connected = False
            self.update_icon(force=True)
            return False

    def start(self):
        self.is_running = True
        self.thread = threading.Thread(target=self.sync_clipboard, daemon=True)
        self.thread.start()
        self.watchdog = threading.Thread(target=self.icon_watchdog, daemon=True)
        self.watchdog.start()

    def stop(self):
        self.is_running = False
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass

    def show_status(self, icon, item):
        status = "Connected" if self.is_connected else "Disconnected"
        message = (
            f"Clipboard Sync Client\n\n"
            f"Status: {status}\n"
            f"Server: {self.server_host}:{self.server_port}"
        )
        ctypes.windll.user32.MessageBoxW(0, message, "Clipboard Sync", 0x40)

    def quit_app(self, icon, item):
        self.stop()
        icon.stop()


def main():
    logger.info("=== Clipboard Sync Client Started ===")

    server_host = "192.168.0.1"
    server_port = 12345

    if len(sys.argv) > 1:
        server_host = sys.argv[1]
    if len(sys.argv) > 2:
        server_port = int(sys.argv[2])

    client = ClipboardSyncClient(server_host, server_port)

    try:
        icon = pystray.Icon(
            "ClipboardSyncClient",
            client.create_disconnected_image(),
            "Clipboard Sync - Client (Disconnected)"
        )
        logger.info("System tray icon created")
    except Exception as e:
        logger.error(f"Failed to create icon: {e}")
        return

    icon.menu = pystray.Menu(
        item('Status', client.show_status),
        pystray.Menu.SEPARATOR,
        item('Quit', client.quit_app)
    )

    client.icon = icon
    client.start()
    logger.info("Client thread started")

    try:
        logger.info("Starting system tray...")
        icon.run()
    except Exception as e:
        logger.error(f"System tray error: {e}")
    finally:
        client.stop()


if __name__ == "__main__":
    main()
