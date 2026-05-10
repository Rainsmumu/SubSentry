# SubSentry Windows 离线部署说明

## 目标环境

- Windows 10/11
- Python 3.8 或更高版本
- 目标电脑无需联网

## 部署包内容

部署目录应至少包含：

```text
SubSentry/
├── app.py
├── cable_config.py
├── circuit_analyzer.py
├── excel_builder.py
├── report_builder.py
├── deploy_check.py
├── requirements.txt
├── install_python_312.bat
├── install_offline_deps.bat
├── check_env.bat
├── start.bat
├── stop_subsentry.bat
├── resolve_python.bat
├── python-installer/
│   └── python-3.12.10-amd64.exe
├── templates/
├── static/
│   └── vendor/
│       ├── alpine.min.js
│       └── tailwindcss.js
├── data/
└── 金桥机房电路表.xlsx
```

## 首次安装

1. 把整个 `SubSentry` 文件夹复制到 Windows 电脑。
2. 确认 `金桥机房电路表.xlsx` 位于 `SubSentry` 根目录。
3. 如果电脑只有 Python 3.6，先双击运行 `install_python_312.bat`。
4. 双击运行 `install_offline_deps.bat`。脚本会在当前目录创建本地 `.venv`，不会改动系统 Python 环境。
5. 双击运行 `check_env.bat`。
6. 双击运行 `start.bat`。
7. 浏览器访问 `http://127.0.0.1:8080`。

## 局域网访问

如果其他电脑需要访问：

1. 在 Windows 电脑运行 `ipconfig`，找到本机 IPv4 地址。
2. 其他电脑访问 `http://Windows电脑IP:8080`。
3. 如果打不开，需要在 Windows 防火墙中允许 Python 访问专用网络，或放通 TCP 8080。

## 故障状态文件

系统运行状态保存在：

```text
data/fault_state.json
```

升级版本时不要覆盖这个文件，否则当前故障记录会丢失。

## 回退原则

每个正式发布包都应对应一个 Git 标签。回退时使用对应版本的部署包覆盖程序文件，但保留：

- `金桥机房电路表.xlsx`
- `data/fault_state.json`

## 常见问题

### Python 版本过低

运行：

```bat
python --version
```

如果低于 3.8，需要先安装更高版本 Python，或更换电脑。

本发布包内置 Python 3.12.10 Windows 64 位安装程序。电脑只有 Python 3.6 时，先运行：

```bat
install_python_312.bat
```

### 页面没有样式或按钮无反应

检查以下文件是否存在：

```text
static/vendor/alpine.min.js
static/vendor/tailwindcss.js
```

离线部署不能依赖外网 CDN。

### 缺少 Flask/openpyxl

运行：

```bat
install_offline_deps.bat
```

如果仍失败，说明 `wheels/` 离线依赖包不完整。

### 出现 `'raise' 不是内部或外部命令`

这是旧版部署脚本在 Windows CMD 中解析 `python -c` 命令时触发的问题。请使用 `v2026.05.06-windows-offline-r2` 或更新版本。

### Python 3.9 提示缺少 `importlib-metadata`

这是 Python 3.9 使用 Flask 2.3 时需要的条件依赖。请使用 `v2026.05.06-windows-offline-r3` 或更新版本。
