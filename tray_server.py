"""
剪贴板同步服务端 - 系统托盘版
在系统托盘运行，不占用命令行窗口
"""

import socket
import struct
import threading
import time
import sys
import os
import logging
import ctypes

log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.log')
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
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


class Clipboard:
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


def _make_circle_icon(fill, outline, letter, letter_xy=(22, 18)):
    size = 64
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([4, 4, 60, 60], fill=fill, outline=outline, width=3)
    dc.text(letter_xy, letter, fill=(255, 255, 255, 255))
    return image


class ClipboardSyncServer:
    def __init__(self, host='0.0.0.0', port=12345):
        self.host = host
        self.port = port
        self.server = None
        self.is_running = False
        self.clients = []
        self.clipboard = Clipboard()
        self.icon = None
        self.client_count = 0
        self._lock = threading.Lock()
        self._desired_icon_state = None
        self._img_connected = _make_circle_icon(
            (46, 204, 113, 255), (39, 174, 96, 255), "S"
        )
        self._img_waiting = _make_circle_icon(
            (241, 196, 15, 255), (243, 156, 18, 255), "S"
        )
        logger.info(f"Server initialized: {host}:{port}")

    def create_image(self):
        return self._img_connected

    def create_no_client_image(self):
        return self._img_waiting

    def _tray_ready(self):
        """
        托盘真正可刷新条件：run() 已启动 且 visible=True。
        pystray 在 visible=False 时赋值 icon 不会 NIM_MODIFY。
        """
        if not self.icon:
            return False
        return bool(getattr(self.icon, '_running', False)) and bool(
            getattr(self.icon, 'visible', False)
        )

    def update_icon(self, force=False):
        if not self.icon:
            return False

        has_client = self.client_count > 0
        if has_client:
            img, title, label = (
                self._img_connected,
                f"Clipboard Sync - Server ({self.client_count} client)",
                "green (client connected)",
            )
        else:
            img, title, label = (
                self._img_waiting,
                "Clipboard Sync - Server (waiting)",
                "yellow (no client)",
            )

        with self._lock:
            if not self._tray_ready():
                self._desired_icon_state = has_client
                logger.debug("Tray not ready yet, icon update deferred")
                return False

            try:
                self.icon.icon = img
                self.icon.title = title
                prev = self._desired_icon_state
                self._desired_icon_state = has_client
                if prev != has_client:
                    logger.info("Icon updated: %s", label)
                else:
                    logger.debug("Icon re-applied: %s", label)
                return True
            except Exception as e:
                logger.error(f"Error updating icon: {e}")
                return False

    def icon_watchdog(self):
        waited = 0.0
        while self.is_running and not self._tray_ready() and waited < 15:
            time.sleep(0.05)
            waited += 0.05
        if not self.is_running:
            return
        self.update_icon(force=True)
        last = self.client_count > 0
        stale = 0
        while self.is_running:
            time.sleep(1)
            cur = self.client_count > 0
            if last != cur or self._desired_icon_state != cur or not self._tray_ready():
                self.update_icon(force=True)
                last = cur
                stale = 0
            else:
                stale += 1
                if stale >= 8:
                    self.update_icon(force=True)
                    stale = 0

    def handle_client(self, conn, addr):
        with self._lock:
            self.client_count += 1
        self.update_icon(force=True)
        logger.info(f"Client connected: {addr[0]}:{addr[1]}")

        try:
            send_msg(conn, "CONNECTED")
        except Exception as e:
            logger.error(f"Handshake failed: {e}")

        last_content = ""
        last_sent_content = ""

        try:
            while self.is_running:
                data = recv_msg(conn, timeout=0.3)

                if data is None:
                    try:
                        conn.settimeout(0.05)
                        probe = conn.recv(1, socket.MSG_PEEK)
                        if probe == b'':
                            logger.info(f"Client disconnected: {addr[0]}")
                            break
                    except socket.timeout:
                        pass
                    except Exception:
                        logger.info(f"Client disconnected: {addr[0]}")
                        break
                elif data != last_content:
                    self.clipboard.copy(data)
                    last_content = data
                    last_sent_content = data  # 防止回声
                    logger.info(f"Clipboard updated from client {addr[0]}")

                try:
                    current_content = self.clipboard.paste()
                    if current_content and current_content != last_sent_content:
                        send_msg(conn, current_content)
                        last_sent_content = current_content
                        logger.info(f"Clipboard sent to client {addr[0]}")
                except Exception as e:
                    logger.error(f"Error sending data: {e}")
                    break

                time.sleep(0.15)

        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self.client_count = max(0, self.client_count - 1)
            self.update_icon(force=True)
            logger.info(f"Client connection closed: {addr[0]}")

    def start_server(self):
        self.is_running = True
        logger.info("Starting server...")

        while self.is_running:
            try:
                self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server.bind((self.host, self.port))
                self.server.listen(5)
                self.server.settimeout(1)
                logger.info(f"Server listening on {self.host}:{self.port}")

                while self.is_running:
                    try:
                        conn, addr = self.server.accept()
                        client_thread = threading.Thread(
                            target=self.handle_client,
                            args=(conn, addr),
                            daemon=True
                        )
                        client_thread.start()
                    except socket.timeout:
                        continue
                    except OSError:
                        break

            except Exception as e:
                logger.error(f"Server error: {e}")
                if self.is_running:
                    logger.info("Server will restart in 2 seconds...")
                    time.sleep(2)
            finally:
                if self.server:
                    try:
                        self.server.close()
                    except Exception:
                        pass

    def start(self):
        self.thread = threading.Thread(target=self.start_server, daemon=True)
        self.thread.start()
        self.watchdog = threading.Thread(target=self.icon_watchdog, daemon=True)
        self.watchdog.start()

    def stop(self):
        self.is_running = False
        if self.server:
            try:
                self.server.close()
            except Exception:
                pass

    def show_status(self, icon, item):
        status = f"Clients connected: {self.client_count}"
        message = (
            f"Clipboard Sync Server\n\n"
            f"Status: Running\n"
            f"Port: {self.port}\n"
            f"{status}"
        )
        ctypes.windll.user32.MessageBoxW(0, message, "Clipboard Sync", 0x40)

    def quit_app(self, icon, item):
        self.stop()
        icon.stop()


def main():
    logger.info("=== Clipboard Sync Server Started ===")

    host = '0.0.0.0'
    port = 12345

    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    server = ClipboardSyncServer(host, port)

    try:
        icon = pystray.Icon(
            "ClipboardSyncServer",
            server.create_no_client_image(),
            "Clipboard Sync - Server (waiting)"
        )
        logger.info("System tray icon created")
    except Exception as e:
        logger.error(f"Failed to create icon: {e}")
        return

    icon.menu = pystray.Menu(
        item('Status', server.show_status),
        pystray.Menu.SEPARATOR,
        item('Quit', server.quit_app)
    )

    server.icon = icon
    server.start()
    logger.info("Server thread started")

    try:
        logger.info("Starting system tray...")
        icon.run()
    except Exception as e:
        logger.error(f"System tray error: {e}")
    finally:
        server.stop()


if __name__ == "__main__":
    main()
