# API 路由

micro-eval Web UI 由本地 Next.js 开发服务器提供服务。所有 API 路由均从磁盘上的 `.micro-eval/` JSON 文件读取数据——没有远程服务器、没有数据库连接、也没有认证层。API 严格仅限本地使用。在**服务器模式**（`micro-eval serve`）下，还会开放额外的 workspace 作用域路由和队列管理路由——详见下方的[服务器模式 API 路由](#服务器模式-api-路由)。

::: tip 启动服务器
```bash
uv run micro-eval ui
# 服务器启动于 http://localhost:3000
```
以下所有路由均相对于 `http://localhost:3000`。
:::

## 概览

| 方法 | 路由 | 用途 |
|--------|-------|---------|
| `GET` | `/api/runs` | 列出所有 run 记录 |
| `GET` | `/api/runs/[id]` | 获取单个 run 的完整详情 |
| `GET` | `/api/runs/[id]/cells/[cellId]` | 获取单个 cell 结果 |
| `POST` | `/api/runs/[id]/cells/[cellId]/evaluate` | 追加人工评分 |
| `GET` | `/api/runs/[id]/cells/[cellId]/trace` | 获取 cell 的 trace 数据 |
| `GET` | `/api/runs/[id]/artifacts` | 列出某次 run 的所有 artifact |
| `GET` | `/api/trends` | 查询跨 run 的趋势数据 |

---

## GET /api/runs

列出 `.micro-eval/runs/` 中的所有 run 记录。每条记录从其对应的 `run.json` 文件加载。结果按时间倒序返回（最新的在前）。

**响应：** `RunRecord[]`

```bash
curl http://localhost:3000/api/runs
```

**响应示例：**

```json
[
  {
    "id": "run_20260614_171843",
    "timestamp": "2026-06-14T17:18:43Z",
    "status": "completed",
    "config_path": "eval.yaml",
    "task_count": 3,
    "config_count": 2,
    "repetitions": 2,
    "cell_count": 12,
    "pass_count": 9,
    "error_count": 1,
    "decision": "improved",
    "duration_s": 87.4
  },
  {
    "id": "run_20260611_090155",
    "timestamp": "2026-06-11T09:01:55Z",
    "status": "completed",
    "config_path": "eval.yaml",
    "task_count": 3,
    "config_count": 2,
    "repetitions": 2,
    "cell_count": 12,
    "pass_count": 7,
    "error_count": 0,
    "decision": "inconclusive",
    "duration_s": 94.1
  }
]
```

**decision 取值：** `improved` | `regressed` | `mixed` | `inconclusive` | `not_comparable` | `needs_human_review`

---

## GET /api/runs/[id]

获取单个 run 的完整详情，包括所有 cell 结果、artifact、证据和评分。此端点读取并合并 `.micro-eval/runs/<id>/` 下的所有文件。

**路径参数：**

| 参数 | 类型 | 描述 |
|-----------|------|-------------|
| `id` | string | Run ID（例如 `run_20260614_171843`） |

**响应：** 包含嵌入结果的完整 `RunRecord`。

```bash
curl http://localhost:3000/api/runs/run_20260614_171843
```

**响应示例：**

```json
{
  "id": "run_20260614_171843",
  "timestamp": "2026-06-14T17:18:43Z",
  "status": "completed",
  "plan": {
    "tasks": ["refactor", "add-tests", "fix-bug"],
    "configurations": ["sonnet-skill-v1", "sonnet-skill-v2"],
    "repetitions": 2,
    "execution_seed": null
  },
  "result_matrix": {
    "cells": [
      {
        "id": "refactor__sonnet-skill-v1__0",
        "task_id": "refactor",
        "config_id": "sonnet-skill-v1",
        "rep_index": 0,
        "status": "pass",
        "exit_code": 0,
        "duration_ms": 4210,
        "cost_usd": 0.008,
        "validation_results": [
          { "type": "exit_code", "passed": true },
          { "type": "contains", "passed": true }
        ],
        "judge_score": null,
        "human_score": null
      }
    ]
  },
  "decision": {
    "status": "improved",
    "winning_config": "sonnet-skill-v2",
    "caveats": []
  },
  "artifacts": [],
  "metadata": {
    "workspace_provider": "logical",
    "isolation_level": "logical"
  }
}
```

::: warning 大型 run
包含大量 cell 和大型 artifact 的 run 可能产生体积可观的 JSON 响应。UI 会对结果矩阵的展示进行分页，但此端点始终返回完整负载。在脚本中使用时，建议改用 `/api/runs/[id]/cells/[cellId]` 逐个获取 cell。
:::

---

## GET /api/runs/[id]/cells/[cellId]

获取单个 cell 结果。Cell ID 编码了其在 run 矩阵中的坐标。

**路径参数：**

| 参数 | 类型 | 描述 |
|-----------|------|-------------|
| `id` | string | Run ID |
| `cellId` | string | 格式为 `<task_id>__<config_id>__<rep_index>` 的 Cell ID |

**响应：** `CellResult`

```bash
curl http://localhost:3000/api/runs/run_20260614_171843/cells/refactor__sonnet-skill-v1__0
```

**响应示例：**

```json
{
  "id": "refactor__sonnet-skill-v1__0",
  "task_id": "refactor",
  "config_id": "sonnet-skill-v1",
  "rep_index": 0,
  "status": "pass",
  "exit_code": 0,
  "exit_reason": "normal",
  "duration_ms": 4210,
  "cost_usd": 0.008,
  "stdout": "Refactoring complete. 14 functions updated.",
  "stderr": "",
  "stdout_truncated": false,
  "stderr_truncated": false,
  "validation_results": [
    {
      "type": "exit_code",
      "passed": true,
      "expected": 0,
      "actual": 0
    },
    {
      "type": "contains",
      "passed": true,
      "stream": "stdout",
      "value": "refactoring complete",
      "case_sensitive": false
    }
  ],
  "judge_score": null,
  "judge_error": null,
  "human_score": null,
  "trace_ref": {
    "trace_id": "tr_abc123",
    "langfuse_url": "https://cloud.langfuse.com/trace/tr_abc123"
  }
}
```

**Cell status 取值：**

| 状态 | 含义 |
|--------|---------|
| `pass` | 所有预期均通过 |
| `fail` | 一个或多个预期未通过 |
| `error` | 环境准备失败、agent 崩溃，或在执行预期校验之前超时 |
| `skipped` | Cell 未被执行（例如触发了 `stop_on_cell_error`） |

---

## POST /api/runs/[id]/cells/[cellId]/evaluate

向 cell 追加人工评分和评论。这是 API 中唯一的写入端点——其他所有路由均为只读。

**路径参数：**

| 参数 | 类型 | 描述 |
|-----------|------|-------------|
| `id` | string | Run ID |
| `cellId` | string | Cell ID |

**请求体：**

```json
{
  "score": 8,
  "comment": "Output is correct but could be more concise.",
  "evaluator": "alice"
}
```

| 字段 | 类型 | 必填 | 描述 |
|-------|------|----------|-------------|
| `score` | number (0–10) | 是 | 人工质量评分 |
| `comment` | string | 是 | 自由文本标注 |
| `evaluator` | string | 否 | 评分者标识；默认为 `"human"` |

**副作用：**

1. 将评分条目写入 `.micro-eval/runs/<id>/cells/<cellId>/evaluation.json`
2. 重新计算该 run 的 `decision.json`，可能更新整体决策状态

**响应：** 更新后的 `EvaluationResult`

```bash
curl -X POST http://localhost:3000/api/runs/run_20260614_171843/cells/refactor__sonnet-skill-v1__0/evaluate \
  -H "Content-Type: application/json" \
  -d '{"score": 8, "comment": "Output is correct but could be more concise.", "evaluator": "alice"}'
```

**响应示例：**

```json
{
  "cell_id": "refactor__sonnet-skill-v1__0",
  "score": 8,
  "comment": "Output is correct but could be more concise.",
  "evaluator": "alice",
  "timestamp": "2026-06-15T10:22:05Z",
  "decision_updated": true,
  "new_decision_status": "needs_human_review"
}
```

::: tip 决策状态发生变化时
如果新的人工评分导致整体 run 决策发生变化（例如，原本为 `inconclusive` 的 cell 在有了足够多的标注后达到 `improved`），响应中会包含 `decision_updated: true` 以及更新后的 `new_decision_status`。刷新 run 视图即可查看更新后的矩阵。
:::

::: warning 无认证机制
此端点写入磁盘时不进行任何认证校验。它仅为单用户本地使用而设计。请勿将 micro-eval UI 服务器暴露在公共网络接口上。
:::

---

## GET /api/runs/[id]/cells/[cellId]/trace

获取 cell 的 trace 数据。trace 引用从 cell 的 `trace_ref` 清单条目中解析，该条目在执行时由 Langfuse 集成记录。

**路径参数：**

| 参数 | 类型 | 描述 |
|-----------|------|-------------|
| `id` | string | Run ID |
| `cellId` | string | Cell ID |

**响应：** 带摘要的 `TraceRef`

```bash
curl http://localhost:3000/api/runs/run_20260614_171843/cells/refactor__sonnet-skill-v1__0/trace
```

**响应示例（trace 可用）：**

```json
{
  "cell_id": "refactor__sonnet-skill-v1__0",
  "trace_id": "tr_abc123",
  "langfuse_url": "https://cloud.langfuse.com/trace/tr_abc123",
  "summary": {
    "total_tokens": 3820,
    "prompt_tokens": 1240,
    "completion_tokens": 2580,
    "total_cost_usd": 0.008,
    "duration_ms": 4210,
    "model": "claude-sonnet-4-5",
    "span_count": 7
  }
}
```

**响应示例（未配置 trace）：**

```json
{
  "cell_id": "refactor__sonnet-skill-v1__0",
  "trace_id": null,
  "langfuse_url": null,
  "summary": null,
  "reason": "Langfuse credentials not configured at run time"
}
```

::: tip 配置 Langfuse
trace 数据在执行时捕获，而非按需获取。要查看 trace，请在执行 `micro-eval run` 前设置 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`（以 `LANGFUSE_SECRET_KEY` 传入）和 `LANGFUSE_HOST`。详见[执行 → Trace 捕获](/zh/guide/execution#step-6-trace-capture-optional)。
:::

---

## GET /api/runs/[id]/artifacts

列出某次 run 的所有 artifact。artifact 引用从 `.micro-eval/runs/<id>/artifacts/manifest.json` 的 artifact 清单中读取。实际 artifact 内容通过每个 `ArtifactRef` 中的静态文件路径单独提供。

**路径参数：**

| 参数 | 类型 | 描述 |
|-----------|------|-------------|
| `id` | string | Run ID |

**响应：** `ArtifactRef[]`，已过滤至该 run 边界内的 artifact。

```bash
curl http://localhost:3000/api/runs/run_20260614_171843/artifacts
```

**响应示例：**

```json
[
  {
    "artifact_id": "art_0001",
    "cell_id": "refactor__sonnet-skill-v1__0",
    "name": "output/report.md",
    "content_type": "text/markdown",
    "size_bytes": 4820,
    "digest": "sha256:a1b2c3d4...",
    "static_path": "/api/runs/run_20260614_171843/artifacts/art_0001/content",
    "truncated": false,
    "warning": null
  },
  {
    "artifact_id": "art_0002",
    "cell_id": "fix-bug__sonnet-skill-v2__1",
    "name": "output/patch.diff",
    "content_type": "text/x-diff",
    "size_bytes": 10485761,
    "digest": "sha256:e5f6a7b8...",
    "static_path": null,
    "truncated": true,
    "warning": "Artifact exceeds max_artifact_bytes (10 MB). Content not stored. Digest only."
  }
]
```

**ArtifactRef 字段：**

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `artifact_id` | string | run 内的稳定 artifact 标识符 |
| `cell_id` | string | 产生此 artifact 的 cell |
| `name` | string | 相对于 workspace 根目录的原始路径 |
| `content_type` | string | MIME 类型，根据扩展名推断 |
| `size_bytes` | number | 捕获时的文件大小 |
| `digest` | string | SHA-256 内容摘要 |
| `static_path` | string \| null | 获取 artifact 内容的 URL 路径；未存储时为 `null` |
| `truncated` | boolean | 内容超过 `max_artifact_bytes` 时为 `true` |
| `warning` | string \| null | 边界违规或内容缺失的可读说明 |

::: warning 带警告的 artifact
当 `truncated` 为 `true` 或 `warning` 非空时，`static_path` 将为 `null`——没有内容可供访问。若您拥有原始文件，digest 仍会被记录以供完整性校验。如需在后续 run 中捕获更大的 artifact，请在 `eval.yaml` 中增大 `run.guardrails.max_artifact_bytes`。
:::

---

## GET /api/trends

查询特定 configuration 的跨 run 趋势数据。响应从 SQLite 索引（`.micro-eval/index.db`）中组装，并包含各 run 之间 configuration digest 发生变化时的漂移断点。

**查询参数：**

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|-----------|------|----------|---------|-------------|
| `config_id` | string | 是 | — | 要查询的 configuration ID |
| `since` | string (ISO-8601) | 否 | *(所有 run)* | 排除此时间戳之前的 run |
| `limit` | number | 否 | `50` | 返回的最大数据点数量 |

**响应：** 带断点标注的趋势序列。

::: code-group

```bash [basic]
curl "http://localhost:3000/api/trends?config_id=sonnet-skill-v2"
```

```bash [with filters]
curl "http://localhost:3000/api/trends?config_id=sonnet-skill-v2&since=2026-06-01T00:00:00Z&limit=10"
```

:::

**响应示例：**

```json
{
  "config_id": "sonnet-skill-v2",
  "data_points": [
    {
      "run_id": "run_20260610_143022",
      "timestamp": "2026-06-10T14:30:22Z",
      "digest": "a3f9c2b1",
      "pass_rate": 0.72,
      "mean_latency_ms": 4200,
      "p50_latency_ms": 4100,
      "p95_latency_ms": 9800,
      "cost": 0.031
    },
    {
      "run_id": "run_20260611_090155",
      "timestamp": "2026-06-11T09:01:55Z",
      "digest": "a3f9c2b1",
      "pass_rate": 0.75,
      "mean_latency_ms": 4050,
      "p50_latency_ms": 3950,
      "p95_latency_ms": 9500,
      "cost": 0.029
    },
    {
      "run_id": "run_20260614_171843",
      "timestamp": "2026-06-14T17:18:43Z",
      "digest": "c1d7a412",
      "pass_rate": 0.81,
      "mean_latency_ms": 3700,
      "p50_latency_ms": 3650,
      "p95_latency_ms": 8200,
      "cost": 0.027
    }
  ],
  "breakpoints": [
    {
      "run_id": "run_20260614_171843",
      "reason": "digest changed: a3f9c2b1 → c1d7a412",
      "timestamp": "2026-06-14T17:18:43Z"
    }
  ]
}
```

**响应字段：**

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `config_id` | string | 被查询的 configuration ID |
| `data_points` | array | 按时间排序的各 run 指标列表 |
| `data_points[].run_id` | string | Run 标识符 |
| `data_points[].timestamp` | string | Run 完成时间（ISO-8601） |
| `data_points[].digest` | string | 执行时的 configuration digest |
| `data_points[].pass_rate` | number | 通过的 cell 占比（0.0–1.0） |
| `data_points[].mean_latency_ms` | number | Cell 平均挂钟时长 |
| `data_points[].p50_latency_ms` | number | Cell 时长中位数 |
| `data_points[].p95_latency_ms` | number | Cell 时长第 95 百分位 |
| `data_points[].cost` | number | 本次 run 的总费用（美元，需要 Langfuse） |
| `breakpoints` | array | 相邻数据点之间的漂移断点 |
| `breakpoints[].run_id` | string | digest 变化后的第一个 run |
| `breakpoints[].reason` | string | digest 变化的可读描述 |
| `breakpoints[].timestamp` | string | 断点后第一个 run 的时间戳 |

::: warning 跨断点比较
断点两侧的数据点属于不同的有效 configuration。不要对跨越断点的通过率变化得出结论——该变化可能是由 configuration 差异而非 agent 本身的质量变化引起的。详见[趋势分析 → 漂移感知断点](/zh/guide/trend-analysis#drift-aware-breakpoints)。
:::

::: tip 重建索引
`/api/trends` 路由从 SQLite 索引读取数据。若索引缺失或过期，请重建：
```bash
uv run micro-eval index import-json
```
:::

---

## 错误响应

所有路由均返回标准 HTTP 错误码。错误响应体始终包含 `detail` 字段。

```json
{
  "error": "not_found",
  "detail": "Run run_20260601_000000 not found in .micro-eval/runs/"
}
```

| 状态码 | 触发条件 |
|--------|-----------|
| `400 Bad Request` | 缺少必填查询参数；请求体 schema 不合法 |
| `404 Not Found` | Run ID 或 Cell ID 在磁盘上不存在 |
| `409 Conflict` | 检测到并发写入（例如对同一 cell 同时发起两次 evaluate 调用） |
| `422 Unprocessable Entity` | 请求体通过 JSON 解析但字段验证失败 |
| `500 Internal Server Error` | 磁盘读取错误、JSON 损坏或索引故障 |

::: danger run 文件损坏
若 `run.json` 或 `plan.json` 被截断或格式损坏（例如写入过程中发生崩溃），该 run 的所有路由均会返回 `500`。其他 run 不受影响。请直接检查该文件，必要时将其删除——在执行 `micro-eval index import-json` 之前，索引条目将保持过期状态。
:::

---

## 纯本地设计

该 API 没有认证、没有限流、也没有 CORS 头。它仅供 `micro-eval ui` 命令打开的浏览器标签页在 `localhost` 上使用。

::: danger 请勿暴露至网络
不要将 Next.js 服务器绑定到 `0.0.0.0`，也不要通过面向公网的服务器对其进行反向代理。写入端点（`POST /evaluate`）没有任何访问控制，且 `.micro-eval/` 中的 run 数据可能包含在 artifact 捕获前未被完全脱敏的敏感 agent 输出或密钥。
:::

## 相关页面

- [趋势分析](/zh/guide/trend-analysis) — SQLite 索引与漂移断点的工作原理
- [评分](/zh/guide/evaluation) — 三层评分流水线（确定性校验 → LLM judge → 人工）
- [安全模型](/zh/guide/security) — 密钥脱敏、workspace 边界与子进程隔离
- [Web UI](/zh/reference/web-ui) — 消费这些路由的浏览器界面

---

## 服务器模式 API 路由

以下路由仅在运行 `micro-eval serve` 时可用。在本地模式（`micro-eval ui`）下访问这些路由会返回 `404`。

::: warning 仅限内网
服务器模式路由**没有认证机制**。身份通过 `X-Micro-Eval-Member` HTTP 请求头自我申报，仅用于归因，不作为访问控制依据。请仅在受信的私有网络中部署。
:::

::: info 注意事项
- **服务器模式路由在非服务器模式下运行时返回 404。**
- **所有写入路由均需要 `X-Micro-Eval-Member` 请求头和 `Content-Type: application/json`。**
:::

### 概览

| 方法 | 路由 | 用途 |
|--------|-------|---------|
| `GET` | `/api/workspaces` | 列出所有 workspace |
| `POST` | `/api/workspaces` | 创建新 workspace |
| `GET` | `/api/workspaces/[id]` | 获取 workspace 元数据 |
| `PATCH` | `/api/workspaces/[id]` | 更新 workspace 元数据 |
| `DELETE` | `/api/workspaces/[id]` | 删除 workspace |
| `GET` | `/api/workspaces/[id]/runs` | 列出 workspace 内的 run |
| `POST` | `/api/workspaces/[id]/runs/enqueue` | 入队新的运行任务 |
| `GET` | `/api/workspaces/[id]/runs/[runId]` | 获取 workspace 内的某次 run |
| `GET` | `/api/workspaces/[id]/config` | 获取 workspace 的 eval.yaml |
| `GET` | `/api/workspaces/[id]/trends` | 查询 workspace 作用域的趋势数据 |
| `GET` | `/api/queue` | 获取队列面板摘要 |
| `GET` | `/api/jobs/[jobId]` | 获取单个任务记录 |
| `POST` | `/api/jobs/[jobId]/cancel` | 取消排队或运行中的任务 |
| `GET` | `/api/templates` | 列出所有模板 |
| `GET` | `/api/templates/[id]` | 获取单个模板 |
| `GET` | `/api/server/status` | 服务器健康状态和进程信息 |

---

### Workspace 路由

**GET /api/workspaces** — 返回 `WorkspaceMeta` 对象列表，按 `last_run_at` 倒序排列。默认不包含已归档的 workspace；传入 `?include_archived=true` 可包含它们。

**POST /api/workspaces** — 创建新 workspace。请求体字段：`name`（必填）、`owner`（必填）、`template_id`、`description`。返回创建的 `WorkspaceMeta`。

**GET /api/workspaces/[id]** — 获取单个 workspace 的完整元数据。

**PATCH /api/workspaces/[id]** — 更新 `name`、`description` 或 `status`（`active` | `archived`）。返回更新后的 `WorkspaceMeta`。

**DELETE /api/workspaces/[id]** — 删除 workspace 及其所有关联的 run 数据，返回 `204 No Content`。此操作不可恢复。

**GET /api/workspaces/[id]/config** — 以 `text/plain` 格式返回 workspace 的原始 `eval.yaml` 内容。

**GET /api/workspaces/[id]/trends** — 与本地 `/api/trends` 路由格式相同，但仅限于该 workspace 的 run。支持 `config_id`、`since`、`limit` 查询参数。

---

### 运行入队与状态

**GET /api/workspaces/[id]/runs** — 列出 workspace 内的所有 run，按时间倒序排列，返回 `RunRecord[]` 摘要。

**POST /api/workspaces/[id]/runs/enqueue** — 为该 workspace 入队新的评测运行。worker 会串行取出并执行。

请求体：

```json
{
  "overrides": {}
}
```

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `overrides` | object | 否 | 在构建计划前，叠加到 workspace `eval.yaml` 之上的 JSON 覆盖字段。 |

响应：创建的 `Job` 记录（状态：`queued`）。

必填请求头：`X-Micro-Eval-Member`、`Content-Type: application/json`。

**GET /api/workspaces/[id]/runs/[runId]** — 获取 workspace 内已完成的某次 run 记录。格式与本地 `/api/runs/[id]` 路由相同。

---

### 队列路由

**GET /api/queue** — 返回跨所有 workspace 的整体队列摘要。

```json
{
  "queued": 2,
  "running": 1,
  "done_today": 14,
  "jobs": [ /* 任务记录，最新的在前 */ ]
}
```

**GET /api/jobs/[jobId]** — 通过 ID 获取单条 `Job` 记录，包含 `status`、`progress`、时间戳及错误信息。

**POST /api/jobs/[jobId]/cancel** — 请求取消排队或运行中的任务。排队中的任务立即取消；运行中的任务完成当前 cell 后停止。请求体：`{}`。必填请求头：`X-Micro-Eval-Member`、`Content-Type: application/json`。

---

### 模板路由

模板通过 CLI（`micro-eval template create/update/delete`）管理，通过浏览器 API 为**只读**。

**GET /api/templates** — 以 `TemplateMeta[]` 形式列出所有模板。

**GET /api/templates/[id]** — 获取单个模板的元数据。不返回模板文件内容；如需检查文件，请使用 CLI。

---

### 服务器状态

**GET /api/server/status** — 返回基本的服务器健康信息。

```json
{
  "version": "0.4.1",
  "mode": "server",
  "worker_alive": true,
  "queue_depth": 2,
  "data_root": "/srv/micro-eval",
  "uptime_s": 3601
}
```
