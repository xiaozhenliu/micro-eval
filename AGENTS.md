# Main Branch Agent Instructions

You are operating on the `main` release branch of `micro-eval`.

Critical rules:

- Always reply to the user in Simplified Chinese.
- Do not use TDD. Implement from specification and user path first, then verify.
- Do not develop new features directly on `main`.
- Do not manually merge `dev` into `main`.
- Release from `dev` to `main` only through `scripts/release-to-main.sh`.
- Keep dev-only files out of `main`:
  - `docs/superpowers/`
  - `docs/_archive/`
  - `docs/references/`
  - `micro-eval-brd.md`
  - `micro-eval-prd.md`
- If source changes are needed, switch back to `dev` and make changes there.

This file is generated from `scripts/release/templates/agents-publish-template.md` during release.
Do not hand-edit the generated `AGENTS.md` on `main`; edit the template on `dev` instead.
