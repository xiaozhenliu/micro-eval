---
title: Release Backfill Record — v0.2.3 through v0.4.1
doc_type: release_evidence
status: active
created_at: 2026-07-02T14:05+08:00
updated_at: 2026-07-02T14:05+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - release
  - backfill
  - process-incident
related:
  - CHANGELOG.md
  - docs/releases/2026-07-02-v0.3.3-dependency-inventory.md
  - docs/releases/2026-07-02-v0.3.4-dependency-inventory.md
  - docs/releases/2026-07-02-v0.4.0-dependency-inventory.md
  - docs/engineering/release-process.md
---

# Release Backfill Record — v0.2.3 through v0.4.1

Release evidence, dependency inventories, and git tags stopped being produced
after v0.2.2 (2026-06-12). This record backfills what can be honestly
reconstructed, documents what cannot, and explains why the process broke.

## Why the release process broke (incident summary)

1. **2026-06-15, commit `e00e327`** ("Merge branch 'dev'", the v0.3.3
   projection): dev was merged into main. Per the release filter, the merge
   result excluded `.codex/` — which contained the executable release skill
   (`micro-eval-release`: SKILL.md, publish templates, and the authoritative
   scripts).
2. **Same day**: the `dev` branch was rebuilt on top of main's lineage
   (main's history became dev's first-parent chain; the old dev lineage
   survives only as `e00e327^2`). Commit `dbfa3ca` ("restore dev-only files
   and dev .gitignore after main merge") restored CLAUDE.md and other
   dev-only files but **missed `.codex/skills/micro-eval-release/`**.
3. `scripts/release/*.py` and `scripts/release/preflight-release.sh` survived
   on the new lineage only as 6–10 line compatibility wrappers delegating to
   the now-missing `.codex` path, so they were **broken from 2026-06-15 until
   2026-07-02**, when the full versions were restored from commit `eaa3da6`
   (the last commit carrying them). `scripts/release-to-main.sh` remained a
   real, working script throughout.
4. Consequence: every release after v0.2.2 shipped without release evidence,
   dependency inventory, or git tag, and v0.3.5 shipped without a `VERSION`
   bump (see anomalies below).

## Version → commit map

| Version | Date (CHANGELOG) | dev commit | main projection | Tag |
|---|---|---|---|---|
| v0.2.3–v0.2.10 | 2026-06-14 | `34c4b8e` … `97dde08` | none (internal iterations) | not created — see policy below |
| v0.3.0 | 2026-06-14 | `2e19ec5` | none | not created |
| v0.3.1 | 2026-06-15 | `69b3f7b` | none | not created |
| v0.3.2 | 2026-06-15 | `4fd51c1` | none | not created |
| v0.3.3 | 2026-06-15 | `4af8eda` | `e00e327` | **v0.3.3 (backfilled 2026-07-02)** |
| v0.3.4 | 2026-06-15 | `82162e0` | `06d8e98` (matches `origin/main`) | **v0.3.4 (backfilled 2026-07-02)** |
| v0.3.5 | 2026-06-15 | no VERSION bump exists | folded into v0.4.0 projection | not created |
| v0.4.0 | 2026-06-19 | `0ce87b3` | `8218ff3` (local main only) | **v0.4.0 (backfilled 2026-07-02)** |
| v0.4.1 | 2026-06-20 | `44e82bb` | not yet projected | deferred (decision 2026-07-02) |

Note: `06d8e98` was the last of three v0.3.4 merges made on 2026-06-15
(`c010f18` 15:44, `19d10bc` 15:54, `06d8e98` 16:00); it is the one
`origin/main` points at and is therefore the canonical projection.

## Tagging policy for this backfill

- Tags were created **only on main-lineage release merges** (v0.3.3, v0.3.4,
  v0.4.0). They are annotated, local-only, and must not be pushed without
  explicit approval.
- Versions with no main projection (v0.2.3–v0.2.10, v0.3.0–v0.3.2, v0.3.5)
  are **deliberately not tagged**: the only commits they could point at are
  dev commits, and pushing such tags would publish dev-only private documents
  (CLAUDE.md, BRD, PRD) to the public remote. This table is their permanent
  record instead.

## Anomalies found during backfill

- **v0.3.5 has no `VERSION` bump anywhere in history** (`git log --all
  -S"0.3.5" -- VERSION` is empty). It exists only as a CHANGELOG entry;
  `VERSION` went 0.3.4 → 0.4.0 directly. Treat v0.3.5 as a
  CHANGELOG-documented docs milestone, not an installable version.
- **`origin/main` is at `06d8e98` (v0.3.4)**. v0.4.0 exists only on local
  main and has never been pushed. Remote tags end at v0.2.2.

## Backfilled artifacts and their limits

- Dependency inventories for v0.3.3 / v0.3.4 / v0.4.0 were generated on
  2026-07-02 from each tag's tree in a temporary worktree, using the full
  inventory script recovered from `eaa3da6` (the scripts inside the tags
  themselves are broken wrappers). Package and lockfile data reflect the
  tagged commits; toolchain versions reflect the backfill machine, as stated
  in each file's header.
- **Release evidence (test runs, build hashes, review status) is not
  backfilled.** Test executions from release day cannot be honestly
  reproduced after the fact; CI history and CHANGELOG "Verification" sections
  are the closest surviving evidence. Backfilling fake evidence would defeat
  the purpose of evidence.

## Follow-ups

- v0.4.1 dev→main release: deferred by user decision (2026-07-02).
- Restoration of the release skill (SKILL.md + templates from `e00e327^2`):
  pending user decision; the working scripts under `scripts/release/` were
  already restored on 2026-07-02.
- Pushing local main (v0.4.0) and the three backfilled tags to origin:
  requires explicit approval.
