# Issue #1: Decision 算法单一来源 — 实施方案 (v2)

> v2: 根据 Codex review 修订。回应 6 条审查意见（2 critical, 3 important, 1 minor）。

## 问题

UI 提交 human evaluation 时，TypeScript `recomputeDecision()` 手工镜像了 Python `build_decision()` + `build_aggregation()` 的完整决策算法（pass@k/pass^k、cost 聚合、caveat 收集、verdict ladder），约 130 行 TS 重复约 190 行 Python。v0.2.4 加了跨语言等价性契约测试防漂移，但重复代码和维护负担仍在。

额外问题：TS 侧 `buildHumanEvaluation` 的 hash 输入是 `JSON.stringify({cellId, input, createdAt})`，Python 侧是 `f"{cell_id}|{pass_fail}|{score}|..."` — 同一笔评分在两个路径下会产生不同的 `evaluation_id`。这是重复实现导致的隐性不一致。

## 目标

- Python `build_decision()` 成为唯一决策算法
- Python `build_human_evaluation()` 成为唯一 evaluation 构造路径
- UI `recomputeDecision()` 及全部 evaluation 构造/写入代码被删除
- human evaluation 提交后仍能即时返回更新后的 decision

## 方案：evaluate route 完全委托 Python subprocess

### 原理

`RunStore.append_evaluation()` (run_store.py L96-140) 已实现完整流程：追加 evaluation + evidence → 更新 cell refs → 调用 `build_decision` → 写入 run.json + decision.json。`build_human_evaluation()` (evaluation/human.py) 已实现 evaluation + evidence 构造。UI 只需把用户输入传给 Python，Python 走已有路径完成所有工作。

本项目是本地 CLI 工具，evaluate 是低频人工交互，subprocess 延迟（~200-500ms）完全可接受。

### 改动清单

#### 1. 新增 Python CLI 子命令 `micro-eval apply-evaluation`

**文件**: `src/micro_eval/cli/evaluate.py`（新建）

```python
# Accepts JSON payload via stdin to support complex fields (scores dict).
# Outputs { evaluation, evidence, decision } JSON to stdout.
# All logs go to stderr; stdout is reserved for machine-readable output.
@app.command("apply-evaluation")
def apply_evaluation_command(
    run_id: str = typer.Option(..., "--run-id", help="Run ID"),
    cell_id: str = typer.Option(..., "--cell-id", help="Cell ID"),
):
    project_root = Path.cwd()
    payload = json.load(sys.stdin)
    # payload: { pass_fail, score, scores, comment, evaluator }
    evaluation, evidence = build_human_evaluation(
        cell_id=cell_id,
        pass_fail=payload.get("pass_fail"),
        score=payload.get("score"),
        scores=payload.get("scores"),
        comment=payload.get("comment", ""),
        evaluator=payload.get("evaluator", "human"),
    )
    store = RunStore(project_root)
    record = store.append_evaluation(
        run_id=run_id, cell_id=cell_id,
        evaluation=evaluation, evidence=evidence,
    )
    result = {
        "evaluation": evaluation.model_dump(mode="json"),
        "evidence": evidence.model_dump(mode="json"),
        "decision": record.decision.model_dump(mode="json") if record.decision else None,
    }
    sys.stdout.write(json.dumps(result))
```

> **Review #1 回应**: 使用 stdin JSON 模式而非逐个 CLI flag，解决 `scores`（`Record<string, float>`）无法通过简单 flag 传递的问题。

**文件**: `src/micro_eval/cli/main.py` — 注册子命令

#### 2. 改写 UI evaluate API route

**文件**: `ui/src/app/api/runs/[id]/cells/[cellId]/evaluate/route.ts`

Before:
```ts
const { evaluation, evidence } = buildHumanEvaluation(decodedCellId, input);
appendEvaluationFile(runDir, decodedCellId, evaluation);
const updatedRun = appendEvaluationToRun(run, evaluation, evidence);
saveRun(updatedRun);
return NextResponse.json({ evaluation, evidence, decision: updatedRun.decision });
```

After:
```ts
import { execFileSync } from "node:child_process";

// argv-only: user input fields are array elements, never interpolated into a shell string.
const uvBin = process.env.MICRO_EVAL_UV_PATH || "uv";
const args = ["run", "micro-eval", "apply-evaluation", "--run-id", id, "--cell-id", decodedCellId];
let result;
try {
  const stdout = execFileSync(uvBin, args, {
    input: JSON.stringify(input),
    encoding: "utf-8",
    cwd: getProjectRoot(),
    timeout: 30_000,
  });
  result = JSON.parse(stdout);
} catch (err) {
  // If stdout is not valid JSON (e.g. Python warning leaked to stdout),
  // return the raw output in the error for debugging.
  const detail = err instanceof Error ? err.message : String(err);
  return NextResponse.json({ error: "evaluation backend failed", detail }, { status: 502 });
}
return NextResponse.json(result);
```

> **Review #3 回应**: 明确使用 `execFileSync(bin, [...args])` 数组形式，user input 通过 stdin 传入，不参与 argv 构造，杜绝 shell injection。
>
> **Review #4 回应**: 支持 `MICRO_EVAL_UV_PATH` 环境变量覆盖，默认 fallback 到 PATH 中的 `uv`。
>
> **Review #5 回应**: `JSON.parse` 包在 try/catch 中，失败时返回 502 + 原始错误信息。

#### 3. 删除 UI 侧重复代码

**文件**: `ui/src/lib/evaluation.ts`

**整个文件删除。** 理由：
- `recomputeDecision()` + 6 个辅助函数（`aggregateCost`, `passAtK`, `passHatK`, `combination`, `dedupe`, `median`）— 决策算法重复，~130 行
- `appendEvaluationToRun()` — 调用 `recomputeDecision` 的唯一入口，~15 行
- `buildHumanEvaluation()` — Python `build_human_evaluation` 替代，~40 行
- `appendEvaluationFile()` — Python `RunStore.append_evaluation` 内部已处理，~7 行
- `redactSecrets()` — 无其他调用方（grep 确认），~7 行
- `safePathSegment()` — 无其他调用方（grep 确认），~4 行
- `HumanEvaluationInput` interface — 不再需要（输入验证由 route 中的 zod schema 完成）

**文件**: `ui/src/app/api/runs/[id]/cells/[cellId]/evaluate/route.ts` — 删除对 `@/lib/evaluation` 的 import

> **Review #2 回应**: Evaluation ID 生成格式差异问题。本方案是一次性切换（不存在"迁移期"），切换后所有新 evaluation 由 Python `build_human_evaluation` 构造，使用 Python 的 ID 格式。已有旧 evaluation 的 ID 已固化在 run.json 中，不受影响——它们的 `evaluation_id` 是 stable ID，只要不重复即可正常工作，无需迁移。

#### 4. 更新测试

**删除**:
- `ui/src/lib/__tests__/decision-equivalence.test.ts` — 不再有 TS 侧算法需要对比
- `ui/src/lib/__tests__/evaluation.test.ts` — 整个文件（所有用例都测试被删除的函数）

**不新增测试**：新 CLI 子命令是 ~30 行胶水，调用的 `build_human_evaluation`、`RunStore.append_evaluation`、`build_decision` 各自已有测试覆盖。给薄胶水层加专门测试是过度测试。

**保留**:
- `tests/contract/golden/decision-equivalence.json` — 继续保留
- `tests/contract/test_golden.py::test_decision_equivalence_golden_matches_python_algorithm` — 继续保留（验证 `build_decision` 本身不退化）
- `scripts/generate-golden.py::_write_decision_equivalence_fixture()` — 继续保留

> **Review #6 回应**: golden fixture 保留策略明确如上。`decision-equivalence.json` 和 Python 侧 golden 测试继续保护 `build_decision` 不退化。仅删除 TS 侧消费方（`decision-equivalence.test.ts`）。Python 侧 golden test 的 docstring 中"The vitest counterpart asserts recomputeDecision produces the same decision"一句需更新，改为说明该 fixture 现仅由 Python 侧消费。

### 不改动

- `ui/src/lib/schema.ts` — zod schema 不变（`DecisionReportSchema` 用于解析 Python 返回的 JSON）
- `ui/src/lib/api.ts` — `getRun`, `saveRun` 等不变（evaluate route 不再调用 `saveRun`，Python 负责写盘）
- `src/micro_eval/decision/summary.py` — 保持不变，它就是 single source of truth
- `src/micro_eval/decision/aggregation.py` — 保持不变
- `src/micro_eval/store/run_store.py` — `append_evaluation` 保持不变，CLI 直接调用它
- `src/micro_eval/evaluation/human.py` — 保持不变，CLI 直接调用它

### 依赖与风险

| 风险 | 缓解 |
|------|------|
| subprocess 找不到 `uv` | 支持 `MICRO_EVAL_UV_PATH` 环境变量；失败时返回 502 + 清晰错误信息 |
| Python 侧 import warning 污染 stdout | CLI 子命令显式配置 logging handler 到 stderr；TS 侧 JSON.parse 有 try/catch 兜底 |
| 并发 evaluate 请求竞争 run.json 写入 | 当前已有此风险，Python RunStore 同理。低频人工操作下可忽略；未来可加文件锁 |
| 旧 TS 路径产生的 evaluation ID 格式与新 Python 路径不同 | 一次性切换，不存在混用期。旧 ID 已固化在 run.json，新 ID 由 Python 生成，两者不冲突 |

### 实施顺序

1. **Step 1**: 新增 Python CLI 子命令（纯 Python，不碰 UI）
2. **Step 2**: 改写 UI evaluate route 调用 subprocess（此时 TS 侧旧代码仍在，可作为 fallback 验证）
3. **Step 3**: 验证 UI 端到端工作后，删除 `evaluation.ts` + 相关测试
4. **Step 4**: 更新 golden test docstring，运行全套测试确认绿色

### 改动量估算

| 范围 | 新增/修改 | 删除 |
|------|----------|------|
| Python CLI 子命令 (`evaluate.py`) | ~45 行 | 0 |
| Python CLI 注册 (`main.py`) | ~2 行 | 0 |
| UI evaluate route | ~25 行 | ~10 行 |
| UI `evaluation.ts` | 0 | **226 行（整文件）** |
| UI tests | 0 | ~200 行 |
| Golden test docstring | ~2 行 | ~2 行 |
| **合计** | **~74 行** | **~438 行** |

净删除 ~364 行。决策算法和 evaluation 构造均归一到 Python 单一来源。
