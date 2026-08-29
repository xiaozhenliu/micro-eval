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

## Release model

- Release from `dev` to `main` only through `scripts/release-to-main.sh`.
- `scripts/release/public-projection.toml` is the only path-classification source of truth; every tracked path must be public, private, or generated, and unknown paths must abort release.
- Run the local-only stage from a clean `dev` worktree: `scripts/release-to-main.sh stage dev main`. Local `main` moves only after all candidate gates pass.
- Publish only as a separate action with explicit authorization and the exact verified SHA: `scripts/release-to-main.sh publish --expected-sha <SHA> dev main`.
- A public remote must never contain `dev`; never push `dev`, `--all`, or `--mirror`. An optional tag must be the annotated `vX.Y.Z` tag for the same verified SHA and be pushed atomically with `main`.
- Never bypass candidate-tree, generated-file, sensitive-path, wheel/sdist, or verified-receipt gates.

## Work tracking

- On `dev`, `TODOS.md` is the only Work Register for unfinished work. Before a
  non-trivial behavior, schema, security, release, or multi-file change, add
  one `LOCAL-<EFFORT>-<NN>` ticket or `GH-<number>` Issue pointer there; keep
  the details only in that authority source.
- Local tickets are the default for internal work. Use a GitHub Issue only
  when public feedback or collaboration is genuinely needed. The ticket-first
  threshold and the separate `Triage`, `Executor`, and lifecycle `Status`
  fields are defined in `docs/agents/issue-tracker.md`.
- A one-file typo, formatting-only edit, or similarly trivial documentation
  correction may proceed without a ticket. When uncertain, create the ticket
  first.
- Resolve work with completion evidence, remove it from `TODOS.md`, and record
  user-visible facts in `CHANGELOG.md` or implementation evidence in a dev log.
- `.scratch/**`, `TODOS.md`, and dev logs are development-only records. Keep
  them tracked on `dev` and out of public projection; never use `main` for
  source development.

This file is generated into `main` from the development-only release
instruction template during release. On `dev`, edit that template and keep
this file synchronized with it. Do not hand-edit the generated `AGENTS.md` on
`main`.
