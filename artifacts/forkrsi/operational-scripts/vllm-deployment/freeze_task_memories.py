"""Freeze unchanged final memories from existing source-extraction cache, without model calls."""
import asyncio,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from forkmem.rsi.campaign import Campaign,load,save
from forkmem.rsi.ledger import sha
ROOT=Path("/root/autodl-tmp/ForkRSI")
OLD=ROOT/"runs/forkrsi/campaign-v2"
OUT=ROOT/"runs/forkrsi/vllm-deployment/frozen-task-memories.json"
async def main():
 c=Campaign(OLD,ROOT/"runs/forkrsi/source-package-v1",ROOT/"configs/forkrsi/protocol-v1.json")
 async def forbidden(*args,**kwargs):
  raise RuntimeError("No new extraction/model calls allowed during backend migration")
 c.client.generate=forbidden
 try:
  seal=load(OLD/"final-freeze.json")
  assert sha(seal["value"])==seal["seal_sha256"]
  assert c.check_inputs()==seal["value"]["inputs"]
  rows=[]
  for logical in c.protocol["final_modes"]:
   if logical.endswith("_evolved"):
    evidence=logical.removesuffix("_evolved")
    compiler=seal["value"]["selections"][evidence]["C"]
   elif logical.endswith("_initial"):
    evidence=logical.removesuffix("_initial");compiler=c.c0
   else:evidence=logical;compiler=c.c0
   for entry in c.manifest["tasks"]:
    if entry["split"]!="final":continue
    body,injected,info=await c.memory(compiler,evidence,entry["task_id"])
    for seed in c.protocol["task_seeds"]:
     meta={**info,"memory_sha256":hashlib.sha256(body.encode()).hexdigest(),"injected_positive_ids":injected}
     old_path=OLD/"evaluations/final"/evidence/compiler/f"seed-{seed}"/entry["task_id"]/"metrics.json"
     if old_path.exists():
      previous=load(old_path)
      assert load(Path(previous["episode_dir"])/"compiler-memory.json")==meta
     rows.append({
      "logical_final_mode":logical,"evidence_mode":evidence,"compiler_id":compiler,
      "task_id":entry["task_id"],"task_path":entry["path"],"task_definition_sha256":entry["sha256"],"seed":seed,
      "memory_body":body,"injected_positive_ids":injected,"memory_meta":meta,
      "previous_complete_cell_exists":old_path.exists(),
     })
  assert len(rows)==56
  value={"created_utc":datetime.now(timezone.utc).isoformat(),"old_campaign":str(OLD),
   "old_final_seal":seal,"policy":"User requested vLLM migration. Preselected C/I, all 56 prompt memories, task/verifier/initial files and per-task budgets unchanged. No extraction, proposal or reselection after final outcomes.",
   "protocol":c.protocol,"cells":rows,"auxiliary_model_calls":0}
  save(OUT,{"sha256":sha(value),"value":value})
  print(json.dumps({"frozen_cells":len(rows),"snapshot_sha256":sha(value),"new_model_calls":0}))
 finally:await c.close()
asyncio.run(main())
