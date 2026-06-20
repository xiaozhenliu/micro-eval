# AgentBeats 调研报告

> 调研日期：2026-06-20
> 来源：官方文档 (docs.agentbeats.dev)、GitHub (github.com/agentbeats)、Berkeley RDI 竞赛页

---

## 1. 项目概览

**AgentBeats** 是由 UC Berkeley RDI (Responsible Decentralized Intelligence) Center 开发的开源 Agent 评测平台，基于 **Agentified Agent Assessment (AAA)** 范式。

核心理念：用专门的 **评估 Agent（assessor agent）** 来评测其他 **被评估 Agent（assessee agent）**，而非传统的固定 harness 方式。

- 官网：https://agentbeats.dev/
- 文档：https://docs.agentbeats.dev/
- GitHub 组织：https://github.com/agentbeats （12 个仓库）
- 主仓库：https://github.com/agentbeats/agentbeats （标注 DEPRECATED，新版即将发布）

## 2. 解决的问题

传统 Agent benchmark（SWE-Bench、Tau-Bench、BrowserGym 等）的三个核心限制：

| 问题 | 描述 |
|------|------|
| LLM-centric harness | 固定的测试框架难以评估不同工作流/控制循环/架构的 agent |
| 高集成成本 | 每个 benchmark 需要大量自定义集成 |
| 测试-生产不对齐 | 测试环境与生产部署行为不匹配，结果不可信 |

## 3. 核心概念

### 3.1 AAA 框架 (Agentified Agent Assessment)

"让 agent 评测 agent"——评估本身由专门的 agent 执行，而非静态脚本或固定 harness。

### 3.2 Agent 角色

| 角色 | 颜色代号 | 职责 |
|------|---------|------|
| **Green Agent** | 🟢 | 评估编排者：定义评测环境、发放任务、收集结果、计算指标。相当于"裁判+赛场" |
| **Purple Agent** | 🟣 | 被评估者：具备特定能力（coding、web use 等），接受评测任务并执行 |
| **Blue Agent** | 🔵 | 防御者（特定场景，如 prompt injection 防御） |
| **Red Agent** | 🔴 | 攻击者（特定场景，如 prompt injection 攻击） |

### 3.3 通信协议

- **A2A (Agent-to-Agent)** — Google 的 agent 间通信标准，用于任务分发和结果上报
- **MCP (Model Context Protocol)** — 标准化工具和资源访问

任何同时实现 A2A + MCP 的 agent 都可以直接参与评测，无需针对特定 benchmark 做适配。

## 4. 平台架构

```
┌─────────────────────────────────────────────┐
│              AgentBeats Platform             │
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │ Agent    │  │ Assessment│  │ Leaderboard│ │
│  │ Registry │  │ Runner   │  │ & Observ.  │ │
│  └──────────┘  └──────────┘  └───────────┘ │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │         GitHub Actions Runtime       │   │
│  │  ┌──────────┐    ┌──────────────┐    │   │
│  │  │ Green    │◄──►│ Purple       │    │   │
│  │  │ Agent    │A2A │ Agent        │    │   │
│  │  │ (Docker) │    │ (Docker)     │    │   │
│  │  └──────────┘    └──────────────┘    │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │  SDK (Python) + Agent Card (TOML)   │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### 关键基础设施

- **Agent Registry** — 注册和管理 green/purple agent
- **Assessment Runner** — 基于 GitHub Actions，Docker 容器化执行
- **Leaderboard** — DuckDB 查询驱动，结果 JSON 存于 GitHub 仓库
- **Observability** — 实时评测监控
- **SDK** — Python SDK (`pip install agentbeats`)

## 5. 技术栈

| 层 | 技术 |
|----|------|
| SDK | Python 3.11+, `agentbeats` PyPI 包 |
| 通信 | A2A protocol, MCP |
| 容器化 | Docker, GitHub Container Registry (GHCR) |
| 执行环境 | GitHub Actions (CI/CD runner) |
| 结果存储 | JSON 文件 + Git 仓库（single source of truth） |
| 查询 | DuckDB SQL over JSON |
| 配置 | TOML (agent card, scenario config) |
| 前端 | Web dashboard (agentbeats.dev) |

## 6. 工作流程

### 6.1 评测提交流程（Quick Submit）

1. 在 agentbeats.dev 注册 green agent（提供 Docker 镜像引用）
2. Fork leaderboard template 仓库
3. 安装 GitHub App 到 leaderboard 仓库
4. Purple agent 通过 Quick Submit 表单提交
5. 自动创建 PR → GitHub Actions 执行评测 → 合并 PR → 更新排行榜

### 6.2 本地测试流程（Manual Submit）

```bash
# 配置 scenario.toml
pip install tomli-w requests
python generate_compose.py --scenario scenario.toml
cp .env.example .env
mkdir -p output
docker compose up --abort-on-container-exit
```

### 6.3 Agent Card 格式（TOML）

```toml
name = "My Agent"
url = "http://YOUR_IP:PORT/"
```

## 7. AgentX-AgentBeats 竞赛

由 Berkeley RDI + Agentic AI MOOC（~4 万注册学员）联合举办，总奖金 **$1M+**。

### 阶段

| 阶段 | 时间 | 内容 |
|------|------|------|
| Phase 1 | 2025-10 → 2026-01 | 构建 green agent（评估器/benchmark） |
| Phase 2 | 2026-03 → 2026-06 | 构建 purple agent（参赛选手） |

### 评测赛道

Coding, Web/Computer Use, Research, Game, Finance, Cybersecurity, Healthcare, Legal, Agent Safety, Multi-agent, Business Process, DeFi

### 赞助商

DeepMind ($50k GCP/Gemini credits), Nebius ($50k inference), OpenAI ($10k/$5k/$1k per track), Lambda, Amazon (AWS credits), Snowflake, Hugging Face

## 8. 与 micro-eval 的对比分析

| 维度 | AgentBeats | micro-eval |
|------|-----------|------------|
| **定位** | 开放竞赛/学术评测平台 | 小团队内部评测决策工具 |
| **评测范式** | Agent 评 Agent (AAA) | 人工 + 自动评分混合 |
| **通信协议** | A2A + MCP (强制) | 无协议要求，stdin/文件传参 |
| **执行环境** | Docker + GitHub Actions (云端) | 本地 subprocess + git worktree |
| **目标用户** | 学术研究者、竞赛参与者、大规模 benchmark | 1-20 人 AI 小团队日常评测 |
| **隔离方式** | Docker 容器 | git worktree + OS sandbox (Seatbelt/Bubblewrap) |
| **结果展示** | 公开 Leaderboard | 本地矩阵对比页 |
| **评分** | green agent 自定义 | validation → LLM judge 分层 |
| **可复现性** | Docker 镜像 + GitHub Actions | SameStartSnapshot (workspace + toolchain fingerprint) |
| **多 agent** | 原生 A2A 多 agent | N×M 矩阵展开 |
| **成本** | 云端运行，需 Docker + GH Actions | 零基础设施，本地运行 |

### 可借鉴之处

1. **Agent Card (TOML) 格式** — 标准化的 agent 描述方式，micro-eval 的 AgentSpec 可以参考其结构
2. **DuckDB over JSON** — 轻量级结果查询方案，micro-eval 的 SQLite 索引策略与之类似
3. **Leaderboard 查询模式** — 自定义 SQL 查询驱动排行榜，可作为 micro-eval 趋势分析的参考
4. **评测赛道分类** — 其 benchmark 分类维度（coding/web/research/game 等）可作为 micro-eval 任务分类的参考

### 不适合 micro-eval 的部分

1. **A2A/MCP 强制协议** — micro-eval 面向任意 agent command，不应强制通信协议
2. **Docker + GitHub Actions** — micro-eval 强调零基础设施本地运行，Docker 违背设计约束
3. **Agent 评 Agent 范式** — micro-eval 的评分是 validation → LLM judge 分层，不需要额外的评估 agent
4. **公开 Leaderboard** — micro-eval 是团队内部工具，不需要公开排行榜

## 9. 相关资源

- 官方文档：https://docs.agentbeats.dev/
- GitHub 主仓库：https://github.com/agentbeats/agentbeats
- 教程仓库：https://github.com/agentbeats/tutorial
- Green Agent 模板：https://github.com/agentbeats/green-agent-template
- 竞赛页：https://rdi.berkeley.edu/agentx-agentbeats
- AAA 论文/概念：https://medium.com/@shikibuton10x/new-horizons-in-agent-evaluation-democratization-and-standardization-with-agentbeats-and-the-e43f432c686e
- Tau2 benchmark (green agent 示例)：https://github.com/RDI-Foundation/tau2-agentbeats
- DeoGaze (竞赛冠军)：https://github.com/RDI-Foundation/DeoGaze-agentbeats
