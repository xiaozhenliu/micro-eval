---
id: LOCAL-NEXT-03
title: 准备并完成下一次正式发布
effort: next-release
type: task
status: resolved
triage: ready-for-agent
executor: agent
blocked_by:
  - LOCAL-NEXT-01
  - LOCAL-NEXT-02
created_at: 2026-08-29T13:00+08:00
updated_at: 2026-08-29T16:19+08:00
---

# LOCAL-NEXT-03 — 准备并完成下一次正式发布

**What to build:** 在本轮功能和修复全部完成后，以一次完整、可审计的正式发布交付成果：统一版本号与变更记录，生成发布证据，通过本地质量门禁，再按项目规定的发布路径投影到 `main`，而不是提前推送不完整状态。

- [x] 根据实际变更确定发布版本，并同步所有版本面与 `CHANGELOG` 的 Unreleased 内容。
- [x] 发布证据、依赖清单、测试、UI/Python 构建、版本一致性和 release preflight 全部通过。
- [x] 仅通过项目规定的发布脚本将 `dev` 投影到 `main`，且 dev-only 文件不会进入发布分支。
- [x] 在任何远端推送、打 tag 或发布动作前获得维护者明确授权，并在发布后记录最终提交与验证结果。

## Completion evidence

- Preparation commit: `e47c6a0`; current verified release evidence: `docs/releases/2026-08-29-v0.4.6-release-evidence.md`.
- Verification: version consistency, full Python/UI checks, release preflight, package builds, archive allowlists, and public projection gates passed.
- Authorization trace: local-only staging and separate exact-SHA publication are documented in `docs/engineering/release-process.md`; the historical v0.4.5 authorization-boundary incident remains recorded in the release evidence.
