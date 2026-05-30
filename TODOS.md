# TODOS.md

## Phase 2+ (来自工程评审 2026-05-31)

### Run ordering 随机化
**What:** 随机化 baseline/candidate 的执行顺序，并记录到 Run JSON 中。
**Why:** 避免顺序效应偏差（缓存预热、API rate limit 等）。并行执行已缓解大部分问题，但记录顺序是好习惯。
**Context:** Codex outside voice 提出。并行执行后两个 agent 几乎同时启动，顺序效应已大幅减小。但如果未来支持串行模式或多 agent (>2) 对比，顺序随机化变得重要。
**Depends on:** MVP 完成

### Task 模型增强
**What:** 为 coding agent 评测场景增强 task 模型：repo fixture、setup command、test command、allowed files、diff expectations、cleanup rules。
**Why:** 当前 prose input_payload + expected_output 对于 "fix auth.ts" 类任务不够精确——无法自动验证 agent 是否真的修对了。
**Context:** Codex outside voice 提出。MVP 阶段用 prose + 人工评分验证核心流程，Phase 2 增强 task 模型支持自动化验证。
**Depends on:** MVP 完成 + 用户反馈确认需求

### Secret redaction
**What:** Run JSON 写入时过滤可能的 secrets（env vars、API keys、tokens）。
**Why:** .micro-eval/ 目录中的 JSON 可能包含 agent stderr 输出中泄露的 secrets。
**Context:** Codex outside voice 提出。MVP 是本地工具风险可控，但如果未来支持报告分享则必须解决。
**Depends on:** MVP 完成

### Concurrency control
**What:** 添加 --max-parallel、全局超时、取消机制、断点恢复。
**Why:** Agent 评测慢且贵，没有这些控制机制在真实工作负载下体验会很差。
**Context:** Codex outside voice 提出。MVP 先做基础的 per-agent timeout + 两个 agent 并行。
**Depends on:** MVP 完成 + 实际使用反馈

### output_mode: directory 评分机制
**What:** 明确 directory 输出模式的评分方式（task-specific validators）。
**Why:** 当前设计中 output_mode: directory 没有说明如何对目录输出评分。没有 task-specific validators，目录输出就是"换了个形式的截图"。
**Context:** Codex outside voice 提出。MVP 先支持 output_mode: file，directory 模式推迟到有真实用例时再设计。
**Depends on:** MVP 完成 + 真实 directory-output agent 用例

### JSON → SQLite 迁移路径
**What:** 当 run 数量增长、需要查询/历史分析时，从 JSON 文件迁移到 SQLite。
**Why:** JSON 文件存储对 MVP 够用，但一旦需要跨 run 查询、趋势分析、标注聚合，文件系统会成为瓶颈。
**Context:** Codex outside voice 提出。MVP 不需要数据库，但应该在数据模型设计时考虑未来迁移的便利性（schema_version 字段已有）。
**Depends on:** 用户反馈确认需要跨 run 查询
