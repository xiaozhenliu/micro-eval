#!/usr/bin/env bash
# release-to-main.sh — Merge dev into main with dev-only file filtering.
#
# Usage:  scripts/release-to-main.sh [--dry-run]
#
# What it does:
#   1. Verifies preconditions (on dev, clean tree, tests pass)
#   2. Merges dev → main
#   3. Restores main's .gitignore (appends dev-only exclusions)
#   4. Removes dev-only files from main's index
#   5. Commits the cleanup
#   6. Pushes main (never dev)
#   7. Switches back to dev
#
# The script never pushes dev. Dev stays local-only.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# ─── Dev-only paths: tracked on dev, excluded from main ───────────────
# Update this list when adding new dev-only directories or files.
DEV_ONLY_PATTERNS=(
  "CLAUDE.md"
  "TODOS.md"
  "micro-eval-brd.md"
  "micro-eval-prd.md"
  "docs/dev/"
  "docs/superpowers/"
  "docs/_archive/"
  "docs/references/"
  "docs/bug_reports/"
  "docs/analysis/"
)

# ─── Gitignore block appended to main's .gitignore after merge ────────
MAIN_GITIGNORE_BLOCK="
# Dev-only docs (tracked on dev branch; never published to main)
CLAUDE.md
micro-eval-brd.md
micro-eval-prd.md
TODOS.md

# Dev-only internal docs
docs/dev/
docs/superpowers/
docs/_archive/
docs/references/
docs/bug_reports/
docs/analysis/
"

# ─── Helpers ──────────────────────────────────────────────────────────

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

# ─── Precondition checks ─────────────────────────────────────────────

current_branch="$(git branch --show-current)"
[[ "$current_branch" == "dev" ]] || die "Must be on dev branch (currently on $current_branch)"

[[ -z "$(git status --porcelain)" ]] || die "Working tree is not clean. Commit or stash changes first."

info "Running Python tests..."
if ! uv run pytest -q --timeout=60 2>&1 | tail -3; then
  die "Python tests failed"
fi

info "Running UI tests..."
if ! (cd ui && npx vitest run 2>&1 | tail -3); then
  die "UI tests failed"
fi

info "Verifying UI build..."
if ! (cd ui && npm run build 2>&1 | grep -q "Compiled successfully"); then
  die "UI build failed"
fi

# ─── Version consistency check ────────────────────────────────────────

version_file="$(cat VERSION)"
version_py="$(python3 -c "import re; print(re.search(r'__version__\s*=\s*\"(.+?)\"', open('src/micro_eval/__init__.py').read()).group(1))")"
[[ "$version_file" == "$version_py" ]] || die "VERSION ($version_file) != __init__.py ($version_py)"
info "Version: $version_file"

# ─── Dry-run gate ─────────────────────────────────────────────────────

if $DRY_RUN; then
  info "[DRY RUN] All checks passed. Would merge dev → main, filter dev-only files, push main."
  exit 0
fi

# ─── Merge dev → main ────────────────────────────────────────────────

dev_sha="$(git rev-parse HEAD)"
info "Switching to main..."
git checkout main

info "Merging dev ($dev_sha) into main..."
git merge dev --no-edit

# ─── Restore main .gitignore ─────────────────────────────────────────
# The merge may have overwritten main's .gitignore with dev's version.
# We re-append the dev-only exclusion block if it's missing.

if ! grep -q "Dev-only internal docs" .gitignore 2>/dev/null; then
  info "Restoring dev-only exclusions in .gitignore..."
  echo "$MAIN_GITIGNORE_BLOCK" >> .gitignore
  git add .gitignore
fi

# ─── Remove dev-only files from main index ────────────────────────────

removed=0
for pattern in "${DEV_ONLY_PATTERNS[@]}"; do
  if git ls-files --error-unmatch "$pattern" &>/dev/null; then
    git rm --cached -r "$pattern" 2>/dev/null
    ((removed++)) || true
  fi
done

if (( removed > 0 )); then
  info "Removed $removed dev-only path(s) from main index."
  git commit -m "chore: remove dev-only files from main tracking

Automated by scripts/release-to-main.sh."
else
  info "No dev-only files to remove (already clean)."
fi

# ─── Final verification on main ──────────────────────────────────────

info "Verifying tests on main..."
if ! uv run pytest -q --timeout=60 2>&1 | tail -3; then
  die "Tests failed on main! Aborting push. Fix manually."
fi

# ─── Push main only ──────────────────────────────────────────────────

info "Pushing main to origin..."
git push origin main

# ─── Switch back to dev ───────────────────────────────────────────────

info "Switching back to dev..."
git checkout dev

info "Done. main pushed with v$version_file. Dev branch is local-only."
