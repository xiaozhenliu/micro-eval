# 趋势分析

跟踪各个 configuration 在多次 run 中随时间推移的表现。趋势分析可以帮助你回答诸如"上次 prompt 修改是否提升了通过率？"或"升级底层模型后，agent 延迟是否出现了漂移？"等问题。

## 工作原理

micro-eval 以 JSON run 文件作为**权威数据源**。在 JSON store 旁边还有一个派生的 SQLite 索引，它支持快速的时间序列查询，而无需重复存储数据。

```
.micro-eval/
├── runs/
│   ├── run_20260610_143022.json   ← 权威数据源
│   ├── run_20260611_090155.json
│   └── run_20260614_171843.json
└── index.db                       ← 派生索引，可从 JSON 重建
```

每当 `run_store.finalize_run` 写入新的 run 时，索引会自动更新。v0.3.0 之前已有的 JSON run 可以通过一条命令导入：

```bash
uv run micro-eval index import-json
```

::: tip 索引存储的内容
SQLite 索引为每个 run 存储轻量级元数据——config digest、task id 列表、通过计数、延迟百分位数、总费用以及时间戳。原始 artifacts 和 trace 仅保留在 JSON 中。
:::

## 漂移感知断点

**configuration digest** 是对实际影响 configuration 执行方式的字段所计算的哈希值，包括：`command`、`params`、`repetitions` 和 `skills_profile`。digest 会与每条 run 记录一同存入索引。

当你在多次 run 中复用同一个 configuration id，但修改了其内容——例如指向新的 agent 命令或调整超时时间——digest 就会发生变化。micro-eval 会在这两次 run 之间记录一个**漂移断点**：

```
Run 1 (2026-06-10)  Run 2 (2026-06-11)  ⚡ DRIFT  Run 3 (2026-06-14)  Run 4 (2026-06-15)
[digest: a3f9...]   [digest: a3f9...]             [digest: c1d7...]   [digest: c1d7...]
                                          ↑
                              config.command 已更改
```

::: warning 不要跨断点得出结论
漂移断点前后的结果属于不同的 configuration——即使 id 相同也是如此。跨断点比较通过率，就像在比较两个不同的 agent，结论会产生误导。趋势图会在图表上直观标注断点，让你清晰看到不连续点的位置。
:::

### 触发断点的条件

| 变更字段 | 是否记录断点？ |
|---------------|---------------------|
| `command` | 是 |
| `params` | 是 |
| `repetitions` | 是 |
| `skills_profile` | 是 |
| `description`（仅标签） | 否 |
| `environment` 变量 | 否 |

## 通过 API 查询趋势

Next.js 本地 UI 暴露了一个 `/api/trends` 路由，供趋势图表页面调用。你也可以直接查询该路由用于脚本或调试。

**必填参数：** `config_id`——你想查看的 configuration id。

```bash
curl "http://localhost:3000/api/trends?config_id=my-agent"
```

**响应示例：**

```json
{
  "config_id": "my-agent",
  "series": [
    {
      "run_id": "run_20260610_143022",
      "timestamp": "2026-06-10T14:30:22Z",
      "digest": "a3f9c2b1",
      "pass_rate": 0.72,
      "p50_latency_ms": 4200,
      "p95_latency_ms": 9800,
      "total_cost_usd": 0.031,
      "breakpoint_after": false
    },
    {
      "run_id": "run_20260611_090155",
      "timestamp": "2026-06-11T09:01:55Z",
      "digest": "a3f9c2b1",
      "pass_rate": 0.75,
      "p50_latency_ms": 4100,
      "p95_latency_ms": 9500,
      "total_cost_usd": 0.029,
      "breakpoint_after": true
    },
    {
      "run_id": "run_20260614_171843",
      "timestamp": "2026-06-14T17:18:43Z",
      "digest": "c1d7a412",
      "pass_rate": 0.81,
      "p50_latency_ms": 3700,
      "p95_latency_ms": 8200,
      "total_cost_usd": 0.027,
      "breakpoint_after": false
    }
  ],
  "breakpoints": [
    {
      "after_run_id": "run_20260611_090155",
      "reason": "digest changed: a3f9c2b1 → c1d7a412",
      "timestamp": "2026-06-14T17:18:43Z"
    }
  ]
}
```

### 可选参数

| 参数 | 默认值 | 说明 |
|-----------|---------|-------------|
| `config_id` | *（必填）* | 要查询的 configuration id |
| `since` | *（全部 run）* | ISO-8601 时间戳；排除该日期之前的 run |
| `limit` | `50` | 返回的最大 run 数量 |

```bash
# 6 月 1 日以来的最近 10 次 run
curl "http://localhost:3000/api/trends?config_id=my-agent&since=2026-06-01T00:00:00Z&limit=10"
```

## 在 UI 中查看趋势

启动本地 UI 并打开 **Trends** 标签页：

```bash
uv run micro-eval ui
# 在浏览器中打开 http://localhost:3000
```

趋势图展示以下内容：
- **通过率**随时间变化（主 y 轴）
- **P50 / P95 延迟**作为次要序列
- **每次 run 的费用**以柱状图展示
- **漂移断点**以垂直虚线标注，并附带说明 digest 变化的提示框

将鼠标悬停在任意数据点上，可查看 run id、时间戳及 task 明细。点击数据点可直接跳转到该 run 的结果矩阵页面。

## 使用场景

### Prompt 变更后的回归检测

你更新了 agent 的系统 prompt，想确认它是否破坏了已有 task：

```bash
# 在变更前后使用相同的 config id 运行评测套件
uv run micro-eval run --config eval.yaml

# 修改 prompt 后再次运行
uv run micro-eval run --config eval.yaml

# 打开趋势图，比较相邻的两个数据点
uv run micro-eval ui
```

如果两次 run 的 `breakpoint_after` 均为 `false`（相同 digest），则可以直接比较通过率和延迟。

### 持续监控 Agent 表现

在 CI 中设置每晚运行评测套件，并将结果写入本地 store：

```yaml
# .github/workflows/nightly-eval.yml
name: Nightly Eval
on:
  schedule:
    - cron: '0 2 * * *'
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install uv && uv sync
      - run: uv run micro-eval run --config eval.yaml
      - uses: actions/upload-artifact@v4
        with:
          name: eval-results-${{ github.run_id }}
          path: .micro-eval/runs/
```

将 artifacts 下载到本地后导入：

```bash
# 将 artifacts 解压到 .micro-eval/runs/，然后重建索引
uv run micro-eval index import-json
uv run micro-eval ui
```

### 检测基础设施变更的影响

当你升级模型提供商、更改 sandbox 配置或切换隔离级别时，configuration digest 可能会发生变化，从而产生漂移断点。以此为信号，在断点两侧各运行一组更大的 repetition 集，以确认通过率差异是否具有统计意义。

::: tip Configuration digest 覆盖执行环境，而非基础设施
将 OS sandbox 从 `os_policy`（Seatbelt）切换为 `logical`（git worktree）不会改变 configuration digest，因为 `isolation_level` 不在 digest 范围内。只有直接影响 agent 接收内容和执行行为的字段才会被纳入 digest 计算。如果你想比较不同的隔离级别，请使用独立的 configuration id。
:::

## 重建索引

SQLite 索引完全派生自 JSON 数据。若索引损坏或与 JSON 不同步，可删除后重建：

```bash
# 删除过期索引
rm .micro-eval/index.db

# 从 store 中的所有 JSON run 重建索引
uv run micro-eval index import-json
```

::: warning index.db 不是备份
永远不要将 `index.db` 视为权威数据源。请始终保留 JSON run 文件。一旦删除 JSON run，这些数据点将从趋势历史中永久消失。
:::

## 后续步骤

- [安全性](/zh/guide/security) — 如何对 secrets 进行脱敏处理以及如何执行 workspace 边界约束
