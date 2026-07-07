#!/usr/bin/env bash
# release-to-main.sh — Safely publish dev to main with dev-only file filtering.
#
# Usage:  scripts/release-to-main.sh [--dry-run]
#
# Strategy: merge --no-commit (never auto-commit), strip dev-only files from
# the index, VERIFY nothing dev-only survives, then commit and push.
# The script never pushes dev. Dev stays local-only.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# ─── Dev-only paths: tracked on dev, MUST NOT appear on main ─────────
# Update this list when adding new dev-only directories or files.
DEV_ONLY_PATTERNS=(
  "*CLAUDE.md"
  "TODOS.md"
  "micro-eval-brd.md"
  "micro-eval-prd.md"
  "docs/dev"
  "docs/superpowers"
  "docs/_archive"
  "docs/references"
  "docs/bug_reports"
  "docs/analysis"
  "docs/security"
  ".codex"
)

# ─── Gitignore block that main needs but dev doesn't ─────────────────
read -r -d '' MAIN_GITIGNORE_EXTRAS << 'GITIGNORE_EOF' || true

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
docs/security/
.codex/
GITIGNORE_EOF

# ─── Helpers ──────────────────────────────────────────────────────────

die() {
  echo "FATAL: $*" >&2
  exit 1
}
info() { echo "==> $*"; }
warn() { echo "WARNING: $*" >&2; }

abort_merge() {
  warn "Aborting merge on main..."
  git merge --abort 2>/dev/null || true
  git checkout dev 2>/dev/null || true
  die "$1"
}

# ─── Precondition checks ─────────────────────────────────────────────

current_branch="$(git branch --show-current)"
[[ "$current_branch" == "dev" ]] || die "Must be on dev branch (currently on $current_branch)"
[[ -z "$(git status --porcelain)" ]] || die "Working tree is not clean. Commit or stash first."

info "Running Python tests..."
pytest_out="$(uv run pytest -q --timeout=60 2>&1)"
if ! echo "$pytest_out" | grep -qE "^[0-9]+ passed"; then
  echo "$pytest_out" | tail -5
  die "Python tests failed"
fi
echo "$pytest_out" | tail -1

info "Running UI tests..."
vitest_out="$(cd ui && npx vitest run 2>&1)"
if echo "$vitest_out" | grep -q "FAIL"; then
  echo "$vitest_out" | tail -5
  die "UI tests failed"
fi
echo "$vitest_out" | grep -E "PASS|Tests"

info "Verifying UI build..."
build_out="$(cd ui && npm run build 2>&1)"
if ! echo "$build_out" | grep -q "Compiled successfully"; then
  echo "$build_out" | tail -10
  die "UI build failed"
fi
echo "$build_out" | grep "Compiled successfully"

# ─── Version consistency ──────────────────────────────────────────────

version_file="$(cat VERSION | tr -d '[:space:]')"
version_py="$(grep '__version__' src/micro_eval/__init__.py | sed 's/.*"\(.*\)".*/\1/')"
version_pkg="$(node -p "require('./ui/package.json').version")"
[[ "$version_file" == "$version_py" ]] || die "VERSION ($version_file) != __init__.py ($version_py)"
[[ "$version_file" == "$version_pkg" ]] || die "VERSION ($version_file) != package.json ($version_pkg)"
info "Version: $version_file"

# ─── Dry-run gate ─────────────────────────────────────────────────────

if $DRY_RUN; then
  info "[DRY RUN] All preconditions passed. Would merge dev → main, filter dev-only files, push main."
  exit 0
fi

# ─── Merge dev → main (--no-commit: never auto-commit) ───────────────

dev_sha="$(git rev-parse HEAD)"
info "Switching to main..."
git checkout main

info "Merging dev ($dev_sha) into main (--no-commit)..."
# --no-commit prevents auto-commit so we can strip dev-only files first.
# --no-ff ensures a merge commit even for fast-forward cases.
git merge dev --no-commit --no-ff || true
# "|| true" because --no-commit makes git exit 0 on success but the merge
# may report conflicts. Check for conflicts explicitly:
if git ls-files -u | grep -q .; then
  abort_merge "Merge conflicts detected. Resolve manually."
fi

# ─── Restore main .gitignore ─────────────────────────────────────────

if ! grep -q "Dev-only internal docs" .gitignore 2>/dev/null; then
  info "Appending dev-only exclusions to .gitignore..."
  echo "$MAIN_GITIGNORE_EXTRAS" >> .gitignore
  git add .gitignore
fi

# ─── Strip dev-only files from the index ──────────────────────────────

for pattern in "${DEV_ONLY_PATTERNS[@]}"; do
  if git ls-files "$pattern" | grep -q .; then
    info "Stripping dev-only: $pattern"
    git rm --cached -r "$pattern" 2>/dev/null || true
  fi
done

# ─── HARD VERIFICATION: no dev-only file may be staged ────────────────

info "Verifying no dev-only files are staged..."
leaked=""
for pattern in "${DEV_ONLY_PATTERNS[@]}"; do
  # Only flag files that would be ADDED or MODIFIED (not deleted).
  # After git rm --cached, deleted files in diff are expected and safe.
  staged="$(git diff --cached --name-only --diff-filter=ACMR -- "$pattern" 2>/dev/null || true)"
  if [[ -n "$staged" ]]; then
    leaked="$leaked  $pattern ($staged)\n"
  fi
done

if [[ -n "$leaked" ]]; then
  echo ""
  echo "!!! DEV-ONLY FILES LEAKED INTO MAIN STAGING AREA !!!"
  echo -e "$leaked"
  abort_merge "Dev-only files detected in staging. Release aborted."
fi
info "Verification passed: no dev-only files in staging."

# ─── Commit the merge ────────────────────────────────────────────────

git commit -m "release: merge dev v$version_file into main

Source: dev @ $dev_sha
Automated by scripts/release-to-main.sh — dev-only files stripped."

# ─── Final test on main ──────────────────────────────────────────────

info "Running tests on main..."
pytest_main="$(uv run pytest -q --timeout=60 2>&1)"
if ! echo "$pytest_main" | grep -qE "^[0-9]+ passed"; then
  echo "$pytest_main" | tail -5
  die "Tests failed on main after merge! NOT pushing. Fix manually."
fi
echo "$pytest_main" | tail -1

# ─── Push main only ──────────────────────────────────────────────────

info "Pushing main to origin..."
git push origin main

# ─── Return to dev ────────────────────────────────────────────────────

info "Switching back to dev..."
git checkout dev

echo ""
info "Release complete: main @ v$version_file pushed. Dev is local-only."
