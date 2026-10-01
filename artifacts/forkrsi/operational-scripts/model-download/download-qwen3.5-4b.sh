#!/usr/bin/env bash
set -u
export PYTHONUNBUFFERED=1
export MODELSCOPE_ENDPOINT=https://modelscope.cn
export MODELSCOPE_DOWNLOAD_PARALLELS=4
status_file=/root/autodl-tmp/qwen3.5-4b-download.status
printf '%s\n' "RUNNING $(date -Iseconds)" > "$status_file"
printf '%s\n' "Starting Qwen/Qwen3.5-4B download at $(date -Iseconds)"
/root/autodl-tmp/modelscope-download-env/bin/ms-hub download Qwen/Qwen3.5-4B --local-dir /root/autodl-tmp/models/Qwen3.5-4B --max-workers 4
result=$?
if [ "$result" -eq 0 ]; then
    printf '%s\n' "COMPLETED $(date -Iseconds)" > "$status_file"
else
    printf '%s\n' "FAILED exit=$result $(date -Iseconds)" > "$status_file"
fi
cat "$status_file"
exit "$result"
