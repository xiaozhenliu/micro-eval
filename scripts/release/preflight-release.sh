#!/usr/bin/env bash
set -euo pipefail

VERSION_VALUE="${1:-$(cat VERSION)}"
[[ "$VERSION_VALUE" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || {
  echo "Invalid release version: $VERSION_VALUE" >&2
  exit 1
}

shopt -s nullglob
dependency_markdown=(docs/releases/*-v"$VERSION_VALUE"-dependency-inventory.md)
dependency_json=(docs/releases/*-v"$VERSION_VALUE"-dependency-inventory.json)
release_evidence=(docs/releases/*-v"$VERSION_VALUE"-release-evidence.md)
[[ ${#dependency_markdown[@]} -eq 1 ]] || {
  echo "Expected one Markdown dependency inventory for v$VERSION_VALUE" >&2
  exit 1
}
[[ ${#dependency_json[@]} -eq 1 ]] || {
  echo "Expected one JSON dependency inventory for v$VERSION_VALUE" >&2
  exit 1
}
[[ ${#release_evidence[@]} -eq 1 ]] || {
  echo "Expected one release evidence document for v$VERSION_VALUE" >&2
  exit 1
}

python scripts/release/check-version-consistency.py --version "$VERSION_VALUE"
python scripts/release/public_projection.py plan --source WORKTREE
uv run python -m compileall src/micro_eval tests
uv run pytest -q
(
  cd ui
  npm run lint
  npx vitest run
  npm run build
)
uv build
python scripts/release/public_projection.py verify-artifacts \
  --dist-dir dist --version "$VERSION_VALUE"
git diff --check
git diff --cached --check
if grep -RInE 'create_subprocess_shell|shell=True' --exclude='test_execution_contract.py' src tests ui/src examples; then
  echo 'Forbidden shell subprocess pattern found' >&2
  exit 1
fi
