#!/usr/bin/env bash
set -euo pipefail
cd /root/autodl-tmp/ForkRSI
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_PROGRESS_BAR=off
export UV_CACHE_DIR=/root/autodl-tmp/uv-cache
export UV_PYTHON_INSTALL_DIR=/root/autodl-tmp/uv-python
export UV_HTTP_TIMEOUT=120
printf '%s\n' "STARTED $(date -Iseconds)"
python -m venv /root/autodl-tmp/forkrsi-tools-env
/root/autodl-tmp/forkrsi-tools-env/bin/python -m pip install --index-url https://mirrors.aliyun.com/pypi/simple uv
/root/autodl-tmp/forkrsi-tools-env/bin/uv python install 3.13
/root/autodl-tmp/forkrsi-tools-env/bin/uv sync --locked --python 3.13
python -m venv --system-site-packages /root/autodl-tmp/forkrsi-model-env
/root/autodl-tmp/forkrsi-model-env/bin/python -m pip install --index-url https://mirrors.aliyun.com/pypi/simple 'transformers>=5.2.0' accelerate safetensors fastapi uvicorn
printf '%s\n' "COMPLETED $(date -Iseconds)" > runs/forkrsi/bootstrap.status
