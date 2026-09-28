# Repository Agent Instructions

You are operating in the `micro-eval` repository. Before applying any
branch-sensitive rule, determine the actual current branch with
`git branch --show-current`; do not infer it from this file.

## Critical rules

- Always reply to the user in Simplified Chinese.
- In Simplified Chinese responses and documentation, keep `ticket` in English; do not translate it as “票”.
- Do not use TDD. Implement from specification and user path first, then verify.

## Branch model

- `dev` is the daily development branch and the only source branch for a release. Perform normal feature, fix, documentation, and release-preparation work on `dev`.
- `main` is a verified public release projection. It is not the daily development branch and must not contain private development state.
- Do not develop new features directly on `main`. If source changes are needed while on `main`, return to `dev` and make them there.
- Do not manually merge `dev` into `main`, and do not check out `main` in the active `dev` worktree merely to publish a release.
- If the current branch is neither `dev` nor `main`, treat it as non-publishable work: do not infer release authority, and return to a clean `dev` branch before release preparation or publication.

## Private dev Pull Request workflow

- `origin` is the public remote. It must never receive `dev`, `agent/*`, or
  `human/*` refs, nor any private development path.
- `private` is the private development remote. Once it is configured,
  `private/dev` is the daily source authority; non-emergency changes enter it
  only through a Pull Request from `agent/<slug>` or `human/<slug>`.
- Do not provision a private repository, add or push `private`, change branch
  protection, create a Pull Request, or merge one without the maintainer's
  separately explicit authorization. Do not use `--all`, `--mirror`, or
  force-push for either remote.
- Pull Requests must link their ticket and include scope, acceptance mapping,
  verification evidence, risk, and public-projection impact. Authors cannot
  approve their own work. Security, schema, release, breaking, and high-risk
  changes require an independent human approval.
- Emergency bypasses require a separate ticket and evidence in the next normal
  Pull Request. `main` remains exclusively managed by `release-to-main.sh`.

## Release model

- Release from `dev` to `main` only through `scripts/release-to-main.sh`.
- `scripts/release/public-projection.toml` is the only path-classification source of truth; every tracked path must be public, private, or generated, and unknown paths must abort release.
- Run the local-only stage from a clean `dev` worktree: `scripts/release-to-main.sh stage dev main`. Local `main` moves only after all candidate gates pass.
- Publish only as a separate action with explicit authorization and the exact verified SHA: `scripts/release-to-main.sh publish --expected-sha <SHA> dev main`.
- A public remote must never contain `dev`; never push `dev`, `--all`, or `--mirror`. An optional tag must be the annotated `vX.Y.Z` tag for the same verified SHA and be pushed atomically with `main`.
- Never bypass candidate-tree, generated-file, sensitive-path, wheel/sdist, or verified-receipt gates.

## Work tracking

- The Linear project `micro-eval` (team `GRO`) is the only Work Register.
  Before a non-trivial behavior, schema, security, release, or multi-file
  change, create one Linear issue (`GRO-<number>`) that carries the scope and
  acceptance criteria; keep the details only there. The contract is
  `docs/agents/issue-tracker.md` and the state vocabulary is
  `docs/agents/triage-labels.md`.
- Use a GitHub Issue (`GH-<number>`) only when public feedback or
  collaboration is genuinely needed.
- Before implementation starts, split an issue into sub-issues: one per
  independently deliverable, verifiable implementation step. The parent issue
  keeps the goal and acceptance criteria; each sub-issue carries one step and
  its own completion evidence.
- A one-file typo, formatting-only edit, or similarly trivial documentation
  correction may proceed without an issue. When uncertain, create the issue
  first.
- Resolve work by moving the issue to `Done` with completion evidence, and
  record user-visible facts in `CHANGELOG.md` or implementation evidence in a
  dev log.
- `.scratch/**` and dev logs are development-only records: `.scratch/` now
  holds the read-only pre-2026-09-05 ticket archive. Keep them tracked on
  `dev` and out of public projection; never use `main` for source development.
- The offline governance check validates the archived records and their
  projection classification. Run it once, immediately before committing:
  `uv run python scripts/check-work-governance.py`.


This file is generated into `main` from the development-only release
instruction template during release. On `dev`, edit that template and keep
this file synchronized with it. Do not hand-edit the generated `AGENTS.md` on
`main`.
