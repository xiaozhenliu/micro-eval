---
name: micro-eval-release
description: Use when preparing, validating, documenting, committing, tagging, or publishing a micro-eval release, including version bumps, changelog updates, dev logs, README updates, dependency inventory, release evidence, dev commits, and dev-to-main publishing.
---

# micro-eval Release

This project-level skill is the checklist for `micro-eval` release work. Do not reconstruct the release flow from memory. Follow the workflow below exactly.

## Resources

All release scripts live in the repository (single copy, tracked on both `dev` and `main`):

- `scripts/release/sync-version.py`
- `scripts/release/check-version-consistency.py`
- `scripts/release/generate-dependency-inventory.py`
- `scripts/release/preflight-release.sh`
- `scripts/release-to-main.sh`

This skill does not carry its own script copies. History note: it used to, and when this skill file was lost in the 2026-06-15 branch rebuild, the repository copies turned out to be non-functional stubs — see `docs/releases/2026-07-02-release-backfill-record.md`. Keeping one real copy in `scripts/` prevents that failure mode.

The publish template lives beside this file:

- `assets/templates/agents-publish-template.md` — projected to `main` as `AGENTS.md`.

`CLAUDE.md` is dev-only (a `@AGENTS.md` stub matched by the `*CLAUDE.md`
exclusion) and is intentionally NOT projected to `main`; `main` has never
tracked a root `CLAUDE.md`. `main` tooling reads `AGENTS.md` directly.

The human-readable reference is `docs/engineering/release-process.md`; if it and this file disagree, fix both in the same change.

## Required reads

Before release work, read:

1. `AGENTS.md`
2. this `SKILL.md`
3. `docs/DEVELOPMENT.md` for current local command context
4. `docs/documentation-standard.md` before writing release docs/dev logs
5. `docs/engineering/security-guidelines.md`

If code changes touch subprocess, env, artifacts, workspace, report, or UI/API exposure, also read the specific security guide linked from `security-guidelines.md`.

## Workflow

1. Confirm current branch is `dev`; never manually publish by checking out `main` in the active worktree.
2. Identify target version and release scope.
3. Treat `VERSION` as the single human-edited version source.
4. Sync current version surfaces:
   ```bash
   scripts/release/sync-version.py X.Y.Z
   ```
5. Check version consistency:
   ```bash
   scripts/release/check-version-consistency.py --version X.Y.Z
   ```
6. Update `CHANGELOG.md`, top-level `README.md`, release dev log, release evidence, and dependency inventory.
7. Generate dependency inventory:
   ```bash
   scripts/release/generate-dependency-inventory.py --version X.Y.Z
   ```
8. Run preflight:
   ```bash
   scripts/release/preflight-release.sh X.Y.Z
   ```
9. Commit release changes to `dev` with an English commit message.
10. From clean `dev`, publish through the compatibility entry required by `AGENTS.md`:
    ```bash
    scripts/release-to-main.sh dev main
    ```
    This is the only supported way to publish `main`.
11. Verify `main` excludes dev-only release exclusions, that `main` `AGENTS.md` matches the skill asset template, and that no root `CLAUDE.md` is tracked on `main`.
12. Create a local annotated tag only if approved. Do not push unless explicitly approved.

## Hard gates

- Abort if not on `dev` before release preparation or publishing.
- Abort if version surfaces disagree.
- Abort if release evidence or dependency inventory is missing.
- Abort if trusted paths contain `create_subprocess_shell` or `shell=True`.
- Abort if `git diff --check`, `git diff --cached --check`, tests, build, or package build fail.
- Abort if release publishing reports a dirty source tree or `main` keeps dev-only release exclusions.
- Never record secrets, credential paths, absolute local executable paths, home-directory paths, or environment dumps in release docs.

## Validation commands

Run at minimum for release changes:

```bash
scripts/release/check-version-consistency.py --version "$(cat VERSION)"
scripts/release/preflight-release.sh "$(cat VERSION)"
```

For release publishing:

```bash
scripts/release-to-main.sh dev main
if git ls-tree -r --name-only main | grep -E '^(\.codex/|\.understand-anything/|docs/dev/|docs/superpowers/|docs/_archive/|docs/references/|docs/bug_reports/|micro-eval-brd\.md|micro-eval-prd\.md$)'; then
  echo 'main contains dev-only release exclusions' >&2
  exit 1
fi
tmpdir=$(mktemp -d)
git show main:AGENTS.md > "$tmpdir/AGENTS.md"
cmp "$tmpdir/AGENTS.md" .codex/skills/micro-eval-release/assets/templates/agents-publish-template.md
# CLAUDE.md is dev-only (a @AGENTS.md stub matched by the *CLAUDE.md exclusion)
# and must stay absent from main; main tooling reads AGENTS.md directly.
if git ls-tree -r --name-only main | grep -qx 'CLAUDE.md'; then
  echo 'unexpected root CLAUDE.md tracked on main' >&2
  exit 1
fi
rm -rf "$tmpdir"
```
