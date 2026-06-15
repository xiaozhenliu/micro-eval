# Web UI

micro-eval Web UI 是一个**本地运行的 Next.js 应用**，与你的项目一同提供服务。它通过 API 路由读取 `.micro-eval/` 目录下的 JSON 文件——无需数据库、无需云端、无需身份验证。

::: tip 本地优先设计
Web UI 绑定到 `localhost`，直接从你的文件系统读取数据。评测数据不会离开本机。
:::

## 启动

::: code-group

```bash [通过 CLI]
# 指向任意项目并启动服务
MICRO_EVAL_PROJECT_ROOT=/path/to/project micro-eval ui --port 3000
```

```bash [通过 npm（源码检出）]
# 在 ui/ 目录下设置环境变量后运行
export MICRO_EVAL_PROJECT_ROOT=/path/to/project
cd ui && npm run dev
```

:::

启动后，在浏览器中打开 `http://localhost:3000`。

::: warning 端口冲突
如果 3000 端口已被占用，请传入 `--port <number>` 选择其他端口。CLI 启动时会打印实际的访问 URL。
:::

## 数据流

Web UI 不会直接写入评测数据。API 路由将 HTTP 请求转换为对 `.micro-eval/` 目录的文件系统读写操作：

```
Browser → Next.js API route → .micro-eval/runs/<id>/*.json
                            ↘ .micro-eval/runs/<id>/evaluation.json  (writes)
```

决策结果在每次人工评测写入后于服务端重新计算。评测状态**不**使用 `localStorage` 存储。

---

## 页面

### `/` — Run 列表

首页展示 `.micro-eval/runs/` 下找到的所有 run。

| 列 | 描述 |
|---|---|
| Run ID | 唯一标识符，点击跳转到 run 详情页 |
| Project | run manifest 中的项目名称 |
| Status | `completed`、`failed`、`running` |
| Created | run 开始时间的 ISO 时间戳 |
| Tasks | run 中的任务数量 |
| Configurations | 参与评测的配置数量 |

点击任意行跳转到对应 run 的详情页。

---

### `/run/[id]` — Run 详情

主要分析界面，在单页上展示四个面板。

#### 决策摘要

页面顶部的判定徽章显示计算得出的决策状态：

| 徽章 | 含义 |
|---|---|
| `improved` | 新配置在大多数任务上得分更高 |
| `regressed` | 新配置得分下降 |
| `mixed` | 各任务结果不一 |
| `inconclusive` | 信号不足，无法区分 |
| `not_comparable` | Run 快照不一致——基线对比无效 |
| `needs_human_review` | 自动评分已延后；需要人工标注 |

徽章旁会同时显示**置信度**（低 / 中 / 高），由分数方差和重复次数推算得出。

#### Caveats 面板

如果 run 产生了任何 caveat——隔离级别不匹配、缺少 Langfuse 凭证、跳过了 LLM judge 调用——这些信息将以可折叠的警告形式显示在此处。

::: warning Caveats 影响可比性
当 `SameStartSnapshot` 检查发现各配置之间的 workspace commit、fixture digest 或 toolchain fingerprint 存在差异时，会自动发出 `not_comparable` 决策。
:::

#### Result Matrix

以**任务为行、配置为列**的网格视图，每个单元格按颜色标注：

- 绿色 — 所有预期均通过
- 红色 — 一个或多个预期失败
- 橙色 — 执行错误（超时、无 `exit_code` 预期的非零退出等）
- 灰色 — 已跳过或未运行

**点击任意单元格**可打开详情抽屉，显示：

- 输出摘要（stdout/stderr 节选）
- 收集到的 evidence（预期结果、LLM judge 评分、人工标注）
- Artifact 链接

#### 人工评测面板

可直接在 UI 中为任意单元格添加评分和评语。字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| Score | 0–1 的数值 | 追加到该单元格的 evidence 列表中 |
| Comment | 自由文本 | 原文存储在 `evaluation.json` 中 |

提交后会在服务端触发决策重新计算。判定徽章将在下次页面加载时更新。

```json
// .micro-eval/runs/<id>/evaluation.json（示例条目）
{
  "task_id": "write-tests",
  "configuration_id": "sonnet-4-5",
  "repetition": 0,
  "score": 0.9,
  "comment": "Output correct but formatting was inconsistent.",
  "annotated_at": "2026-06-15T10:42:00Z"
}
```

---

### `/run/[id]/review` — 复盘界面

更深入的分析页面，专为 run 结束后的回顾设计。在 Phase 2 中新增。

#### Matrix 热图

以热图形式渲染相同的任务 × 配置网格，对所有单元格的通过/失败着色进行归一化处理。便于发现哪些任务在所有配置中都系统性地难以通过。

#### 成本面板

从 Langfuse trace 数据（如有）聚合的各配置成本指标：

- 总 token 消耗（prompt + completion）
- 每任务平均成本
- 各重复次数的成本分布图

::: tip Langfuse 为可选项
如果未设置 `LANGFUSE_SECRET_KEY`，成本面板将显示"No trace data"占位符。复盘页的其余部分仍完全可用。
:::

#### Trace 面板

每个单元格的 trace 摘要：延迟、工具调用次数、span 树深度。点击摘要可展开完整的 span 列表。

#### Evidence 查看器

选择任意单元格，浏览其完整的 evidence 链：

1. 确定性验证器结果（exit code、contains、file_exists、command）
2. LLM judge 评分与理由（如已运行）
3. 人工标注（如已添加）

#### 聚合统计

热图下方的统计栏显示 run 级别的聚合数据：

| 指标 | 描述 |
|---|---|
| `pass@k` | 每个任务-配置对在 k 次重复中的通过率 |
| Median latency | 每次任务执行的墙钟时间中位数 |
| Total cost | 所有单元格中 Langfuse 上报的 token 成本总和 |

---

### `/run/[id]/artifact/[artifactId]` — Artifact 查看器

渲染 run 过程中捕获的单个 artifact。

#### 文本 artifact

当 `media_type` 为 `text/*` 时，以语法高亮方式内联渲染。较长的 artifact 会分页显示。

#### 元数据侧边栏

| 字段 | 值 |
|---|---|
| Kind | `stdout`、`file`、`diff`、`custom` |
| Size | 字节数 |
| Media type | manifest 中的 MIME 类型 |
| SHA-256 | 用于完整性校验的摘要 |

#### 边界强制执行

访问需通过两项检查：

1. `artifact_id` 必须出现在 run 的 artifact manifest 中
2. 解析后的文件路径必须保持在 `.micro-eval/runs/<id>/` 内部

::: danger 越界请求将被拒绝
任何解析到 run 目录之外的 artifact URL 都将返回 HTTP 403。即使 artifact manifest 条目存在格式问题，此机制也能防止路径遍历攻击。
:::

#### 超大及二进制 artifact

| 情况 | 行为 |
|---|---|
| `size > 1 MB` | 显示警告占位符；原始内容不发送到浏览器 |
| `media_type` 为二进制 | 显示警告占位符；提供下载链接 |
| Artifact 不在 manifest 中 | HTTP 404 |
| 路径越出 run 边界 | HTTP 403 |

---

## 配置参考

Web UI 在启动时读取一个环境变量：

```bash
MICRO_EVAL_PROJECT_ROOT=/absolute/path/to/project
```

所有对 `.micro-eval/` 的读写均相对于此根目录。不需要其他任何配置。

::: tip Secrets 不会被对外提供
匹配 `MICRO_EVAL_SECRET_*` 的环境变量会在服务端自动脱敏，不会包含在 API 响应或渲染的 artifact 内容中。
:::

---

## API 路由（内部）

这些路由供 Next.js 页面使用，不是公开 API，可能在次要版本之间发生变化。

| 路由 | 方法 | 描述 |
|---|---|---|
| `/api/runs` | GET | 列出所有 run manifest |
| `/api/runs/[id]` | GET | 单个 run manifest + 决策结果 |
| `/api/runs/[id]/matrix` | GET | 包含 evidence 的完整 result matrix |
| `/api/runs/[id]/evaluate` | POST | 写入人工评测条目 |
| `/api/runs/[id]/artifacts/[artifactId]` | GET | 提供 artifact 内容 |
| `/api/runs/[id]/traces` | GET | 聚合后的 trace 数据（Langfuse） |

---

## 故障排查

**页面显示"No runs found"**

检查 `MICRO_EVAL_PROJECT_ROOT` 是否指向包含 `.micro-eval/runs/` 的目录。在项目中运行 `micro-eval list` 确认 run 是否存在。

**标注后决策徽章仍显示 `needs_human_review`**

人工评测会在下次完整页面加载时触发重新计算。请对 run 详情页执行强制刷新（`Ctrl+Shift+R` / `Cmd+Shift+R`）。

**成本面板显示"No trace data"**

执行 run 时未设置 Langfuse 凭证（`LANGFUSE_SECRET_KEY`、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_HOST`）。成本数据在 run 时捕获，无法事后补录。

**Artifact 查看器返回 403**

Artifact manifest 条目中包含解析到 run 目录之外的路径。这是数据完整性问题——请重新执行评测以生成干净的 artifact。
