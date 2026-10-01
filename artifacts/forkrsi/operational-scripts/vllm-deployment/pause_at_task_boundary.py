"""Pause the legacy worker immediately after an atomic completed-cell metrics write."""
import os,json,ctypes,select,struct,time,signal
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path("/root/autodl-tmp/ForkRSI")
D=ROOT/"runs/forkrsi/vllm-deployment"
C=ROOT/"runs/forkrsi/campaign-v2"
assert (D/"install-complete.txt").exists()
assert json.loads((D/"install-exit.json").read_text())["exit_code"]==0
worker=json.loads((C/"worker.json").read_text())
pid=worker["pid"]
proc=Path("/proc")/str(pid)/"cmdline"
assert proc.exists() and b"run_forkrsi_campaign.py final" in proc.read_bytes().replace(b"\0",b" ")
snapshot=json.loads((D/"frozen-task-memories.json").read_text())
paths=[C/"evaluations/final"/r["evidence_mode"]/r["compiler_id"]/f"seed-{r['seed']}"/r["task_id"] for r in snapshot["value"]["cells"]]
initial=sum((p/"metrics.json").exists() for p in paths)
lib=ctypes.CDLL(None,use_errno=True)
fd=lib.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
if fd<0:raise OSError(ctypes.get_errno(),"inotify_init1")
watches={}
def register():
 for p in {parent for target in paths for parent in [target,target.parent,target.parent.parent,target.parent.parent.parent]}:
  if p.is_dir() and p not in watches.values():
   wd=lib.inotify_add_watch(fd,os.fsencode(p),0x8|0x80|0x100)
   if wd<0:raise OSError(ctypes.get_errno(),"inotify_add_watch "+str(p))
   watches[wd]=p
register()
print(json.dumps({"watching_pid":pid,"completed_before":initial}),flush=True)
deadline=time.monotonic()+1200
try:
 while time.monotonic()<deadline:
  if not proc.exists():raise RuntimeError("legacy worker ended before boundary pause")
  ready,_,_=select.select([fd],[],[],0.2)
  if not ready:
   register();continue
  buf=os.read(fd,65536)
  offset=0
  pause=None
  while offset<len(buf):
   wd,mask,cookie,length=struct.unpack_from("iIII",buf,offset)
   name=buf[offset+16:offset+16+length].split(b"\0",1)[0].decode()
   offset+=16+length
   if name=="metrics.json" and mask&(0x8|0x80):
    pause=watches[wd]/name;break
  if pause is not None:
   os.kill(pid,signal.SIGSTOP)
   row=json.loads(pause.read_text())
   completed=sum((p/"metrics.json").exists() for p in paths)
   assert completed>initial
   record={"checked_utc":datetime.now(timezone.utc).isoformat(),"pid":pid,"state":"paused_at_completed_task_boundary",
    "reason":"Explicit user request to deploy vLLM and accelerate with parallel independent tasks; original partial final data/costs retained without mixed-backend aggregation.",
    "completed_before":initial,"completed_at_pause":completed,"last_completed_metrics":str(pause),"last_completed_episode_id":row["episode_id"],
    "old_model_service_log_lines":len((ROOT/"runs/forkrsi/model-service/requests.jsonl").read_text().splitlines()),
    "proc_status":(Path("/proc")/str(pid)/"status").read_text(),
    "frozen_task_memory_snapshot_sha256":snapshot["sha256"]}
   (D/"backend-migration-boundary.json").write_text(json.dumps(record,indent=2)+"\n")
   print(json.dumps(record,ensure_ascii=False),flush=True)
   break
  register()
 else:raise TimeoutError("no completed task boundary within 20 minutes")
finally:os.close(fd)
