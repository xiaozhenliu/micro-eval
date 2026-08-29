---
id: LOCAL-NEXT-08
title: 收紧 wheel 与 sdist 公开产物
effort: next-release
type: task
status: resolved
triage: ready-for-agent
executor: agent
blocked_by:
  - LOCAL-NEXT-06
  - LOCAL-NEXT-07
created_at: 2026-08-29T13:00+08:00
updated_at: 2026-08-29T16:19+08:00
---

# LOCAL-NEXT-08 — 收紧 wheel 与 sdist 公开产物

**What to build:** wheel 和 sdist 使用显式内容白名单，从候选公开树构建，并对归档文件清单做 fail-closed 验证。

- [x] sdist 不再包含 `.omx`、`.scratch`、`.superpowers`、`.codex`、内部 docs、缓存或其他未跟踪本地文件。
- [x] wheel 继续只包含 `micro_eval` 包、dist-info 和许可证所需文件。
- [x] 构建后逐项验证 tar/zip 内容；未知条目、绝对路径和路径穿越使发布失败。
- [x] CI 和正式发布入口都运行产物清单验证，回归测试覆盖恶意/意外归档条目。

## Context

当前本地 preflight 生成的 sdist 有 697 个条目，其中 197 个不是 Git tracked 文件，并包含多类本地会话、issue 和内部文档路径。

## 给高中实习生的解释

GitHub 上的源码不是唯一发布物；Python 用户还会下载 wheel 和 sdist，它们像另外两个快递箱。以前 sdist 会把本机没提交的草稿一起打包。现在两个箱子各有明确装箱单，打包后程序会逐项开箱核对；陌生文件、危险路径或链接都会让发布失败。最终 sdist 从 697 项降到 76 项。

## Completion evidence

- Implementation trace: `docs/dev/log/2026-08-28-1709-dev-log-fail-closed-public-release.md`.
- Verification: explicit wheel/sdist allowlists, unsafe archive paths, links, and unexpected entries are rejected; v0.4.6 artifacts passed with 73 wheel and 76 sdist entries.
