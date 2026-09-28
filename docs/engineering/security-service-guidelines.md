---
title: micro-eval Product/Service Security Guidelines
language: en
authoritative: true
doc_type: reference
status: active
created_at: 2026-06-03T09:28+08:00
updated_at: 2026-09-27T16:00+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - engineering
  - security
  - service
related:
  - docs/engineering/security-guidelines.md
  - docs/engineering/frontend-guidelines.md
  - docs/releases/
---

# micro-eval Product/Service Security Guidelines

This file constrains the security boundaries `micro-eval` exposes to users as a product surface, covering the CLI, local UI/API, static reports, release packages, and possible future service offerings.

## Current MVP service boundary

- The MVP is a local-first tool; it provides no multi-team collaboration, RBAC/SSO, complex auditing, or hosted service capabilities.
- The local UI/API may only read `.micro-eval/` run data of the current project and manifest-bound artifacts.
- Reports and the UI must never expose raw filesystem paths that have not passed the manifest/ref boundary validation.
- Release packages must not depend on dev-only documents or private runtime material.

## UI/API and report exposure

- API routes must validate run/artifact boundaries; they never act as an arbitrary-path file-read entry point.
- Artifact content is exposed only through explicit `artifact_id` / manifest refs.
- Text/HTML reports must avoid injection risk; rendering user/agent output requires escaping or a safe template policy.
- The UI/Decision surfaces caveats to users instead of hiding security degradations.

## Release and branch boundaries

- `scripts/release/public-projection.toml` is the single source of truth for public path classification; every tracked path must be explicitly public, private, or generated, and unknown/conflicting paths abort the release.
- `main` must exactly match the candidate public tree generated from the allowlist; private paths, local artifacts, and historically leaked paths must not enter the candidate tree through merges.
- A candidate version must pass tests, build, and archive verification before local `main` moves via a compare-and-swap update; a failure must not move `main`.
- wheel/sdist artifacts are built from the candidate public tree and their archive manifests are verified item by item; untracked logs, caches, or local issue files from the daily `dev` workspace are never read.
- The public Git remote may receive only the verified `main` and an explicitly approved annotated tag pointing at the same SHA; if `dev` appears on the public remote, the release aborts — `--all` and `--mirror` are forbidden.
- Release evidence must record security-relevant verification results.
- The release-generated `AGENTS.md` / `CLAUDE.md` carry only the guardrails needed on the main branch and must not leak dev-only content.

## Future service boundaries

If `micro-eval` evolves from a local tool into a hosted service, new service security guidelines must be written first, covering at least:

- authentication / authorization;
- tenant isolation;
- audit logging;
- hosted sandbox / network isolation;
- secret storage and rotation;
- data retention and deletion;
- abuse prevention and rate limiting.

## Team Server service security appendix (v0.4)

### Trust model
- **Trusted intranet assumption**: the server runs on a team intranet and all members trust each other.
- **No authentication**: the `X-Micro-Eval-Member` header is a self-declared identity used only for attribution records, not authorization.
- Boundary conditions of this assumption: the server is never exposed to the public internet; team members do not forge identities on purpose; browsers may still visit malicious external pages.

### CSRF protection (four layers)
1. Content-Type enforcement: write endpoints accept only `application/json`.
2. Custom header check: write endpoints require the `X-Micro-Eval-Member` header.
3. No CORS headers: no `Access-Control-Allow-Origin` is ever returned.
4. Host header allowlist: Host headers outside the allowlist are rejected (mitigates DNS rebinding).

### Enqueue configuration overrides
The v0.4 `POST /api/workspaces/[id]/runs/enqueue` does not accept `config_overrides`;
a request body containing that field returns `400 Bad Request` instead of silently ignoring it.
The only supported browser request field is the optional `expected_plan_digest`; the run plan is
built server-side from the workspace configuration. Members cannot override `agent.command`,
`workspace`, `output_dir`, or `project_root` through an enqueue request.

### Attribution records (minimal auditing)
All write operations record `X-Micro-Eval-Member`. Attribution records are immutable
(`workspace.owner` cannot change after creation).

### Scope
This appendix applies only to `micro-eval serve` mode. The `micro-eval ui` local mode is unaffected.
