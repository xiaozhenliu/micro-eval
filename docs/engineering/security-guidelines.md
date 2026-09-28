---
title: micro-eval Security Guidelines Index
language: en
authoritative: true
doc_type: reference
status: active
created_at: 2026-06-02T18:00+08:00
updated_at: 2026-09-27T16:00+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - engineering
  - security
  - micro-eval
related:
  - docs/engineering/security-service-guidelines.md
  - docs/engineering/security-user-run-guidelines.md
  - docs/engineering/security-development-guidelines.md
---

# micro-eval Security Guidelines Index

Security is not a single dimension. This project splits the security guidelines into three layers so that the risks of users running agents, product/service boundaries, and development implementation constraints never blur into one file. Chinese companion translations (`*.zh-CN.md`) exist for human reading; the English files are authoritative and agents must read those.

## Three-layer security source of truth

| Layer | File to read | Applies to |
| --- | --- | --- |
| Product/service security | `docs/engineering/security-service-guidelines.md` | What the product itself may and may not expose when `micro-eval` runs as a CLI, local UI/API, report generator, release package, or future service. |
| User run security | `docs/engineering/security-user-run-guidelines.md` | How secrets, workspaces, network, artifacts, and caveats are handled and surfaced when users test their own agents/skills with `micro-eval`. |
| Development security | `docs/engineering/security-development-guidelines.md` | What developers or agents must follow when changing the runner, adapters, stores, UI/API, reports, decision logic, or validation. |

## Usage rules

- Before implementing, read at least `security-development-guidelines.md`.
- If a change affects user-initiated runs, workspaces, secrets, artifacts, network caveats, or evidence, also read `security-user-run-guidelines.md`.
- If a change affects the CLI, local UI/API, reports, release packages, raw artifact access, or future service boundaries, also read `security-service-guidelines.md`.
- Never redefine concrete security rules in this index; concrete rules live only in the matching layer file.
