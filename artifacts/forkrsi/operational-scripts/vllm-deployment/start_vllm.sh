#!/bin/bash
set -euo pipefail
cd /root/autodl-tmp/ForkRSI
export PATH=/root/autodl-tmp/forkrsi-vllm-runtime/bin:/usr/local/cuda/bin:$PATH
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0
export VLLM_USE_FLASHINFER_SAMPLER=0
export VLLM_NO_USAGE_STATS=1
export VLLM_DO_NOT_TRACK=1
export OMP_NUM_THREADS=4
export VLLM_CACHE_ROOT=/root/autodl-tmp/vllm-cache
export TORCHINDUCTOR_CACHE_DIR=/root/autodl-tmp/vllm-cache/torchinductor
/root/miniconda3/bin/python -c 'import json,os,pathlib,time; pathlib.Path("runs/forkrsi/vllm-deployment/engine-worker.json").write_text(json.dumps({"pid":os.getppid(),"started_unix":time.time()}))'
exec /root/autodl-tmp/forkrsi-vllm-runtime/bin/vllm serve /root/autodl-tmp/models/Qwen3.5-4B \
 --host 127.0.0.1 --port 8002 --served-model-name Qwen3.5-4B \
 --dtype bfloat16 --tensor-parallel-size 1 --language-model-only \
 --max-model-len 32768 --max-num-seqs 16 --max-num-batched-tokens 8192 \
 --gpu-memory-utilization 0.90 --generation-config vllm --enable-prefix-caching
