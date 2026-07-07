---
title: Development Log - GRO-173 Host Header Allowlist (audit M1, DNS rebinding)
doc_type: dev_log
status: active
created_at: 2026-07-07T22:29+08:00
updated_at: 2026-07-07T22:29+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - security
  - csrf
  - dns-rebinding
  - GRO-173
related:
  - docs/security/2026-07-07-security-audit.md
  - docs/engineering/security-service-guidelines.md
---

# Development Log - GRO-173 Host Header Allowlist (audit M1)

## Summary

Implemented CSRF-protection layer 4 (anti DNS-rebinding), the one layer of the
Team Server's four-layer CSRF model that had never been built. Without it, a
successful DNS rebind makes an attacker's web page same-origin with
`micro-eval serve`, letting it forge the `X-Micro-Eval-Member` header and defeat
layers 1 (Content-Type) and 2 (custom header). Carried over from 2026-06-20 F1
(was P1), zero prior progress.

## What changed

- **`ui/src/proxy.ts` (new)** — Host allowlist enforcement. Passes through when
  `MICRO_EVAL_SERVER_MODE !== "true"` (local `micro-eval ui` mode is single-user
  and out of scope per the security service guidelines appendix); otherwise
  compares the request `Host` header against an allowlist and returns 400 on
  mismatch. The allowlist = loopback defaults built from the bound port
  (`localhost:port`, `127.0.0.1:port`, `[::1]:port`) plus any `allowed_hosts`
  from `server.json`.
- **`src/micro_eval/cli/serve.py`** — injects `MICRO_EVAL_BIND_PORT` and
  `MICRO_EVAL_ALLOWED_HOSTS` (comma-joined `config.allowed_hosts`) into the
  `next start` env; prints a startup hint when `allowed_hosts` is empty.
- **`ui/src/__tests__/proxy.test.ts` (new)** — 15 vitest cases including the
  spec §14.6 acceptance names (rejects-unknown, dns-rebinding) plus hardening
  (trailing dot, `X-Forwarded-Host` ignored, messy allowlist env).

## Key design decisions

1. **Next.js 16: `middleware` → `proxy`.** Per `ui/AGENTS.md` ("This is NOT the
   Next.js you know"), I read the bundled docs first
   (`node_modules/next/dist/docs/.../file-conventions/proxy.md`): Next.js 16
   deprecated the `middleware` file convention and renamed it to `proxy` (file
   `src/proxy.ts`, exported function `proxy`, default Node.js runtime so
   `process.env` is available). Writing `middleware.ts` would have been silently
   ignored — a build was run to confirm `ƒ Proxy (Middleware)` appears in the
   route table, proving the file is actually wired.
2. **Secure by default = loopback only.** With `allowed_hosts` empty (the
   default), only loopback is accepted; team members reaching the server over
   LAN by hostname/IP get a 400 until an admin adds their hostname to
   `allowed_hosts`. You cannot defend against rebinding without knowing your
   legitimate hostnames, so the admin must declare them. `serve.py` prints a
   hint so this is discoverable rather than mysterious. (Note: an older design
   sketch suggested defaulting to `<hostname>:<port>`; the secure-default here
   supersedes that — reflected in CHANGELOG.)
3. **Server-mode gate keeps local UI untouched.** The proxy runs for every route
   in both modes (same app), so the very first check short-circuits non-server
   mode. This matches the security appendix's 适用范围 (serve mode only).
4. **Loopback defaults computed in the proxy, not trusted solely from env.**
   Fail-open only for loopback (never arbitrary hosts) so a bug/omission in env
   injection can't brick localhost access; everything else fails closed.

## Verification

- `ui`: `npx vitest run` — 106 passed (was 91; +15 proxy); `tsc --noEmit` clean;
  `npm run lint` clean; `npm run build` shows `ƒ Proxy (Middleware)` (wired).
- `uv run pytest` — 595 passed (serve.py change is env glue; syntax + server
  suite verified).
- **codex mcp review (gpt-5.5, xhigh): APPROVE** — no Host bypass across unknown/
  missing/duplicate Host, port mismatch, IPv6 forms, trailing dot, case tricks,
  `:authority`/`X-Forwarded-Host` confusion; confirmed the build matcher covers
  API write routes and `/_next/data`, and there is no shell-injection surface in
  the env injection. Re-reviewed after adding the three hardening tests: still
  APPROVE.

## Security notes (per security-development-guidelines.md checklist)

- **Secrets redaction**: N/A — no new persisted/returned text; the 400 body is a
  static `{ error: "host not allowed" }`.
- **Workspace boundary**: unaffected.
- **Shell interpolation**: none — `serve.py` passes an `env` dict to
  `subprocess.Popen(..., env=env)`; no user input reaches a shell. `allowed_hosts`
  is comma-joined for transport and split/trimmed in the proxy (a comma is not a
  valid Host character, so no parse ambiguity).
