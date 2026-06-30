# 桌面应用打包实战笔记（Tauri + Nuitka）

把「FastAPI 后端 + Vue 前端」打包成桌面应用的全过程记录。重点是**不会出现在官方文档里**的踩坑与解法，以及关键设计决策的理由。配套实现见 `Tauri-README.md`、`scripts/build_backend.py`、`src-tauri/`、`.github/workflows/`。

---

## 1. 架构选型

```
Tauri Rust shell（单进程）
 ├─ WebView ── 加载 frontend/dist（Vue SPA，由 Tauri 内嵌，不走后端）
 └─ 子进程 ── Contents/Resources/binaries/ops-intel-agent-backend/ops-intel-agent-backend
             （Nuitka --standalone，自带 Python 运行时 + chromadb + onnxruntime）
             监听 127.0.0.1:8000；前端 axios 直连
```

数据（SQLite、chroma_db、vectors.json）一律写入应用数据目录，不污染安装目录：
- macOS：`~/Library/Application Support/com.opsintel.agent/`
- Windows：`%APPDATA%\com.opsintel.agent\`
- Linux：`~/.config/com.opsintel.agent/`

### 1.1 为什么后端用 Nuitka（而非 PyInstaller）

用户指定。两者都能把 Python 编译成独立二进制，对比：

| 维度 | Nuitka | PyInstaller |
|------|--------|-------------|
| 原理 | 编译成 C 再链接 | 字节码 + 解释器打包 |
| 启动速度 | 快（原生） | onefile 慢（每次解压到 temp） |
| 重依赖（chromadb/onnxruntime） | 需手动调参，但可控 | hook 体系成熟，偶发更黑盒 |
| 体积 | 相近（都受 chromadb 拖累，~250MB exe） | 相近 |

结论：选 Nuitka 没问题，但 chromadb + onnxruntime 是真正的体积与兼容性瓶颈（与工具无关）。

### 1.2 为什么 `--standalone`（而非 `--onefile`）

`--onefile` 把所有库塞进单文件，每次启动解压到临时目录——对 chromadb/onnxruntime 这种大量原生库 + 数据文件的依赖**又慢又脆**。`--standalone` 产出文件夹，库就地加载，启动快、可靠性高。代价是「二进制」是一个文件夹而非单文件，用 `bundle.resources` 整体打进 app 即可。

### 1.3 为什么 `bundle.resources` + `std::process::Command`（而非 `externalBin`）

`externalBin`（Tauri 官方 sidecar 方案）要求**单文件** + `tauri-plugin-shell` 启动，与 `--onefile` 绑定。我们用 `--standalone` 文件夹，改用：

- `tauri.conf.json` → `bundle.resources: ["binaries/ops-intel-agent-backend/**/*"]` 把整个文件夹打进 app；
- Rust 侧 `std::process::Command::new(resource_dir()/binaries/.../ops-intel-agent-backend)` 启动；
- 免装 shell 插件、免 capability 配置，路径解析自己掌控。

---

## 2. 踩坑实录（按发现顺序，每条都附解法）

### 坑 1 · `src-tauri/icons/` 为空 → `tauri build` 直接失败

Tauri 必须有图标才能打包。`cargo tauri icon <源图>` 一键生成全平台图标集。
**解法**：准备一张 ≥1024×1024 的 PNG（`src-tauri/source-icon.png`），`make tauri-icons`。

### 坑 2 · `frontendDist` 路径是相对 `src-tauri/`

`tauri.conf.json` 里的路径相对 `src-tauri/`（即 `tauri.conf.json` 所在目录），不是仓库根。
**解法**：`"frontendDist": "../frontend/dist"`。

### 坑 3 · Tauri v2 默认**不**注入 `window.__TAURI__`

前端用 `window.__TAURI__` 检测桌面环境，在 v2 里恒为 `undefined`，导致「设置」页保存/重启后端**静默失效**。v2 注入的是 `window.__TAURI_INTERNALS__`（`@tauri-apps/api/core` 的 `invoke` 走它）。
**解法**：检测改为 `'__TAURI_INTERNALS__' in window`，无需开 `withGlobalTauri`。

### 坑 4 · `time 0.3.52` 破坏 `cookie 0.18.1`（传递依赖冲突）

`tauri/wry` 依赖 `cookie 0.18.1`，它调用 `format.parse(s.as_bytes())`（1 参）。`time` 在 0.3.5x 把 `Parsable::parse` 改成 2 参（小版本内破坏兼容），cargo 解析到最新的 `time 0.3.52` 就编译失败。同时 `plist 1.9.0` 要求 `time >= 0.3.47`。
**解法**：`cargo update -p time --precise 0.3.47`（满足 plist 下界、又是 1 参 parse 的最后版本），把 `src-tauri/Cargo.lock` 提交进仓库锁定。

### 坑 5 · Tauri `resources` 的 `**` 不匹配顶层文件

`"binaries/ops-intel-agent-backend/**"` 在 Tauri 用的 `glob` crate 里**不匹配**目录下的顶层文件（只匹配子层）。于是编译期 `generate_context!` 校验资源 glob 报「path not found」，连带 `cargo check` 都失败。且**目录不存在时同样报错**。
**解法**：
1. glob 改成 `"binaries/ops-intel-agent-backend/**/*"`（显式匹配文件）；
2. 提交一个占位 `README.md` 到该目录（`.gitignore` 忽略构建产物但保留 README），让目录恒存在——否则未编译 sidecar 时 `cargo tauri dev` 都会报错。

### 坑 6 · 直接编译 `ops_intel_agent/__main__.py` → 自己的 `logging.py` 遮蔽 stdlib（**最隐蔽**）

把 `ops_intel_agent/__main__.py` 当 Nuitka 入口直接编译，Nuitka 会把**包目录当源根**，把同目录的 `ops_intel_agent/logging.py` 提升为顶层 `logging.py`，**遮蔽 stdlib 的 `logging`**。于是入口里 `import logging` 加载到的是我们自己的文件 → 它 `import structlog` → `structlog.stdlib` 读 `logging.NOTSET` → 循环导入崩溃：

```
AttributeError: partially initialized module 'logging' has no attribute 'NOTSET'
```

Nuitka 早就警告过：「编译带 `__main__` 的包时，应指定包目录而非 `__main__.py` 本身」。
**解法**：新建**位于包外**的入口 `backend_entry.py`（仓库根），内容仅 `from ops_intel_agent.__main__ import main; main()`。Nuitka 编译它时 `ops_intel_agent` 作为正常包被引入，`import logging` 正确解析到 stdlib，我们的模块留在 `ops_intel_agent.logging` 命名空间。

> 教训：**别在会被扁平化的包里给模块起 stdlib 的名字**（`logging`、`config`、`types` 等）。即便正常 Python 不冲突（绝对导入），打包扁平化时会出问题。

### 坑 7 · Nuitka 4.x 没有 `pydantic` 插件

老教程都写 `--enable-plugin=pydantic`，4.x 直接 `FATAL: unknown plug-in 'pydantic'`。pydantic v2 的 rust core 现由 Nuitka 的自动包支持处理。
**解法**：删掉该选项，改 `--include-package=pydantic --include-package=pydantic_core` 显式强制包含。

### 坑 8 · dev 工具（mypy/pytest）被 `chromadb.test` 拖进编译

`--include-package=chromadb` 会把它的 `chromadb.test` 子包也扫进来，进而拉入 `pytest`、`mypy` 等 dev 工具——二进制膨胀、C 编译变慢，且运行时根本用不到。
**解法**：
```
--nofollow-import-to=chromadb.test
--nofollow-import-to=pytest
--nofollow-import-to=mypy
--nofollow-import-to=ruff
--nofollow-import-to=respx
```

### 坑 9 · `dmg` 偶发 `bundle_dmg.sh` / `hdiutil` 失败

macOS 打 `.dmg` 时 `hdiutil detach` 偶发 "Resource busy"（Spotlight/fsevents 碰了挂载卷），大包更易触发。
**解法**：**重试**即可（基本第二次就过）。`.app` 本身才是交付物，`.dmg` 只是分发格式。

### 坑 10 · `cargo tauri build --bundles dmg`（仅 dmg）会清理 `.app`

只打 dmg 时，Tauri 成功后会把 `.app` 删掉。想要两者并存就用默认的全量 `cargo tauri build`（app+dmg 都生成，且失败也不清理 app）。

### 坑 11 · `beforeBuildCommand` 的 CWD 已是 `frontend/`

实测：Tauri 根据 `frontendDist` 推导出前端目录，**自动 cd 进去**再跑 `beforeBuildCommand`。所以命令里**不要**再 `cd`（`cd ../frontend` 反而跳错位置）。
**解法**：`"beforeBuildCommand": "npm run build"`（裸命令）。
> 验证小技巧：把命令临时设成 `pwd > /tmp/x; exit 1`，跑一次 `cargo tauri build` 看 tauri 实际在哪个目录执行。

### 坑 12 · `__main__.py` 的相对导入在编译入口下失效

`from .config import ...` 在 `python -m ops_intel_agent`（有包上下文）下 OK，但作为 Nuitka 编译入口（`__main__` 无包上下文）会失败。
**解法**：`__main__.py` 全部用**绝对导入** `from ops_intel_agent.config import ...`，两种运行方式都稳。

---

## 3. 构建 / 发布流程

### 本地

```bash
make tauri-icons      # 换 Logo 时：cargo tauri icon src-tauri/source-icon.png
make backend-binary   # Nuitka 编 sidecar（默认增量；--clean 全量）
make tauri-dev        # 开发：Vite + uv 后端
make tauri-build      # 发行：先编 sidecar，再 cargo tauri build
```

产物：`src-tauri/target/release/bundle/` 下的 `.app`/`.dmg`（mac）、`.msi`/`.exe`（win）、`.deb`/`.AppImage`（linux）。

### CI / 发布（`.github/workflows/desktop.yml`）

- **push 到 main / PR**：4 平台矩阵（macos-arm64、macos-x86_64、windows、linux）并行构建，产物作为 workflow artifact 上传，供下载验证。
- **push tag `v*`**：同样构建，再把各平台包附加到 GitHub Release。
- 手动 `workflow_dispatch` 也可触发。

发版：`git tag v0.1.0 && git push origin v0.1.0`，CI 自动出包并挂到 Release。

---

## 4. 维护清单

| 场景 | 操作 |
|------|------|
| 换应用图标 | 替换 `src-tauri/source-icon.png`（≥1024²），`make tauri-icons`，提交 `icons/` |
| 后端加 Python 依赖 | `uv add <pkg>`；若它有原生库/数据文件，在 `scripts/build_backend.py` 加 `--include-package=<pkg>` 或 `--include-data-dir=` |
| 改 Rust 端的依赖 | 改 `src-tauri/Cargo.toml`，**提交 `Cargo.lock`**（保住 time=0.3.47 等锁定） |
| 瘦身 | 确定不用 chroma：删 `--include-package=chromadb/onnxruntime`，桌面默认改 `vector_store=memory`（Rust `AppSettings::default`） |
| 跨平台分发 | Nuitka **不能交叉编译**，每个目标平台需在该平台的 CI runner 上构建（矩阵已覆盖） |
| Windows 未签名警告 | 用户右键 → 打开；或配置代码签名证书后加 `bundle.windows.certificateThumbprint` 等 |
| macOS 未签名 | 首次右键打开，或系统设置 → 隐私与安全性放行 |

---

## 5. 体积参考（aarch64-apple-darwin）

| 组件 | 体积 |
|------|------|
| Nuitka sidecar 可执行 | ~250 MB |
| sidecar 文件夹（含 chromadb/onnxruntime 库） | ~423 MB |
| `.app` 总大小 | ~432 MB |
| `.dmg`（压缩后） | ~125 MB |

大头是 `chromadb` + `onnxruntime`。本项目里 chroma 只做向量存取（embedding 由项目自己算），不触发 ONNX 模型下载，离线可用。
