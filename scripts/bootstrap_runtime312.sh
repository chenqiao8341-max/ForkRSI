#!/usr/bin/env bash
set -euo pipefail
cd /root/autodl-tmp/ForkRSI
status=runs/forkrsi/runtime312.status
trap 'code=$?; if [ "$code" -ne 0 ]; then printf "FAILED exit=%s\n" "$code" > "$status"; fi' EXIT
printf "RUNNING\n" > "$status"
/root/miniconda3/bin/python -m venv --system-site-packages /root/autodl-tmp/forkrsi-runtime
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_PROGRESS_BAR=off
constraints=()
if [ -f artifacts/forkrsi/runtime312-constraints.txt ]; then
  constraints=(-c artifacts/forkrsi/runtime312-constraints.txt)
fi
/root/autodl-tmp/forkrsi-runtime/bin/python -m pip install "${constraints[@]}" --index-url https://mirrors.aliyun.com/pypi/simple --ignore-requires-python -e . 'transformers>=5.2.0' accelerate safetensors fastapi uvicorn pytest pytest-asyncio ruff mypy types-PyYAML
/root/autodl-tmp/forkrsi-runtime/bin/python -m pip freeze > artifacts/forkrsi/runtime312-freeze.txt
printf "COMPLETED\n" > "$status"
