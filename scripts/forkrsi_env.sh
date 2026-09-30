# Source this only in the remote research workspace.
export PATH=/root/autodl-tmp/forkrsi-tools-env/bin:$PATH
export UV_CACHE_DIR=/root/autodl-tmp/uv-cache
export UV_PYTHON_INSTALL_DIR=/root/autodl-tmp/uv-python
export FORKMEM_SANDBOX_BACKEND=chroot-seccomp
export FORKMEM_LLM_BASE_URL=http://127.0.0.1:8000/v1
export FORKMEM_LLM_MODEL=Qwen3.5-4B
export FORKMEM_LLM_MAX_CONCURRENCY=1
export FORKMEM_LLM_TIMEOUT_SECONDS=900
