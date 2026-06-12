#!/usr/bin/env bash
set -euo pipefail

SOURCE_BRANCH="${1:-dev}"
TARGET_BRANCH="${2:-main}"
COMMIT_MESSAGE="${RELEASE_COMMIT_MESSAGE:-Release dev to main excluding dev-only documents}"
KEEP_RELEASE_WORKTREE="${KEEP_RELEASE_WORKTREE:-0}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
TEMPLATE_DIR="$SKILL_DIR/assets/templates"
AGENTS_PUBLISH_TEMPLATE="$TEMPLATE_DIR/agents-publish-template.md"
CLAUDE_PUBLISH_TEMPLATE="$TEMPLATE_DIR/claude-publish-template.md"

EXCLUDED_DIRS=(
  ".codex"
  ".understand-anything"
  "docs/dev"
  "docs/superpowers"
  "docs/_archive"
  "docs/references"
  "docs/bug_reports"
)

EXCLUDED_FILES=(
  "micro-eval-brd.md"
  "micro-eval-prd.md"
)

MAIN_GITIGNORE_PATTERNS=(
  ".codex/"
  ".understand-anything/"
  "docs/dev/"
  "docs/superpowers/"
  "docs/_archive/"
  "docs/references/"
  "docs/bug_reports/"
  "micro-eval-brd.md"
  "micro-eval-prd.md"
)

MAIN_GITIGNORE_REMOVALS=(
  "AGENTS.md"
  "CLAUDE.md"
)

require_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "Error: required file is missing: $file" >&2
    exit 1
  fi
}

remove_gitignore_pattern() {
  local pattern="$1"
  local file=".gitignore"
  [[ -f "$file" ]] || return 0
  local tmp
  tmp="$(mktemp)"
  grep -vxF "$pattern" "$file" > "$tmp" || true
  mv "$tmp" "$file"
}

append_gitignore_pattern() {
  local pattern="$1"
  local file=".gitignore"
  touch "$file"
  if ! grep -qxF "$pattern" "$file"; then
    printf '\n%s\n' "$pattern" >> "$file"
  fi
}

require_file "$AGENTS_PUBLISH_TEMPLATE"
require_file "$CLAUDE_PUBLISH_TEMPLATE"

if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "$SOURCE_BRANCH" >/dev/null; then
  echo "Error: source branch does not exist: $SOURCE_BRANCH" >&2
  exit 1
fi

if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "$TARGET_BRANCH" >/dev/null; then
  echo "Error: target branch does not exist: $TARGET_BRANCH" >&2
  exit 1
fi

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
  echo "Error: source working tree must be clean before release" >&2
  git -C "$REPO_ROOT" status --short >&2
  exit 1
fi

worktree_parent="$(mktemp -d "${TMPDIR:-/tmp}/micro-eval-release.XXXXXX")"
main_worktree="$worktree_parent/main"
cleanup() {
  if [[ "$KEEP_RELEASE_WORKTREE" == "1" ]]; then
    echo "Keeping release worktree: $main_worktree" >&2
    return 0
  fi
  git -C "$REPO_ROOT" worktree remove --force "$main_worktree" >/dev/null 2>&1 || true
  rm -rf "$worktree_parent"
}
trap cleanup EXIT

# Use a temporary target worktree so the agent never has to switch the active dev checkout to main.
git -C "$REPO_ROOT" worktree add "$main_worktree" "$TARGET_BRANCH"

if [[ -n "$(git -C "$main_worktree" status --porcelain)" ]]; then
  echo "Error: target worktree is not clean: $main_worktree" >&2
  git -C "$main_worktree" status --short >&2
  exit 1
fi

(
  cd "$main_worktree"

  # Record the source branch as merged while keeping explicit control of the release tree.
  git merge -s ours --no-commit "$SOURCE_BRANCH"

  # Remove files that were deleted on the source branch so main mirrors dev minus exclusions.
  deleted_paths=()
  while IFS= read -r -d '' path; do
    deleted_paths+=("$path")
  done < <(git diff --name-only --diff-filter=D -z HEAD "$SOURCE_BRANCH")

  # Check out all source-branch files, then apply main-only exclusions and generated guardrails.
  git checkout "$SOURCE_BRANCH" -- .

  if (( ${#deleted_paths[@]} > 0 )); then
    git rm -f --ignore-unmatch -- "${deleted_paths[@]}"
  fi

  for dir in "${EXCLUDED_DIRS[@]}"; do
    git rm -r -f --ignore-unmatch -- "$dir"
  done

  for file in "${EXCLUDED_FILES[@]}"; do
    git rm -f --ignore-unmatch -- "$file"
  done

  cp "$AGENTS_PUBLISH_TEMPLATE" AGENTS.md
  cp "$CLAUDE_PUBLISH_TEMPLATE" CLAUDE.md
  git add -f AGENTS.md CLAUDE.md

  for pattern in "${MAIN_GITIGNORE_REMOVALS[@]}"; do
    remove_gitignore_pattern "$pattern"
  done

  for pattern in "${MAIN_GITIGNORE_PATTERNS[@]}"; do
    append_gitignore_pattern "$pattern"
  done
  git add .gitignore

  if [[ -n "$(git ls-files '.codex/*' '.understand-anything/*' 'docs/dev/*' 'docs/superpowers/*' 'docs/_archive/*' 'docs/references/*' 'docs/bug_reports/*')" ]]; then
    echo "Error: dev-only release exclusions are still tracked in the release tree" >&2
    git ls-files '.codex/*' '.understand-anything/*' 'docs/dev/*' 'docs/superpowers/*' 'docs/_archive/*' 'docs/references/*' 'docs/bug_reports/*' >&2
    exit 1
  fi

  cmp AGENTS.md "$AGENTS_PUBLISH_TEMPLATE"
  cmp CLAUDE.md "$CLAUDE_PUBLISH_TEMPLATE"

  git status --short
  git commit -m "$COMMIT_MESSAGE"
)
