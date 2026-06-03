---
name: micro-eval-release
description: Use when preparing, validating, documenting, committing, tagging, or publishing a micro-eval release, including version bumps, changelog updates, dev logs, README updates, dependency inventory, release evidence, dev commits, and dev-to-main publishing.
---

# micro-eval Release

Use this skill for `micro-eval` release work. Keep `AGENTS.md` authoritative for hard constraints and `docs/engineering/release-process.md` authoritative for detailed process.

## Required reads

Before release work, read:

1. `AGENTS.md`
2. `docs/engineering/release-process.md`
3. `docs/DEVELOPMENT.md`
4. `docs/documentation-standard.md`
5. `docs/engineering/security-guidelines.md`

If code changes touch subprocess, env, artifacts, workspace, report, or UI/API exposure, also read the specific security guide linked from `security-guidelines.md`.

## Workflow

1. Confirm current branch is `dev`; never manually publish by checking out `main` in the active worktree.
2. Identify target version and release scope.
3. Treat `VERSION` as the single human-edited version source.
4. Sync version surfaces with `scripts/release/sync-version.py X.Y.Z`.
5. Check consistency with `scripts/release/check-version-consistency.py --version X.Y.Z`.
6. Update `CHANGELOG.md`, top-level `README.md`, release dev log, release evidence, and dependency inventory.
7. Generate dependency inventory with `scripts/release/generate-dependency-inventory.py --version X.Y.Z`.
8. Run the release validation matrix from `docs/engineering/release-process.md`.
9. Commit release changes to `dev` with an English commit message.
10. From clean `dev`, publish with `scripts/release-to-main.sh dev main`.
11. Verify `main` excludes dev-only docs and generated publish templates match.
12. Create a local annotated tag only if approved. Do not push unless explicitly approved.

## Hard gates

- Abort if version surfaces disagree.
- Abort if release evidence or dependency inventory is missing.
- Abort if trusted paths contain `create_subprocess_shell` or `shell=True`.
- Abort if `git diff --check`, tests, build, or package build fail.
- Abort if `scripts/release-to-main.sh` reports a dirty source tree or `main` keeps dev-only docs.
- Never record secrets, credential paths, or environment dumps in release docs.

## Validation commands

Run at minimum for release changes:

```bash
python scripts/release/check-version-consistency.py --version "$(cat VERSION)"
uv run python -m compileall src/micro_eval tests
uv run pytest -q
(cd ui && npm run lint && npm run build)
uv build
git diff --check
git diff --cached --check
if grep -RInE 'create_subprocess_shell|shell=True' src tests ui examples; then
  echo 'Forbidden shell subprocess pattern found' >&2
  exit 1
fi
```

For release publishing:

```bash
scripts/release-to-main.sh dev main
test -z "$(git ls-files 'docs/superpowers/*' 'docs/_archive/*' 'docs/references/*')"
```
