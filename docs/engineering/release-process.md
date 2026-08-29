---
title: micro-eval Release Process
doc_type: reference
status: active
created_at: 2026-06-03T13:09+08:00
updated_at: 2026-08-29T12:39+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - engineering
  - release
  - versioning
related:
  - AGENTS.md
  - docs/agents/issue-tracker.md
  - CHANGELOG.md
  - VERSION
  - docs/DEVELOPMENT.md
  - docs/documentation-standard.md
  - docs/engineering/security-guidelines.md
  - docs/releases/2026-07-02-release-backfill-record.md
  - scripts/release-to-main.sh
---

# micro-eval Release Process

This document is the human-readable release reference. The release scripts live in repository `scripts/release/*` and `scripts/release-to-main.sh` (single copy, tracked on both branches). The development environment also provides the executable release checklist skill; if that skill and this document disagree, fix both in the same change. Public release consumers should use the repository scripts and this reference, which do not depend on private development records.

## Goals

- Keep release work repeatable and auditable.
- Keep `VERSION`, package metadata, runtime metadata, UI package metadata, and run evidence aligned.
- Keep executable release automation inside `scripts/release/` and `scripts/release-to-main.sh`.
- Record release evidence and dependency inventory before publishing.
- Publish `main` only through the existing projection script from a clean `dev` checkout.
- Make `scripts/release/public-projection.toml` the single path-classification source of truth.
- Keep local projection as the default; require a separate verified-SHA push action before updating `origin/main`.
- Keep the public remote free of `dev`; public repositories have no private branches.
- Move local `main` only after every candidate test, build, and artifact gate passes.
- Avoid leaking secrets or runtime artifacts into release documentation or commits.

## Release boundaries

- Daily development happens on `dev`.
- Keep `dev` local or on a separate private remote. A branch inside a public
  repository is public even when it is not the default branch.
- Public GitHub CI runs on projected `main` and public pull requests; it does
  not require pushing private `dev` to the public repository.
- Do not manually switch the current worktree to `main` for publishing.
- Stage local `main` only with the release script. This one-command stage is
  local-only and never contacts a remote:

```bash
scripts/release-to-main.sh stage dev main
```

The equivalent explicit spelling is:

```bash
scripts/release-to-main.sh --local-only dev main
```

`--no-push` is an alias for `--local-only`. Local projection prints a verified
full SHA. Only after explicit authorization may that exact SHA be published in
a separate action:

```bash
scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> dev main
```

The publish action rejects missing, unverified, stale, abbreviated, or
non-`main` SHAs, and it aborts if the public remote contains `dev`. It displays
`origin/main` and the exact commit before running Git.

If both `main` and the release tag are explicitly approved, publish them in one
atomic remote update:

```bash
scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> \
  --tag vX.Y.Z dev main
```

The tag must be annotated, must equal `v` plus the receipt version, and must
point to the same verified commit as `main`. Never push `dev`, `--all`, or
`--mirror` to the public remote.

## Public projection policy

`scripts/release/public-projection.toml` classifies every tracked source path:

- `public`: restored from the committed `dev` SHA into the candidate tree;
- `private`: retained on `dev` and never restored into `main`;
- `generated`: written from an explicit source/target mapping.

A path matching zero or multiple classes aborts release. Known-sensitive paths
and private-key markers are additional deny checks, not the publication source
of truth. The projection implementation lives in
`scripts/release/public_projection.py` and is exercised through the same
interface used by the release script and tests.

The Module constructs the candidate from an empty index in an isolated worktree,
so an old leak already present on `main` disappears unless the current public
policy restores it. It generates `AGENTS.md` from the release Skill asset and
`.gitignore` from `scripts/release/main.gitignore`; both are verified as part of
the exact candidate tree rather than by duplicated post-release path lists.

Candidate construction writes a `staged` local receipt but does not move
`main`. After candidate Python/UI tests, builds, sensitive-path checks, and
wheel/sdist validation pass, verification updates local `main` with an atomic
compare-and-swap and marks the receipt `verified`. A failed candidate leaves
`main` unchanged, so the stage can be retried after fixing the cause.

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
- Whether to atomically publish an annotated `vX.Y.Z` tag for the verified SHA.
- Whether pushing branches/tags is allowed. Default: no push unless explicitly confirmed.

## Version bump workflow

1. Run a preflight version audit:

```bash
scripts/release/check-version-consistency.py --version "$(cat VERSION)"
```

2. Sync a new version when needed:

```bash
scripts/release/sync-version.py X.Y.Z
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
- Main projection verification after `scripts/release-to-main.sh stage dev main`.

## Preflight validation matrix

Run the release checks appropriate to the changed files. For release work, the default gate is:

```bash
scripts/release/check-version-consistency.py --version "$(cat VERSION)"
scripts/release/preflight-release.sh "$(cat VERSION)"
```

Preflight classifies the current worktree, builds wheel/sdist from explicit
Hatch inputs, and verifies every archive entry against the artifact allowlist.
Unknown, absolute, traversing, or linked archive entries fail the release.

Security-oriented greps must check that trusted paths do not introduce shell subprocess execution:

```bash
if grep -RInE 'create_subprocess_shell|shell=True' --exclude='test_execution_contract.py' src tests ui/src examples; then
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

## Project dev to main

From a clean `dev` working tree, perform the one-command local stage:

```bash
scripts/release-to-main.sh stage dev main
```

Use `scripts/release-to-main.sh --help` to inspect the behavior before running
it. The stage never switches the active `dev` worktree or contacts a remote. It
first invokes the complete release preflight, constructs a candidate in an
isolated worktree, reruns Python/UI gates against the public tree, builds
wheel/sdist from that tree, verifies their contents, then atomically moves local
`main` and stores a verified receipt under the Git common directory. Any failed
gate leaves local `main` unchanged.

Review the printed full SHA. If and only if the user authorizes updating
`origin/main`, execute the separate publish action with that exact value:

```bash
scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> dev main
```

The command rechecks that local `main` equals the SHA, the receipt is `verified`,
its policy digest still matches, and public `origin` does not contain `dev`. It
then announces `Push target: origin/main` and `Verified commit: <SHA>` before
pushing only `<SHA>:refs/heads/main`. Authorization to publish `main` does not
authorize a tag unless `--tag vX.Y.Z` is also explicitly present.

## Atomic tag workflow

Do not run an unqualified `git tag` while the active worktree remains on `dev`;
that could tag the private development commit. If the user explicitly approves
both the public branch and tag, use the verified publish interface:

```bash
scripts/release-to-main.sh publish --expected-sha <FULL_VERIFIED_SHA> \
  --tag vX.Y.Z dev main
```

The Module creates or validates an annotated tag for the exact verified SHA and
uses `git push --atomic` so remote `main` and the tag update together or neither
updates.

## Abort conditions

Abort the release and fix the cause when any of these are true:

- Version surfaces disagree.
- Build artifact version disagrees with `VERSION`.
- Release evidence or dependency inventory is missing.
- Security grep finds shell subprocess execution in trusted paths.
- Tests or build fail.
- A candidate gate fails; local `main` must remain at its previous SHA.
- `dev` working tree is dirty before `scripts/release-to-main.sh`.
- `main` projection still tracks dev-only docs.
- A tracked path is unknown, multiply classified, or forbidden in public output.
- A wheel/sdist entry is outside the artifact allowlist.
- The local `main` tree differs from the policy-derived candidate tree.
- The expected push SHA lacks a current `verified` receipt.
- The public remote contains `dev`, or a requested tag is not the annotated
  version tag for the same verified SHA.
- `--push` was selected without explicit authorization; use the default local-only mode.
- Secrets, credential paths, or runtime artifacts are present in release docs or staged changes.
