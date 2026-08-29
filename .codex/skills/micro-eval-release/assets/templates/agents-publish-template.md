# Main Branch Agent Instructions

You are operating on the `main` release branch of `micro-eval`.

Critical rules:

- Always reply to the user in Simplified Chinese.
- In Simplified Chinese responses and documentation, keep `ticket` in English; do not translate it as “票”.
- Do not use TDD. Implement from specification and user path first, then verify.
- Do not develop new features directly on `main`.
- Do not manually merge `dev` into `main`.
- Release from `dev` to `main` only through `scripts/release-to-main.sh`.
- `scripts/release/public-projection.toml` is the only path-classification source of truth; every tracked path must be public, private, or generated, and unknown paths must abort release.
- One-command stage is local-only: `scripts/release-to-main.sh stage dev main`. Local `main` moves only after all candidate gates pass.
- Publish only as a separate action with explicit authorization and the exact verified SHA: `scripts/release-to-main.sh publish --expected-sha <SHA> dev main`.
- A public remote must never contain `dev`; never push `dev`, `--all`, or `--mirror`. An optional tag must be the annotated `vX.Y.Z` tag for the same verified SHA and be pushed atomically with `main`.
- Never bypass candidate-tree, generated-file, sensitive-path, wheel/sdist, or verified-receipt gates.
- If source changes are needed, switch back to `dev` and make changes there.

This file is generated from `.codex/skills/micro-eval-release/assets/templates/agents-publish-template.md` during release.
Do not hand-edit the generated `AGENTS.md` on `main`; edit the skill asset template on `dev` instead.
