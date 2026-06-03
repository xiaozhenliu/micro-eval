#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
VERSION_VALUE="${1:-$(cat "$REPO_ROOT/VERSION")}"

cd "$REPO_ROOT"
"$SCRIPT_DIR/check-version-consistency.py" --version "$VERSION_VALUE"
uv run python -m compileall src/micro_eval tests
uv run pytest -q
(
  cd ui
  npm run lint
  npm run build
)
uv build
git diff --check
git diff --cached --check
if grep -RInE 'create_subprocess_shell|shell=True' src tests ui examples; then
  echo 'Forbidden shell subprocess pattern found' >&2
  exit 1
fi
