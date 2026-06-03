---
title: "Agentic Rubrics 工程研究报告"
date: 2026-06-01
status: 完成
type: research
version: "1.0"
tags:
  - rubric-engineering
  - scoring
  - research
---

# Agentic Rubrics 工程研究报告

## micro-eval 项目技术文档 v1.0

---

## 1. Executive Summary

### 什么是 Agentic Rubric？

Agentic Rubric 是一种**结构化的、可编程的评分系统**，用于评估 AI Agent 的输出质量。与传统的"LLM-as-Judge"（让一个 LLM 直接打分）不同，Agentic Rubric 将评分分解为多个独立的**验证器（Verifier）**，每个验证器负责一个具体维度的检查，最终通过加权聚合产生可解释的综合分数。

核心洞察：**确定性验证 > LLM 判断**。Scale AI 的研究表明，当 rubric 与测试结果不一致时，rubric 在 54% 的情况下实质正确——但这也意味着 46% 的情况下测试更可靠。最佳策略是分层：能用代码验证的绝不用 LLM，LLM 仅处理代码无法覆盖的主观维度。

### 成本-可靠性权衡

| 验证方式 | 单次成本 | 可靠性 | 延迟 |
|---------|---------|--------|------|
| 确定性检查（regex/diff/test） | ~$0 | 高（但覆盖窄） | <1s |
| 启发式评分（ROUGE/语义相似度） | ~$0 | 中 | <1s |
| LLM-as-Judge（单次调用） | $0.01-0.10 | 中（受操纵风险） | 2-10s |
| Agentic 验证（代码执行+LLM） | $0.05-0.50 | 高（如果隔离正确） | 10-60s |
| 人工评判 | $5-50 | 最高 | 分钟-小时 |

**决策点**：micro-eval MVP 应优先实现 Layer 0-1（确定性验证），Phase 2 引入 LLM 评分，Phase 3 实现自适应路由。验证成本不应超过 agent 执行成本的 30%。

---

## 2. 核心概念模型

### 2.1 Agentic Rubric 的定义

Agentic Rubric = **结构化评分维度** + **可编程验证器** + **加权聚合策略** + **证据链**

与传统方法的对比：

| 特征 | 传统 LLM-as-Judge | Agentic Rubric |
|------|-------------------|----------------|
| 评分过程 | 单次 LLM 调用 | 多验证器并行执行 |
| 可解释性 | 自然语言理由 | 结构化证据链 |
| 可复现性 | 低（温度/随机性） | 高（确定性层完全可复现） |
| 抗操纵性 | 低（prompt injection） | 高（确定性检查不可绕过） |
| 成本 | 固定（每次一次 LLM 调用） | 可变（按需触发昂贵层） |
| 维度覆盖 | 依赖 prompt 质量 | 显式定义，可审计 |

### 2.2 分类体系

```
Agentic Rubric
├── 确定性 Rubric（全部由代码验证器组成）
│   ├── 测试通过率
│   ├── 构建成功
│   ├── Lint/Type 检查
│   └── Schema 合规
├── 混合 Rubric（确定性 + LLM）
│   ├── 代码正确性 + 风格评判
│   ├── 功能验证 + 可读性评分
│   └── 安全检查 + 设计合理性
└── 自适应 Rubric（根据任务动态生成维度）
    ├── 代码修复类 → [correctness, integrity, completeness]
    ├── 对话类 → [relevance, coherence, helpfulness]
    └── 工具使用类 → [tool_selection, parameter_accuracy, error_handling]
```

### 2.3 评分可靠性光谱

```
确定性验证 ──→ 启发式评分 ──→ LLM 评判 ──→ 人工评判
  │                │              │              │
  │ 可复现性=100%  │ 可复现=95%+  │ 可复现=60-80% │ 可复现=70-85%
  │ 覆盖面=窄     │ 覆盖=中      │ 覆盖=广       │ 覆盖=最广
  │ 成本=零       │ 成本=极低    │ 成本=中        │ 成本=极高
  │ 抗操纵=完全   │ 抗操纵=高    │ 抗操纵=低      │ 抗操纵=中
  ▼                ▼              ▼              ▼
  测试/lint/diff   ROUGE/embed    GPT-4/Claude   专家审核
```

关键文献支撑：
- Fiedler (2026) 证明 LLM 评判存在系统性偏差，PPI++ 是推荐的校正方法
- Claw-Eval 发现不透明评测遗漏 44% 的安全违规
- AdaRubric 证明固定维度导致人类相关性下降 0.15

**决策点**：micro-eval 的 `Scorer` 类（当前仅支持 exact match 和 contains）应重构为分层 Pipeline，确定性层作为不可绕过的基础。

---

## 3. 架构设计

### 3.1 完整 Verifier Pipeline 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Rubric Definition (YAML)                   │
│  axes: [{name, weight, verifiers[], pass_threshold}]             │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 加载 & 校验
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     VerifierEngine (调度层)                        │
│                                                                   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐           │
│  │  Build  │  │  Test   │  │  Lint   │  │ Custom  │  ...       │
│  │Verifier │  │ Runner  │  │Checker  │  │ Script  │           │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘           │
│       │             │            │             │                  │
│       ▼             ▼            ▼             ▼                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │          Sandbox Layer (进程隔离 / cgroup / RO mount)     │    │
│  │          超时 + 内存限制 + 网络控制 + syscall 过滤        │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬──────────────────────────────────┘
                               │ VerifierResult[]
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Scoring Composition Layer                        │
│                                                                   │
│  ┌── 聚合策略 ──────────────────────────────────────────────┐   │
│  │ weighted_mean: Σ(score_i × weight_i) / Σ(weight_i)       │   │
│  │ min_critical: 关键维度一票否决                             │   │
│  │ dimension_aware: 防止高分维度掩盖低分维度                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  输出: RubricScore {final_score, axis_scores[], evidence_chain}  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   RunResult (写入 .micro-eval/)                    │
│  score + pass_fail + evidence + latency + cost                   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 关键接口定义

```python
"""核心 Protocol — 所有验证器必须实现"""

@runtime_checkable
class Verifier(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def resource_limits(self) -> ResourceLimits: ...

    async def verify(self, ctx: VerifierContext) -> VerifierResult: ...

    def can_run(self, ctx: VerifierContext) -> bool: ...
```

```python
"""验证器上下文 — 只读视图，防止验证器修改被评测环境"""

@dataclass(frozen=True)
class VerifierContext:
    workspace_path: Path          # agent 输出所在路径（只读挂载）
    diff_text: Optional[str]      # git diff
    original_commit: str          # 起始 commit SHA
    task_input: str               # 原始任务输入
    expected_output: Optional[str]
    artifacts: dict[str, Path]    # 额外产物
    env_vars: dict[str, str]      # 允许的环境变量
```

```python
"""验证器结果 — 统一输出格式"""

@dataclass
class VerifierResult:
    verifier_name: str
    status: VerifierStatus        # passed|failed|partial|error|timeout|skipped
    score: float                  # 0.0 ~ 1.0
    findings: list[Finding]       # 结构化发现
    passed_checks: int
    total_checks: int
    raw_output: str               # 截断后的原始输出
    latency_s: float
    metadata: dict[str, Any]
```

### 3.3 与 micro-eval 现有架构的集成点

当前 `engine/scorer.py` 的 `Scorer` 类仅支持 exact match。集成方案：

```
现有架构:
  engine/runner.py → 执行 agent → RunResult
  engine/scorer.py → exact match → score

重构后:
  engine/runner.py → 执行 agent → RunResult + workspace_path
  engine/scorer.py → Scorer (保留，作为 Layer 1 的一部分)
  verifiers/engine.py → VerifierEngine (新增，管理完整 pipeline)
  verifiers/protocol.py → Verifier Protocol (新增)
  verifiers/rubric.py → AgenticRubric model (新增)
  verifiers/builtin/ → 内置验证器 (新增)
```

`RunResult` schema 需扩展：

```python
class RunResult(BaseModel):
    # ... 现有字段 ...
    rubric_score: Optional[RubricScore] = None  # 新增：完整 rubric 评分
    evidence_chain: list[Finding] = Field(default_factory=list)  # 新增
    rubric_version: Optional[str] = None  # 新增：使用的 rubric 版本
```

**决策点**：重构应保持向后兼容——当 task 未配置 rubric 时，退回到现有 exact match 逻辑。

---

## 4. 内置 Verifier 目录

### 4.1 TestRunner

| 属性 | 值 |
|------|-----|
| **用途** | 运行项目测试套件，解析通过/失败数量 |
| **输入** | workspace_path（含项目代码） |
| **输出** | pass_rate, 失败测试列表 |
| **配置** | `command`（自动检测或手动指定）, `fail_threshold`, `test_pattern` |
| **适用任务** | 代码修复、功能实现、重构 |
| **性能** | 10-120s（取决于测试套件规模） |
| **隔离需求** | Level 1（子进程隔离，无网络） |

自动检测逻辑：
- `pytest.ini` / `pyproject.toml` → `python -m pytest --tb=short -q`
- `package.json` → `npm test`
- `Cargo.toml` → `cargo test`
- `Makefile` → `make test`

### 4.2 BuildVerifier

| 属性 | 值 |
|------|-----|
| **用途** | 验证项目能否成功构建/编译 |
| **输入** | workspace_path |
| **输出** | binary pass/fail + 编译错误信息 |
| **配置** | `command`（自动检测或手动指定） |
| **适用任务** | 所有代码类任务（前置条件） |
| **性能** | 5-60s |
| **隔离需求** | Level 1 |

评分：`exit_code == 0 → 1.0`，否则 `0.0`。编译错误提取为 Finding。

### 4.3 LintChecker

| 属性 | 值 |
|------|-----|
| **用途** | 运行静态分析工具（linter + type checker） |
| **输入** | workspace_path + diff_text（仅检查变更文件） |
| **输出** | 问题列表，按严重程度分类 |
| **配置** | `tools`（ruff/mypy/eslint/clippy）, `severity_filter`, `only_changed_files` |
| **适用任务** | 代码质量评估 |
| **性能** | 3-30s |
| **隔离需求** | Level 0（纯静态分析，无副作用） |

评分公式：`1.0 - (blocker_count × 0.3 + major_count × 0.1 + minor_count × 0.02)`，下限 0.0。

### 4.4 DiffAnalyzer

| 属性 | 值 |
|------|-----|
| **用途** | 验证代码变更是否符合预期模式 |
| **输入** | diff_text |
| **输出** | 匹配/不匹配的规则列表 |
| **配置** | `must_modify`（必须修改的路径）, `must_not_modify`（禁止修改的路径）, `pattern_required`（diff 中必须包含的模式）, `max_lines_changed` |
| **适用任务** | 精确修复验证、安全审计 |
| **性能** | <1s |
| **隔离需求** | Level 0（纯文本分析） |

评分：`matched_criteria / total_criteria`。

### 4.5 SchemaValidator

| 属性 | 值 |
|------|-----|
| **用途** | 验证 agent 输出符合预定义 schema |
| **输入** | agent output（stdout/file） |
| **输出** | 合规/不合规字段列表 |
| **配置** | `schema_type`（json_schema/pydantic/regex）, `schema_path` |
| **适用任务** | API 输出验证、结构化数据生成 |
| **性能** | <1s |
| **隔离需求** | Level 0 |

### 4.6 CustomScript

| 属性 | 值 |
|------|-----|
| **用途** | 执行用户自定义验证脚本 |
| **输入** | workspace_path + 环境变量 |
| **输出** | exit code + stdout（第一行为 score，后续为 JSON findings） |
| **配置** | `script_path` 或 `script`（内联）, `interpreter` |
| **适用任务** | 任何自定义验证逻辑 |
| **性能** | 用户定义（受 timeout 限制） |
| **隔离需求** | Level 2（Docker 容器，用户代码不可信） |

约定：`exit 0` = pass, `exit 1` = fail, `exit 2` = partial。

**决策点**：MVP（Phase 1）仅实现 TestRunner + BuildVerifier。这两个覆盖了最常见的"代码是否正确"验证需求，且实现复杂度低。

---

## 5. 安全模型

### 5.1 威胁面分析

```
┌─────────────────────────────────────────────────────┐
│                    威胁面全景                          │
├─────────────────────────────────────────────────────┤
│                                                       │
│  T1: Agent 输出包含恶意代码                           │
│      → 验证器执行时触发（代码注入）                    │
│      → 影响: 宿主机被控制                             │
│      → 缓解: 沙箱隔离 + 只读挂载                     │
│                                                       │
│  T2: Agent 操纵评分管线                               │
│      → 修改验证脚本/测试文件/评分逻辑                  │
│      → 影响: 分数虚高，评测失效                       │
│      → 缓解: 评估器锁定（只读）+ 签名校验             │
│                                                       │
│  T3: LLM 评判被 prompt injection 攻击                │
│      → Agent 输出中嵌入操纵评判的指令                  │
│      → 影响: LLM 评分被翻转（成功率 >30%）           │
│      → 缓解: 确定性检查优先 + 多评判集成              │
│                                                       │
│  T4: 资源耗尽攻击                                    │
│      → Agent 输出触发无限循环/内存爆炸                 │
│      → 影响: 验证器崩溃，评测挂起                     │
│      → 缓解: 硬超时 + cgroup 内存限制                 │
│                                                       │
│  T5: 环境逃逸                                        │
│      → 沙箱侧信道（如 DNS 逃逸）                     │
│      → 影响: 数据泄露、横向移动                       │
│      → 缓解: 网络隔离 + 最小权限                     │
│                                                       │
│  T6: Reward Hacking                                  │
│      → Agent 学会产生"看起来好"但实质不好的输出        │
│      → 影响: 评测指标失效（Goodhart's Law）           │
│      → 缓解: absence-based 标准 + 定期换 rubric      │
│                                                       │
└─────────────────────────────────────────────────────┘
```

### 5.2 隔离策略

micro-eval 采用**分级隔离**，根据验证器的危险等级自动选择：

```python
class IsolationLevel(enum.IntEnum):
    """验证器隔离级别。"""
    in_process = 0    # 纯计算，无副作用（DiffAnalyzer, SchemaValidator）
    subprocess = 1    # 子进程 + seccomp + 内存限制（TestRunner, LintChecker）
    container = 2     # Docker 容器 + 网络隔离（CustomScript）
    vm = 3            # VM 级隔离（未来：不可信第三方验证器）
```

每个验证器在 `resource_limits` 中声明所需隔离级别。Engine 根据声明分配执行环境。

### 5.3 防御措施清单

| 优先级 | 措施 | 实现方式 |
|--------|------|---------|
| P0 | 验证器只读访问 workspace | `VerifierContext.workspace_path` 以只读方式挂载 |
| P0 | 硬超时 | `asyncio.wait_for` + SIGKILL 兜底 |
| P0 | 内存限制 | cgroup v2 memory.max（默认 512MB） |
| P1 | 评分管线锁定 | rubric YAML + 验证器代码签名校验 |
| P1 | 确定性检查不可被 LLM 覆盖 | 确定性失败 = 最终失败，无论 LLM 评分 |
| P1 | 网络隔离 | 默认 `network_allowed=False` |
| P2 | 多评判集成 | 同一维度多个验证器投票 |
| P2 | 锚定任务 | TaskSet 中混入已知答案的校准任务（10-15%） |
| P3 | 输出截断 | `max_output_bytes=1MB`，防止 log bomb |
| P3 | Absence-based 标准 | Rubric 模板强制包含"不应该做什么"的检查 |

**决策点**：P0 措施必须在 Phase 1 实现。P1 在 Phase 2。P2/P3 在 Phase 3。评估器锁定引入 25-31% 运行时开销（来源：[2603.11337]），这是可接受的安全税。

---

## 6. 成本优化

### 6.1 验证成本模型

```
总验证成本 = Σ(verifier_cost_i) + orchestration_overhead

其中:
  verifier_cost = compute_time × $/cpu-second
                + llm_tokens × $/token (如果使用 LLM)
                + storage × $/GB (Docker 镜像)

典型场景（单个 task × 单个 agent）:
  TestRunner:     ~$0.001 (CPU 10s × $0.0001/s)
  BuildVerifier:  ~$0.001
  LintChecker:    ~$0.0005
  LLM Judge:      ~$0.05 (GPT-4 ~2000 tokens)
  CustomScript:   ~$0.002

  确定性 rubric 总成本: ~$0.003/evaluation
  混合 rubric 总成本:   ~$0.05/evaluation
```

**30% 规则**：验证成本不应超过 agent 执行成本的 30%。如果 agent 执行花费 $0.10，验证预算为 $0.03。

### 6.2 缓存策略

```python
"""三层缓存架构"""

class VerifierCache:
    """
    Layer 1: 确定性结果缓存
      key = hash(verifier_name + workspace_content_hash + config)
      TTL = 永久（内容不变则结果不变）
      命中率: 高（相同代码重复评测时）

    Layer 2: 环境缓存
      key = hash(project_deps + python_version)
      内容 = 已安装依赖的 Docker 镜像
      TTL = 7 天
      节省: 避免重复 pip install / npm install

    Layer 3: LLM 评分缓存
      key = hash(rubric_prompt + agent_output + model_version)
      TTL = 24 小时（LLM 行为可能随版本变化）
      命中率: 中（相同输出重复评判时）
    """
```

### 6.3 自适应验证（何时跳过昂贵验证）

```python
def should_run_expensive_verification(
    cheap_results: list[VerifierResult],
    rubric: AgenticRubric,
) -> bool:
    """
    决策逻辑:
    1. 如果 build 失败 → 跳过所有后续验证（代码不可运行）
    2. 如果 test 全部通过 + lint 无 blocker → 可跳过 LLM 评判
    3. 如果 test 通过率 < 50% → 跳过 style 评判（已经明确失败）
    4. 如果是 anchor task 且确定性分数正常 → 跳过 LLM 校准
    """
    # Build 失败 = 立即终止
    build_results = [r for r in cheap_results if r.verifier_name == "build_verifier"]
    if build_results and build_results[0].status == VerifierStatus.failed:
        return False  # 不需要跑昂贵验证

    # 全部确定性检查通过 = 可能不需要 LLM
    all_passed = all(
        r.status in (VerifierStatus.passed, VerifierStatus.skipped)
        for r in cheap_results
    )
    if all_passed and rubric.axes_all_deterministic:
        return False

    return True  # 需要跑昂贵验证
```

参考 ICML 2026 的 Instance-Optimal Estimation：不是所有样本都需要最贵的评判。简单样本用便宜评判即可，复杂样本才触发完整验证。

**决策点**：Phase 1 不实现自适应路由（所有配置的验证器都执行）。Phase 3 引入 `fail_fast` 模式和自适应跳过逻辑。

---

## 7. 实现路线图（建议）

### Phase 1: 基础 Verifier（与 MVP 对齐）

**目标**：让 `micro-eval run` 支持 rubric 配置，用确定性验证器替代当前的 exact match。

**交付物**：
1. `src/micro_eval/verifiers/protocol.py` — Verifier Protocol + 数据类
2. `src/micro_eval/verifiers/rubric.py` — AgenticRubric Pydantic model
3. `src/micro_eval/verifiers/engine.py` — VerifierEngine（调度 + 聚合）
4. `src/micro_eval/verifiers/builtin/test_runner.py` — TestRunner
5. `src/micro_eval/verifiers/builtin/build_verifier.py` — BuildVerifier
6. `engine/scorer.py` 重构 — 集成 VerifierEngine，保持向后兼容
7. YAML rubric 加载逻辑（集成到 `config/loader.py`）

**验收标准**：
- `uv run micro-eval run --rubric coding-correctness.yaml` 可执行
- TestRunner 能自动检测 pytest 并解析结果
- 现有 25 个 pytest 测试继续通过
- 无 rubric 时退回 exact match（向后兼容）

**工期估算**：3-5 天

### Phase 2: 高级 Verifier + LLM 评分

**目标**：支持 DiffAnalyzer、CustomScript、LLM-as-Judge 维度。

**交付物**：
1. `verifiers/builtin/diff_analyzer.py`
2. `verifiers/builtin/lint_checker.py`
3. `verifiers/builtin/custom_script.py`
4. `verifiers/builtin/schema_validator.py`
5. `verifiers/llm_judge.py` — LLM 评分集成（通过 DeepEval GEval）
6. 冲突处理逻辑（确定性 vs LLM 分歧时的策略）
7. 评分置信度报告（J index + confidence score）

**验收标准**：
- CustomScript 在子进程隔离中运行，有超时和内存限制
- LLM 评分附带 reasoning + confidence
- 确定性检查失败时 LLM 评分不可覆盖

**工期估算**：5-8 天

### Phase 3: 自适应 + 缓存 + 统计

**目标**：优化成本、提升可靠性、支持多次运行统计。

**交付物**：
1. 验证结果缓存层（content-hash based）
2. 自适应路由（`fail_fast` + 跳过逻辑）
3. Pass@k / Pass^k 双指标支持
4. 锚定任务机制
5. Rubric 版本化 + 演化追踪
6. 评判器校准 run 支持
7. Docker 容器隔离（CustomScript 升级）

**验收标准**：
- 相同输入重复评测时缓存命中率 > 80%
- 支持 `--epochs 3` 参数运行多次并报告一致性
- 锚定任务偏离时标记 run 为不可信

**工期估算**：8-12 天

---

## 8. 参考文献

### 学术论文


| # | 论文/项目 | 核心贡献 | 链接 |
|---|----------|---------|------|
| 1 | Agentic Rubrics as Contextual Verifiers (Scale AI, 2026) | 评分器本身应是 agent，能执行代码验证 | [arxiv 2601.04171](https://arxiv.org/abs/2601.04171) |
| 2 | Task-Adaptive Rubrics (2026) | Rubric 应根据任务类型自动适配维度 | [arxiv 2603.21362](https://arxiv.org/abs/2603.21362) |
| 3 | Towards Trustworthy Evaluation of Autonomous Agents (2026) | 可信评测的系统性框架 | [arxiv 2604.06132](https://arxiv.org/abs/2604.06132) |
| 4 | Bias and Uncertainty in LLM-as-a-Judge (2026) | LLM 评判的系统性偏差分析 | [arxiv 2605.06939](https://arxiv.org/abs/2605.06939) |
| 5 | Security in LLM-as-a-Judge (2026) | Judge 被操纵的攻击面分析 | [arxiv 2603.29403](https://arxiv.org/html/2603.29403v1) |
| 6 | Instance-Optimal Multi-Judge on a Budget (2026) | 成本约束下的最优评判分配 | [arxiv 2605.23362](https://arxiv.org/abs/2605.23362) |
| 7 | Automated Rubric Synthesis for RL (2026) | 自动生成 rubric 的方法论 | [arxiv 2605.23454](https://arxiv.org/html/2605.23454v1) |
| 8 | Unifying Rubric-based LLM Evaluation (2026) | 统一 rubric 评测框架 | [arxiv 2603.00077](https://arxiv.org/abs/2603.00077) |

### 工业实现

| # | 项目 | 核心贡献 | 链接 |
|---|------|---------|------|
| 1 | SWE-bench | Docker 三层镜像 + pytest 验证 | [swebench.com](https://www.swebench.com/) |
| 2 | Braintrust | 分层评分（deterministic → heuristic → LLM） | [braintrust.dev](https://braintrust.dev/docs/best-practices/scorers) |
| 3 | METR Inspect | Solver/Scorer 分离 + 多步验证 | [inspect.ai-safety-institute.org.uk](https://inspect.ai-safety-institute.org.uk/) |
| 4 | DeepEval | GEval + Custom Metric 框架 | [github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval) |
| 5 | EvalPlus / HumanEval+ | 测试增强（80x 测试用例） | [github.com/evalplus](https://github.com/evalplus/evalplus) |
| 6 | LiveCodeBench | 动态测试生成 + 无污染评测 | [livecodebench.github.io](https://livecodebench.github.io/) |
| 7 | OpenHands | EventStream 架构 + Docker 评测 | [arxiv 2511.03690](https://arxiv.org/html/2511.03690v2) |

### 安全研究

| # | 来源 | 核心发现 | 链接 |
|---|------|---------|------|
| 1 | One Token to Fool LLM-as-a-Judge | 单 token 即可翻转评分 | [arxiv 2507.08794](https://arxiv.org/abs/2507.08794) |
| 2 | Prompt-Injection in Evaluation | 30%+ 成功率操纵 judge | [arxiv 2505.13348](https://arxiv.org/abs/2505.13348) |
| 3 | Claw-Eval | 不透明评测遗漏 44% 安全违规 | 学术论文 |
| 4 | AdaRubric | 固定维度导致人类相关性下降 0.15 | 学术论文 |
| 5 | Fiedler (2026) | PPI++ 校正 LLM 评判偏差 | 学术论文 |

---

## 纳入状态说明（2026-06-02）

本报告的采纳/不采纳由 [[2026-06-01-rubric-engineering-decision]] 统一裁定，落地到 `2026-06-02-unicorn-design.md` §4。要点：

- **采纳并落地**：核心洞察"确定性验证 > LLM 判断"（升为不变量 #6）、分层短路、30% 成本规则、聚合策略、验证器只读访问 workspace，均在设计文档 §4.1 present。
- **按决策不采纳**：§3.2 Verifier Protocol、§3.1 VerifierEngine、§6.2 三层缓存、§6.3 自适应路由——设计文档改用更轻的显式 `ScoreStage` pipeline（§4.1），与"不重新发明 DeepEval BaseMetric / 不过度工程化"的决策一致。
- **⚠️ 一处偏差**：本报告 §5.1 的 **Reward Hacking（T6）缓解**（absence-based 标准、锚定任务、定期换 rubric）**尚未进入设计文档**。决策记录原称"补充到 §12"不准确，已在该记录的"覆盖核查与修订（2026-06-02）"中更正——结论为合理 deferred，待 RL / 对抗场景再纳入。
