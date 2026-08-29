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
- `scripts/release/public_projection.py`
- `scripts/release/public-projection.toml`
- `scripts/release/main.gitignore`
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
10. From clean `dev`, run the one-command local stage. It builds and verifies
    the deterministic public candidate without contacting a remote:
    ```bash
    scripts/release-to-main.sh stage dev main
    ```
    Stage invokes the complete release preflight itself; step 8 is still run
    before the dev commit so failures can be fixed before staging.
    The command classifies every tracked path through
    `scripts/release/public-projection.toml`, constructs `main` in an isolated
    worktree, tests/builds the candidate public tree, verifies wheel/sdist
    contents, and writes a local verified receipt under the Git common dir.
    Local `main` moves atomically only after every candidate gate passes; a
    failure leaves it unchanged and the command can be retried safely.
11. Review the printed verified `main` SHA and release evidence. The projection
    Module has already verified that `main` equals the public policy, generated
    `AGENTS.md`/`.gitignore` are exact, and private paths are absent.
12. Publish only as a separate, explicitly authorized action using the exact
    verified SHA:
    ```bash
    scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> dev main
    ```
    If an annotated release tag is also explicitly approved, publish it in the
    same atomic remote update so it must point to the verified commit:
    ```bash
    scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> \
      --tag vX.Y.Z dev main
    ```
    The publish command must reject missing, stale, or unverified receipts,
    reject a public remote that contains `dev`, and display `origin/main`, the
    exact SHA, and optional tag before executing. Never push `dev`, `--all`, or
    `--mirror` to the public remote.

## Hard gates

- Abort if not on `dev` before release preparation or publishing.
- Abort if version surfaces disagree.
- Abort if release evidence or dependency inventory is missing.
- Abort if trusted paths contain `create_subprocess_shell` or `shell=True`.
- Abort if `git diff --check`, `git diff --cached --check`, tests, build, or package build fail.
- Abort if any tracked path is unclassified, multiply classified, or forbidden in public output.
- Abort if wheel/sdist contains an entry outside the artifact allowlist.
- Abort without moving local `main` if any candidate test, build, or artifact verification fails.
- Abort if release publishing reports a dirty source tree or `main` differs from the deterministic public projection.
- Abort if `--push` was selected without explicit authorization; local-only is the default.
- Abort push if `--expected-sha` lacks a current verified receipt or differs from local `main`.
- Abort publish if the public remote contains `dev`, or if a requested tag is not the annotated `vX.Y.Z` tag for the same verified SHA.
- Treat a public repository as having no private branches. Keep `dev` local or
  on a separate private remote; public CI must not require a `dev` push.
- Never record secrets, credential paths, absolute local executable paths, home-directory paths, or environment dumps in release docs.

## Validation commands

Run at minimum for release changes:

```bash
scripts/release/check-version-consistency.py --version "$(cat VERSION)"
scripts/release/preflight-release.sh "$(cat VERSION)"
```

For release publishing:

```bash
scripts/release-to-main.sh stage dev main
# After explicit authorization, substitute the SHA printed above:
scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> dev main
```
