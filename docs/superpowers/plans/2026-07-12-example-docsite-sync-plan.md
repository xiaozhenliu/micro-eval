# Example Docsite Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync the public documentation site example pages with the latest expanded example design: 5 examples, 40 tracked capabilities, and the new config variants.

**Architecture:** Treat `examples/README.md` as the current source for example inventory and capability coverage. Update the English and Chinese docs-site example indexes to match that source, then build the VitePress site and verify links/coverage are no longer stale.

**Tech Stack:** VitePress, Markdown, bilingual documentation, source-checkout examples

---

## Context

The 2026-07-12 readiness check found that source examples and `examples/README.md` reflect v0.4.4 design, but docs-site example indexes are stale:

- `examples/README.md` lists 5 examples and 40 tracked capabilities.
- `site/examples/index.md` lists only 3 examples.
- `site/zh/examples/index.md` lists only 3 examples.
- Docs-site matrices omit `conversational-eval`, `team-server-quickstart`, `eval.enriched.yaml`, and `eval.blank.yaml`.

This plan covers documentation-site sync only. Release version/golden consistency is tracked separately in `docs/superpowers/plans/2026-07-12-v0-4-4-release-consistency-plan.md`.

## Files

- Read source: `examples/README.md`
- Read source: `examples/run-example.py`
- Read source: `examples/conversational-eval/README.md`
- Read source: `examples/team-server-quickstart/README.md`
- Modify: `site/examples/index.md`
- Modify: `site/zh/examples/index.md`
- Verify existing pages: `site/examples/agent-codefix-showdown.md`
- Verify existing pages: `site/examples/multi-task-matrix.md`
- Verify existing pages: `site/examples/git-workspace-isolation.md`
- Verify existing pages: `site/guide/conversational-evaluation.md`
- Verify existing pages: `site/guide/team-server.md`
- Verify Chinese pages: `site/zh/guide/conversational-evaluation.md`
- Verify Chinese pages: `site/zh/guide/team-server.md`

---

### Task 1: Reconcile example inventory against source README

**Files:**
- Read: `examples/README.md`
- Read: `examples/run-example.py`
- Read: `site/examples/index.md`
- Read: `site/zh/examples/index.md`

- [ ] **Step 1: Confirm source example list**

Run:

```bash
rtk rg -n 'ALL_EXAMPLES|agent-codefix-showdown|multi-task-matrix|git-workspace-isolation|conversational-eval|team-server-quickstart' examples/run-example.py examples/README.md
```

Expected:

- `ALL_EXAMPLES` includes:
  - `agent-codefix-showdown`
  - `multi-task-matrix`
  - `git-workspace-isolation`
  - `conversational-eval`
  - `team-server-quickstart`

- [ ] **Step 2: Confirm docs-site stale inventory**

Run:

```bash
rtk rg -n 'conversational-eval|team-server-quickstart|eval\.enriched|eval\.blank|Capability Coverage Matrix' site/examples/index.md site/zh/examples/index.md
```

Expected before implementation:

- Missing or incomplete references confirm the sync gap.

---

### Task 2: Update English docs-site example index

**Files:**
- Modify: `site/examples/index.md`
- Read source: `examples/README.md`

- [ ] **Step 1: Update Quick Start commands**

In `site/examples/index.md`, add examples for:

```bash
python examples/run-example.py --example conversational-eval
python examples/run-example.py --example team-server-quickstart
```

Keep the existing default, specific, all, and real-agent command groups.

- [ ] **Step 2: Update Available Examples table**

Replace the 3-example table with 5 rows:

- Agent Codefix Showdown
- Multi-Task Matrix
- Git Workspace Isolation
- Conversational Evaluation
- Team Server Quickstart

Keep descriptions aligned with `examples/README.md`, including:

- `eval.blank.yaml` blank workspace + `input_mode: file`
- `eval.enriched.yaml` enriched config fields
- DeepEval requirement for conversational scoring
- `micro-eval serve` workflow for Team Server Quickstart

- [ ] **Step 3: Update Capability Coverage Matrix**

Mirror the 5-column, 40-capability matrix from `examples/README.md`.

Expected columns:

- `codefix-showdown`
- `multi-task-matrix`
- `git-workspace-isolation`
- `conversational-eval`
- `team-server`

Expected newly represented capabilities include:

- `blank` workspace
- `stdin` input mode
- `file` input mode
- Conversational evaluation
- JSONL subprocess bridge
- Structured RubricSpec
- `randomize_execution_order`
- `skills_profile`
- `parameters`
- `denominator_policy: exclude_failed`
- `inconclusive_policy: block`
- `stop_on_cell_error: true`
- `micro-eval serve`
- Template management
- Workspace management
- HTTP API
- Member attribution
- Serial queue
- CSRF protection

- [ ] **Step 4: Add Config Variants section**

Add a short section matching `examples/README.md`:

```bash
python examples/multi-task-matrix/run.py --variant enriched
cd examples/agent-codefix-showdown && uv run micro-eval run --config eval.blank.yaml
```

Explain that variants expand coverage without adding more example directories.

---

### Task 3: Update Chinese docs-site example index

**Files:**
- Modify: `site/zh/examples/index.md`
- Read source: `examples/README.md`
- Read source: `site/examples/index.md`

- [ ] **Step 1: Translate updated Quick Start commands**

Mirror the English command set and add:

```bash
python examples/run-example.py --example conversational-eval
python examples/run-example.py --example team-server-quickstart
```

- [ ] **Step 2: Translate Available Examples table**

Update from 3 rows to 5 rows, preserving product terms consistently:

- `Agent Codefix Showdown`
- `Multi-Task Matrix`
- `Git Workspace Isolation`
- `Conversational Evaluation`
- `Team Server Quickstart`

Use Chinese explanatory text but keep config/file names literal.

- [ ] **Step 3: Translate Capability Coverage Matrix**

Mirror all 5 columns and 40 capabilities from the English page.

Keep technical tokens unchanged:

- `eval.blank.yaml`
- `eval.enriched.yaml`
- `input_mode: file`
- `denominator_policy: exclude_failed`
- `inconclusive_policy: block`
- `stop_on_cell_error: true`
- `micro-eval serve`
- `X-Micro-Eval-Member`

- [ ] **Step 4: Add Chinese Config Variants section**

Add the same two command examples and explain the purpose of config variants in Chinese.

---

### Task 4: Verify docs links and build

**Files:**
- Verify: `site/examples/index.md`
- Verify: `site/zh/examples/index.md`
- Verify: `site/guide/conversational-evaluation.md`
- Verify: `site/zh/guide/conversational-evaluation.md`
- Verify: `site/guide/team-server.md`
- Verify: `site/zh/guide/team-server.md`

- [ ] **Step 1: Check references exist**

Run:

```bash
rtk rg -n 'conversational-eval|team-server-quickstart|eval\.enriched|eval\.blank|40 capabilities|5 examples|Team Server Quickstart|Conversational Evaluation' site examples/README.md
```

Expected:

- Both docs-site example indexes reference the new examples and variants.
- Existing guide pages continue to cover conversational evaluation and team server concepts.

- [ ] **Step 2: Build docs site**

Run from `site/`:

```bash
rtk npm run docs:build
```

Expected:

- Build exits `0`.
- Large chunk warnings are acceptable unless new warnings indicate broken links or markdown errors.

- [ ] **Step 3: Check final diff**

Run:

```bash
rtk git diff --stat
rtk git diff -- site/examples/index.md site/zh/examples/index.md
```

Expected:

- Diff is limited to docs-site example index sync.
- No unrelated docs pages are modified unless required by broken links discovered during build.

---

### Task 5: Optional follow-up after docs sync

**Files:**
- Optional create after implementation: `docs/dev/log/YYYY-MM-DD-HHMM-dev-log-example-docsite-sync.md`

- [ ] **Step 1: Decide whether a dev log is warranted**

Create a dev log only if the implementation uncovers non-obvious documentation architecture decisions, such as:

- Whether to create dedicated docs-site pages for `conversational-eval` or `team-server-quickstart`.
- Whether example coverage should be generated from `examples/README.md` in the future.
- Whether the docs-site should link to source examples directly when no dedicated page exists.

- [ ] **Step 2: Record follow-ups if not implemented now**

If dedicated example pages are deferred, record that explicitly under "Risks and follow-ups" in the dev log or the implementation summary.

