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
├── requirements.txt
├── install_offline_deps.bat
├── check_env.bat
├── start.bat
├── stop_subsentry.bat
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
3. 双击运行 `install_offline_deps.bat`。
4. 双击运行 `check_env.bat`。
5. 双击运行 `start.bat`。
6. 浏览器访问 `http://127.0.0.1:8080`。

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
