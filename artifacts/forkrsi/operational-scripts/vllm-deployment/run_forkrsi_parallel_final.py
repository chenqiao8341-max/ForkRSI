"""Parallel backend replication of the already selected frozen ForkRSI final arms."""
from __future__ import annotations
import argparse,asyncio,fcntl,json,os,time,traceback,subprocess
from pathlib import Path
from typing import Any
import httpx
from transformers import AutoTokenizer
from forkmem.agent import run_task
from forkmem.environment import digest,git
from forkmem.llm import LLMClient
from forkmem.rsi.campaign import authenticated_result,load,save,usage,score
from forkmem.rsi.ledger import sha

def protected_core(old_revision:str)->dict[str,str]:
    names=git(Path.cwd(),"ls-tree","-r","--name-only",old_revision,"src").splitlines()
    result={}
    for name in names:
        before=subprocess.check_output(["git","show",old_revision+":"+name])
        actual=Path(name).read_bytes()
        if actual!=before:raise ValueError("Original execution/validation core changed: "+name)
        result[name]=digest(actual)
    return result

def verify_memories(path:Path)->dict[str,Any]:
    snapshot=load(path)
    value=snapshot["value"]
    if sha(value)!=snapshot["sha256"]:raise ValueError("Frozen memory snapshot changed")
    authorized=load(Path("runs/forkrsi/vllm-deployment/user-requested-migration.json"))
    if snapshot["sha256"]!=authorized["frozen_memory_snapshot_sha256"]:raise ValueError("User-requested unchanged-memory snapshot changed")
    old=value["old_final_seal"]
    if sha(old["value"])!=old["seal_sha256"]:raise ValueError("Original seal changed")
    origin=Path(value["old_campaign"])
    if load(origin/"final-freeze.json")!=old:raise ValueError("Original final seal mismatch")
    protocol=value["protocol"]
    manifest=load(Path(protocol["manifest"]))
    if digest(Path(protocol["manifest"]).read_bytes())!=old["value"]["inputs"]["manifest_sha256"]:
        raise ValueError("Original task manifest changed")
    definitions={e["task_id"]:e for e in manifest["tasks"] if e["split"]=="final"}
    expected={(mode,task,seed) for mode in protocol["final_modes"] for task in definitions for seed in protocol["task_seeds"]}
    actual={(r["logical_final_mode"],r["task_id"],r["seed"]) for r in value["cells"]}
    if actual!=expected or len(actual)!=len(value["cells"]):raise ValueError("Final grid changed")
    tokenizer=AutoTokenizer.from_pretrained(protocol["model_path"],local_files_only=True)
    pools=load(origin/"pools.json")["pools"]
    search=load(origin/"search-result.json")
    for row in value["cells"]:
        entry=definitions[row["task_id"]]
        if row["task_path"]!=entry["path"] or row["task_definition_sha256"]!=entry["sha256"]:
            raise ValueError("Task identity changed")
        if digest(Path(entry["path"]).read_bytes())!=entry["sha256"]:raise ValueError("Task/verifier/initial files changed")
        meta=row["memory_meta"]
        if digest(row["memory_body"].encode())!=meta["memory_sha256"]:raise ValueError("Memory body changed")
        if len(tokenizer.encode(row["memory_body"],add_special_tokens=False))!=meta["tokens"]:raise ValueError("Memory tokenizer count changed")
        candidates=pools[row["task_id"]]["candidate_positive_ids"]
        if meta["candidate_positive_ids"]!=candidates or not set(row["injected_positive_ids"])<=set(candidates):
            raise ValueError("Successful source IDs changed")
        mode=row["logical_final_mode"]
        expected_c=search["C0"]
        if mode.endswith("_evolved"):expected_c=old["value"]["selections"][mode.removesuffix("_evolved")]["C"]
        expected_evidence=mode.removesuffix("_evolved").removesuffix("_initial")
        if row["compiler_id"]!=expected_c or row["evidence_mode"]!=expected_evidence:raise ValueError("Preselected arm changed")
        cap=0 if mode=="none" else protocol["original_token_cap"] if mode in {"flat_verified","fork_verified"} else protocol["compiler_token_cap"]
        if meta["tokens"]>cap:raise ValueError("Memory cap changed")
    source=Path("/root/autodl-tmp/ForkRSI/runs/forkrsi/source-package-v1")
    inputs=old["value"]["inputs"]
    for name,key in [("corpus.json","corpus_sha256"),("manifest.json","source_manifest_sha256"),("program-audit.json","source_program_audit_sha256"),("program-audit-review.json","source_program_review_sha256")]:
        if digest((source/name).read_bytes())!=inputs[key]:raise ValueError("Original source evidence changed: "+name)
    return snapshot

def freeze(args:argparse.Namespace)->None:
    snapshot=verify_memories(args.memories)
    value=snapshot["value"]
    old=value["old_final_seal"]["value"]
    if git(Path.cwd(),"status","--porcelain"):raise ValueError("Commit additive deployment code before sealing")
    worker=load(Path(value["old_campaign"])/"worker.json")
    proc=Path("/proc")/str(worker["pid"])/"cmdline"
    if proc.exists() and b"run_forkrsi_campaign.py" in proc.read_bytes():
        raise ValueError("Close the legacy worker before backend migration seal")
    health=httpx.get("http://127.0.0.1:8000/health",timeout=10,trust_env=False).json()
    if not health.get("ready") or health.get("backend")!="vllm" or health["active"]:
        raise ValueError("vLLM must be ready and idle before sealing")
    core=protected_core(old["inputs"]["code_revision"])
    protocol=dict(value["protocol"])
    protocol.update(version="forkrsi-vllm-backend-replication-v1",episode_concurrency=args.concurrency,
        request_budget=len(value["cells"])*protocol["max_steps"]*4,
        task_backend="vllm-0.21.0-bfloat16",compiled_memory_policy="Reuse exact preselected cached Transformers extraction outputs; no new source/C/I proposals or selection",
        interpretation="User-requested backend replication on the same final semantic tasks; prior opened outcomes retained and not used for strategy changes. Not new unseen tasks or independent samples.")
    save(args.root/"protocol.json",protocol)
    origin=Path(value["old_campaign"])
    (args.root/"pools.json").write_bytes((origin/"pools.json").read_bytes())
    (args.root/"search-result.json").write_bytes((origin/"search-result.json").read_bytes())
    value_new={
        "inputs":{**old["inputs"],"code_revision":git(Path.cwd(),"rev-parse","HEAD"),"protocol_sha256":digest((args.root/"protocol.json").read_bytes())},
        "protocol":protocol,"selections":old["selections"],"pools_sha256":digest((args.root/"pools.json").read_bytes()),
        "created_unix":time.time(),"final_outcomes_opened":False,
        "original_final_seal_sha256":value["old_final_seal"]["seal_sha256"],
        "original_memory_snapshot_sha256":snapshot["sha256"],"memories_path":str(args.memories.resolve()),
        "original_core_sha256":core,"backend_startup":{k:v for k,v in health.items() if k not in {"ready","active","peak_active"}},
        "backend_launcher_sha256":digest(Path("runs/forkrsi/vllm-deployment/start_vllm.sh").read_bytes()),
        "user_migration_record_sha256":digest(Path("runs/forkrsi/vllm-deployment/user-requested-migration.json").read_bytes()),
        "runtime_sha256":health["runtime_freeze_sha256"],
    }
    save(args.root/"final-freeze.json",{"seal_sha256":sha(value_new),"value":value_new})
    save(args.root/"status.json",{"state":"sealed","final_outcomes_opened":False,"expected_cells":len(value["cells"])})
    print(json.dumps({"sealed_cells":len(value["cells"]),"concurrency":args.concurrency,"seal_sha256":sha(value_new)}),flush=True)

async def evaluate(args:argparse.Namespace)->None:
    seal=load(args.root/"final-freeze.json")
    frozen=seal["value"]
    if sha(frozen)!=seal["seal_sha256"]:raise ValueError("vLLM seal changed")
    if git(Path.cwd(),"status","--porcelain") or git(Path.cwd(),"rev-parse","HEAD")!=frozen["inputs"]["code_revision"]:
        raise ValueError("Sealed code changed")
    snapshot=verify_memories(Path(frozen["memories_path"]))
    if snapshot["sha256"]!=frozen["original_memory_snapshot_sha256"]:raise ValueError("Sealed memory snapshot changed")
    protected_core(snapshot["value"]["old_final_seal"]["value"]["inputs"]["code_revision"])
    if digest((args.root/"protocol.json").read_bytes())!=frozen["inputs"]["protocol_sha256"]:raise ValueError("Protocol changed")
    if digest((args.root/"pools.json").read_bytes())!=frozen["pools_sha256"]:raise ValueError("Pool changed")
    if digest(Path("runs/forkrsi/vllm-deployment/user-requested-migration.json").read_bytes())!=frozen["user_migration_record_sha256"]:raise ValueError("Migration record changed")
    if digest(Path("runs/forkrsi/vllm-deployment/start_vllm.sh").read_bytes())!=frozen["backend_launcher_sha256"]:raise ValueError("Serving launcher changed")
    health=httpx.get("http://127.0.0.1:8000/health",timeout=10,trust_env=False).json()
    if not health.get("ready") or health.get("backend")!="vllm":raise ValueError("vLLM not ready")
    if {k:v for k,v in health.items() if k not in {"ready","active","peak_active"}}!=frozen["backend_startup"]:
        raise ValueError("Sealed serving backend changed")
    protocol=frozen["protocol"]
    cells=snapshot["value"]["cells"]
    modes=protocol["final_modes"]
    tasks=list(dict.fromkeys(r["task_id"] for r in cells))
    cells=sorted(cells,key=lambda r:(tasks.index(r["task_id"]),modes.index(r["logical_final_mode"]),r["seed"]))
    sem=asyncio.Semaphore(protocol["episode_concurrency"])
    rows=[]
    save(args.root/"worker.json",{"pid":os.getpid(),"phase":"final","driver":str(Path(__file__).resolve()),"started_unix":time.time()})
    save(args.root/"status.json",{"state":"running","phase":"final","backend":"vllm","final_outcomes_opened":True,"completed":0,"expected_cells":len(cells)})
    async def cell(row:dict[str,Any])->dict[str,Any]:
        async with sem:
            target=args.root/"evaluations/final"/row["evidence_mode"]/row["compiler_id"]/f"seed-{row['seed']}"/row["task_id"]
            meta=row["memory_meta"]
            metrics=target/"metrics.json"
            if metrics.exists():
                result=load(metrics)
                actual=authenticated_result(target)
                if actual["success"]!=result["success"] or actual["log_sha256"]!=result["log_sha256"] or load(target/"compiler-memory.json")!=meta:
                    raise ValueError("Completed cache authentication mismatch")
            else:
                if target.exists():raise ValueError("Incomplete episode requires native-checkpoint audit; fresh rerun forbidden: "+str(target))
                target.parent.mkdir(parents=True,exist_ok=True)
                client=LLMClient(target.parent/(target.name+"-llm.jsonl"),concurrency=1,request_budget=protocol["max_steps"]*4)
                try:
                    metadata=await run_task(Path(row["task_path"]),target,client,mode=row["evidence_mode"],seed=row["seed"],max_steps=protocol["max_steps"],
                        prepared_memory=(row["memory_body"],row["injected_positive_ids"]))
                finally:await client.close()
                save(target/"compiler-memory.json",meta)
                actual=authenticated_result(target)
                result={**actual,"task_id":row["task_id"],"seed":row["seed"],"mode":row["evidence_mode"],"logical_final_mode":row["logical_final_mode"],
                    "compiler_id":row["compiler_id"],"candidate_positive_ids":meta["candidate_positive_ids"],"injected_positive_ids":row["injected_positive_ids"],
                    "memory_tokens":meta["tokens"],"usage":usage(client.log_path),"episode_dir":str(target),"episode_id":metadata["episode_id"],
                    "evidence_id":"episode:"+metadata["episode_id"],"backend":"vllm","memory_snapshot_sha256":snapshot["sha256"]}
                save(metrics,result)
            rows.append(result)
            save(args.root/"status.json",{"state":"running","phase":"final","backend":"vllm","final_outcomes_opened":True,"completed":len(rows),"expected_cells":len(cells),
                "last_task":row["task_id"],"last_mode":row["logical_final_mode"],"success":result["success"]})
            print(json.dumps({"completed":len(rows),"mode":row["logical_final_mode"],"task_id":row["task_id"],"success":result["success"]}),flush=True)
            return result
    outcomes=await asyncio.gather(*(cell(r) for r in cells),return_exceptions=True)
    errors=[repr(r) for r in outcomes if isinstance(r,BaseException)]
    if errors:
        save(args.root/"status.json",{"state":"interrupted_or_failed","final_outcomes_opened":True,"completed":len(rows),"errors":errors})
        raise RuntimeError("Some actual final cells did not close; records retained")
    results={}
    for mode in modes:
        group=[r for r in rows if r["logical_final_mode"]==mode]
        group.sort(key=lambda r:(tasks.index(r["task_id"]),r["seed"]))
        results[mode]={"stage":"final","mode":group[0]["mode"],"compiler_id":group[0]["compiler_id"],"split":"final","rows":group,"score":score(group)}
    assert len(rows)==len(cells)==56
    save(args.root/"final-result.json",{"seal_sha256":seal["seal_sha256"],"results":results,"completed_unix":time.time(),"backend":"vllm"})
    save(args.root/"status.json",{"state":"complete","final_outcomes_opened":True,"completed":len(rows),"backend":"vllm"})

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("phase",choices=["freeze","final"])
    parser.add_argument("--root",type=Path,default=Path("runs/forkrsi/campaign-vllm-final-v1"))
    parser.add_argument("--memories",type=Path,default=Path("runs/forkrsi/vllm-deployment/frozen-task-memories.json"))
    parser.add_argument("--concurrency",type=int,default=8,choices=[1,4,8])
    args=parser.parse_args()
    args.root=args.root.resolve()
    args.root.mkdir(parents=True,exist_ok=True)
    with (args.root/"worker.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.phase=="freeze":
            if (args.root/"final-freeze.json").exists():raise ValueError("Existing seal cannot be replaced")
            freeze(args)
        else:
            try:asyncio.run(evaluate(args))
            except BaseException:
                save(args.root/"failure.json",{"time":time.time(),"traceback":traceback.format_exc()})
                raise
if __name__=="__main__":main()
