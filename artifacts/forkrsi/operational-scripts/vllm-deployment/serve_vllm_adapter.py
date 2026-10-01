"""Text-only parallel vLLM adapter preserving the original prompt/sampling policy."""
from __future__ import annotations
import asyncio,hashlib,json,time,os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
import httpx
from fastapi import FastAPI,HTTPException,Request
from transformers import AutoTokenizer
ROOT=Path("/root/autodl-tmp/ForkRSI")
MODEL=Path("/root/autodl-tmp/models/Qwen3.5-4B")
LOG=ROOT/"runs/forkrsi/model-service-vllm"
LOG.mkdir(parents=True,exist_ok=True)
TOKENIZER=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
ENGINE=os.getenv("FORKRSI_VLLM_ENGINE_URL","http://127.0.0.1:8002")
LIMIT=int(os.getenv("FORKRSI_VLLM_CONCURRENCY","8"))
SEM=asyncio.Semaphore(LIMIT)
ACTIVE=0
PEAK=0
STARTUP={
 "backend":"vllm","model":"Qwen3.5-4B","model_dir":str(MODEL),
 "weights_frozen":True,"dtype":"bfloat16","concurrency_limit":LIMIT,
 "started_unix":time.time(),"engine_url":ENGINE,
 "adapter_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 "config_sha256":hashlib.sha256((MODEL/"config.json").read_bytes()).hexdigest(),
 "prompt_policy":"Original Transformers tokenizer renders exact thinking-disabled chat prompt; pretokenized IDs go to vLLM /v1/completions.",
 "sampling_policy":"Per-request seed, temperature/top_p; top_k=-1, penalties disabled; generation-config=vllm. No bitwise determinism claim.",
 "structured_output":"Prompted JSON only, client strict validation/four-attempt repair. response_format is not forwarded, matching the former service.",
 "stop_token_ids":[248044],
 "runtime_freeze_sha256":hashlib.sha256((ROOT/"runs/forkrsi/vllm-deployment/runtime-freeze.txt").read_bytes()).hexdigest(),
}
(LOG/"startup.json").write_text(json.dumps(STARTUP,indent=2)+"\n")
def record(name,event):
 with (LOG/name).open("a") as f: f.write(json.dumps(event,ensure_ascii=False)+"\n")
@asynccontextmanager
async def lifespan(app):
 app.state.client=httpx.AsyncClient(timeout=900,trust_env=False,limits=httpx.Limits(max_connections=32,max_keepalive_connections=16))
 yield
 await app.state.client.aclose()
app=FastAPI(lifespan=lifespan)
@app.get("/health")
async def health():
 try:
  response=await app.state.client.get(ENGINE+"/health",timeout=5)
  ready=response.status_code==200
 except httpx.HTTPError:
  ready=False
 return {**STARTUP,"ready":ready,"active":ACTIVE,"peak_active":PEAK}
@app.post("/tokenize")
async def tokenize(body:dict):
 ids=TOKENIZER.encode(body.get("prompt",""),add_special_tokens=bool(body.get("add_special_tokens",False)))
 return {"count":len(ids),"tokens":ids}
@app.post("/v1/chat/completions")
async def complete(body:dict,request:Request):
 global ACTIVE,PEAK
 messages=body.get("messages")
 if not isinstance(messages,list) or any(not isinstance(m,dict) or not isinstance(m.get("content",""),str) for m in messages):
  raise HTTPException(400,"messages must be a list of text-only message objects")
 maximum=int(body.get("max_tokens",3000))
 if not 1<=maximum<=8192: raise HTTPException(400,"max_tokens must be 1..8192")
 if body.get("chat_template_kwargs",{}).get("enable_thinking",False): raise HTTPException(400,"thinking is fixed off")
 if body.get("model","Qwen3.5-4B")!="Qwen3.5-4B": raise HTTPException(400,"model is fixed")
 prompt=TOKENIZER.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
 ids=TOKENIZER.encode(prompt,add_special_tokens=True)
 if len(ids)>24000: raise HTTPException(400,"experimental prompt ceiling is 24000 tokens")
 seed=int(body.get("seed",0))
 start=time.monotonic()
 task_id=uuid4().hex
 event={
  "service_request_id":task_id,"client_request_id":request.headers.get("X-Request-ID"),
  "seed":seed,"prompt_tokens":len(ids),"max_tokens":maximum,
  "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),
  "prompt_token_ids_sha256":hashlib.sha256(json.dumps(ids,separators=(",",":")).encode()).hexdigest(),
  "temperature":float(body.get("temperature",0.3)),"top_p":float(body.get("top_p",1)),
  "accepted_unix":time.time(),"response_format_forwarded":False,
 }
 record("accepted.jsonl",event)
 async with SEM:
  ACTIVE+=1
  PEAK=max(PEAK,ACTIVE)
  event["generation_start_unix"]=time.time()
  event["active_at_start"]=ACTIVE
  try:
   response=await app.state.client.post(ENGINE+"/v1/completions",json={
    "model":"Qwen3.5-4B","prompt":ids,"max_tokens":maximum,
    "seed":seed,"temperature":event["temperature"],"top_p":event["top_p"],
    "stop_token_ids":[248044],"top_k":-1,"min_p":0,"repetition_penalty":1,"presence_penalty":0,"frequency_penalty":0,
   })
   response.raise_for_status()
   result=response.json()
   usage=result["usage"]
   if usage["prompt_tokens"]!=len(ids) or usage["total_tokens"]!=usage["prompt_tokens"]+usage["completion_tokens"]:
    raise ValueError("vLLM usage/prompt-token alignment mismatch")
   choice=result["choices"][0]
   content=choice["text"]
   event.update(status="complete",usage=usage,finish_reason=choice.get("finish_reason"),
    backend_response_id=result.get("id"),response_sha256=hashlib.sha256(content.encode()).hexdigest())
   return {"id":"forkrsi-vllm-"+task_id,"object":"chat.completion","model":"Qwen3.5-4B",
    "choices":[{"index":0,"message":{"role":"assistant","content":content},"finish_reason":choice.get("finish_reason")}],
    "usage":usage}
  except BaseException as exc:
   event.update(status="failed_or_cancelled",error_type=type(exc).__name__,error=str(exc)[:800])
   raise
  finally:
   ACTIVE-=1
   event["finished_unix"]=time.time()
   event["latency_seconds"]=time.monotonic()-start
   record("requests.jsonl",event)
if __name__=="__main__":
 import uvicorn
 uvicorn.run(app,host="127.0.0.1",port=8000)
