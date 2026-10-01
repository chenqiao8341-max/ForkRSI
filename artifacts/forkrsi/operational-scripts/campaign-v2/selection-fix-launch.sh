#!/usr/bin/env bash
set -u
cd /root/autodl-tmp/ForkRSI
source scripts/forkrsi_env.sh
timeout 3600 python -u scripts/run_forkrsi_campaign.py search > runs/forkrsi/campaign-v2/selection-fix-worker.log 2>&1
export FORKRSI_SEARCH_EXIT_CODE=$?
python - <<'EXITPY'
import os,json,time
from pathlib import Path
Path('runs/forkrsi/campaign-v2/selection-fix-exit.json').write_text(json.dumps({'exit_code':int(os.environ['FORKRSI_SEARCH_EXIT_CODE']),'finished_unix':time.time()},indent=2)+'\n')
EXITPY
