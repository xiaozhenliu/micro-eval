# Unicorn：micro-eval 完整形态设计

**代号**: Unicorn
**日期**: 2026-06-01
**状态**: Draft
**基于**: 方案 A（Skill Creator 模式 + 通用化）

---

## 1. 设计目标

把 micro-eval 从"能跑的 MVP 骨架"变成"对开发者真正可用的评测工具"。

核心问题：当前实现把 agent 简化为 `command + stdin/stdout`，评分用精确匹配——这对真实的 coding agent、workflow agent、skill 评测毫无意义。

**Unicorn 要回答的根本问题**：
- 什么是 agent？→ 一个在特定环境中执行任务的程序
- 什么是输入？→ 任务描述 + 执行环境（workspace）
- 什么是输出？→ 产出物（artifacts）+ 执行轨迹（trace）+ 成本（cost）
- 怎么判好坏？→ 自动验证 + LLM-as-judge + 人工标注，三层递进

---

## 2. 设计原则

1. **环境即输入**：agent 的输入不只是文本，而是 task description + workspace state
2. **断言式评分**：用 expectations（可验证断言）取代 expected_output（精确匹配）
3. **三层评分递进**：validation → grading → annotation
4. **N-way 对比**：不限于 2 个 agent，支持任意数量的 EvalTarget 对比
5. **Workspace 抽象**：执行环境是独立概念，为沙盒扩展预留
6. **Skill 是一等公民**：既能单独测 Skill，也能集成测（Skill 挂载到 Agent 上）

---

## 3. 领域模型

### 3.1 EvalTarget（被评测对象）

被评测的东西。三种类型，统一接口。

```yaml
# Agent：完整的可执行程序
- type: agent
  name: claude-code-v2
  command: "claude -p --output-file {output_dir}/result.txt"
  input_mode: stdin | file | arg
  output_mode: stdout | file | directory
  timeout_s: 300
  env: {ANTHROPIC_API_KEY: "..."}
  workspace_needs: git_repo  # 需要什么类型的 workspace

# Skill：挂载到 host agent 上的能力单元
- type: skill
  name: frontend-design-v2
  skill_path: ./skills/frontend-design/
  host_agent: claude-code  # 挂载到哪个 agent
  version: "2.1"

# Workflow：编排式管线
- type: workflow
  name: langgraph-router-v2
  entrypoint: "python agents/router_v2.py"
  config: ./configs/router-v2.yaml
  output_mode: directory
```

**关键设计**：
- Agent 是"黑盒"——只关心 command + 输入输出协议
- Skill 必须指定 host_agent——因为 Skill 不能独立运行
- Workflow 是带配置的可执行脚本

### 3.2 Task（评测任务）

一个可重复运行的评测单元。核心改变：**输入不再是一段文本，而是 prompt + workspace + expectations**。

```yaml
id: fix-auth-redirect
name: 修复登录重定向 bug
tags: [bug-fix, auth, P1]

# 给 agent 的任务描述
prompt: |
  The login page redirects to /dashboard but should redirect to /home
  when the session has expired. Fix this bug.

# 执行环境
workspace:
  type: git_repo
  source:
    repo: ./fixtures/auth-app
    commit: abc123
  setup_commands:
    - npm install
  resource_limits:
    timeout_s: 300
    max_tokens: 100000

# 成功断言（可验证的条件列表）
expectations:
  - "auth.ts 或 auth.js 被修改"
  - "重定向目标从 /dashboard 改为 /home"
  - "现有测试仍然通过"
  - "没有引入新的 lint 错误"

# 自动验证（可选，优先于 LLM judge）
validation:
  commands:
    - "npm test"
    - "npm run lint"
  pass_criteria: all_pass  # all_pass | any_pass | score_threshold

# 评分策略
scoring:
  method: hybrid  # auto_only | llm_judge | hybrid | human_only
  rubric:
    - axis: correctness
      weight: 3
      description: "是否正确修复了 bug"
    - axis: integrity
      weight: 2
      description: "是否破坏了现有功能"
    - axis: quality
      weight: 1
      description: "代码质量、风格一致性"
```

**Task 类型示例**（覆盖你的全部场景）：

| 场景 | workspace.type | expectations 示例 | validation 示例 |
|------|---------------|-------------------|-----------------|
| Bug 修复 | git_repo | "目标文件被修改" "测试通过" | `npm test` |
| Feature 开发 | git_repo | "新增 API endpoint" "有对应测试" | `npm test && npm run lint` |
| 架构设计 | blank/files | "产出包含架构图" "覆盖关键组件" | 无（LLM judge） |
| UI 开发 | git_repo | "组件可渲染" "无 a11y 错误" | `npm run build` |
| 文档撰写 | files | "覆盖所有章节" "无事实错误" | 无（LLM judge） |
| Skill 测试 | git_repo | "Skill 被正确触发" "产出符合预期" | 自定义脚本 |

### 3.3 WorkspaceSpec（执行环境）

执行环境的抽象层。当前实现 worktree，未来扩展 Docker/远程沙盒。

```yaml
# 类型 1：Git repo（最常见）
workspace:
  type: git_repo
  source:
    repo: ./fixtures/my-app       # 本地路径或 URL
    commit: abc123                 # 可选，默认 HEAD
    branch: main                  # 可选
  setup_commands:
    - npm install
  resource_limits:
    timeout_s: 300
    memory_mb: 4096               # 未来 Docker 用
    cpu_cores: 2                  # 未来 Docker 用
  cleanup: auto

# 类型 2：文件集合（文档撰写等）
workspace:
  type: files
  source:
    paths:
      - ./fixtures/context-docs/
      - ./fixtures/reference.md
  resource_limits:
    timeout_s: 120

# 类型 3：空白（从头创建）
workspace:
  type: blank
  resource_limits:
    timeout_s: 600

# 类型 4：Docker（未来）
workspace:
  type: docker
  image: node:20-slim
  source:
    repo: ./fixtures/my-app
    commit: abc123
  setup_commands:
    - npm install
  resource_limits:
    timeout_s: 300
    memory_mb: 8192
    cpu_cores: 4
  network: none                   # 网络隔离
```

**Provider 接口**（内部实现）：
```python
class WorkspaceProvider(Protocol):
    def create(self, spec: WorkspaceSpec) -> WorkspaceHandle: ...
    def collect_artifacts(self, handle: WorkspaceHandle) -> list[Artifact]: ...
    def cleanup(self, handle: WorkspaceHandle) -> None: ...
```

当前只实现 `GitWorktreeProvider` 和 `FilesProvider`，未来加 `DockerProvider`。

### 3.4 Run（评测执行）

```yaml
id: run-20260601-143022
timestamp: "2026-06-01T14:30:22Z"
status: completed  # pending | running | completed | failed | cancelled

# 被对比的目标（支持 N 个）
targets:
  - {type: agent, name: claude-code-v1, ...}
  - {type: agent, name: claude-code-v2, ...}
  - {type: skill, name: frontend-design-v2, host_agent: claude-code, ...}

# 任务集
task_set:
  source: ./tasks/           # 目录或显式列表
  filter:
    tags: [bug-fix]          # 可选过滤
    ids: [fix-auth, fix-nav] # 可选指定

# 执行配置
execution:
  mode: parallel             # parallel | sequential | round_robin
  max_concurrent: 4
  randomize_order: true      # 避免顺序效应

# 环境快照
environment:
  git_commit: abc123
  config_hash: sha256:...
  python_version: "3.11.9"
  timestamp: "2026-06-01T14:30:22Z"
```

### 3.5 RunResult（单个 task × target 的结果）

```yaml
task_id: fix-auth-redirect
target_id: claude-code-v2
status: completed

# 产出物
artifacts:
  - type: diff
    path: .micro-eval/artifacts/run-xxx/fix-auth/claude-code-v2/changes.patch
  - type: file
    path: .micro-eval/artifacts/run-xxx/fix-auth/claude-code-v2/output.txt
  - type: directory
    path: .micro-eval/artifacts/run-xxx/fix-auth/claude-code-v2/workspace/

# 执行指标
metrics:
  latency_s: 45.2
  tokens_used: 12500
  cost_usd: 0.037
  tool_calls: 18
  errors_encountered: 0

# 自动验证结果
validation:
  status: passed             # passed | failed | skipped | error
  commands_run:
    - {command: "npm test", exit_code: 0, duration_s: 3.2}
    - {command: "npm run lint", exit_code: 0, duration_s: 1.1}

# LLM-as-judge 评分
grading:
  expectations:
    - {text: "auth.ts 被修改", passed: true, evidence: "diff 显示 auth.ts +3/-1"}
    - {text: "重定向目标改为 /home", passed: true, evidence: "第 42 行 redirect('/home')"}
    - {text: "现有测试通过", passed: true, evidence: "npm test exit 0"}
    - {text: "无新 lint 错误", passed: true, evidence: "npm run lint exit 0"}
  rubric_scores:
    correctness: 5
    integrity: 5
    quality: 4
  summary:
    passed: 4
    failed: 0
    total: 4
    pass_rate: 1.0
    overall_score: 9.3

# 人工标注（可选）
annotation:
  score: 9
  notes: "修复正确，代码简洁"
  annotator: "xz"
  timestamp: "2026-06-01T15:00:00Z"
```

---

## 4. 评分系统

### 4.1 三层递进评分

```
Layer 1: Validation（自动验证）
  ↓ 通过/失败/跳过
Layer 2: Grading（LLM-as-judge）
  ↓ expectations 逐条验证 + rubric 打分
Layer 3: Annotation（人工标注）
  ↓ 主观评价 + 备注
```

**Layer 1: Validation**
- 运行 task 定义的 validation.commands
- 纯机械判断：exit code 0 = pass
- 适用于有测试的 coding 任务
- 没有 validation commands 时跳过此层

**Layer 2: Grading（核心创新）**
- 独立的 Grader agent 评估产出
- 输入：task.expectations + agent 产出的 artifacts + execution trace
- 输出：逐条 {text, passed, evidence} + rubric_scores + claims 验证
- Grader 不是执行 agent 本身——避免自评偏见
- 支持 blind comparison：两个产出匿名对比

**Layer 3: Annotation**
- 人工在 Web UI 中标注
- 持久化到 RunResult（不再用 localStorage）
- 支持导出为训练数据

### 4.2 评分策略（ScoringSpec）

```yaml
scoring:
  method: hybrid
  # method 选项：
  #   auto_only    — 只跑 validation commands
  #   llm_judge    — 只用 LLM grading
  #   hybrid       — validation + LLM grading
  #   human_only   — 只等人工标注

  # Rubric 轴（可自定义）
  rubric:
    - axis: correctness
      weight: 3
    - axis: integrity
      weight: 2
    - axis: quality
      weight: 1

  # LLM Judge 配置
  judge:
    model: claude-sonnet-4-20250514
    temperature: 0
    max_retries: 2
```

### 4.3 Blind Comparison（盲评对比）

参考 Skill Creator 的 comparator 模式：

1. 两个 target 的产出匿名标记为 A / B
2. 独立 Judge agent 不知道哪个是哪个
3. 基于 rubric 打分 + 选出 winner
4. Post-hoc analyzer 揭盲后分析"为什么赢"

适用场景：当你不确定哪个版本更好，需要消除确认偏误。

### 4.4 Rubric 框架（基于 Rubrics Survey 论文）

参考论文 "The Rules of the Game: A Survey of Rubrics for Large Language Models"（2026），
对 Unicorn 评分系统做以下增强。

#### 4.4.1 核心差异分析

论文揭示了当前 Unicorn 设计的三个盲区：

| 维度 | 论文框架 | Unicorn 当前设计 | 差距 |
|------|---------|-----------------|------|
| 评测对象 | 过程（trajectory）+ 结果（output） | 只评结果 | 缺少过程评测 |
| Rubric 粒度 | 多维度 × 多等级（1-5 per axis） | 粗糙的 3 轴 | 维度不够精细 |
| Rubric 来源 | 自动生成 + 迭代优化 + 动态演化 | 用户手写 | 缺少自动化 |
| 评分一致性 | 多 judge 投票 + 校准 | 单 judge | 缺少可靠性保障 |

#### 4.4.2 过程评测（Trajectory Evaluation）

Agent 评测不能只看最终产出。论文指出 trajectory-aware 评测对 agent 至关重要：

```yaml
# RunResult 增加 trajectory 评分
trajectory_grading:
  # 工具调用效率
  tool_efficiency:
    total_calls: 18
    redundant_calls: 2        # 重复/无效调用
    score: 0.89               # (total - redundant) / total
  
  # 推理路径质量
  reasoning_quality:
    backtrack_count: 1        # 回溯次数
    dead_end_count: 0         # 死胡同次数
    progressive: true         # 是否持续推进
  
  # 资源使用合理性
  resource_usage:
    tokens_vs_complexity: 0.85  # token 消耗与任务复杂度的比值
    time_vs_baseline: 1.2       # 相对基线的时间倍数
  
  # 错误恢复能力
  error_recovery:
    errors_encountered: 1
    recovered: 1
    recovery_quality: "clean"   # clean | messy | failed
```

适用场景：
- Coding agent 是否在无效方向上浪费了大量 token
- Agent 是否过度使用工具（每步都 grep 而不是理解代码）
- Agent 遇到错误后是否能优雅恢复

#### 4.4.3 多维度 Rubric 体系

论文将评测维度按任务类型精细化。Unicorn 采用 **task-adaptive rubric**：
根据 task 的 tags/类型自动选择合适的 rubric 模板。

**Coding 任务默认 Rubric（4 轴，参考 Agentic Rubrics）**：

```yaml
rubric_template: coding
axes:
  - axis: file_change
    weight: 2
    levels:
      5: "精确修改了正确的文件和位置"
      3: "修改了正确文件但位置不精确"
      1: "修改了错误的文件或遗漏关键文件"
    criteria:
      - "是否修改了正确的文件"
      - "修改范围是否最小化"
      - "是否有不必要的改动"

  - axis: spec_alignment
    weight: 3
    levels:
      5: "完全满足任务描述的所有要求"
      3: "满足主要要求但遗漏细节"
      1: "未满足核心要求"
    criteria:
      - "是否解决了描述的问题"
      - "是否覆盖了所有边界条件"
      - "是否符合隐含约束"

  - axis: integrity
    weight: 3
    levels:
      5: "现有功能完全不受影响"
      3: "轻微副作用但不影响核心功能"
      1: "破坏了现有功能"
    criteria:
      - "现有测试是否通过"
      - "是否引入新的 lint/type 错误"
      - "是否破坏了其他模块"

  - axis: runtime
    weight: 2
    levels:
      5: "代码可运行且行为正确"
      3: "代码可运行但有边界问题"
      1: "代码无法运行或行为错误"
    criteria:
      - "是否能通过编译/构建"
      - "运行时行为是否符合预期"
      - "性能是否在可接受范围"
```

**文档撰写任务默认 Rubric**：

```yaml
rubric_template: document
axes:
  - axis: content_factuality
    weight: 3
    levels:
      5: "所有陈述均有依据，无事实错误"
      3: "主要内容正确，有少量不精确"
      1: "存在明显事实错误或虚构内容"

  - axis: completeness
    weight: 3
    levels:
      5: "覆盖所有要求的章节和要点"
      3: "覆盖主要内容但有遗漏"
      1: "大量内容缺失"

  - axis: professional_presentation
    weight: 2
    levels:
      5: "结构清晰、格式专业、语言精准"
      3: "结构合理但有格式或语言问题"
      1: "结构混乱、格式不一致"

  - axis: practical_utility
    weight: 2
    levels:
      5: "读者可直接据此行动"
      3: "有参考价值但需补充信息"
      1: "对读者无实际帮助"
```

**UI/设计任务默认 Rubric**：

```yaml
rubric_template: ui_design
axes:
  - axis: visual_fidelity
    weight: 2
    levels:
      5: "完全符合设计规范"
      3: "大体符合但有细节偏差"
      1: "与设计规范严重不符"

  - axis: functionality
    weight: 3
    levels:
      5: "所有交互正常工作"
      3: "核心交互正常但有边缘问题"
      1: "核心交互不工作"

  - axis: accessibility
    weight: 2
    levels:
      5: "符合 WCAG AA 标准"
      3: "基本可访问但有改进空间"
      1: "存在严重可访问性问题"

  - axis: code_quality
    weight: 1
    levels:
      5: "组件化良好、可维护"
      3: "可工作但结构有改进空间"
      1: "代码混乱、难以维护"
```

#### 4.4.4 Rubric 自动生成与迭代优化

论文提出的 rubric 构建方法论，Unicorn 分阶段采纳：

**Phase 1（手动 + 模板）**：
- 提供预置 rubric 模板（coding / document / ui_design）
- 用户可自定义 axes 和 levels
- Task 通过 `rubric_template` 字段选择模板

**Phase 2（半自动生成）**：
- 从 task description 自动推导 expectations
- 从 expectations 自动生成 rubric criteria
- 用户确认/修改后使用

```python
class RubricGenerator:
    def generate_from_task(self, task: Task) -> Rubric:
        """从 task 描述自动生成 rubric（LLM 辅助）"""
        ...
    
    def refine_from_results(self, rubric: Rubric, results: list[GradingResult]) -> Rubric:
        """基于评分结果迭代优化 rubric（去除无区分力的 criteria）"""
        ...
```

**Phase 3（动态演化）**：
- Contrastive generation：对比两个 agent 产出的差异，自动发现新的评分维度
- 去重压缩：合并重叠的 criteria
- Meta-evaluation：评估 rubric 本身的质量（区分力、一致性）

#### 4.4.5 评分可靠性保障

论文指出单 judge 评分存在偏见和不一致。Unicorn 采用：

```yaml
judge:
  # 多 judge 投票（可选，提高可靠性）
  ensemble:
    enabled: false              # 默认关闭（省成本）
    judges: 3                   # judge 数量
    agreement_threshold: 0.67   # 2/3 一致即通过
    models:                     # 可用不同模型
      - claude-sonnet-4-20250514
      - claude-sonnet-4-20250514
      - claude-sonnet-4-20250514

  # 校准机制
  calibration:
    reference_examples: []      # 参考评分样例（few-shot）
    anchor_tasks: []            # 锚定任务（已知正确评分的 task）
```

**何时启用 ensemble**：
- 高风险决策（决定是否上线某个 agent 版本）
- 评分方差大的 task（单 judge 不稳定）
- Blind comparison 场景

#### 4.4.6 Rubric 与现有三层评分的关系

```
Layer 1: Validation（自动验证）
  → 不变，仍然是 exit code 判断
  
Layer 2: Grading（LLM-as-judge）
  → 增强：
    a) Expectation 验证（逐条断言）
    b) Rubric 评分（多维度 × 多等级）    ← 新增
    c) Trajectory 评分（过程评测）        ← 新增
    d) Claims 验证（隐含声明检查）
  
Layer 3: Annotation（人工标注）
  → 不变，但可参考 Rubric 结构化标注
```

---

## 5. 执行引擎

### 5.1 执行流程

```
micro-eval run --config eval.yaml
  │
  ├─ 1. 加载配置 → 解析 targets + tasks
  ├─ 2. 创建 workspace → WorkspaceProvider.create(spec)
  ├─ 3. 执行 targets × tasks → AgentExecutor.run()
  │     ├─ 并行/串行/轮转（可配置）
  │     ├─ 每个 (target, task) 在独立 workspace 中运行
  │     └─ 收集 artifacts + metrics
  ├─ 4. 自动验证 → ValidationRunner.run()
  ├─ 5. LLM 评分 → Grader.grade()
  ├─ 6. 聚合结果 → RunResult[]
  └─ 7. 持久化 → .micro-eval/runs/<run-id>/
```

### 5.2 Agent 执行协议

Agent 是黑盒。micro-eval 只关心：
- **怎么传入任务**：stdin / file / arg
- **怎么收集产出**：stdout / file / directory / git diff
- **怎么知道结束**：进程退出 + exit code

```python
class AgentExecutor:
    async def execute(
        self,
        target: EvalTarget,
        task: Task,
        workspace: WorkspaceHandle,
    ) -> ExecutionResult:
        # 1. 准备输入
        input_payload = self.prepare_input(target, task, workspace)
        # 2. 执行命令
        proc_result = await self.run_process(target.command, input_payload, workspace)
        # 3. 收集产出
        artifacts = self.collect_artifacts(target, workspace, proc_result)
        # 4. 收集指标
        metrics = self.collect_metrics(proc_result)
        return ExecutionResult(artifacts=artifacts, metrics=metrics)
```

### 5.3 Skill 执行协议

Skill 测试 = 把 Skill 挂载到 host agent 上，然后按 Agent 协议执行。

```python
class SkillExecutor:
    async def execute(
        self,
        skill: SkillTarget,
        task: Task,
        workspace: WorkspaceHandle,
    ) -> ExecutionResult:
        # 1. 将 skill 注入到 host agent 的可用 skill 列表
        host_command = self.inject_skill(skill, workspace)
        # 2. 按 Agent 协议执行
        return await AgentExecutor().execute(
            target=host_command, task=task, workspace=workspace
        )
```

对于 Claude Code 场景，inject_skill 就是把 SKILL.md 放到 `.claude/commands/` 目录。

### 5.4 并发控制

```yaml
execution:
  mode: parallel          # parallel | sequential | round_robin
  max_concurrent: 4       # 最大并行数
  randomize_order: true   # 随机化执行顺序
  retry_on_error: 1       # 错误重试次数
  global_timeout_s: 3600  # 全局超时
```

---

## 6. CLI 设计

```bash
# 核心命令
micro-eval init                          # 生成 eval.yaml + tasks/ 模板
micro-eval run [--config eval.yaml]      # 执行评测
micro-eval run --targets a,b --tasks t1  # 指定 target 和 task
micro-eval grade <run-id>                # 对已有 run 补充 LLM 评分
micro-eval compare <run-id-1> <run-id-2> # 跨 run 对比
micro-eval report <run-id>               # 生成 HTML 报告

# 辅助命令
micro-eval doctor                        # 检查环境依赖
micro-eval list runs                     # 列出历史 run
micro-eval list tasks                    # 列出可用 task
micro-eval show <run-id>                 # 终端中查看 run 结果
micro-eval ui                            # 启动 Web UI
```

---

## 7. 数据存储

### 7.1 文件结构

```
project-root/
├── eval.yaml                    # 项目配置（targets + 执行参数）
├── tasks/
│   ├── fix-auth-redirect.yaml   # 单个 task
│   ├── add-search-api.yaml
│   └── write-arch-doc.yaml
├── fixtures/                    # workspace 源文件
│   ├── auth-app/                # git repo fixture
│   └── context-docs/            # 文件集 fixture
├── skills/                      # 被测 skill（可选）
│   └── frontend-design/
│       └── SKILL.md
└── .micro-eval/
    ├── runs/
    │   └── run-20260601-143022/
    │       ├── manifest.json    # Run 元数据
    │       ├── results/
    │       │   ├── fix-auth--claude-v1.json
    │       │   └── fix-auth--claude-v2.json
    │       └── artifacts/
    │           ├── fix-auth--claude-v1/
    │           │   ├── changes.patch
    │           │   └── stdout.txt
    │           └── fix-auth--claude-v2/
    │               ├── changes.patch
    │               └── stdout.txt
    ├── annotations/             # 人工标注（持久化）
    │   └── run-20260601-143022.json
    └── config.json              # 全局配置（judge model 等）
```

### 7.2 存储策略

- **Phase 1**：JSON 文件（当前，够用）
- **Phase 2**：SQLite（当需要跨 run 查询、趋势分析时迁移）
- `schema_version` 字段保证向前兼容

---

## 8. Web UI

### 8.1 页面结构

| 页面 | 功能 |
|------|------|
| Run 列表 | 所有历史 run，按时间排序，显示 pass rate / cost / 状态 |
| Run 详情 | task × target 结果矩阵，支持展开查看 artifacts |
| 对比页 | 两个 target 的产出并排对比（diff view） |
| Grading 页 | 查看 LLM judge 的逐条评分 + evidence |
| 标注页 | 人工评分 + 备注（持久化到文件） |
| 趋势页 | 跨 run 的 pass rate / cost 变化曲线 |

### 8.2 关键交互

- **Artifact viewer**：根据类型渲染（diff → syntax highlight, 文件 → 代码块, 目录 → 树形）
- **Inline annotation**：在对比页直接标注，不需要跳转
- **Filter & sort**：按 tag、status、score 过滤任务

---

## 9. 迭代改进循环

参考 Skill Creator 的核心循环，micro-eval 支持：

```
定义 tasks → 配置 targets → run → grade → review → 改进 target → re-run
```

具体：
1. 用户定义 tasks（expectations 驱动）
2. 配置多个 targets（agent v1 vs v2，或 skill v1 vs v2）
3. 执行 run
4. 自动 validation + LLM grading
5. 用户在 UI 中 review + annotate
6. 基于结果改进 agent/skill
7. 重新 run，对比改进效果

**Benchmark 模式**：多次运行同一配置，统计 mean ± stddev，消除随机性。

---

## 10. 沙盒扩展路径

### 10.1 当前（Phase 1）

```python
class GitWorktreeProvider:
    """零依赖，本地秒开。适合大部分 coding agent 评测。"""
    def create(self, spec) -> WorkspaceHandle: ...

class FilesProvider:
    """复制文件到临时目录。适合文档撰写等场景。"""
    def create(self, spec) -> WorkspaceHandle: ...
```

### 10.2 未来（Phase 2+）

```python
class DockerProvider:
    """Docker container 隔离。支持 resource limits、网络隔离。"""
    def create(self, spec) -> WorkspaceHandle: ...

class RemoteSandboxProvider:
    """远程沙盒（E2B、OpenHands 等）。完全隔离。"""
    def create(self, spec) -> WorkspaceHandle: ...
```

**Provider 注册机制**：
```yaml
# .micro-eval/config.json
workspace_providers:
  git_repo: builtin.git_worktree
  docker: builtin.docker        # 需要 Docker 安装
  remote: plugins.e2b           # 第三方插件
```

### 10.3 接口契约

所有 Provider 实现同一接口：
```python
class WorkspaceProvider(Protocol):
    def create(self, spec: WorkspaceSpec) -> WorkspaceHandle: ...
    def exec_command(self, handle, cmd: str) -> CommandResult: ...
    def collect_artifacts(self, handle) -> list[Artifact]: ...
    def collect_diff(self, handle) -> Optional[str]: ...
    def cleanup(self, handle) -> None: ...
```

新增 Provider 不影响上层任何代码。

---

## 11. 与现有 MVP 的关系

### 11.1 保留

- Python CLI + Typer 框架
- Next.js Web UI 骨架
- pytest 测试基础设施
- git worktree workspace 隔离（升级为 Provider）
- JSON 文件存储（升级结构）

### 11.2 重写

- **领域模型**：从 baseline/candidate 二元 → N-way EvalTarget
- **Task 模型**：从 input_payload + expected_output → prompt + workspace + expectations
- **评分引擎**：从精确匹配 → validation + LLM judge + annotation 三层
- **执行引擎**：从硬编码 subprocess → AgentExecutor + SkillExecutor + WorkspaceProvider
- **Web UI 数据层**：从读 flat JSON → 读结构化 run 目录

### 11.3 新增

- `micro-eval init` / `micro-eval doctor`
- LLM-as-judge grading 系统
- Blind comparison 模式
- Benchmark 模式（多次运行统计）
- 人工标注持久化
- Artifact viewer（diff、文件、目录）
- 跨 run 趋势分析

---

## 12. 技术栈（不变）

| 层 | 技术 |
|----|------|
| CLI + 引擎 | Python 3.11+ / uv / Typer / Pydantic |
| 评分 | 自写 + DeepEval（custom metric） |
| LLM Judge | Anthropic SDK（Claude Sonnet/Opus） |
| 观测（可选） | Langfuse Python SDK |
| Web UI | Next.js + TypeScript + Zod |
| 测试 | pytest + vitest |

---

## 13. 不做（Unicorn 范围外）

- 多团队协作 / RBAC / SSO
- 托管式 Web dashboard
- 自动化 CI 集成（用户自己接）
- 复杂的推荐引擎
- OpenHands 深度集成（留给 Phase 3）
- 自动生成 task（用户手写或用 LLM 辅助生成）
