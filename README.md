# Clipboard Sync

两台 Windows 电脑通过局域网实时同步剪贴板文本。复制一边，另一边直接粘贴。

## 功能

- 双向同步：服务端 ↔ 客户端
- 系统托盘运行，不占命令行窗口
- 自动重连 / 服务端自动重启
- 开机自启动统一管理（可查看当前角色与 IP）
- 内置 `pyperclip`，无需额外安装剪贴板库

## 环境要求

| 组件 | 说明 |
|------|------|
| Windows 10/11 | 两台电脑同一局域网 |
| Python 3.8+ | 勾选 “Add to PATH” |
| 依赖 | `pip install pystray pillow` |

## 快速开始

### 1. 安装依赖

两台电脑都执行：

```bat
pip install pystray pillow
```

### 2. 服务端电脑

双击 `start_tray_server.bat`，或：

```bat
python tray_server.py
```

托盘颜色：

- 黄色 = 等待客户端
- 绿色 = 有客户端已连接

### 3. 客户端电脑

双击 `start_tray_client.bat`，或：

```bat
python tray_client.py <服务端IP>
```

例如：

```bat
python tray_client.py 192.168.0.1
```

托盘颜色：

- 蓝色 = 已连接
- 灰色 = 未连接

### 4. 使用

任一台电脑 `Ctrl+C` 复制文本，另一台 `Ctrl+V` 粘贴。

右键托盘图标可查看状态或退出。

## 开机自启动

双击 `autostart.bat`：

| 按键 | 作用 |
|------|------|
| 1 | 安装服务端自启动 |
| 2 | 安装客户端自启动（会询问服务端 IP） |
| 3 | 卸载自启动，并清理旧启动项 |
| 4 | 刷新状态 |
| 0 | 退出 |

打开后会显示当前状态，例如：

```text
当前自启动项: 客户端
服务端 IP   : 192.168.0.1
```

启动项写入位置：

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ClipboardSync.vbs
```

## 文件说明

```text
Clipboard-Sync/
├── tray_server.py          # 服务端
├── tray_client.py          # 客户端
├── start_tray_server.bat   # 一键启动服务端
├── start_tray_client.bat   # 一键启动客户端
├── autostart.bat           # 自启动管理入口
├── autostart.py            # 自启动管理主程序
├── autostart_status.py     # 命令行快速查状态
├── pyperclip/              # 内置剪贴板库
├── 使用说明.md             # 中文详细说明
└── README.md               # 本文件
```

## 命令行参数

**服务端**

```bat
python tray_server.py [端口]
```

默认端口 `12345`。

**客户端**

```bat
python tray_client.py <服务端IP> [端口]
```

## 故障排查

| 现象 | 处理 |
|------|------|
| 托盘一直是灰色 | 确认服务端已启动、IP/端口正确、防火墙放行 12345 |
| 无法连接 | 两台电脑需在同一局域网；`ping <服务端IP>` 测试 |
| autostart.bat 打不开 | 用 cmd 执行 `python autostart.py` 查看报错 |
| 中文安装路径开机不启动 | 用新版 `autostart.py` 重装自启动（VBS 必须按系统 ANSI/GBK 写入，不能用 UTF-8） |
| 日志 | 目录下 `server.log` / `client.log` |

## 端口与协议

- 端口：`12345`（TCP）
- 仅同步文本，不含加密，建议在可信局域网使用

## License

见仓库中的 [LICENSE](LICENSE)。
