#!/bin/bash
set -euo pipefail
export UV_CACHE_DIR=/root/autodl-tmp/uv-cache
TASK_ENV=/root/autodl-tmp/forkrsi-vllm-runtime
TASK_LOG=/root/autodl-tmp/ForkRSI/runs/forkrsi/vllm-deployment
mkdir -p "$TASK_LOG"
/root/autodl-tmp/forkrsi-tools-env/bin/uv venv --python /root/autodl-tmp/forkrsi-runtime/bin/python "$TASK_ENV"
/root/autodl-tmp/forkrsi-tools-env/bin/uv pip install --python "$TASK_ENV/bin/python" --index-url https://pypi.org/simple --torch-backend=auto 'vllm==0.21.0'
"$TASK_ENV/bin/python" -c 'import vllm, torch, transformers; print("VERSIONS",vllm.__version__,torch.__version__,torch.version.cuda,transformers.__version__)'
/root/autodl-tmp/forkrsi-tools-env/bin/uv pip freeze --python "$TASK_ENV/bin/python" > "$TASK_LOG/runtime-freeze.txt"
"$TASK_ENV/bin/vllm" serve --help > "$TASK_LOG/serve-help.txt"
date -u +%FT%TZ > "$TASK_LOG/install-complete.txt"
