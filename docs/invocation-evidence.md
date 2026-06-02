# Invocation Evidence Capture

本文说明 `0.1.1` 的 agent 调用证据捕获能力。它是从 legacy `v0.1` flat run schema 走向 `mvp.local_pairwise.v1` Artifact/Trace Layer 的过渡层，不是最终 P0 artifact 模型。

## 变化范围

每次 agent invocation 现在会记录足够解释执行过程的证据：

- `stdout_summary`：stdout 的短摘要。
- `stdout_ref`：保留 stdout 文本的项目相对路径。
- `stderr_summary`：stderr 的短摘要。
- `stderr_ref`：保留 stderr 文本的项目相对路径。
- `exit_code`：子进程退出码，能取得时记录。
- `output_dir`：本次 invocation 的 artifact 目录。
- `output_artifacts`：`file` 或 `directory` output mode 生成的输出文件。
- `failure_mode`：timeout 或非零退出等结构化失败提示。

run JSON 仍写入 `.micro-eval/runs/{run_id}.json`。Invocation artifacts 另行写入：

```text
.micro-eval/
├── runs/
│   └── {run_id}.json
└── artifacts/
    └── {run_id}/
        └── {task_id}--{agent_name}/
            ├── input.txt
            ├── stdout.txt
            ├── stderr.txt
            ├── output.txt
            └── ...other output files
```

## Agent I/O 契约

Agent command 会通过 `shlex.split()` 解析为 argv，并由 `asyncio.create_subprocess_exec` 执行。Task 内容通过 stdin 或 runner-owned input file 传入，不插入 shell 字符串。

`agent.command` 支持这些占位符：

| Placeholder | 含义 |
|-------------|------|
| `{input_file}` | `input_mode: file` 时的 runner-owned input file 路径 |
| `{output_dir}` | 输出 artifact 目录 |
| `{output_file}` | `output_mode: file` 的首选输出文件路径 |

子进程环境先从 host environment allowlist 继承，再合并 `agent.env`。Runner 还会注入：

| Variable | 含义 |
|----------|------|
| `MICRO_EVAL_OUTPUT_DIR` | 与 `{output_dir}` 相同 |
| `MICRO_EVAL_OUTPUT_FILE` | 与 `{output_file}` 相同 |

## Output Modes

`stdout` mode 使用 stdout 作为 scoring output，同时仍持久化 stdout/stderr artifacts。

`file` mode 优先读取 `MICRO_EVAL_OUTPUT_FILE` / `{output_file}`。如果该文件不存在，runner 会读取 output directory 中第一个非内部文件。

`directory` mode 会把 output directory 下的非内部文件收集到 `output_artifacts`。如果 stdout 为空，`output_summary` 会列出 artifact refs。

## 安全行为

Runner 对 stdout/stderr 各自最多保留 10 MB。任一流被截断时，`stderr_summary` 会附加 micro-eval truncation note。

文本输出在保存为 artifact 或 summary 前，会对 `agent.env` 中的值做 redaction。包含 NUL 字节的 binary-like artifacts 会跳过 in-place redaction。

## 当前限制

本 slice 有意小于完整 MVP profile：

- 还没有 `manifest.json`。
- 还没有 canonical `ArtifactRef` / `EvidenceItem` ID。
- 还没有 `RunPlan`、`RunCell` 或 Configuration matrix。
- 还没有 SameStartSnapshot、CellSnapshot 或 SnapshotGateResult。
- 还没有用于人工评分持久化的 `evaluation.json`。
- Cell artifact path 仍基于 `task_id--agent_name`；baseline/candidate 使用同名 agent 时仍可能碰撞。

下一步架构工作应先做 P0-a：引入 Configuration、RunPlan、RunCell、AgentInvocation、AdapterResult 和 Local CLI adapter，同时保留当前 evidence 行为。
