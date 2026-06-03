---
name: micro-eval-release
description: Use when preparing, validating, documenting, committing, tagging, or publishing a micro-eval release, including version bumps, changelog updates, dev logs, README updates, dependency inventory, release evidence, dev commits, and dev-to-main publishing.
---

# micro-eval Release

This project-level skill is the executable source for `micro-eval` release work. Do not reconstruct the release flow from project docs. Use the bundled scripts and assets in this skill.

## Bundled resources

Authoritative scripts live beside this file:

- `scripts/sync-version.py`
- `scripts/check-version-consistency.py`
- `scripts/generate-dependency-inventory.py`
- `scripts/preflight-release.sh`
- `scripts/release-to-main.sh`

Publish templates live in:

- `assets/templates/agents-publish-template.md`
- `assets/templates/claude-publish-template.md`

Repository-level `scripts/release/*.py`, `scripts/release/preflight-release.sh`, and `scripts/release-to-main.sh` are compatibility wrappers only.

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
   .codex/skills/micro-eval-release/scripts/sync-version.py X.Y.Z
   ```
5. Check version consistency:
   ```bash
   .codex/skills/micro-eval-release/scripts/check-version-consistency.py --version X.Y.Z
   ```
6. Update `CHANGELOG.md`, top-level `README.md`, release dev log, release evidence, and dependency inventory.
7. Generate dependency inventory:
   ```bash
   .codex/skills/micro-eval-release/scripts/generate-dependency-inventory.py --version X.Y.Z
   ```
8. Run preflight:
   ```bash
   .codex/skills/micro-eval-release/scripts/preflight-release.sh X.Y.Z
   ```
9. Commit release changes to `dev` with an English commit message.
10. From clean `dev`, publish through the compatibility entry required by `AGENTS.md`:
    ```bash
    scripts/release-to-main.sh dev main
    ```
    The wrapper delegates to this skill's `scripts/release-to-main.sh`.
11. Verify `main` excludes dev-only docs and generated publish templates match the skill assets.
12. Create a local annotated tag only if approved. Do not push unless explicitly approved.

## Hard gates

- Abort if not on `dev` before release preparation or publishing.
- Abort if version surfaces disagree.
- Abort if release evidence or dependency inventory is missing.
- Abort if trusted paths contain `create_subprocess_shell` or `shell=True`.
- Abort if `git diff --check`, `git diff --cached --check`, tests, build, or package build fail.
- Abort if release publishing reports a dirty source tree or `main` keeps dev-only docs.
- Never record secrets, credential paths, absolute local executable paths, home-directory paths, or environment dumps in release docs.

## Validation commands

Run at minimum for release changes:

```bash
.codex/skills/micro-eval-release/scripts/check-version-consistency.py --version "$(cat VERSION)"
.codex/skills/micro-eval-release/scripts/preflight-release.sh "$(cat VERSION)"
```

For release publishing:

```bash
scripts/release-to-main.sh dev main
if git ls-tree -r --name-only main | grep -E '^(docs/superpowers/|docs/_archive/|docs/references/|micro-eval-brd\.md|micro-eval-prd\.md$)'; then
  echo 'main contains dev-only release exclusions' >&2
  exit 1
fi
tmpdir=$(mktemp -d)
git show main:AGENTS.md > "$tmpdir/AGENTS.md"
git show main:CLAUDE.md > "$tmpdir/CLAUDE.md"
cmp "$tmpdir/AGENTS.md" .codex/skills/micro-eval-release/assets/templates/agents-publish-template.md
cmp "$tmpdir/CLAUDE.md" .codex/skills/micro-eval-release/assets/templates/claude-publish-template.md
rm -rf "$tmpdir"
```
