# v0.4.4 Release Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring all v0.4.4 version and golden contract surfaces into release-ready consistency.

**Architecture:** Treat the root `VERSION` file as the release source of truth. Sync Python runtime version, README version surfaces, UI package lock metadata, and generated P0 golden fixtures, then verify with the existing release consistency and contract checks.

**Tech Stack:** Python 3.11+, uv, pytest, Node/npm package metadata, generated JSON golden fixtures

---

## Context

The 2026-07-12 readiness check found that `VERSION` and `ui/package.json` are already `0.4.4`, but several release surfaces still report `0.4.3`. This causes:

- `scripts/release/check-version-consistency.py` to fail.
- `tests/contract/test_golden.py::test_golden_generation_is_idempotent` to fail after regenerating golden fixtures.
- P0 replay canonical fixture metadata to disagree with the current release version.

This plan covers only release consistency. Documentation-site example coverage is tracked separately in `docs/superpowers/plans/2026-07-12-example-docsite-sync-plan.md`.

## Files

- Modify: `src/micro_eval/__init__.py`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `ui/package-lock.json`
- Modify: `tests/contract/golden/run-p0-contract.json`
- Modify: `ui/src/lib/fixtures/canonical-run-p0.json`
- Read/verify: `VERSION`
- Read/verify: `scripts/release/check-version-consistency.py`
- Read/verify: `scripts/generate-golden.py`
- Read/verify: `tests/contract/test_golden.py`

---

### Task 1: Sync static version surfaces to v0.4.4

**Files:**
- Modify: `src/micro_eval/__init__.py`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `ui/package-lock.json`
- Read: `VERSION`
- Read: `ui/package.json`

- [ ] **Step 1: Confirm source-of-truth version**

Run:

```bash
rtk sed -n '1,20p' VERSION
rtk sed -n '1,40p' ui/package.json
```

Expected:

- `VERSION` is `0.4.4`
- `ui/package.json` version is `0.4.4`

- [ ] **Step 2: Update Python runtime version**

Change `src/micro_eval/__init__.py`:

```python
__version__ = "0.4.4"
```

- [ ] **Step 3: Update README version text**

Update both files:

- `README.md`
- `README.zh-CN.md`

Required replacements:

- Badge text: `Version: 0.4.4`
- Badge URL segment: `version-0.4.4-6f42c1`
- Current version text: `0.4.4`

- [ ] **Step 4: Update UI lockfile root versions**

Update `ui/package-lock.json` root package metadata to match `ui/package.json`:

- top-level `"version": "0.4.4"`
- `packages[""].version = "0.4.4"`

Do not change dependency versions unless `npm install` is intentionally run and produces lockfile changes.

- [ ] **Step 5: Verify static version grep**

Run:

```bash
rtk rg -n '0\.4\.3|0\.4\.4|__version__|tool_version' VERSION README.md README.zh-CN.md src/micro_eval/__init__.py ui/package.json ui/package-lock.json
```

Expected:

- Release surfaces that describe the current version use `0.4.4`.
- Historical changelog mentions of older versions, if included in a broader grep, are not changed.

---

### Task 2: Regenerate and review P0 golden fixture version metadata

**Files:**
- Modify: `tests/contract/golden/run-p0-contract.json`
- Modify: `ui/src/lib/fixtures/canonical-run-p0.json`
- Read/verify: `scripts/generate-golden.py`

- [ ] **Step 1: Regenerate golden fixtures**

Run:

```bash
rtk uv run python scripts/generate-golden.py
```

Expected:

- Generator exits `0`.
- The only expected changes are `replay_canonical.tool_version` updates from `0.4.3` to `0.4.4` in:
  - `tests/contract/golden/run-p0-contract.json`
  - `ui/src/lib/fixtures/canonical-run-p0.json`

- [ ] **Step 2: Inspect golden diff**

Run:

```bash
rtk git diff -- tests/contract/golden/run-p0-contract.json ui/src/lib/fixtures/canonical-run-p0.json
```

Expected:

- Only the P0 fixture `tool_version` fields change to `0.4.4`.
- No timestamps, IDs, digests, paths, or unrelated generated fields change unexpectedly.

---

### Task 3: Run release consistency and contract verification

**Files:**
- Read/verify: `scripts/release/check-version-consistency.py`
- Read/verify: `tests/contract/test_golden.py`
- Read/verify: `ui/src/lib/__tests__/golden-contract.test.ts`

- [ ] **Step 1: Run release version consistency check**

Run:

```bash
rtk uv run python scripts/release/check-version-consistency.py
```

Expected:

- All non-dist checks pass.
- Dist wheel/sdist checks may still fail until release artifacts are built; if so, record that as expected pre-dist state.

- [ ] **Step 2: Run Python contract golden tests**

Run:

```bash
rtk uv run pytest tests/contract -q
```

Expected:

- All tests pass.
- `test_golden_generation_is_idempotent` no longer rewrites committed fixture bytes.

- [ ] **Step 3: Run UI golden contract tests if available through existing UI test command**

Run from `ui/`:

```bash
rtk npm run lint
```

If a local vitest command is available in the repo workflow, also run the targeted golden contract test:

```bash
rtk npx vitest run src/lib/__tests__/golden-contract.test.ts
```

Expected:

- UI schema still accepts the regenerated golden fixtures.
- No stripped-field or version drift regression appears.

---

### Task 4: Record verification and keep branch clean

**Files:**
- Verify: Git status
- Optional create after implementation: `docs/dev/log/YYYY-MM-DD-HHMM-dev-log-v0-4-4-release-consistency.md`

- [ ] **Step 1: Check final diff**

Run:

```bash
rtk git diff --stat
rtk git diff -- src/micro_eval/__init__.py README.md README.zh-CN.md ui/package-lock.json tests/contract/golden/run-p0-contract.json ui/src/lib/fixtures/canonical-run-p0.json
```

Expected:

- Diff is limited to the files listed in this plan.

- [ ] **Step 2: Check working tree status**

Run:

```bash
rtk git status --short --branch
```

Expected:

- Only intentional release consistency files are modified.

- [ ] **Step 3: Add dev log only after implementation if useful**

If the implementation uncovers additional release-process facts, create a concise dev log under `docs/dev/log/` with:

- Summary
- Context
- Changes
- Verification
- Risks and follow-ups

Do not create release evidence under `docs/releases/` until the actual release readiness pass is complete.

