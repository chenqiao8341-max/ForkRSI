#!/usr/bin/env bash
set -u
cd /root/autodl-tmp/ForkRSI
source scripts/forkrsi_env.sh
timeout 21600 python -u scripts/run_forkrsi_campaign.py final > runs/forkrsi/campaign-v2/final-worker.log 2>&1
export FORKRSI_FINAL_EXIT_CODE=$?
python - <<'EXITPY'
import os,json,time
from pathlib import Path
Path('runs/forkrsi/campaign-v2/final-exit.json').write_text(json.dumps({'exit_code':int(os.environ['FORKRSI_FINAL_EXIT_CODE']),'finished_unix':time.time()},indent=2)+'\n')
EXITPY
