---
title: Development Log - GRO-172 template_id Path Traversal (audit H1)
doc_type: dev_log
status: active
created_at: 2026-07-07T21:57+08:00
updated_at: 2026-07-07T21:57+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - security
  - path-traversal
  - GRO-172
related:
  - docs/security/2026-07-07-security-audit.md
  - docs/engineering/security-development-guidelines.md
  - docs/engineering/security-service-guidelines.md
---

# Development Log - GRO-172 template_id Path Traversal (audit H1)

## Summary

Closed the single HIGH finding of the 2026-07-07 audit: `template_id` supplied to
`POST /api/workspaces` (and the CLI `workspace create` / `template …` commands)
flowed into a filesystem path with no charset validation. Under pathlib,
`Path(".../templates") / "/etc"` collapses to `/etc` and `"../.."` walks up, so a
member (or, combined with M1's missing Host allowlist, a remote page via DNS
rebinding) could copy any server-readable directory into their workspace and read
it out through a self-controlled `eval.yaml` + agent — arbitrary file read as the
**server process user**, crossing the member's local OS permission boundary.

## Root cause

`WorkspaceManager.create()` and `TemplateRegistry.get/create/update/delete` built
`templates_dir / template_id` and only checked `.exists()`. The project already had
the correct pattern (`WorkspaceManager.resolve_path`: regex + `resolve()` prefix
check) for workspace ids, but the template branch bypassed it. The UI's
`safeTemplateId` regex existed but (a) was never called by the vulnerable route and
(b) still admitted pure-dot names (`.`/`..`).

## What changed

- **`src/micro_eval/server/template.py`** — new module-level `_TEMPLATE_ID_RE`
  (`(?!\.+\Z)[A-Za-z0-9._-]{1,64}\Z`) and `resolve_template_dir(templates_dir,
  template_id)` helper: charset allowlist + `resolve()` + `templates_root + os.sep`
  prefix check, mirroring `resolve_path`. Returns a path that may not exist yet;
  callers decide whether non-existence is an error. `get/create/update/delete` all
  route through it.
- **`src/micro_eval/server/workspace.py`** — `create()` template branch now calls
  `resolve_template_dir` instead of raw `data_root / "templates" / template_id`.
- **`ui/src/lib/server-validation.ts`** — extracted shared `TEMPLATE_ID_RE`
  (`/^(?!\.+$)[a-zA-Z0-9._-]{1,64}$/`), tightened `safeTemplateId` to use it (now
  rejects `.`/`..`).
- **`ui/src/app/api/workspaces/route.ts`** — schema field is now
  `z.string().regex(TEMPLATE_ID_RE, "invalid template_id")`.
- Regression tests: `tests/unit/server/test_template.py` (direct `resolve_template_dir`
  + get/create/update/delete traversal rejection), `tests/unit/server/test_workspace.py`
  (create rejects traversal, external dir never copied), and new
  `ui/src/lib/__tests__/template-id-validation.test.ts`.

## Key design decisions

1. **Python is the authoritative boundary.** Both the CLI and the UI reach these
   classes, so validation lives in `template.py`; the UI regex is defense-in-depth,
   not the only gate.
2. **`\Z` not `$` in the Python regex.** Python's `$` also matches just before a
   trailing `\n`, so `re.match(r"...$", "tpl\n")` would succeed. `\Z` anchors the true
   end. JS `$` (no `m` flag) already anchors end-of-input, so the mirror regex is safe.
3. **Charset excludes `/`, lookahead excludes pure dots.** Together these reject
   `/etc`, `../../x`, `.`, `..`; the `resolve()` + prefix check is belt-and-suspenders
   (also catches a valid-name symlink pointing outside the root).
4. **Single shared regex per side.** One `TEMPLATE_ID_RE` const in TS, one
   `_TEMPLATE_ID_RE` in Python — no divergent copies to drift.

## Verification

- `uv run pytest` — 595 passed (was 517 baseline + new assertions).
- `ui`: `npx vitest run` — 91 passed; `tsc --noEmit` clean; `npm run lint` clean.
- `ruff check` on changed files clean (pre-existing unused `import json` in
  `workspace.py` left untouched — out of scope).
- **codex mcp review (gpt-5.5, xhigh): APPROVE** — no bypass found across absolute
  paths, `..`, slashes/backslashes, unicode, trailing newline, sibling prefix
  collision, or symlink escape; coverage of all entry points confirmed.

## Security notes (per security-development-guidelines.md checklist)

- **Secrets redaction**: not applicable — no new evidence/artifact/UI text path; change
  is input validation only.
- **Workspace boundary**: this *is* the fix — the template copy source is now confined
  to `templates_dir` via allowlist + resolve prefix check; the external-dir-copy
  regression test proves nothing lands under `workspaces/`.
- **Shell interpolation**: unchanged — the UI still uses `execFileSync(bin, [...argv])`;
  `template_id` is an argv element, never interpolated into a shell string.
