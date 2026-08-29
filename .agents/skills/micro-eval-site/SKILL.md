---
name: micro-eval-site
description: Automatically update or audit micro-eval's bilingual VitePress site from code, schema, UI, example, version, or security changes. Analyze git impact, edit the affected English and Chinese pages, and verify coverage with mapped source tests plus the production site build; use other project guidance for internal docs/ or the Next.js app itself.
---

# micro-eval project site

Deliver a verified site update, not an impact report. The workflow has three
separate gates: deterministic impact analysis, agent-authored content changes,
and independent test verification.

## Boundaries

- `site/` is the public VitePress project and documentation site.
- `ui/` is the Next.js product UI; its behavior may require site updates, but
  changing the product belongs to the source task.
- `docs/` is the engineering/development documentation domain, not a substitute
  for the user-facing site.
- Public pages may consult private development sources but may only link to
  paths included by `scripts/release/public-projection.toml`.
- Deployment from projected `main` through GitHub Pages is a separate action
  requiring explicit authorization.

Apply the root repository instructions first: verify the actual branch and
follow the ticket-first threshold. This repository implements from the user
path before testing; it does not use TDD.

## Three-layer update loop

Use a temporary directory outside the repository for the plan and resolution
ledger. Choose the comparison base that contains the last state whose site was
known to be current. `HEAD` analyzes staged, unstaged, and untracked worktree
changes; a tag, branch, or commit also includes committed changes since that
base.

```bash
SITE_SKILL=.agents/skills/micro-eval-site
SITE_RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/micro-eval-site.XXXXXX")"
python3 "$SITE_SKILL/scripts/site_update.py" plan \
  --base HEAD \
  --plan "$SITE_RUN_DIR/plan.json" \
  --resolution "$SITE_RUN_DIR/resolution.json" \
  --strict
```

### 1. Impact analysis

The planner reads git changes, applies the project impact map, checks that
candidate pages and locale counterparts exist, and selects source tests. It
fails closed for any user-facing behavior path that has no mapping.

Read every matched rule in the report. Inspect the relevant source diff,
current implementation, candidate pages, and locale counterparts. If the
planner reports an unmapped behavior path, update
`references/site-impact-map.toml` to account for the new domain and rerun the
plan. Use `--path` only to diagnose or test the map; delivery verification
requires a git-derived plan.

### 2. Content update

For every matched rule, choose exactly one outcome:

- `updated`: edit the smallest correct subset of candidate pages. Update the
  English and Simplified Chinese counterparts together with semantic parity.
- `no-doc-impact`: use only when the changed contract is genuinely invisible
  to site readers, and record the concrete reason. Uncertainty requires source
  inspection, not this outcome.

Record each decision as it is completed:

```bash
python3 "$SITE_SKILL/scripts/site_update.py" resolve \
  --resolution "$SITE_RUN_DIR/resolution.json" \
  --rule cli \
  --outcome updated \
  --page site/reference/cli.md \
  --page site/zh/reference/cli.md \
  --rationale "Documented the new CLI option in both locale references."
```

For a rule with no reader-visible effect, omit `--page` and use
`--outcome no-doc-impact` with its evidence. Do not stop after filling the
ledger: the declared pages must exist in the actual git diff.

### 3. Test verification

Run the verifier only after all rules are resolved:

```bash
python3 "$SITE_SKILL/scripts/site_update.py" verify \
  --plan "$SITE_RUN_DIR/plan.json" \
  --resolution "$SITE_RUN_DIR/resolution.json"
```

The verifier independently rescans git and rejects stale plans, incomplete or
duplicate resolutions, unmapped behavior, missing pages, missing locale pairs,
pages declared updated but absent from the diff, and updated pages without
their counterpart. It then runs `git diff --check`, the production VitePress
build, and every source test selected by the matched impact rules. A delivery
is complete only when it prints `"status": "verified"`. The hidden
test-harness bypass for command execution is not completion evidence.

If source behavior changes after planning, regenerate the plan and resolution
ledger rather than carrying forward stale attestations.

## Content authorities

Verify changed claims against the closest current authority. Existing site
text and historical plans are not evidence that a claim remains true.

| Site content | Preferred current authority |
| --- | --- |
| Version, positioning, install, quick start | `VERSION`, root READMEs, package metadata, current CLI behavior |
| Concepts and domain language | current product specs and `docs/agents/domain.md` |
| CLI reference | CLI implementation and `--help` output |
| `eval.yaml` / task schema | Pydantic models, validation code, maintained examples |
| API routes and Web UI | current `ui/src/` routes, schemas, and contract tests |
| Examples and capability matrix | `examples/README.md` and runnable example files |
| Security guidance | current `docs/engineering/security-*.md` rules and enforced behavior |
| Release or compatibility claims | `CHANGELOG.md`, release evidence, verified implementation |

When sources disagree, resolve the disagreement in the authority domain or
state only the narrower verified fact. The site does not become a new source
of truth.

## Information architecture

- landing: `site/index.md` and `site/zh/index.md`
- journey-oriented guides: `site/guide/` and `site/zh/guide/`
- lookup-oriented references: `site/reference/` and `site/zh/reference/`
- runnable scenarios: `site/examples/` and `site/zh/examples/`
- navigation, sidebars, locales, metadata: `site/.vitepress/config.ts`
- static assets: `site/public/`

Put concepts and journeys in guides, exact contracts in references, and
scenario walkthroughs in examples. When pages move or their discoverability
changes, update both locale branches in `site/.vitepress/config.ts` and all
affected links. Account for the configured `/micro-eval/` base path in assets.
Keep commands, schema keys, paths, identifiers, and `ticket` in source spelling.

For landing, theme, Mermaid, or asset changes, add visual inspection of both
locale routes at desktop and narrow widths; the deterministic verifier covers
contracts and builds, not visual judgment. Report the base, matched rules,
resolved outcomes, changed locale pages, tests run, and any explicitly deferred
drift.
