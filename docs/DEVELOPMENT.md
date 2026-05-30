# 开发指南

## 前置要求

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)（推荐）或 pip
- Node.js 18+（Web UI 开发）
- Git（workspace 隔离功能需要）

## 开发环境搭建

### Python CLI + 引擎

```bash
# 克隆仓库
git clone <repo-url> && cd micro-eval

# 安装开发依赖
uv pip install -e ".[dev,scoring,observability]"

# 验证安装
micro-eval --help

# 运行测试
uv run pytest
```

### Web UI

```bash
cd ui
npm install
npm run dev    # http://localhost:3000
```

UI 默认读取上级目录的 `.micro-eval/runs/` 数据。可通过环境变量覆盖：

```bash
MICRO_EVAL_PROJECT_ROOT=/path/to/project npm run dev
```

## 项目结构

```
micro-eval/
├── src/micro_eval/
│   ├── cli/                 # CLI 入口与命令
│   │   ├── main.py          # Typer app 注册
│   │   ├── run.py           # run 命令实现
│   │   └── report.py        # report 命令 + Jinja2 模板
│   ├── config/
│   │   └── loader.py        # YAML 配置加载与校验
│   ├── engine/
│   │   ├── runner.py        # 核心执行引擎（asyncio）
│   │   ├── scorer.py        # 评分逻辑
│   │   └── workspace.py     # git worktree 隔离
│   └── models/
│       └── schema.py        # Pydantic 领域模型
├── tests/
│   ├── unit/                # 单元测试
│   └── e2e/                 # 端到端测试
├── ui/                      # Next.js Web UI
│   └── src/
│       ├── app/             # App Router 页面
│       ├── components/      # React 组件
│       └── lib/             # 数据层 + zod schema
├── eval.yaml.example        # 配置示例
└── pyproject.toml           # Python 项目配置
```
## 架构图

```
用户
 │
 ▼
┌──────────────────────────────────────────────────────────────┐
│ CLI Layer (Typer)                                            │
│ main.py → run.py / report.py / ui                           │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ Config Layer                                                 │
│ loader.py: load_config() → ProjectConfig                     │
│            load_tasks()  → list[Task]                        │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ Execution Layer                                              │
│                                                              │
│ AgentRunner.run_eval()                                       │
│   ├─ asyncio.gather (parallel) 或 sequential loop            │
│   └─ _run_single(agent, task)                                │
│       ├─ 准备输入 (stdin / file)                              │
│       ├─ asyncio.create_subprocess_shell                     │
│       ├─ wait_for(timeout)                                   │
│       └─ 收集输出 (stdout / file)                             │
│                                                              │
│ Scorer.score() → 0.0~1.0                                    │
│ Scorer.judge_pass_fail() → TaskStatus                        │
│                                                              │
│ WorkspaceManager                                             │
│   ├─ create() → git worktree add --detach                   │
│   ├─ collect_diff() → git diff                              │
│   └─ cleanup() → git worktree remove                        │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ Data Layer                                                   │
│ Pydantic models (schema.py) → JSON 序列化                     │
│ 存储: .micro-eval/runs/<run-id>.json                         │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ Web UI (Next.js 16 + React 19 + Tailwind 4)                 │
│ api.ts: 读取 .micro-eval/runs/ JSON 文件                      │
│ schema.ts: zod 校验（与 Python Pydantic 对齐）                 │
│ ComparisonTable / RunList / AnnotationPanel                  │
└──────────────────────────────────────────────────────────────┘
```

## 关键设计决策

以下决策来自工程评审，是代码实现的约束边界：

### 1. 自写执行层，不用 DeepEval 做编排

**原因**：DeepEval 的 test runner 假设同步、单 agent 场景，无法满足 baseline/candidate 并行对比需求。自写 ~200 行 asyncio 代码完全可控。

**体现**：`engine/runner.py` 中 `AgentRunner` 直接调用 `asyncio.create_subprocess_shell`，DeepEval 仅在 `scorer.py` 中作为可选评分库。

### 2. stdin/文件传参，禁止 shell 字符串插值

**原因**：防止注入攻击，保证输入完整性（含特殊字符、多行文本）。

**体现**：`_run_single()` 中 `input_payload` 通过 `proc.communicate(input=...)` 传入 stdin，或写入临时文件后通过 `{input_file}` 模板变量注入路径。

### 3. git worktree 隔离

**原因**：保证每次 run 的起点一致（同一 commit），baseline 和 candidate 不互相污染。

**体现**：`workspace.py` 中 `WorkspaceManager.create()` 调用 `git worktree add --detach`。

### 4. asyncio 并行执行

**原因**：baseline 和 candidate 独立运行，并行可将总耗时减半。

**体现**：`run_eval()` 中 `asyncio.gather(*coros)` 并行执行所有 task × agent 组合。

### 5. Pydantic + zod 双端 schema

**原因**：Python 端和 TypeScript 端共享数据契约，JSON 文件是两端的桥梁。

**体现**：`models/schema.py`（Pydantic）与 `ui/src/lib/schema.ts`（zod）字段一一对应。

## 测试

### 运行测试

```bash
# 全部测试
uv run pytest

# 仅单元测试
uv run pytest tests/unit/

# 仅 E2E 测试
uv run pytest tests/e2e/

# 带覆盖率
uv run pytest --cov=micro_eval

# 单个文件
uv run pytest tests/unit/test_runner.py -v
```

### 测试结构

```
tests/
├── conftest.py              # 共享 fixtures
├── unit/
│   ├── test_schema.py       # 模型序列化/反序列化
│   ├── test_config_loader.py # 配置加载与校验
│   └── test_runner.py       # 执行引擎（mock subprocess）
└── e2e/
    └── test_full_flow.py    # 完整 run 流程
```

### 编写新测试

测试使用 `pytest` + `pytest-asyncio`。异步测试标记 `@pytest.mark.asyncio`：

```python
import pytest
from micro_eval.engine.runner import AgentRunner
from micro_eval.models.schema import AgentConfig, Task

@pytest.mark.asyncio
async def test_my_feature(tmp_path):
    agent = AgentConfig(name="test", command="echo hello")
    task = Task(
        id="t1",
        name="test task",
        input_payload="input",
    )
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(agent, task)
    assert result.status.value == "pass"
```

`pyproject.toml` 已配置 `asyncio_mode = "auto"`，无需手动设置 event loop。

## 添加新功能指南

### 添加新 CLI 命令

1. 在 `src/micro_eval/cli/` 下创建新模块（如 `compare.py`）
2. 定义命令函数，使用 Typer 装饰器
3. 在 `main.py` 中注册：`app.command(name="compare")(compare_command)`

### 添加新评分策略

1. 在 `engine/scorer.py` 的 `Scorer` 类中添加方法
2. MVP 阶段使用简单逻辑；后续可引入 DeepEval 的 `CustomMetric`
3. 在 `cli/run.py` 的评分循环中调用新方法

### 添加新领域模型

1. 在 `models/schema.py` 中定义 Pydantic model
2. 同步更新 `ui/src/lib/schema.ts` 中的 zod schema
3. 确保字段名、类型、可选性完全对齐

### 扩展 Web UI

1. 页面放在 `ui/src/app/` 下（App Router）
2. 组件放在 `ui/src/components/`
3. 数据读取通过 `ui/src/lib/api.ts`（Server Component 直接读文件系统）

## 代码风格与约定

### Python

- 类型注解：所有函数签名必须有类型标注
- 使用 `from __future__ import annotations` 延迟求值
- 模型定义使用 Pydantic v2 `BaseModel`
- 异步代码使用 `asyncio`，不用 threading
- 错误处理：自定义异常类（`ConfigError`, `RunnerError`, `WorkspaceError`）

### TypeScript

- 严格模式（`strict: true`）
- 数据校验使用 zod，不用 `any`
- 组件使用函数式 + TypeScript interface 定义 props
- 样式使用 Tailwind CSS utility classes

### 通用

- 配置文件使用 YAML
- 数据交换使用 JSON（Pydantic `model_dump_json()`）
- 文件路径使用 `pathlib.Path`
- 日志/输出使用 `rich` 库


