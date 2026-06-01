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
4. **矩阵对比**：结果空间是 Tasks × Configurations（Agent × Skill × Environment × Params × Repetitions）
5. **Workspace 抽象**：执行环境是独立概念，为沙盒扩展预留
6. **Skill 是一等公民**：既能单独测 Skill，也能集成测（Skill 挂载到 Agent 上）
7. **Provider 可插拔**：Workspace、Trace、Scorer 均为 Provider 接口，第三方可注册扩展

---

## 3. 领域模型

### 3.1 Configuration（评测配置 — 核心概念）

一个 Configuration 是结果矩阵的"列"——描述一个完整的被评测实体及其运行条件。

```yaml
# Configuration = Agent × Skill(optional) × Environment × Params
configurations:
  - id: claude-v2-skill-v1-local
    agent:
      name: claude-code-v2
      command: "claude -p --output-file {output_dir}/result.txt"
      input_mode: stdin
      output_mode: file
      env: {ANTHROPIC_API_KEY: "..."}
    skill:                          # 可选：挂载的 Skill
      path: ./skills/frontend-design/
      version: "1.0"
    environment:                    # 运行环境
      type: worktree
      resource_limits: {timeout_s: 300}
    params:                         # 可调参数
      max_turns: 10
      temperature: 0
    repetitions: 3                  # 重复次数（观察方差）

  - id: claude-v2-skill-v2-local
    agent:
      name: claude-code-v2
      command: "claude -p --output-file {output_dir}/result.txt"
      input_mode: stdin
      output_mode: file
      env: {ANTHROPIC_API_KEY: "..."}
    skill:
      path: ./skills/frontend-design/
      version: "2.0"
    environment:
      type: worktree
      resource_limits: {timeout_s: 300}
    params:
      max_turns: 10
      temperature: 0
    repetitions: 3
```

**笛卡尔积展开（可选语法糖）**：

当你想测试多个维度的组合时，不需要手动列举每一个 Configuration：

```yaml
# 声明式矩阵：系统自动展开为 3 × 2 × 2 = 12 个 Configuration
matrix:
  agents:
    - {name: claude-code, command: "claude -p ...", ...}
    - {name: cursor-agent, command: "cursor-agent ...", ...}
    - {name: codex, command: "codex ...", ...}
  skills:
    - {path: ./skills/frontend-design/, version: "1.0"}
    - {path: ./skills/frontend-design/, version: "2.0"}
  environments:
    - {type: worktree, resource_limits: {timeout_s: 300}}
    - {type: docker, image: "node:20", resource_limits: {timeout_s: 300, memory_mb: 4096}}
  params:
    - {max_turns: 10, temperature: 0}  # 只用一组参数时退化为单值
  repetitions: 3
```

展开规则：
- 所有维度做笛卡尔积
- `skill` 维度可以包含 `null`（表示不挂载 skill）
- 每个组合重复 `repetitions` 次

#### Configuration 的组成维度

| 维度 | 含义 | 示例 |
|------|------|------|
| Agent | 被评测的完整程序 | claude-code, cursor, codex |
| Skill | 挂载到 agent 的能力单元（可选） | frontend-design v1/v2, null |
| Environment | 执行环境 | worktree, docker, remote sandbox |
| Params | 可调参数 | temperature, max_turns, token_budget |
| Repetitions | 重复次数 | 3（用于统计显著性） |

### 3.2 AgentSpec / SkillSpec / WorkflowSpec（组件定义）

Configuration 中的 `agent` 字段引用一个 AgentSpec：

```yaml
# agents.yaml 或 eval.yaml 内联
agents:
  claude-code-v2:
    type: command
    command: "claude -p --output-file {output_dir}/result.txt"
    input_mode: stdin | file | arg
    output_mode: stdout | file | directory
    timeout_s: 300
    env: {ANTHROPIC_API_KEY: "..."}

  cursor-agent:
    type: command
    command: "cursor-agent --task {input_file} --output {output_dir}"
    input_mode: file
    output_mode: directory
    timeout_s: 600

  langgraph-v2:
    type: workflow
    entrypoint: "python agents/router_v2.py"
    config: ./configs/router-v2.yaml
    output_mode: directory
```

SkillSpec：

```yaml
skills:
  frontend-design-v1:
    path: ./skills/frontend-design/
    version: "1.0"
  frontend-design-v2:
    path: ./skills/frontend-design-v2/
    version: "2.0"
```

**关键设计**：
- Agent 是"黑盒"——只关心 command + 输入输出协议
- Skill 必须挂载到 Agent 上——不能独立运行
- Workflow 是带配置的可执行脚本（Agent 的子类型）

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

### 3.3 WorkspaceSpec（执行环境与沙箱）

#### 设计背景

Agent 评测需要隔离，但隔离级别应匹配实际风险：

| 风险场景 | 需要什么 | 不需要什么 |
|---------|---------|-----------|
| 自己的 agent 互相踩踏 | 文件系统隔离 | 内核级隔离 |
| Agent 意外修改宿主机 | 限制写入范围 | 完整容器 |
| 不可信第三方 agent | 内核级隔离 + 网络限制 | — |
| CI/远程评测 | 完全隔离 + 可复现 | — |

**业界现状（2026）**：
- OpenHands V1：本地默认无容器（subprocess），生产才用 Docker
- Claude Code：内置 git worktree + seatbelt 沙箱（macOS）
- SWE-bench：Docker（因为需要完全可复现）
- iso-code/agentree/ccswarm：git worktree 已成为 agent 隔离的事实标准

#### 三层沙箱模型

```
Level 0: Git Worktree（文件隔离）
  → 零开销，agent 之间互不干扰
  → 不防止 agent 访问 worktree 外的文件

Level 1: Process Sandbox（进程级限制）
  → seatbelt (macOS) / bubblewrap (Linux)
  → 限制文件访问范围 + 可选网络限制
  → 启动开销 ~0ms

Level 2: Container / microVM（完全隔离）
  → E2B (Firecracker microVM) / Modal / Docker
  → 内核级隔离，适合不可信代码
  → 启动开销 <1s (E2B) ~ 3s (Docker)
```

#### WorkspaceSpec 定义

```yaml
workspace:
  # === 文件来源 ===
  source:
    type: git_repo | files | blank
    # git_repo 选项
    repo: ./fixtures/my-app       # 本地路径或 URL
    commit: abc123                 # 可选，默认 HEAD
    branch: main                  # 可选
    # files 选项
    paths:
      - ./fixtures/context-docs/
      - ./fixtures/reference.md

  # === 隔离级别 ===
  isolation:
    level: worktree | sandbox | container | remote
    # 各级别的详细配置见下方

  # === 环境准备 ===
  setup_commands:
    - npm install
    - pip install -r requirements.txt

  # === 资源限制 ===
  limits:
    timeout_s: 300
    max_output_mb: 100            # 防止 agent 产出过大文件
    # Level 1+ 可用
    memory_mb: 4096
    cpu_cores: 2
    # Level 1+ 可用
    network: allow_list | none | unrestricted
    network_allow:                # 当 network: allow_list 时
      - "api.anthropic.com"
      - "api.openai.com"

  # === 清理策略 ===
  cleanup: auto | manual | on_success
```

#### Level 0: Git Worktree（默认，Phase 1）

最轻量的隔离。每个 (task, config, repetition) 在独立的 git worktree 中运行。

```yaml
isolation:
  level: worktree
  # worktree 特有选项
  base_ref: HEAD                  # worktree 基于哪个 commit
  keep_on_failure: true           # 失败时保留 worktree 供调试
  collect_diff: true              # 执行后自动收集 git diff
```

**实现**（参考 iso-code 的安全检查）：
```python
class GitWorktreeProvider:
    async def create(self, spec: WorkspaceSpec) -> WorkspaceHandle:
        # 1. 创建 worktree
        worktree_path = f".micro-eval/workspaces/{run_id}/{config_id}/rep-{rep}"
        await run(f"git worktree add {worktree_path} {spec.source.commit}")
        # 2. 运行 setup commands
        for cmd in spec.setup_commands:
            await run(cmd, cwd=worktree_path)
        return WorkspaceHandle(path=worktree_path, type="worktree")

    async def collect_artifacts(self, handle) -> list[Artifact]:
        # 收集 git diff 作为主要 artifact
        diff = await run("git diff", cwd=handle.path)
        return [Artifact(type="diff", content=diff)]

    async def cleanup(self, handle) -> None:
        await run(f"git worktree remove {handle.path} --force")
```

**优势**：零依赖、零启动开销、跨平台、与 git 生态天然集成
**局限**：不防止 agent 读写 worktree 外的文件、不限制网络

#### Level 1: Process Sandbox（Phase 2）

在 worktree 基础上加进程级限制。**启动开销为零**。

**macOS（seatbelt）**：
```yaml
isolation:
  level: sandbox
  sandbox_profile: coding_agent   # 预置 profile 名称
```

预置 profile 示例：
```scheme
;; .micro-eval/sandbox-profiles/coding_agent.sb
(version 1)
(deny default)
;; 允许读写 worktree 目录
(allow file-read* file-write*
  (subpath "${WORKSPACE_PATH}"))
;; 允许读系统库和工具链
(allow file-read*
  (subpath "/usr/lib")
  (subpath "/usr/bin")
  (subpath "/opt/homebrew"))
;; 允许执行
(allow process-exec)
;; 网络：只允许访问 LLM provider
(allow network-outbound
  (remote tcp "api.anthropic.com:443")
  (remote tcp "api.openai.com:443"))
;; 禁止其他网络
(deny network*)
```

**Linux（bubblewrap）**：
```yaml
isolation:
  level: sandbox
  sandbox_backend: bwrap          # bubblewrap
```

等效实现：
```bash
bwrap \
  --ro-bind /usr /usr \
  --ro-bind /bin /bin \
  --ro-bind /lib /lib \
  --bind ${WORKSPACE_PATH} ${WORKSPACE_PATH} \
  --tmpfs /tmp \
  --unshare-net \                 # 网络隔离（可选）
  --die-with-parent \
  -- ${AGENT_COMMAND}
```

**Provider 实现**：
```python
class ProcessSandboxProvider:
    async def create(self, spec: WorkspaceSpec) -> WorkspaceHandle:
        # 1. 先创建 worktree（复用 Level 0）
        handle = await GitWorktreeProvider().create(spec)
        # 2. 生成 sandbox wrapper
        handle.command_prefix = self.build_sandbox_prefix(
            workspace_path=handle.path,
            network=spec.limits.network,
            network_allow=spec.limits.network_allow,
        )
        return handle

    def build_sandbox_prefix(self, workspace_path, network, network_allow):
        if sys.platform == "darwin":
            profile = self.render_seatbelt_profile(workspace_path, network_allow)
            return f"sandbox-exec -f {profile}"
        elif sys.platform == "linux":
            return self.build_bwrap_command(workspace_path, network)
        else:
            # Windows: 降级为无沙箱
            return ""
```

**优势**：零启动开销、限制文件访问范围、可选网络隔离
**局限**：macOS seatbelt 已 deprecated（仍可用）、不防内核漏洞

#### Level 2: Container（Phase 3 可选）

当需要完全隔离时（不可信 agent、CI 环境）。**不推荐作为默认**。

```yaml
isolation:
  level: container
  backend: e2b | modal | docker   # 选择后端
  # E2B 选项
  e2b:
    template: "base"              # 或自定义 template
    timeout_s: 300
  # Modal 选项
  modal:
    image: "python:3.11-slim"
    gpu: false
  # Docker 选项（最重，不推荐）
  docker:
    image: "node:20-slim"
    network: none
```

**推荐优先级**：E2B（<1s 启动，Firecracker microVM）> Modal（按需付费）> Docker（本地重量级）

**Provider 实现**（E2B 示例）：
```python
class E2BProvider:
    async def create(self, spec: WorkspaceSpec) -> WorkspaceHandle:
        sandbox = await Sandbox.create(
            template=spec.isolation.e2b.template,
            timeout=spec.limits.timeout_s,
            envs=self.inject_secrets(spec),
        )
        # 上传 workspace 文件
        if spec.source.type == "git_repo":
            await sandbox.commands.run(f"git clone {spec.source.repo} /workspace")
            await sandbox.commands.run(f"git checkout {spec.source.commit}", cwd="/workspace")
        # 运行 setup
        for cmd in spec.setup_commands:
            await sandbox.commands.run(cmd, cwd="/workspace")
        return WorkspaceHandle(path="/workspace", type="e2b", sandbox=sandbox)

    async def cleanup(self, handle) -> None:
        await handle.sandbox.kill()
```

#### Level 3: Remote Sandbox（Phase 3+）

托管式远程执行，适合 CI 集成和大规模并行评测。

```yaml
isolation:
  level: remote
  provider: e2b | modal | daytona
  # Daytona（OpenHands 集成）
  daytona:
    workspace_class: "standard"
    region: "us-east-1"
```

#### Provider 接口（统一）

所有级别实现同一接口：

```python
class WorkspaceProvider(Protocol):
    name: str  # "worktree", "sandbox", "e2b", "docker", ...

    async def create(self, spec: WorkspaceSpec) -> WorkspaceHandle: ...
    async def exec_command(self, handle: WorkspaceHandle, cmd: str,
                           env: dict | None = None) -> CommandResult: ...
    async def collect_artifacts(self, handle: WorkspaceHandle) -> list[Artifact]: ...
    async def collect_diff(self, handle: WorkspaceHandle) -> str | None: ...
    async def cleanup(self, handle: WorkspaceHandle) -> None: ...

@dataclass
class WorkspaceHandle:
    path: str
    type: str
    command_prefix: str = ""      # sandbox wrapper（Level 1）
    sandbox: Any = None           # remote sandbox instance（Level 2+）

@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool
```

#### 分阶段实现路径

| Phase | 实现 | 隔离级别 | 启动开销 | 适用场景 |
|-------|------|---------|---------|---------|
| 1 | GitWorktreeProvider | Level 0 | 0ms | 自己的 agent，本地开发 |
| 2 | ProcessSandboxProvider | Level 1 | 0ms | 防意外破坏，限制网络 |
| 3 | E2BProvider / ModalProvider | Level 2 | <1s | 不可信 agent，CI |
| 3+ | DaytonaProvider | Level 3 | ~90ms | 大规模并行，远程 |

**Phase 1 不实现 Docker**。Docker 启动慢（1-3s）、需要 daemon、对 macOS 开发者体验差。
如果需要容器级隔离，直接跳到 E2B/Modal（更快、更轻、按需付费）。

#### 第三方 Provider 注册

```toml
# pyproject.toml
[project.entry-points."micro_eval.workspace_providers"]
my_k8s = "my_package:K8sWorkspaceProvider"
```



当前只实现 `GitWorktreeProvider` 和 `FilesProvider`，未来加 `DockerProvider`。

### 3.4 Run（评测执行）

一个 Run 的本质是 **Tasks × Configurations × Repetitions → ResultMatrix**。

```yaml
id: run-20260601-143022
timestamp: "2026-06-01T14:30:22Z"
status: completed  # pending | running | completed | failed | cancelled

# 配置集（矩阵的"列"）
configurations:
  - id: claude-v2-skill-v1
    agent: claude-code-v2
    skill: frontend-design-v1
    environment: {type: worktree}
    params: {max_turns: 10}
  - id: claude-v2-skill-v2
    agent: claude-code-v2
    skill: frontend-design-v2
    environment: {type: worktree}
    params: {max_turns: 10}
  - id: cursor-no-skill
    agent: cursor-agent
    skill: null
    environment: {type: docker, image: "node:20"}
    params: {max_turns: 20}

# 或者用矩阵声明（系统自动展开）
# matrix:
#   agents: [claude-code-v2, cursor-agent]
#   skills: [frontend-design-v1, frontend-design-v2, null]
#   environments: [{type: worktree}, {type: docker}]
#   params: [{max_turns: 10}]
#   repetitions: 3

# 任务集（矩阵的"行"）
task_set:
  source: ./tasks/
  filter:
    tags: [bug-fix]
    ids: [fix-auth, fix-nav]

# 执行配置
execution:
  mode: parallel
  max_concurrent: 4
  randomize_order: true
  repetitions: 3              # 每个 (task, config) 跑几次

# 环境快照
snapshot:
  git_commit: abc123
  config_hash: sha256:...
  timestamp: "2026-06-01T14:30:22Z"
```

**结果矩阵的形状**：

```
              Config-A    Config-B    Config-C
Task-1 rep1   [result]    [result]    [result]
Task-1 rep2   [result]    [result]    [result]
Task-1 rep3   [result]    [result]    [result]
Task-2 rep1   [result]    [result]    [result]
...
```

聚合时可按任意维度 group by：
- 按 agent 聚合 → 对比不同 agent 的整体表现
- 按 skill 聚合 → 对比 skill 版本的效果差异
- 按 environment 聚合 → 对比环境对结果的影响
- 按 task tag 聚合 → 对比不同任务类型的表现

### 3.5 RunResult（单个 cell 的结果）

一个 RunResult 对应矩阵中的一个 cell：`(task_id, config_id, repetition)`。

```yaml
task_id: fix-auth-redirect
config_id: claude-v2-skill-v2
repetition: 1
status: completed

# 产出物
artifacts:
  - type: diff
    path: .micro-eval/artifacts/run-xxx/fix-auth/claude-v2-skill-v2/rep-1/changes.patch
  - type: file
    path: .micro-eval/artifacts/run-xxx/fix-auth/claude-v2-skill-v2/rep-1/output.txt
  - type: directory
    path: .micro-eval/artifacts/run-xxx/fix-auth/claude-v2-skill-v2/rep-1/workspace/

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
  ├─ 4. 采集 trace → TraceProvider.collect()          ← 新增
  ├─ 5. 自动验证 → ValidationRunner.run()
  ├─ 6. LLM 评分 → Grader.grade()
  ├─ 7. 聚合结果 → RunResult[]
  └─ 8. 持久化 → .micro-eval/runs/<run-id>/
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

### 5.5 Trace 采集（TraceProvider 架构）

Agent 执行过程的观测数据（tool calls、token 消耗、LLM 调用链）是 trajectory evaluation 的数据来源。
不同团队有不同的 observability 基础设施，所以 trace 采集抽象为 **Provider 接口**。

#### 设计原则

1. **执行后拉取，不侵入执行** — micro-eval 不注入 agent 运行时，agent 跑完后 Provider 去对应系统拉数据
2. **关联通过环境变量** — 执行前注入 `MICRO_EVAL_TRACE_ID`，agent 如果支持就传给 trace 系统
3. **多 Provider 并存，按优先级 fallback** — 最丰富的数据源优先，进程级采集兜底
4. **输出归一化** — 不管来源是什么，最终都归一化为统一的 TraceData 结构

#### Provider 接口

```python
class TraceProvider(Protocol):
    """从任意来源采集 agent 执行轨迹"""

    name: str  # 如 "langfuse", "langsmith", "self_report"

    def supports(self, target: EvalTarget) -> bool:
        """判断此 provider 是否能为该 target 提供 trace"""
        ...

    def collect(self, ctx: RunContext) -> TraceData | None:
        """在 agent 执行结束后，采集 trace 数据。无数据返回 None。"""
        ...
```

#### 配置

```yaml
# eval.yaml
trace_providers:
  - type: langfuse
    priority: 1
    config:
      host: "https://cloud.langfuse.com"
      public_key: "pk-..."
      secret_key: "sk-..."
      match_by: metadata.eval_trace_id  # 关联方式

  - type: langsmith
    priority: 2
    config:
      api_key: "ls-..."
      project: "my-agent-eval"
      match_by: metadata.eval_trace_id

  - type: self_report
    priority: 3
    config:
      trace_file: "{output_dir}/trace.json"
      format: opentelemetry | micro_eval  # 支持的格式

  - type: builtin
    priority: 99  # 兜底，始终可用
    # 进程级采集：wall clock time、exit code、stderr token 信息
```

#### 关联机制

Agent 执行前，micro-eval 通过环境变量注入关联 ID：

```python
env_inject = {
    "MICRO_EVAL_TRACE_ID": f"{run_id}--{task_id}--{config_id}--rep{repetition}",
    "MICRO_EVAL_RUN_ID": run_id,
    "MICRO_EVAL_CONFIG_ID": config_id,
}
```

各 Provider 用这个 ID 去对应系统查询 trace：

```python
class LangfuseProvider:
    def collect(self, ctx: RunContext) -> TraceData | None:
        traces = self.client.get_traces(
            metadata={"eval_trace_id": ctx.trace_id}
        )
        if not traces:
            return None
        return self.normalize(traces)
```

#### 归一化输出（TraceData）

```python
@dataclass
class TraceData:
    """所有 Provider 的输出都归一化为此结构"""
    steps: list[TraceStep]
    total_tokens: int
    total_cost_usd: float
    total_duration_s: float
    tool_calls: dict[str, int]      # tool name → count
    llm_calls: list[LLMCall]        # 每次 LLM 调用详情
    errors: list[TraceError]

@dataclass
class TraceStep:
    timestamp: str
    type: Literal["llm_call", "tool_use", "thinking", "error"]
    name: str
    duration_s: float
    tokens: int | None
    input_summary: str              # 截断摘要（≤500 chars）
    output_summary: str

@dataclass
class LLMCall:
    model: str
    input_tokens: int
    output_tokens: int
    duration_s: float
    cost_usd: float | None

@dataclass
class TraceError:
    timestamp: str
    message: str
    recovered: bool
```

#### 第三方 Provider 注册

内置：`langfuse`, `langsmith`, `self_report`, `builtin`

第三方通过 Python entry point 注册，无需修改 micro-eval 代码：

```toml
# 第三方 provider 的 pyproject.toml
[project.entry-points."micro_eval.trace_providers"]
arize_phoenix = "my_package.providers:ArizePhoenixProvider"
custom_otel = "my_package.providers:OTelProvider"
```

用户安装包后即可在 eval.yaml 中使用：

```yaml
trace_providers:
  - type: arize_phoenix
    priority: 1
    config:
      endpoint: "http://localhost:6006"
```

#### 与 Trajectory Evaluation 的关系

TraceData 是 4.4.2 节 Trajectory Evaluation 的数据输入：

```
Agent 执行 → TraceProvider.collect() → TraceData
                                           ↓
                              Grader 评估 trajectory_grading：
                                - tool_efficiency（从 tool_calls 计算）
                                - reasoning_quality（从 steps 分析）
                                - resource_usage（从 tokens/duration 计算）
                                - error_recovery（从 errors 分析）
```

没有 trace 数据时（所有 Provider 返回 None），trajectory_grading 跳过，
只保留 builtin Provider 提供的进程级指标（duration、exit code）。

---

## 6. CLI 设计

```bash
# 核心命令
micro-eval init                          # 生成 eval.yaml + tasks/ 模板
micro-eval run [--config eval.yaml]      # 执行评测（全矩阵）
micro-eval run --configs a,b --tasks t1  # 指定 configuration 和 task
micro-eval run --matrix                  # 展开矩阵声明并执行
micro-eval grade <run-id>                # 对已有 run 补充 LLM 评分
micro-eval compare <run-id-1> <run-id-2> # 跨 run 对比
micro-eval report <run-id>               # 生成 HTML 报告
micro-eval report <run-id> --group-by agent   # 按维度聚合报告

# 辅助命令
micro-eval doctor                        # 检查环境依赖
micro-eval list runs                     # 列出历史 run
micro-eval list tasks                    # 列出可用 task
micro-eval list configs                  # 列出已定义的 configuration
micro-eval show <run-id>                 # 终端中查看 run 结果
micro-eval ui                            # 启动 Web UI
```

---

## 7. 数据存储

### 7.1 文件结构

```
project-root/
├── eval.yaml                    # 项目配置（configurations + 执行参数）
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
    │       ├── manifest.json    # Run 元数据（configurations, tasks, matrix）
    │       ├── results/
    │       │   ├── fix-auth--claude-v2-skill-v1--rep1.json
    │       │   ├── fix-auth--claude-v2-skill-v1--rep2.json
    │       │   ├── fix-auth--claude-v2-skill-v2--rep1.json
    │       │   └── fix-auth--cursor-no-skill--rep1.json
    │       ├── artifacts/
    │       │   ├── fix-auth--claude-v2-skill-v1--rep1/
    │       │   │   ├── changes.patch
    │       │   │   ├── stdout.txt
    │       │   │   └── trace.json
    │       │   └── fix-auth--claude-v2-skill-v2--rep1/
    │       │       └── ...
    │       └── aggregations/    # 按维度聚合的统计
    │           ├── by-agent.json
    │           ├── by-skill.json
    │           └── by-environment.json
    ├── annotations/             # 人工标注（持久化）
    │   └── run-20260601-143022.json
    └── config.json              # 全局配置（judge model, providers 等）
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

WorkspaceSpec（3.3 节）已详细定义了四层隔离模型和 Provider 接口。
本节补充**决策依据和演进策略**。

### 10.1 为什么不用 Docker 作为默认

| 问题 | 影响 |
|------|------|
| 启动慢（1-3s per container） | 10 task × 3 config × 3 rep = 90 次启动 → 额外 90-270s |
| 需要 Docker daemon | macOS 开发者需装 Docker Desktop（重量级） |
| 资源占用 | 每个容器占内存，并行时压力大 |
| 对我们的场景过度 | 跑的是自己的 agent，不是不可信代码 |

**替代方案对比**（来自调研）：

| 方案 | 启动 | 隔离级别 | 平台 | 适合 |
|------|------|---------|------|------|
| git worktree | 0ms | 文件隔离 | 全平台 | 自己的 agent |
| seatbelt (macOS) | 0ms | 进程级 | macOS | 防意外破坏 |
| bubblewrap (Linux) | 0ms | namespace | Linux | 防意外破坏 |
| E2B (Firecracker) | <1s | microVM | 云端 | 不可信代码 |
| Modal | <1s | 容器 | 云端 | 大规模并行 |
| Daytona | ~90ms | 容器 | 云端 | OpenHands 集成 |

### 10.2 演进路径

```
Phase 1（现在）: GitWorktreeProvider
  → 零开销，覆盖 90% 场景
  → 可选 ProcessSandboxProvider（seatbelt/bwrap）

Phase 2: ProcessSandboxProvider 成熟
  → 网络白名单（只允许 LLM provider）
  → ulimit 资源限制
  → secret redaction 集成

Phase 3: 远程 Provider（按需）
  → E2BProvider（不可信 agent）
  → ModalProvider（大规模并行评测）
  → DaytonaProvider（OpenHands 集成）
```

**跳过 Docker**：如果需要容器级隔离，直接用 E2B/Modal（更快、更轻、按需付费）。

### 10.3 参考实现

- [iso-code](https://isocode.dev/)：生产级 git worktree 隔离，含崩溃安全和端口租约
- [agent-seatbelt-sandbox](https://github.com/michaelneale/agent-seatbelt-sandbox)：Claude Code 使用的 seatbelt 方案
- [E2B](https://github.com/e2b-dev/e2b)：Firecracker microVM，<1s 启动
- [OpenHands V1](https://arxiv.org/html/2511.03690v2)：本地无容器 + 生产 Docker 的混合模式

---

## 11. Secrets 与 BYOK 安全模型

### 11.1 问题定义

Agent 评测需要 API keys（调用 LLM provider）和可能的其他凭证（GitHub token、数据库连接等）。
安全挑战随部署形态递增：

| 形态 | 风险等级 | 核心问题 |
|------|---------|---------|
| 本地 CLI | 低 | 用户自己的 key，进程级隔离 |
| 本地 Docker | 中 | key 注入容器，容器内代码可读取 |
| 远程沙盒 | 高 | key 离开用户机器，经过第三方基础设施 |
| 多用户/团队 | 高 | 不同用户的 key 需要隔离 |

### 11.2 设计原则

1. **Secrets 永不持久化到 micro-eval 存储** — 不写入 JSON、不写入 run artifacts、不出现在日志中
2. **最小权限** — 每个 Configuration 只获得它需要的 secrets
3. **用户控制** — BYOK 意味着用户决定用哪个 key、给哪个 agent、什么权限
4. **分层安全** — 本地简单（env vars），远程严格（短期 token + proxy）

### 11.3 Secrets 来源层级

```yaml
# eval.yaml — 声明需要哪些 secrets（不包含值）
secrets:
  ANTHROPIC_API_KEY:
    description: "Claude API key for agent execution"
    required: true
    scope: [agent]              # 谁能访问

  OPENAI_API_KEY:
    description: "OpenAI key for baseline comparison"
    required: false
    scope: [agent]

  GITHUB_TOKEN:
    description: "GitHub token for repo access"
    required: false
    scope: [agent, workspace]   # workspace setup 也需要
```

**值的来源（按优先级）**：

```
1. 环境变量（最简单）     — export ANTHROPIC_API_KEY=sk-...
2. .env 文件（本地开发）  — .micro-eval/.env（gitignored）
3. OS Keychain（更安全）  — keyring get micro-eval ANTHROPIC_API_KEY
4. Vault 集成（团队/远程）— vault://micro-eval/ANTHROPIC_API_KEY
```

### 11.4 注入机制

#### 本地执行（Phase 1）

最简单的模型：通过环境变量注入到 agent 进程。

```python
class LocalSecretsInjector:
    def inject(self, config: Configuration, secrets: dict[str, str]) -> dict[str, str]:
        """返回要注入到 agent 进程的 env vars"""
        allowed = self.filter_by_scope(secrets, config)
        return {
            **allowed,
            # micro-eval 自己的关联 ID（非 secret）
            "MICRO_EVAL_TRACE_ID": config.trace_id,
        }
```

安全措施：
- agent 进程的 stderr/stdout 在持久化前做 secret redaction
- artifacts 保存前扫描已知 secret patterns（sk-xxx, ghp_xxx 等）
- `.micro-eval/.env` 自动加入 `.gitignore`

#### Docker 执行（Phase 2）

参考 [Cloudflare Sandbox SDK](https://developers.cloudflare.com/sandbox/configuration/environment-variables/) 的三层注入模型：

```python
class DockerSecretsInjector:
    def inject(self, config: Configuration, secrets: dict[str, str]) -> DockerEnvConfig:
        """三层注入：sandbox 级 / session 级 / command 级"""
        return DockerEnvConfig(
            # sandbox 级：所有命令可见
            sandbox_env=self.filter_by_scope(secrets, scope="workspace"),
            # command 级：只在 agent 命令执行时注入
            command_env=self.filter_by_scope(secrets, scope="agent"),
        )
```

安全措施：
- 网络隔离：`--network=none` 或白名单出站（只允许访问 LLM provider endpoints）
- 文件系统隔离：secrets 不写入容器文件系统
- 执行后清理：容器销毁时 secrets 随之消失

#### 远程沙盒（Phase 3）

参考 [E2B 的 envs 注入](https://changelog.e2b.dev/docs/sandbox/environment-variables) + [Warp 的 BYOK 模型](https://docs.warp.dev/agent-platform/inference/bring-your-own-api-key/)：

```python
class RemoteSecretsInjector:
    def inject(self, config: Configuration, secrets: dict[str, str]) -> RemoteEnvConfig:
        """远程沙盒：secrets 经过加密通道传输，per-sandbox 隔离"""
        # 方案 A：直接注入（E2B 模式）
        # secrets 通过 TLS 传到远程 sandbox，作为 env vars 存在
        # 风险：sandbox 内代码可读取所有 env vars
        
        # 方案 B：Proxy 模式（推荐）
        # secrets 不进入 sandbox，agent 通过 proxy 访问 LLM
        # proxy 在 sandbox 外注入 credentials
        return RemoteEnvConfig(
            mode="proxy",  # 或 "direct"
            proxy_endpoint="https://eval-proxy.internal/v1",
            sandbox_env={
                # agent 看到的是 proxy URL，不是真实 key
                "ANTHROPIC_API_KEY": "proxy-token-xxx",
                "ANTHROPIC_BASE_URL": "https://eval-proxy.internal/v1",
            }
        )
```

### 11.5 BYOK（Bring Your Own Key）模式

当 micro-eval 交付给其他团队使用时，他们需要用自己的 API keys。

**设计**：

```yaml
# 用户的 .micro-eval/.env（不进版本控制）
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx

# 或者用 keychain
# micro-eval secrets set ANTHROPIC_API_KEY
# (交互式输入，存入 OS keychain)
```

**CLI 支持**：

```bash
# 设置 secret（存入 OS keychain）
micro-eval secrets set ANTHROPIC_API_KEY

# 列出已配置的 secrets（只显示名称，不显示值）
micro-eval secrets list

# 验证 secrets 是否可用
micro-eval doctor --check-secrets

# 从 .env 文件导入
micro-eval secrets import .env
```

**Per-Configuration key 覆盖**：

不同 Configuration 可能需要不同的 key（比如测 Claude 用 Anthropic key，测 GPT 用 OpenAI key）：

```yaml
configurations:
  - id: claude-agent
    agent: claude-code
    secrets_override:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}  # 从环境取
  - id: openai-agent
    agent: gpt-agent
    secrets_override:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
```

### 11.6 Secret Redaction（泄露防护）

所有输出路径都经过 redaction：

```python
class SecretRedactor:
    """在持久化前扫描并遮蔽 secrets"""
    
    patterns = [
        r"sk-ant-[a-zA-Z0-9-_]{20,}",   # Anthropic
        r"sk-[a-zA-Z0-9]{20,}",          # OpenAI
        r"ghp_[a-zA-Z0-9]{36,}",         # GitHub PAT
        r"gho_[a-zA-Z0-9]{36,}",         # GitHub OAuth
    ]
    
    def redact(self, text: str, known_secrets: list[str]) -> str:
        """替换已知 secrets + 匹配 patterns"""
        for secret in known_secrets:
            text = text.replace(secret, f"[REDACTED:{secret[:4]}...]")
        for pattern in self.patterns:
            text = re.sub(pattern, "[REDACTED]", text)
        return text
```

应用位置：
- `stdout` / `stderr` 持久化前
- Artifacts 保存前
- TraceData 归一化时
- Web UI 展示时
- LLM Judge 的 input 中（避免 judge 看到 secrets）

### 11.7 安全分阶段路径

| Phase | 形态 | Secrets 方案 | BYOK 方式 |
|-------|------|-------------|-----------|
| 1 | 本地 CLI | env vars + .env 文件 + redaction | 用户设环境变量 |
| 2 | 本地 Docker | per-container env injection + network isolation | 同上 + `micro-eval secrets` CLI |
| 3 | 远程沙盒 | Proxy 模式 + 短期 token + audit log | Vault 集成 / Proxy token exchange |



---

## 12. 与现有 MVP 的关系

### 12.1 保留

- Python CLI + Typer 框架
- Next.js Web UI 骨架
- pytest 测试基础设施
- git worktree workspace 隔离（升级为 Provider）
- JSON 文件存储（升级结构）

### 12.2 重写

- **领域模型**：从 baseline/candidate 二元 → Configuration 矩阵（Agent × Skill × Environment × Params × Repetitions）
- **Task 模型**：从 input_payload + expected_output → prompt + workspace + expectations
- **评分引擎**：从精确匹配 → validation + LLM judge（task-adaptive rubric）+ annotation 三层
- **执行引擎**：从硬编码 subprocess → AgentExecutor + SkillExecutor + WorkspaceProvider + TraceProvider
- **Web UI 数据层**：从读 flat JSON → 读结构化 run 目录 + 多维度聚合

### 12.3 新增

- `micro-eval init` / `micro-eval doctor`
- LLM-as-judge grading 系统
- Blind comparison 模式
- Benchmark 模式（多次运行统计）
- 人工标注持久化
- Artifact viewer（diff、文件、目录）
- 跨 run 趋势分析

---

## 13. 技术栈（不变）

| 层 | 技术 |
|----|------|
| CLI + 引擎 | Python 3.11+ / uv / Typer / Pydantic |
| 评分 | 自写 + DeepEval（custom metric） |
| LLM Judge | Anthropic SDK（Claude Sonnet/Opus） |
| 观测（可选） | Langfuse Python SDK |
| Web UI | Next.js + TypeScript + Zod |
| 测试 | pytest + vitest |

---

## 14. 不做（Unicorn 范围外）

- 多团队协作 / RBAC / SSO
- 托管式 Web dashboard
- 自动化 CI 集成（用户自己接）
- 复杂的推荐引擎
- OpenHands 深度集成（留给 Phase 3）
- 自动生成 task（用户手写或用 LLM 辅助生成）
