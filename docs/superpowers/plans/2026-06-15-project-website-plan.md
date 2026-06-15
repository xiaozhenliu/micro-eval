---
title: Project Website Plan
codename: project_site.v1
status: implemented
author: micro-eval
date: 2026-06-15
authority: docs/superpowers/specs/2026-06-02-unicorn-design.md (Part I), README.md, README.zh-CN.md
---

# Project Website Plan: `project_site.v1`

> micro-eval 需要一个专业的项目网站托管在 GitHub Pages 上，包含完整的面向用户的文档，帮助新用户学会使用本项目。本计划使用 VitePress 构建，定义站点结构、页面规划、内容来源、视觉设计和部署流程。

## 0. 目标与非目标

### 目标

1. 新用户在 10 分钟内理解 micro-eval 是什么、能解决什么问题、如何安装和运行第一个评测
2. 有经验的用户能快速查阅配置参考、CLI 命令、数据模型、API 路由
3. 网站外观专业，符合开源 AI 工具的定位，不像拼凑的 markdown 渲染
4. 中英双语（中文优先，英文作为国际受众入口）
5. 零运维成本：静态站点 + GitHub Pages + 自动部署

### 非目标

- 在线交互式 demo（需后端服务，不适合静态站点）
- 博客 / changelog 页面（changelog 留在 repo 即可）
- 社区论坛或评论系统
- 付费/商业化页面

## 1. 技术选型：VitePress

### 选择理由

| 维度 | VitePress | MkDocs Material |
|------|-----------|-----------------|
| 首页能力 | 内置 Hero + Feature Grid + Custom Layout | 需要 override 或自定义 HTML |
| 视觉质量 | Vue/Vite/Vitest 级别的现代感 | 偏工程文档风格 |
| 自定义组件 | Vue SFC，可嵌入交互式 demo | 受限于 Jinja2 macro |
| 代码高亮 | Shiki（VSCode 引擎），支持行高亮、diff | Pygments，功能稍弱 |
| 搜索 | 内置 MiniSearch 本地搜索，零配置 | 需配置 search plugin |
| 构建速度 | Vite，秒级 HMR | 中等 |
| 中文支持 | 原生 i18n routing（/zh/ 前缀） | 需 i18n plugin |
| 部署 | 官方 GitHub Actions 模板 | 官方 gh-deploy 命令 |
| 与项目技术栈关系 | UI 是 Next.js/TS，前端工具链相近 | Python 工具链匹配但 UI 定制弱 |

### 版本

- VitePress >= 1.6（当前稳定版）
- Node.js 18+

## 2. 站点结构

### 目录布局

```
site/                               # 站点根目录（独立于 docs/，不污染工程文档）
├── .vitepress/
│   ├── config.ts                   # VitePress 主配置（导航、侧边栏、i18n、主题）
│   └── theme/
│       ├── index.ts                # 主题入口（扩展默认主题）
│       ├── style/
│       │   └── custom.css          # 品牌色、字体、间距覆写
│       └── components/
│           ├── HomeHero.vue        # 自定义 Hero（可选，默认 Hero 足够时不需要）
│           └── FeatureCard.vue     # 自定义 Feature 卡片（可选）
├── public/
│   ├── logo.svg                    # 项目 logo
│   ├── og-image.png                # Open Graph 社交分享图
│   └── favicon.ico
├── index.md                        # 英文首页（Hero + Features）
├── guide/
│   ├── index.md                    # What is micro-eval?
│   ├── getting-started.md          # Installation + first run
│   ├── core-concepts.md            # 核心概念（Configuration, Task, Run, Decision）
│   ├── configuration.md            # eval.yaml 完整配置参考
│   ├── tasks.md                    # Task 定义、expectations、workspace、rubric
│   ├── execution.md                # 执行层：矩阵展开、并发、超时、异常隔离
│   ├── evaluation.md               # 评分：validator、LLM judge、人工标注
│   ├── decision.md                 # 决策：聚合、caveat、evidence chain
│   ├── workspace-isolation.md      # Workspace 类型 + 沙箱隔离级别
│   ├── trend-analysis.md           # 跨 run 趋势分析 + drift breakpoint
│   └── security.md                 # 安全模型：secrets、redaction、subprocess
├── reference/
│   ├── cli.md                      # CLI 命令完整参考
│   ├── eval-yaml.md                # eval.yaml schema 字段逐一说明
│   ├── task-yaml.md                # task YAML schema
│   ├── data-model.md               # RunRecord、CellResult、Decision 等核心数据结构
│   ├── api-routes.md               # Web UI API 路由
│   └── web-ui.md                   # Web UI 页面与功能
├── examples/
│   ├── index.md                    # Examples 总览 + 能力覆盖矩阵
│   ├── agent-codefix-showdown.md   # 快速入门 example
│   ├── multi-task-matrix.md        # 多任务矩阵 example（来自 example-coverage-plan）
│   └── git-workspace-isolation.md  # Git 隔离 + 沙箱 example（来自 example-coverage-plan）
├── zh/                             # 中文版（镜像结构）
│   ├── index.md                    # 中文首页
│   ├── guide/
│   │   ├── index.md
│   │   ├── getting-started.md
│   │   ├── core-concepts.md
│   │   ├── configuration.md
│   │   ├── tasks.md
│   │   ├── execution.md
│   │   ├── evaluation.md
│   │   ├── decision.md
│   │   ├── workspace-isolation.md
│   │   ├── trend-analysis.md
│   │   └── security.md
│   ├── reference/
│   │   ├── cli.md
│   │   ├── eval-yaml.md
│   │   ├── task-yaml.md
│   │   ├── data-model.md
│   │   ├── api-routes.md
│   │   └── web-ui.md
│   └── examples/
│       ├── index.md
│       ├── agent-codefix-showdown.md
│       ├── multi-task-matrix.md
│       └── git-workspace-isolation.md
└── package.json                    # VitePress + 构建依赖
```

### 导航结构

**顶部导航栏**：

```
[Logo micro-eval]    Guide    Reference    Examples    [GitHub ↗]    [EN | 中文]
```

**侧边栏**（Guide 区域）：

```
Introduction
  ├── What is micro-eval?
  └── Getting Started

Core Guide
  ├── Core Concepts
  ├── Configuration
  ├── Tasks & Expectations
  ├── Execution
  ├── Evaluation & Scoring
  ├── Decision & Caveats
  ├── Workspace Isolation
  ├── Trend Analysis
  └── Security Model

Reference（独立侧边栏）
  ├── CLI Commands
  ├── eval.yaml Schema
  ├── task.yaml Schema
  ├── Data Model
  ├── API Routes
  └── Web UI

Examples（独立侧边栏）
  ├── Overview
  ├── Agent Codefix Showdown
  ├── Multi-Task Matrix
  └── Git Workspace Isolation
```

## 3. 页面内容规划

### 3.1 首页 (index.md)

VitePress 默认首页布局，配置 frontmatter：

```yaml
layout: home
hero:
  name: micro-eval
  text: Evidence, not vibes.
  tagline: A local-first evaluation tool for small AI teams to compare agents, skills, and prompts with reproducible evidence.
  actions:
    - theme: brand
      text: Get Started
      link: /guide/getting-started
    - theme: alt
      text: View on GitHub
      link: https://github.com/xiaozhenliu/micro-eval
  image:
    src: /logo.svg
    alt: micro-eval
features:
  - icon: 🧪
    title: Matrix Comparison
    details: Expand tasks × configurations × repetitions into a canonical run matrix. Compare baseline and candidate with pass@k, cost, and latency.
  - icon: 🔒
    title: Same-Start Guarantee
    details: Every cell runs from a reproducible starting point. Snapshot mismatch downgrades the decision — no fake winner claims.
  - icon: 🛡️
    title: Multi-Level Sandbox
    details: Git worktree isolation by default. OS policy sandbox (Seatbelt/Bubblewrap) or remote VM (E2B/Modal) for untrusted agents.
  - icon: 📊
    title: Guarded Decisions
    details: Decisions come with evidence chains and caveats. Inconclusive is a valid answer — not silence.
  - icon: 🔍
    title: Full Evidence Chain
    details: Decision → Task → Trace → Diff → Cost → Artifact. Every conclusion traces back to raw evidence.
  - icon: 📈
    title: Trend Analysis
    details: Track configuration performance across runs. Drift-aware breakpoints flag when comparisons become invalid.
```

中文首页 (`zh/index.md`) 镜像翻译，tagline 改为：「用证据，不用体感。面向 AI 小团队的本地评测工具，让 agent/skill/prompt 对比可量化、可溯源、可复现。」

### 3.2 Guide 页面

每个 Guide 页面遵循统一结构：

```
## 概述（1-2 段，这个概念是什么、为什么重要）
## 快速示例（可直接复制的 YAML/命令）
## 详细说明（完整字段、选项、行为解释）
## 常见问题 / 注意事项
## 下一步（链接到相关页面）
```

#### guide/index.md — What is micro-eval?

内容来源：`README.md` 的 "Why micro-eval?" + Features 部分，重写为教学式行文。

核心结构：
- 问题陈述（AI 团队对比 agent 时的痛点）
- micro-eval 的解法（一段话 + 架构图）
- 核心工作流图（配置 → 任务 → 运行 → 决策）
- 适用场景 vs 不适用场景

#### guide/getting-started.md — 安装 + 第一次运行

内容来源：`README.md` Quick Start + `examples/README.md` + `docs/DEVELOPMENT.md` 环境准备。

核心结构：
- 环境要求（Python 3.11+, uv, Node.js 可选）
- 安装步骤（源码 clone + uv sync）
- 第一个评测（`micro-eval init` → `validate` → `run` → `report`）
- 运行 example（`python examples/run-example.py`）
- 启动 Web UI（`micro-eval ui`）
- 检查结果（run.json / decision.json / report.html）

#### guide/core-concepts.md — 核心概念

内容来源：`README.md` Architecture + Unicorn Design §5 模块职责（提炼面向用户的解释，不暴露内部实现）。

解释以下概念及其关系（附图）：
- Configuration（被测组合）
- Task（评测单元）
- Run（一次执行 = Tasks × Configs × Reps）
- RunCell（矩阵中的一个格子）
- Expectation（验证规则）
- Decision（受保护的结论）
- Caveat（降级警告）
- Evidence Chain（证据链）

#### guide/configuration.md — 配置详解

内容来源：`README.md` Configuration and Tasks + `eval.yaml.example` + Unicorn Design §3.1。

覆盖：
- 完整 eval.yaml 结构（带注释的完整示例）
- configurations[] 字段逐一解释
- agent spec（command, input_mode, output_mode, timeout_s, env, required_secrets）
- guardrails（max_concurrency, timeout_s, output_cap_bytes, artifact_cap_bytes, stop_on_cell_error）
- evaluation contract
- trace 配置
- judge 配置
- role (baseline/candidate) 的含义

#### guide/tasks.md — 任务与验证

内容来源：`src/micro_eval/models/task.py` schema + `src/micro_eval/evaluation/validator.py` + example task YAML。

覆盖：
- task.yaml 完整结构
- 四种 expectation 类型（exit_code / contains / file_exists / command），每种给出示例
- workspace spec（blank / files / git_repo），每种给出示例
- setup commands
- rubric
- input_payload

#### guide/execution.md — 执行层

内容来源：Unicorn Design §5.3 + §5.4 + README Features 部分。

覆盖：
- 矩阵展开机制（RunPlan → RunCell）
- 并发控制（asyncio, max_concurrency）
- 超时机制（per-cell timeout → SIGTERM → SIGKILL 升级链）
- 异常隔离（单 cell 失败不阻塞整个 run）
- 执行顺序记录 + 可选随机化
- argv-only 安全执行

#### guide/evaluation.md — 评分系统

内容来源：Unicorn Design §5.7 + README Features 部分。

覆盖：
- 三层评分（deterministic validator → LLM judge → 人工标注）
- pass@k / pass^k 聚合
- EvaluationResult 结构
- evidence_refs 链接
- LLM judge 配置与行为（补充评分，不覆盖确定性结果）
- 人工标注流程（Web UI AnnotationPanel）

#### guide/decision.md — 决策与 Caveat

内容来源：Unicorn Design §5.8 + README Features 部分。

覆盖：
- DecisionReport 结构
- DecisionStatus 六种取值及含义
- Caveat 系统（snapshot mismatch / low sample / missing evidence / config drift）
- 证据链导航（decision → task → trace → diff → cost）
- 跨语言算法一致性（Python/TypeScript 等价）

#### guide/workspace-isolation.md — Workspace 与沙箱

内容来源：Unicorn Design §5.5 + Phase 3 plan + README Features 部分。

覆盖：
- 三种 workspace 类型（blank / files / git_repo）
- 四级隔离（logical → os_policy → container → vm）
- Provider 机制（GitWorktreeProvider / SeatbeltProvider / BubblewrapProvider / E2BProvider / ModalProvider）
- 降级行为（os_policy 不可用 → logical + caveat；remote 不可用 → fail hard）
- SameStartSnapshot 中的隔离维度
- 配置示例

#### guide/trend-analysis.md — 趋势分析

内容来源：Phase 3 plan P3-e + CHANGELOG v0.3.0。

覆盖：
- 跨 run 趋势查询
- SQLite 索引（JSON 仍为 source of truth）
- drift breakpoint（config 变化标注不可比断点）
- API route `/api/trends`
- 使用示例

#### guide/security.md — 安全模型

内容来源：`README.md` Security and Local Data + `docs/engineering/security-guidelines.md`（提炼面向用户的部分）。

覆盖：
- argv-only subprocess（为什么、怎么做）
- secrets 通道（MICRO_EVAL_SECRET_* 命名 + 声明 + 注入 + redaction）
- workspace 边界（agent cwd 是分配的 workspace，不是宿主项目根）
- 网络隔离限制（MVP 不提供网络隔离，需沙箱 provider）
- artifact 安全（manifest-bound access + binary 检测 + cap）

### 3.3 Reference 页面

Reference 页面是严格的参考手册，不做教学，只做查表。

#### reference/cli.md

来源：`README.md` CLI Commands 表 + CLI 源码 `src/micro_eval/cli/*.py`。

格式：每个命令一个小节，包含 synopsis / 参数表 / 示例 / 退出码。

#### reference/eval-yaml.md

来源：`src/micro_eval/models/configuration.py` + eval.yaml.example。

格式：每个字段一行表格（字段名 / 类型 / 默认值 / 必填 / 说明）。嵌套结构用子表格。

#### reference/task-yaml.md

来源：`src/micro_eval/models/task.py`。

格式：同上。重点展示 ExpectationSpec 和 WorkspaceSpec 的字段。

#### reference/data-model.md

来源：`src/micro_eval/models/*.py` + `ui/src/lib/schema.ts`。

展示核心数据结构的字段定义（RunRecord / CellResult / DecisionReport / SameStartSnapshot / EvaluationResult / ArtifactRef / TraceRef / CostMetric），每个结构给出 JSON 示例。

#### reference/api-routes.md

来源：`ui/src/app/api/` 路由文件。

格式：每个路由一节（Method / Path / 参数 / 响应示例）。

#### reference/web-ui.md

来源：`README.md` Web UI 表 + UI 组件列表。

覆盖每个页面的功能、截图占位（后续补截图）、操作指引。

### 3.4 Examples 页面

每个 example 页面：场景说明 → 文件结构 → 运行命令 → 预期输出 → 展示了哪些能力。

来源：`examples/*/README.md`（重写为网站风格，加代码高亮和 callout）。

## 4. 视觉设计

### 品牌色

```css
:root {
  --vp-c-brand-1: #6f42c1;        /* 主品牌色 — 与 README badge 一致 */
  --vp-c-brand-2: #8b5cf6;        /* 悬停态 */
  --vp-c-brand-3: #a78bfa;        /* 轻量背景 */
  --vp-c-brand-soft: rgba(111, 66, 193, 0.14);
}
```

### 设计原则

1. **默认主题 + 最小覆写** — VitePress 默认主题已经足够专业，只覆写品牌色和少量间距。不做过度自定义，降低维护成本。
2. **暗色模式优先** — AI 工具的用户群体普遍偏好暗色。VitePress 默认支持 light/dark 切换。
3. **代码高亮突出** — 大量 YAML/Python/bash 代码块，使用 Shiki 的 VSCode 主题。
4. **VitePress 内置组件充分利用**：
   - `tip` / `warning` / `danger` / `info` callout 用于强调安全注意事项和重要提示
   - 代码组（code group）展示同一操作的不同方式（如 uv vs pip）
   - Badge 标注 Phase 版本

### Logo

暂用文字 logo `micro-eval`。后续可设计图形 logo 替换。

## 5. 内容来源映射

### 可直接复用（提炼 + 重写为教学/参考风格）

| 网站页面 | 来源文件 | 处理方式 |
|---------|---------|---------|
| guide/index.md | README.md §Why | 扩写为教学行文 |
| guide/getting-started.md | README.md §Quick Start + docs/DEVELOPMENT.md | 合并 + 简化面向用户 |
| guide/core-concepts.md | Unicorn Design §5（八模块职责） | 提炼为用户概念，去掉内部实现 |
| guide/configuration.md | README.md §Config + eval.yaml.example | 加注释 + 逐字段说明 |
| guide/tasks.md | models/task.py + validator.py | 从代码提取 schema，配示例 |
| guide/security.md | README.md §Security + security-guidelines.md | 提炼面向用户部分 |
| reference/cli.md | README.md §CLI + cli/*.py 源码 | 扩充参数/示例 |
| reference/eval-yaml.md | models/configuration.py | 自动或手动提取 schema |
| reference/task-yaml.md | models/task.py | 同上 |
| reference/data-model.md | models/*.py + ui schema.ts | 结构化展示 |
| reference/api-routes.md | ui/src/app/api/ | 逐路由文档化 |
| examples/*.md | examples/*/README.md | 重写为网站风格 |

### 需新写的内容

| 网站页面 | 说明 |
|---------|------|
| guide/execution.md | 执行层细节散布在多处，需统一为一篇教程 |
| guide/evaluation.md | 评分系统细节散布在 spec + README，需面向用户重组 |
| guide/decision.md | 决策逻辑需从 spec 提炼为用户可理解的解释 |
| guide/workspace-isolation.md | Phase 3 内容需从 plan/changelog 提炼 |
| guide/trend-analysis.md | Phase 3-e 内容需新写 |
| reference/web-ui.md | 需截图 + 操作指引 |
| 中文版全部页面 | 英文页面的对照翻译 |

## 6. 部署

### GitHub Pages 配置

1. 仓库 Settings → Pages → Source: GitHub Actions
2. 部署到 `https://xiaozhenliu.github.io/micro-eval/`（或绑定自定义域名）

### GitHub Actions Workflow

```yaml
# .github/workflows/deploy-site.yml
name: Deploy Site
on:
  push:
    branches: [main]
    paths: [site/**]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: site/package-lock.json
      - run: npm ci
        working-directory: site
      - run: npm run docs:build
        working-directory: site
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site/.vitepress/dist

  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    needs: build
    runs-on: ubuntu-latest
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

### VitePress 配置骨架

```ts
// site/.vitepress/config.ts
import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'micro-eval',
  description: 'Evidence, not vibes. A local-first evaluation tool for small AI teams.',
  base: '/micro-eval/',

  locales: {
    root: {
      label: 'English',
      lang: 'en',
    },
    zh: {
      label: '简体中文',
      lang: 'zh-CN',
      themeConfig: {
        nav: [
          { text: '指南', link: '/zh/guide/' },
          { text: '参考', link: '/zh/reference/cli' },
          { text: '示例', link: '/zh/examples/' },
        ],
        sidebar: { /* 中文侧边栏 */ },
      },
    },
  },

  themeConfig: {
    logo: '/logo.svg',
    nav: [
      { text: 'Guide', link: '/guide/' },
      { text: 'Reference', link: '/reference/cli' },
      { text: 'Examples', link: '/examples/' },
    ],
    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'What is micro-eval?', link: '/guide/' },
            { text: 'Getting Started', link: '/guide/getting-started' },
          ],
        },
        {
          text: 'Core Guide',
          items: [
            { text: 'Core Concepts', link: '/guide/core-concepts' },
            { text: 'Configuration', link: '/guide/configuration' },
            { text: 'Tasks & Expectations', link: '/guide/tasks' },
            { text: 'Execution', link: '/guide/execution' },
            { text: 'Evaluation & Scoring', link: '/guide/evaluation' },
            { text: 'Decision & Caveats', link: '/guide/decision' },
            { text: 'Workspace Isolation', link: '/guide/workspace-isolation' },
            { text: 'Trend Analysis', link: '/guide/trend-analysis' },
            { text: 'Security Model', link: '/guide/security' },
          ],
        },
      ],
      '/reference/': [
        {
          text: 'Reference',
          items: [
            { text: 'CLI Commands', link: '/reference/cli' },
            { text: 'eval.yaml Schema', link: '/reference/eval-yaml' },
            { text: 'task.yaml Schema', link: '/reference/task-yaml' },
            { text: 'Data Model', link: '/reference/data-model' },
            { text: 'API Routes', link: '/reference/api-routes' },
            { text: 'Web UI', link: '/reference/web-ui' },
          ],
        },
      ],
      '/examples/': [
        {
          text: 'Examples',
          items: [
            { text: 'Overview', link: '/examples/' },
            { text: 'Agent Codefix Showdown', link: '/examples/agent-codefix-showdown' },
            { text: 'Multi-Task Matrix', link: '/examples/multi-task-matrix' },
            { text: 'Git Workspace Isolation', link: '/examples/git-workspace-isolation' },
          ],
        },
      ],
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/xiaozhenliu/micro-eval' },
    ],
    search: {
      provider: 'local',
    },
    footer: {
      message: 'Released under the Apache-2.0 License.',
      copyright: 'Copyright © 2026 micro-eval contributors',
    },
  },
})
```

## 7. 实施计划

### 阶段划分

```
M1 (骨架)  →  M2 (Guide 内容)  →  M3 (Reference 内容)  →  M4 (中文 + 部署)
```

### M1: 站点骨架 + 首页

**交付物**：
- `site/package.json`（VitePress 依赖）
- `site/.vitepress/config.ts`（完整导航/侧边栏/i18n 配置）
- `site/.vitepress/theme/`（品牌色覆写）
- `site/public/`（logo 占位、favicon）
- `site/index.md`（英文首页，完整 Hero + Features）
- `site/zh/index.md`（中文首页）
- 所有页面的占位文件（标题 + "Coming soon"）

**验收**：
- `npm run docs:dev` 启动后首页完整渲染，导航和侧边栏可点击
- 英文/中文切换正常
- 暗色/亮色模式正常

### M2: Guide 内容

**交付物**：
- `site/guide/*.md` 全部 10 个英文页面完成
- 每个页面包含概述 + 示例 + 详细说明 + 下一步链接

**内容优先级（按新用户学习路径排序）**：
1. `getting-started.md` — 最高优先级，新用户第一个看的页面
2. `core-concepts.md` — 建立心智模型
3. `configuration.md` + `tasks.md` — 学会写配置
4. `execution.md` + `evaluation.md` + `decision.md` — 理解运行逻辑
5. `workspace-isolation.md` + `trend-analysis.md` + `security.md` — 高级特性

**验收**：
- 每个页面有实际内容（非占位）
- 代码示例可直接复制使用
- 页面间的交叉链接正确

### M3: Reference + Examples 内容

**交付物**：
- `site/reference/*.md` 全部 6 个英文页面
- `site/examples/*.md` 全部 4 个英文页面（含 Overview）

**验收**：
- CLI 参考覆盖所有 6 个命令
- eval.yaml / task.yaml schema 覆盖所有字段
- Example 页面与 `examples/` 目录内容一致

### M4: 中文翻译 + 部署上线

**交付物**：
- `site/zh/` 下全部页面的中文翻译
- `.github/workflows/deploy-site.yml`
- GitHub Pages 配置
- README.md 添加文档站链接

**验收**：
- `https://xiaozhenliu.github.io/micro-eval/` 可访问
- 中英切换正常
- 搜索功能正常（中英文均可搜索）
- CI 推送 main 后自动部署

## 8. 与 example-coverage-plan 的关系

本计划的 Examples 页面（`site/examples/`）依赖 `2026-06-15-example-coverage-plan.md` 中规划的新 example（`multi-task-matrix` + `git-workspace-isolation`）。

- 如果新 example 先完成：Examples 页面直接从 example README 提炼
- 如果网站先开工：Examples 页面先只写 `agent-codefix-showdown`，其余两个留占位

两个计划可并行推进，M3 是唯一交汇点。

## 9. 维护策略

1. **文档与代码同步** — 涉及 CLI 命令、配置字段、API 路由变更的 PR 必须同时更新网站文档
2. **CI 构建检查** — deploy-site workflow 在 PR 中也触发 build（不部署），确保不破坏站点
3. **版本标注** — 页面中用 VitePress Badge 标注功能所属版本（如 `Since v0.3.0`）
4. **截图更新** — Web UI 页面的截图在 UI 改版时需手动更新（不自动化，频率低）

## 10. 明确不含

- 不把现有 `docs/` 工程文档直接搬到网站（工程文档是内部开发用，不面向用户）
- 不删除 README.md / README.zh-CN.md（它们是 GitHub 仓库首页的入口，与网站共存）
- 不引入 CMS 或动态后端
- 不做在线 playground 或交互式 demo
- 不在网站中暴露内部 spec（Unicorn Design）或 BRD
