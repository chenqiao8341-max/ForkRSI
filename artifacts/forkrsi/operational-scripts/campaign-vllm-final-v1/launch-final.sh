#!/bin/bash
set -uo pipefail
cd /root/autodl-tmp/ForkRSI
source scripts/forkrsi_env.sh
python scripts/check_forkrsi_budget.py --reserve-hours 4 || exit $?
python -u scripts/run_forkrsi_parallel_final.py final
task_exit_code=$?
/root/miniconda3/bin/python - "$task_exit_code" <<'PY'
import json,sys,time
from pathlib import Path
Path("runs/forkrsi/campaign-vllm-final-v1/final-exit.json").write_text(json.dumps({"exit_code":int(sys.argv[1]),"ended_unix":time.time()},indent=2)+"\n")
PY
exit "$task_exit_code"
