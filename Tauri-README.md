# 桌面应用（Tauri）打包指南

把 **前端（Vue 3 SPA）+ 后端（FastAPI）** 打包进一个 Tauri 桌面应用。

## 架构

```
┌──────────────────────────────────────────────────────┐
│  Tauri 桌面应用（Rust shell）                         │
│                                                       │
│  ┌───────────────┐         ┌────────────────────┐    │
│  │  WebView       │  axios  │  子进程：后端        │    │
│  │  (Vue SPA)     │────────▶│  FastAPI :8000      │    │
│  │  → 127.0.0.1   │         │  Nuitka 编译的独立   │    │
│  │    :8000       │         │  二进制（无需 Python）│    │
│  └───────────────┘         └────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

- **前端**：`frontend/dist` 由 Tauri WebView 加载（`build.frontendDist`），无需后端托管。
- **后端**：作为本地子进程监听 `127.0.0.1:8000`。
  - **发行模式**：Rust 启动 `resources/binaries/ops-intel-agent-backend/ops-intel-agent-backend`（Nuitka `--standalone` 编译，自带 Python 运行时与全部依赖）。
  - **开发模式**：未编译二进制时，自动回退到 `uv run uvicorn ...`（需要本机有 uv + 仓库）。
- **数据目录**：SQLite、chroma_db、vectors.json 全部写入应用数据目录（见下），不污染安装目录。

## 前置依赖

```bash
# Rust + Tauri CLI（>=2.0）
rustup default stable
cargo install tauri-cli --version "^2.0"

# 前端
cd frontend && npm install        # 或 bun install

# Python（运行/打包后端时需要）
uv sync
```

## 开发模式（热重载）

```bash
make tauri-dev
# 等价于：cargo tauri dev
```

- Vite 在 `:5174`（devUrl）提供前端；Rust 同时用 `uv run uvicorn` 拉起后端 `:8000`。
- 「设置」页可填 OpenAI Key 并点「重启后端」生效（重启会读取新的 settings.json）。

## 发行打包（三步）

### 1. 生成图标（首次或更换 Logo 时）

准备一张 **≥1024×1024 的 PNG** 放到 `src-tauri/source-icon.png`，然后：

```bash
make tauri-icons      # cargo tauri icon src-tauri/source-icon.png
```

会生成 `src-tauri/icons/` 下全部所需尺寸（含 `.icns` / `.ico`）。

### 2. 编译后端为独立二进制（Nuitka `--standalone`）

```bash
make backend-binary
# uv run --with nuitka scripts/build_backend.py
# 输出：src-tauri/binaries/ops-intel-agent-backend/
```

- 默认 `--standalone`（文件夹）：对 chromadb / onnxruntime 这类重原生依赖**最可靠**，启动快。
- 想要单文件可执行：`uv run --with nuitka scripts/build_backend.py --onefile`（每次启动需解压到临时目录，较慢，且 chromadb 偶有兼容问题）。
- **Nuitka 不能交叉编译**：macOS 上只能打 macOS 包，Windows 上打 Windows 包，需分别在目标平台运行。
- 默认包含 chromadb + onnxruntime，体积约 100–200MB。若确定只用内存向量库，可在脚本里移除 `--include-package=chromadb` / `onnxruntime` 瘦身。

### 3. 构建安装包

```bash
make tauri-build      # 先跑 backend-binary，再 cargo tauri build --release
```

产物位于 `src-tauri/target/release/bundle/`：

| 平台    | 格式                |
|---------|---------------------|
| macOS   | `.app` / `.dmg`     |
| Windows | `.msi` / `.exe`(NSIS)|
| Linux   | `.deb` / `.AppImage`|

## 配置与数据目录

- **设置**：`settings.json` 存于应用数据目录
  - macOS：`~/Library/Application Support/com.opsintel.agent/`
  - Windows：`%APPDATA%\com.opsintel.agent\`
  - Linux：`~/.config/com.opsintel.agent/`
- **离线模式**：清空 OpenAI API Key → 自动使用本地 embedding（256 维字符 n-gram）+ 本地 LLM 模板，无需联网。
- **向量库默认 chroma**：本项目把自算的 embedding 存入 chroma，不会触发 chroma 默认 embedding 的 ONNX 模型下载，因此离线可用。

## 常见问题

- **页面一直显示「连接中…」**：后端没起来。看 Rust 日志；发行包是否跑过 `make backend-binary`？资源里是否包含 `binaries/ops-intel-agent-backend/`？
- **`tauri build` 报找不到图标**：先 `make tauri-icons`。
- **macOS「无法打开，来自身份不明的开发者」**：未签名。右键 → 打开，或在 系统设置 → 隐私与安全性 中允许。
- **`sidecar failed to load` / 找不到后端二进制**：确认 `make backend-binary` 已执行，且 `tauri.conf.json → bundle.resources` 包含 `binaries/ops-intel-agent-backend/**`（已默认配置）。
- **改了设置后前端没刷新数据**：当前实现需手动点「重启后端」，Rust 侧未监听文件变化。

> 桌面模式面向个人学习与演示，不建议直接用于生产或大规模部署。
