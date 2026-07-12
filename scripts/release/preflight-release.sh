#!/usr/bin/env bash
set -euo pipefail

VERSION_VALUE="${1:-$(cat VERSION)}"

python scripts/release/check-version-consistency.py --version "$VERSION_VALUE"
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
if grep -RInE 'create_subprocess_shell|shell=True' --exclude='test_execution_contract.py' src tests ui/src examples; then
  echo 'Forbidden shell subprocess pattern found' >&2
  exit 1
fi
