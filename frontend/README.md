# Ops Intel Agent 控制台（前端）

Vue 3 + Vite + Naive UI 的单页应用，提供：

- **概览 Dashboard** —— 告警 / 知识库统计 + 后端就绪状态
- **告警消息 Alerts** —— 多维筛选（关键词、处理状态、匹配状态、服务、**精确日期**）+ 诊断报告详情
- **知识库 Knowledge** —— 两种检索模式：
  - **向量模糊搜索**：自然语言查询，按余弦相似度排序
  - **按日期 / 列表**：精确日期 / 日期范围 / 错误类型 / 关键词过滤

## 开发

```bash
# 1. 启动后端（终端 A，默认监听 8000）
cd .. && make run

# 2. 启动前端（终端 B，监听 5174，自动代理 API 到 :8000）
cd frontend
npm install
npm run dev
# 打开 http://localhost:5174
```

## 生产构建

```bash
npm run build      # 产物输出到 frontend/dist
```

构建后，FastAPI 会在启动时检测 `frontend/dist`（由 `OIA_FRONTEND_DIR` 控制，默认即此路径）并将其挂载到 `/`，
实现单端口部署：访问 `http://localhost:8000/` 直接得到前端界面，API 仍在 `/alerts`、`/knowledge` 等路径。

> 路由使用 **hash history**（`/#/alerts`），因此前端页面路由不会与后端 API 路径冲突。

## 配置

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `OIA_API_URL` | `http://localhost:8000` | 仅 `npm run dev` 时 Vite 代理目标 |
