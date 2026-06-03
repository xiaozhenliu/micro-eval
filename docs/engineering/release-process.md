---
title: micro-eval Release Process
doc_type: reference
status: active
created_at: 2026-06-03T13:09+08:00
updated_at: 2026-06-03T13:55+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - engineering
  - release
  - versioning
related:
  - AGENTS.md
  - CHANGELOG.md
  - VERSION
  - docs/DEVELOPMENT.md
  - docs/documentation-standard.md
  - docs/engineering/security-guidelines.md
  - .codex/skills/micro-eval-release/SKILL.md
  - scripts/release-to-main.sh
---

# micro-eval Release Process

This document is a human-readable release reference. The executable release workflow is the project-level skill `.codex/skills/micro-eval-release/SKILL.md` plus its bundled `scripts/` and `assets/templates/`. Repository `scripts/release/*` and `scripts/release-to-main.sh` are compatibility wrappers.

## Goals

- Keep release work repeatable and auditable.
- Keep `VERSION`, package metadata, runtime metadata, UI package metadata, and run evidence aligned.
- Keep executable release automation inside `.codex/skills/micro-eval-release/`.
- Record release evidence and dependency inventory before publishing.
- Publish `main` only through the existing projection script from a clean `dev` checkout.
- Avoid leaking secrets or runtime artifacts into release documentation or commits.

## Release boundaries

- Daily development happens on `dev`.
- Do not manually switch the current worktree to `main` for publishing.
- Publish to `main` only with:

```bash
scripts/release-to-main.sh dev main
```

- `main` must not track:
  - `docs/superpowers/`
  - `docs/_archive/`
  - `docs/references/`
  - `docs/bug_reports/`
  - `micro-eval-brd.md`
  - `micro-eval-prd.md`
- `main` `AGENTS.md` and `CLAUDE.md` must be generated from `.codex/skills/micro-eval-release/assets/templates/`.

## Version source strategy

`VERSION` is the single human-edited release version source.

The Python package should read its build version from `VERSION` through Hatch dynamic version metadata:

```toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "VERSION"
pattern = "^(?P<version>.+)$"
```

The release workflow must ensure these current-version surfaces agree:

- `VERSION`
- built Python package metadata and dist artifact names
- Python runtime `micro_eval.__version__`
- `ReplayCanonical.tool_version`
- top-level `README.md` current version
- `ui/package.json`
- `ui/package-lock.json` root package metadata
- shared contract fixtures that include current `tool_version`

Historical release references in `CHANGELOG.md`, dev logs, archived docs, and specs must not be bulk-replaced. They describe past states.

## Required release inputs

Before preparing a release, identify:

- Target version, following SemVer.
- Release type: patch, minor, major, or prerelease.
- User-visible changes for `CHANGELOG.md`.
- Verification scope and any known risks.
- Whether to create a local annotated tag.
- Whether pushing branches/tags is allowed. Default: no push unless explicitly confirmed.

## Version bump workflow

1. Run a preflight version audit:

```bash
.codex/skills/micro-eval-release/scripts/check-version-consistency.py --version "$(cat VERSION)"
```

2. Sync a new version when needed:

```bash
.codex/skills/micro-eval-release/scripts/sync-version.py X.Y.Z
```

3. Re-run the consistency check.
4. Build the package and verify dist artifact names include the target version.
5. Verify a run plan writes `ReplayCanonical.tool_version` equal to the target version.

## Changelog workflow

Use Keep a Changelog style sections:

- `Added`
- `Changed`
- `Fixed`
- `Security`
- `Verification`
- `Known Gaps`

Only record user-facing or release-facing changes. Do not use `CHANGELOG.md` as an implementation diary.

## Dev log workflow

Release preparation or release process changes must write a development log under:

```text
docs/dev/log/YYYY-MM-DD-HHMM-dev-log-<topic>.md
```

The file name must include `dev-log`, and the document must follow `docs/documentation-standard.md` metadata rules.

## README workflow

Before publishing, check that `README.md` reflects:

- Current version.
- Install/source-checkout path.
- Current CLI commands.
- Ready-to-run example entry when applicable.
- UI and wheel/source caveats when applicable.

Keep detailed release mechanics in this document, not in the README.

## Dependency inventory workflow

Each release should generate a human-readable and machine-readable dependency inventory under `docs/releases/`:

```text
docs/releases/YYYY-MM-DD-vX.Y.Z-dependency-inventory.md
docs/releases/YYYY-MM-DD-vX.Y.Z-dependency-inventory.json
```

The inventory should include:

- Python runtime version.
- `uv` version.
- Python package metadata from `pyproject.toml`.
- Runtime dependencies, optional dependencies, dependency groups, and resolved `uv.lock` package names/versions.
- Node and npm versions when available.
- UI `package.json` dependencies/devDependencies.
- UI `package-lock.json` root metadata and resolved package names/versions.
- External agent CLI prerequisites for examples, recorded as best-effort tool availability/version checks without reading secrets.

Do not record environment variables, tokens, account identifiers, absolute executable paths, home-directory paths, or local credential paths.

## Release evidence workflow

Each release should write:

```text
docs/releases/YYYY-MM-DD-vX.Y.Z-release-evidence.md
```

The release evidence should include:

- Version and date.
- Source branch and target branch.
- Dependency inventory links.
- Build artifact names and SHA256 hashes.
- Validation commands and results.
- Code review / architecture review status, when performed.
- UltraQA or adversarial smoke status, when performed.
- Known caveats.
- Main projection verification after `scripts/release-to-main.sh dev main`.

## Preflight validation matrix

Run the release checks appropriate to the changed files. For release work, the default gate is:

```bash
.codex/skills/micro-eval-release/scripts/check-version-consistency.py --version "$(cat VERSION)"
.codex/skills/micro-eval-release/scripts/preflight-release.sh "$(cat VERSION)"
```

Security-oriented greps must check that trusted paths do not introduce shell subprocess execution:

```bash
if grep -RInE 'create_subprocess_shell|shell=True' src tests ui examples; then
  echo 'Forbidden shell subprocess pattern found' >&2
  exit 1
fi
```

Browser storage greps are review signals, not unconditional failures; inspect any hits against the current product security rules.

## Commit to dev

Before committing:

1. Confirm current branch is `dev`.
2. Confirm no unwanted runtime artifacts are staged or untracked.
3. Confirm release evidence and dependency inventory exist.
4. Run the validation matrix.
5. Commit with an English message, for example:

```bash
git commit -m "Prepare vX.Y.Z release"
```

## Publish dev to main

From a clean `dev` working tree:

```bash
scripts/release-to-main.sh dev main
```

After publishing, verify:

```bash
test -z "$(git ls-files 'docs/superpowers/*' 'docs/_archive/*' 'docs/references/*' 'docs/bug_reports/*')"
```

Also confirm the release commit exists on `main` and `AGENTS.md` / `CLAUDE.md` match the skill asset templates.

## Local tag workflow

If the user approves tagging, create an annotated local tag after `dev` and `main` are aligned for the release:

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
```

Do not push branches or tags unless the user explicitly confirms pushing.

## Abort conditions

Abort the release and fix the cause when any of these are true:

- Version surfaces disagree.
- Build artifact version disagrees with `VERSION`.
- Release evidence or dependency inventory is missing.
- Security grep finds shell subprocess execution in trusted paths.
- Tests or build fail.
- `dev` working tree is dirty before `scripts/release-to-main.sh`.
- `main` projection still tracks dev-only docs.
- Secrets, credential paths, or runtime artifacts are present in release docs or staged changes.
