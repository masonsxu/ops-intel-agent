# Ops Intel Agent · 智能运维诊断 Agent

> 把高级工程师的经验“固化”进系统：当服务器异常发生时，自动检索历史相似案例，
> 用 **RAG + LLM** 同时产出一份 **给用户的大白话通知** 和一份 **给一线运维的排查 Playbook**，
> 并把工程师每次的处置沉淀回向量知识库——**系统越用越聪明**。

[![tests](https://img.shields.io/badge/tests-16%20passing-brightgreen)]()
[![python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![license](https://img.shields.io/badge/license-MIT-lightgrey)]()

---

## 目录
- [它解决什么问题](#它解决什么问题)
- [系统架构](#系统架构)
- [核心设计决策：可插拔后端](#核心设计决策可插拔后端)
- [快速开始（零依赖离线运行）](#快速开始零依赖离线运行)
- [知识闭环：系统如何“越用越聪明”](#知识闭环系统如何越用越聪明)
- [API 参考](#api-参考)
- [生产部署（OpenAI + pgvector + 企业微信）](#生产部署openai--pgvector--企业微信)
- [配置项一览](#配置项一览)
- [项目结构](#项目结构)
- [测试](#测试)
- [扩展点](#扩展点)

---

## 它解决什么问题

| 痛点 | 本系统的解法 |
| --- | --- |
| 高级工程师被重复打扰同一类老问题 | 历史经验进向量库，**秒级 RAG 匹配**，直接给出 Playbook |
| 用户看不懂报错，一线又要“翻译”一遍 | LLM 一次性产出 **用户大白话** + **工程师行动指南** 双版本 |
| 故障知识散落在工单/聊天记录里，无法复用 | **闭环沉淀**：工程师一句话处置 → 自动结构化进知识库 |
| 数据库抖动导致 10 个微服务同时刷屏 | **滑窗聚合**：相似告警合并成一条通知 |
| 重启能解决 90% 的故障，却还要打电话 | **Function Calling 按钮**：一键触发自动化脚本 |

---

## 系统架构

```
                          ┌─────────────────────────────────────────┐
   服务器异常日志 ───────▶ │  POST /alerts                           │
   (监控/Log Agent)        │  ① 日志解析 (extractors/log_parser)     │
                          │  ② 向量化 (EmbeddingProvider)           │
                          └────────────────┬────────────────────────┘
                                           ▼
                          ┌─────────────────────────────────────────┐
                          │  ③ RAG 检索 (VectorStore.search top-K)  │
                          │     memory / pgvector 可切换            │
                          └────────────────┬────────────────────────┘
                                           ▼
              相似度 ≥ 阈值? ──── 是 ──▶ matched   (走历史经验)
                  │                              │
                  └──── 否 ──▶ new_incident      ▼
                          ┌─────────────────────────────────────────┐
                          │  ④ LLM 编排 (prompts/templates)         │
                          │     ▸ 大白话翻译   ▸ 用户行动            │
                          │     ▸ 工程师 Playbook ▸ 动作建议         │
                          └────────────────┬────────────────────────┘
                                           ▼
                          ┌─────────────────────────────────────────┐
                          │  ⑤ 通知 (Notifier) + 动作按钮           │
                          │     console / 企业微信 / 钉钉           │
                          └────────────────┬────────────────────────┘
                                           ▼
   工程师处置后 ─────────▶  POST /knowledge/depositions  (闭环沉淀)
                           ▸ LLM 把口语化处置结构化
                           ▸ 写入知识库 + 向量库
                           ▸ 下次同类故障 → 秒级精准匹配
```

**端到端数据流：** `raw log → 解析 → 向量化 → RAG 检索 → LLM 双版本生成 → 通知 + 动作按钮`，外加一条 `处置 → 结构化 → 入库` 的闭环。

---

## 核心设计决策：可插拔后端

每一个外部依赖都抽象成了接口，**同一份代码既能在笔记本上零依赖跑通**（用于评估/演示），**也能切到生产级后端**（只需改环境变量）。这是本项目最关键的架构选择：

| 能力 | 接口 | 离线实现（默认） | 生产实现 |
| --- | --- | --- | --- |
| 向量化 | `EmbeddingProvider` | `LocalEmbeddingProvider`（字符 n-gram 哈希，确定性，语义可分） | `OpenAIEmbeddingProvider`（text-embedding-3-small） |
| 大模型 | `LLMProvider` | `LocalLLMProvider`（模板，遵循相同 Markdown 契约） | `OpenAILLMProvider`（gpt-4o-mini） |
| 向量库 | `VectorStore` | `MemoryVectorStore`（numpy 余弦，**磁盘持久化**） | `PgVectorStore`（PostgreSQL + pgvector） |
| 通知 | `Notifier` | `ConsoleNotifier`（打印） | `WeChatNotifier` / `DingTalkNotifier` |
| 动作 | `ActionRegistry` | 内置 5 个安全 no-op 动作 | 接 Ansible / kubectl / 内部 Runbook |

> **离线模式为什么“真实可用”？** LocalEmbedding 用字符三元组哈希产生向量，相似异常（共享词根/三元组）的余弦相似度天然更高——所以 Redis 超时类日志会稳定命中 Redis 历史案例；LocalLLM 严格输出与真实 LLM 相同的三段式 Markdown，下游解析路径完全一致。这意味着你可以**不花一分钱 API 费、不装数据库**就把整条链路验证完。

---

## 快速开始（零依赖离线运行）

```bash
# 1. 安装依赖（默认就是离线模式）
make install            # 等价于: uv sync

# 2. 初始化演示知识库（3 条真实故障案例）
make seed               # uv run python scripts/seed_demo.py
#   ✓ seeded #1: Redis 连接超时导致登录态丢失
#   ✓ seeded #2: 支付服务数据库连接池耗尽
#   ✓ seeded #3: 网关服务 JVM Old 区溢出
#   Done. 3 vectors in 'knowledge' namespace.

# 3. 启动 API 服务（离线模式）
make run                # uvicorn ... --reload --port 8000

# 4. 另开一个终端，触发告警看效果
make demo               # 种子 + 触发 3 条告警（含 1 条全新故障）
```

你会看到每条告警被分类为 `matched`（命中历史）或 `new_incident`（首次出现），并打印出三段式通知。

**最快的一键体验（不开服务，直接跑完整链路）：**

```bash
make seed && uv run python scripts/fire_demo_alert.py
# 看到 auth/orders 告警 matched（sim≈0.9 / 0.87），recommend 告警 new_incident
```

---

## 知识闭环：系统如何“越用越聪明”

这是把“高级工程师经验”沉淀下来的核心机制，4 步，**全程无需人工整理**：

```bash
# ① 触发一条全新故障（无历史匹配）
curl -X POST localhost:8000/alerts -H 'Content-Type: application/json' -d '{
  "service":"rec","raw_log":"ERROR GPU memory fragmentation in inference-engine v3.2"
}'
# → {"match_status":"new_incident","similarity_score":0.43,"id":1}

# ② 工程师处置后，留下一句口语化记录
curl -X POST localhost:8000/knowledge/depositions -H 'Content-Type: application/json' -d '{
  "alert_id":1,"error_type":"GPU 显存碎片化",
  "root_cause":"推理引擎 v3.2 未限制 tensor cache 上限，显存碎片化导致 layer 47 缓存损坏",
  "resolution":"回滚 inference-engine 到 v3.1 并设置 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
  "engineer":"bob","tags":["gpu","inference"]
}'
# → LLM 自动生成 user_guide / engineer_guide，写入知识库 + 向量库

# ③ 同一故障再次发生 —— 秒级精准命中，无需任何人介入
curl -X POST localhost:8000/alerts -H 'Content-Type: application/json' -d '{
  "service":"rec","raw_log":"ERROR GPU memory fragmentation in inference-engine v3.2"
}'
# → {"match_status":"matched","similarity_score":1.0,"matched_knowledge_id":2}
#   通知里直接带上工程师当初写的处置步骤
```

闭环一旦建立，**第 N+1 次故障的处置成本趋近于零**。

---

## API 参考

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/alerts` | 摄取异常告警，跑完整 triage 流水线，返回告警 + 诊断报告 |
| `GET`  | `/alerts` `?limit=&status_filter=` | 列出近期告警 |
| `GET`  | `/alerts/{id}` | 告警详情（含报告） |
| `GET`  | `/knowledge` `?limit=` | 列出知识库条目（按命中次数降序） |
| `POST` | `/knowledge` | 手动新增知识条目 |
| `POST` | `/knowledge/depositions` | **闭环入口**：工程师处置 → 结构化入库 |
| `DELETE` | `/knowledge/{id}` | 软删除知识条目（同步从向量库移除） |
| `GET`  | `/actions` | 列出可用的自动化动作 |
| `POST` | `/actions/invoke` | 执行动作（如一键重启），写审计记录 |
| `GET`  | `/health` `/ready` | 存活 / 就绪探针（含向量库计数） |

交互式文档：启动后访问 `http://localhost:8000/docs`（Swagger UI）。

`POST /alerts` 的响应里，`report` 字段就是机器人生成的通知内容：

```jsonc
{
  "id": 1, "match_status": "matched", "similarity_score": 0.935,
  "matched_knowledge_id": 1,
  "report": {
    "matched": true,
    "best_similarity": 0.935,
    "plain_language": "后台缓存服务（Redis）出现了短暂故障……",  // 给用户
    "user_actions": "如情况紧急，请回复 '1' 触发自动重启……",      // 给用户
    "engineer_guide": "1. 检查 10.0.1.2 上 redis 容器……",          // 给 SRE
    "suggested_actions": [                                        // 按钮
      {"name":"clear_cache","label":"清空缓存","risk_level":"low"},
      {"name":"restart_service","label":"一键重启服务","risk_level":"low"}
    ],
    "retrieval": [                                                // RAG 命中
      {"knowledge_id":1,"title":"Redis 连接超时…","similarity":0.94},
      ...
    ]
  }
}
```

---

## 生产部署（OpenAI + pgvector + 企业微信）

```bash
# 1. 启动 PostgreSQL + pgvector（docker-compose 已备好）
docker compose up -d pgvector

# 2. 安装生产后端依赖
uv sync --extra prod

# 3. 配置环境变量
cat > .env <<'CFG'
OIA_EMBEDDING_PROVIDER=openai
OIA_LLM_PROVIDER=openai
OIA_VECTOR_STORE=pgvector
OIA_NOTIFIER_PROVIDER=wechat
OPENAI_API_KEY=sk-...
OIA_DATABASE_URL=postgresql+asyncpg://ops:ops@localhost:5432/ops
OIA_PG_CONNECTION_STRING=postgresql://ops:ops@localhost:5432/ops
OIA_WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
CFG

# 4. 启动
make run
```

切换到生产模式后，向量维度自动从离线的 256 升到 1536（OpenAI 维度），Embedding/LLM 走真实 OpenAI API，向量库走 pgvector 的 HNSW 索引，通知发到企业微信群。**业务代码一行不改。**

> **钉钉用户：** 把 `OIA_NOTIFIER_PROVIDER=dingtalk` 并配置 `OIA_DINGTALK_WEBHOOK` + `OIA_DINGTALK_SECRET` 即可，签名已内置。

---

## 配置项一览

所有配置走环境变量（前缀 `OIA_`），完整列表见 [`.env.example`](.env.example)。最常用的：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `OIA_EMBEDDING_PROVIDER` | `local` | `local` / `openai` |
| `OIA_LLM_PROVIDER` | `local` | `local` / `openai` |
| `OIA_VECTOR_STORE` | `memory` | `memory` / `pgvector` |
| `OIA_NOTIFIER_PROVIDER` | `console` | `console` / `wechat` / `dingtalk` |
| `OIA_SIMILARITY_TOP_K` | `3` | RAG 检索条数 |
| `OIA_SIMILARITY_THRESHOLD` | `0.78` | ≥ 此值判为 matched，否则 new_incident |
| `OIA_ACTION_CONFIDENCE_THRESHOLD` | `0.85` | 高于此置信度才挂“危险动作”按钮 |
| `OIA_AGGREGATION_WINDOW_SECONDS` | `300` | 告警聚合窗口 |
| `OIA_AGGREGATION_MIN_CLUSTER_SIZE` | `2` | 聚合成一条通知的最小告警数 |

---

## 项目结构

```
ops-intel-agent/
├── ops_intel_agent/
│   ├── main.py                  # FastAPI 应用 + lifespan
│   ├── config.py                # pydantic-settings，全部后端选择开关
│   ├── extractors/log_parser.py # 把原始日志解析成 结构化字段 + canonical text
│   ├── prompts/templates.py     # ★ 提示词工程：三段式契约 + 解析器
│   ├── core/
│   │   ├── pipeline.py          # ★ 端到端 triage 编排
│   │   ├── aggregator.py        # 滑窗告警聚合（避免群轰炸）
│   │   └── deposition.py        # ★ 知识闭环：处置 → 入库
│   ├── services/
│   │   ├── embeddings/          # base / local / openai
│   │   ├── llm/                 # base / local / openai
│   │   ├── vectorstore/         # base / memory / pgvector
│   │   ├── notifier/            # base / console / wechat / dingtalk
│   │   └── actions/             # Function Calling 动作注册表
│   ├── api/                     # alerts / knowledge / actions / health 路由
│   ├── models/                  # SQLAlchemy: 知识库 / 告警 / 动作审计
│   └── schemas/                 # Pydantic I/O 模型
├── scripts/                     # seed_demo.py / fire_demo_alert.py
├── tests/                       # 16 个测试，全离线，0.2s 跑完
├── docker-compose.yml           # PostgreSQL + pgvector
└── Makefile                     # install/run/seed/demo/test/lint
```

---

## 测试

```bash
make test     # uv run pytest -q   → 16 passed in ~0.2s
make lint     # ruff check + format check
```

测试**完全离线**运行：用 in-memory SQLite + 磁盘隔离的内存向量库 + Local LLM，覆盖了日志解析、向量相似度、RAG 匹配/阈值、动作建议、闭环沉淀、API 全链路。

---

## 扩展点

- **接入真实自动化：** 在 `services/actions/builtin.py` 里把 no-op 实现换成 Ansible/kubectl 调用，即可让“一键重启”真正生效。
- **多副本部署：** 把 `AlertAggregator` 的内存 dict 换成 Redis，聚合即可跨实例共享。
- **按钮交互回调：** 企业微信/钉钉的卡片消息按钮回调接 `/actions/invoke`，实现用户点按钮 → 触发脚本。
- **知识库审核：** deposition 默认 `source=engineer:xxx`，可在管理后台加一道审核才 `is_active=True`。
- **更多向量库：** 实现 `VectorStore` 接口即可接入 Milvus / Qdrant / Pinecone。

---

## License

MIT
