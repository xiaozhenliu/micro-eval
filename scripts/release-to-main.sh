#!/usr/bin/env bash
# release-to-main.sh — Build and verify the fail-closed public projection.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/release-to-main.sh stage [--dry-run] [dev] [main]
  scripts/release-to-main.sh publish --expected-sha SHA [--tag vX.Y.Z] [--dry-run] [dev] [main]

Compatibility forms:
  scripts/release-to-main.sh [--dry-run] [--local-only|--no-push] [dev] [main]
  scripts/release-to-main.sh --push --expected-sha SHA [--tag vX.Y.Z] [--dry-run] [dev] [main]

Default/local-only mode:
  Classify every tracked dev path, build a deterministic public main tree in an
  isolated worktree, validate that tree and its wheel/sdist, then write a local
  verified receipt. It never contacts a remote.

Push mode:
  A separate action that requires the full SHA from a verified local receipt.
  It atomically pushes only that exact SHA to origin/main and, when explicitly
  requested, an annotated vX.Y.Z tag pointing to the same commit.

Options:
  --local-only       Build and verify local main only (default).
  --no-push          Alias for --local-only.
  --push             Push-only mode; does not create or re-project main.
  --expected-sha SHA Full verified main commit required by --push.
  --tag vX.Y.Z       Also create and atomically push this exact release tag.
  --dry-run          Plan projection, or validate a push receipt without pushing.
  -h, --help         Show this help text and exit.
USAGE
}

die() {
  echo "FATAL: $*" >&2
  exit 1
}
info() { echo "==> $*"; }

MODE="local-only"
DRY_RUN=false
EXPECTED_SHA=""
RELEASE_TAG=""
EXPLICIT_MODE=""
POSITIONAL_ARGS=()

if [[ "${1:-}" == "stage" ]]; then
  EXPLICIT_MODE="local-only"
  shift
elif [[ "${1:-}" == "publish" ]]; then
  MODE="push"
  EXPLICIT_MODE="push"
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local-only|--no-push)
      [[ "$EXPLICIT_MODE" != "push" ]] \
        || die "Cannot combine --push with --local-only/--no-push."
      MODE="local-only"
      EXPLICIT_MODE="local-only"
      ;;
    --push)
      [[ "$EXPLICIT_MODE" != "local-only" ]] \
        || die "Cannot combine --push with --local-only/--no-push."
      MODE="push"
      EXPLICIT_MODE="push"
      ;;
    --expected-sha)
      shift
      [[ $# -gt 0 ]] || die "--expected-sha requires a full commit SHA."
      EXPECTED_SHA="$1"
      ;;
    --tag)
      shift
      [[ $# -gt 0 ]] || die "--tag requires vX.Y.Z."
      RELEASE_TAG="$1"
      ;;
    --dry-run)
      DRY_RUN=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        POSITIONAL_ARGS+=("$1")
        shift
      done
      break
      ;;
    -*)
      die "Unknown option: $1. Run with --help for usage."
      ;;
    *)
      POSITIONAL_ARGS+=("$1")
      ;;
  esac
  shift
done

[[ ${#POSITIONAL_ARGS[@]} -le 2 ]] \
  || die "Expected at most source and target branches."

SOURCE_BRANCH="${POSITIONAL_ARGS[0]:-dev}"
TARGET_BRANCH="${POSITIONAL_ARGS[1]:-main}"
PUSH_REMOTE="origin"

[[ "$SOURCE_BRANCH" == "dev" ]] || die "Source branch must be dev."
[[ "$TARGET_BRANCH" == "main" ]] || die "Target branch must be main."
if [[ "$MODE" == "push" ]]; then
  [[ -n "$EXPECTED_SHA" ]] || die "--push requires --expected-sha with the verified full SHA."
elif [[ -n "$EXPECTED_SHA" ]]; then
  die "--expected-sha is only valid with --push."
fi
if [[ "$MODE" != "push" && -n "$RELEASE_TAG" ]]; then
  die "--tag is only valid with publish/--push."
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
PROJECTION_TOOL="scripts/release/public_projection.py"
PROJECTION_POLICY="scripts/release/public-projection.toml"

current_branch="$(git branch --show-current)"
[[ "$current_branch" == "$SOURCE_BRANCH" ]] \
  || die "Must be on $SOURCE_BRANCH branch (currently on $current_branch)."
[[ -z "$(git status --porcelain)" ]] \
  || die "Working tree is not clean. Commit or stash first."

if [[ "$MODE" == "push" ]]; then
  push_args=(
    uv run python "$PROJECTION_TOOL" --policy "$PROJECTION_POLICY" push
    --target "$TARGET_BRANCH"
    --remote "$PUSH_REMOTE"
    --expected-sha "$EXPECTED_SHA"
  )
  $DRY_RUN && push_args+=(--dry-run)
  [[ -z "$RELEASE_TAG" ]] || push_args+=(--tag "$RELEASE_TAG")
  "${push_args[@]}"
  if $DRY_RUN; then
    info "[DRY RUN] Verified receipt accepted. No remote push performed."
  else
    info "Verified commit $EXPECTED_SHA pushed to $PUSH_REMOTE/$TARGET_BRANCH."
  fi
  exit 0
fi

info "Checking fail-closed public path classification..."
plan_json="$(
  uv run python "$PROJECTION_TOOL" --policy "$PROJECTION_POLICY" \
    plan --source "$SOURCE_BRANCH" --json
)"
info "Projection plan: $plan_json"

version_file="$(tr -d '[:space:]' < VERSION)"
info "Version: $version_file"
info "Running the complete release preflight on dev..."
scripts/release/preflight-release.sh "$version_file"

if $DRY_RUN; then
  info "[DRY RUN] Full preflight passed. Would build and verify local $TARGET_BRANCH only."
  exit 0
fi

info "Building deterministic public $TARGET_BRANCH tree..."
project_json="$(
  uv run python "$PROJECTION_TOOL" --policy "$PROJECTION_POLICY" project \
    --source "$SOURCE_BRANCH" --target "$TARGET_BRANCH" \
    --version "$version_file" --json
)"
candidate_sha="$(
  echo "$project_json" \
    | sed -n 's/.*"candidate_sha": "\([0-9a-f]\{40\}\)".*/\1/p'
)"
[[ -n "$candidate_sha" ]] || die "Projection did not return a candidate SHA."
info "Candidate main: $candidate_sha"

validation_parent="$(mktemp -d)"
validation_worktree="$validation_parent/main"
cleanup_validation() {
  git worktree remove --force "$validation_worktree" >/dev/null 2>&1 || true
  rmdir "$validation_parent" >/dev/null 2>&1 || true
}
trap cleanup_validation EXIT

git worktree add --detach "$validation_worktree" "$candidate_sha" >/dev/null

info "Running Python tests on candidate public tree..."
if ! candidate_pytest="$(
    cd "$validation_worktree"
    PYTHONPATH="$validation_worktree/src" \
      uv run --project "$REPO_ROOT" pytest -q --timeout=60 2>&1
  )"; then
  echo "$candidate_pytest" | tail -20
  die "Python tests failed on candidate public tree."
fi
echo "$candidate_pytest" | grep -qE "^[0-9]+ passed" || {
  echo "$candidate_pytest" | tail -20
  die "Python tests failed on candidate public tree."
}
echo "$candidate_pytest" | tail -1

if [[ -d "$REPO_ROOT/ui/node_modules" ]]; then
  ln -s "$REPO_ROOT/ui/node_modules" "$validation_worktree/ui/node_modules"
fi
info "Running UI tests and build on candidate public tree..."
if ! candidate_vitest="$(cd "$validation_worktree/ui" && npx vitest run 2>&1)"; then
  echo "$candidate_vitest" | tail -20
  die "UI tests failed on candidate public tree."
fi
echo "$candidate_vitest" | grep -q "FAIL" && {
  echo "$candidate_vitest" | tail -20
  die "UI tests failed on candidate public tree."
}
if ! candidate_build="$(cd "$validation_worktree/ui" && npm run build 2>&1)"; then
  echo "$candidate_build" | tail -20
  die "UI build failed on candidate public tree."
fi
echo "$candidate_build" | grep -q "Compiled successfully" || {
  echo "$candidate_build" | tail -20
  die "UI build failed on candidate public tree."
}

mkdir -p "$REPO_ROOT/dist"
info "Building wheel and sdist from candidate public tree..."
(cd "$validation_worktree" && uv build --out-dir "$REPO_ROOT/dist")

cleanup_validation
trap - EXIT

info "Verifying local main tree, artifact contents, and release receipt..."
uv run python "$PROJECTION_TOOL" --policy "$PROJECTION_POLICY" verify \
  --candidate-sha "$candidate_sha" --target "$TARGET_BRANCH" \
  --dist-dir "$REPO_ROOT/dist" \
  --version "$version_file"

info "Local projection complete. No remote push performed."
info "Verified main commit: $candidate_sha"
info "To push this exact verified commit after explicit authorization:"
info "scripts/release-to-main.sh publish --expected-sha $candidate_sha dev main"
info "To atomically publish main plus its annotated version tag:"
info "scripts/release-to-main.sh publish --expected-sha $candidate_sha --tag v$version_file dev main"
