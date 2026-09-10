#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --locked
uv run forkmem replay --case artifacts/v2/cases/partial_repair_falsified.json
for case in artifacts/v2/comparisons/*.json; do
  if [[ "$(basename "$case")" != "selection.json" ]]; then
    uv run forkmem replay --case "$case"
  fi
done
