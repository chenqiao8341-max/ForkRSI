"""Snapshot completed frozen final cells; does not alter experiment or selection."""
from __future__ import annotations
import json,sys,subprocess,os
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
ROOT=Path('/root/autodl-tmp/ForkRSI')
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'src'))
from audit_workflow_programs import audit
from forkmem.rsi.campaign import authenticated_result,load,save
from forkmem.rsi.qualification import reviewed_flags,qualify_row
from forkmem.environment import digest
from summarize_forkrsi import statistics,paired_interval
B=ROOT/'runs/forkrsi/campaign-v2'
os.chdir(ROOT)
subprocess.run(['/root/miniconda3/bin/python',str(B/'audit_final_inputs.py')],check=True)
checks=load(B/'final-control-invariants-progress.json')['checks']
by_id={r['episode_id']:r for r in checks}
rows=[]
for p in sorted((B/'evaluations/final').rglob('metrics.json')):
 r=load(p)
 if r['episode_id'] not in by_id: continue
 verified=authenticated_result(Path(r['episode_dir']))
 assert verified['success']==r['success'] and verified['log_sha256']==r['log_sha256']
 rows.append(r)
assert len(rows)==len(checks)
adapter=B/('program-review-final-snapshot-'+str(len(rows)))
adapter.mkdir(exist_ok=True)
save(adapter/'status.json',{'state':'complete','scope':'specified completed final cells only; whole campaign may remain incomplete'})
(adapter/'results.jsonl').write_text(''.join(json.dumps({'episode_dir':r['episode_dir']})+'\n' for r in rows))
audit(adapter,adapter/'program-audit.json')
screen=load(adapter/'program-audit.json')
reviews=load(B/'program-audit-review.json')
known={r['sha256'] for r in reviews['reviews']}
missing=[f for f in screen['flags'] if f['sha256'] not in known]
passes=load(B/'passing-program-reviews-final.json')
passed_ids={r['episode_id'] for r in passes['reviews']}
for flag in missing:
 print('UNREVIEWED_FLAG',json.dumps(flag,ensure_ascii=False))
pending=[]
for r in rows:
 if r['success'] and r['episode_id'] not in passed_ids:
  ep=Path(r['episode_dir'])
  pending.append(r['episode_id'])
  print('UNREVIEWED_PASS',json.dumps(r,ensure_ascii=False))
  print('EXACT_PASSING_CODE', (ep/'repo/solution.py').read_text())
  print('PUBLIC_README', (ep/'repo/README.md').read_text())
  print('PUBLIC_DEPLOYMENT', (ep/'repo/deployment.json').read_text())
  print('FULL_VERIFIER_LOG', (ep/'logs'/(r['execution_id']+'.log')).read_text())
now=datetime.now(timezone.utc)
save(B/'final-authenticated-progress.json',{
 'checked_utc':now.isoformat(),'final_campaign_complete':False,'completed_authenticated_episodes':len(rows),
 'episodes':[{'episode_id':r['episode_id'],'task_id':r['task_id'],'logical_final_mode':by_id[r['episode_id']]['logical_final_mode'],'evidence_mode':r['mode'],'compiler_id':r['compiler_id'],'success':r['success'],'log_sha256':r['log_sha256']} for r in rows]})
stats={}
if not missing and not pending:
 flags=reviewed_flags(screen,reviews)
 groups=defaultdict(list)
 for r in rows: groups[by_id[r['episode_id']]['logical_final_mode']].append(qualify_row(r,flags))
 if len(groups['none'])==8:
  complete={k:v for k,v in groups.items() if len(v)==8}
  stats={k:statistics(v,groups['none']) for k,v in sorted(complete.items())}
  save(B/'completed-controls-progress.json',{
   'checked_utc':now.isoformat(),'scope':'Wholly completed logical final arms only; frozen campaign remains incomplete','final_campaign_complete':False,
   'statistics':stats,'paired_from_none':{k:paired_interval(groups['none'],v) for k,v in sorted(complete.items()) if k!='none'},
   'statistical_unit':'8 semantic tasks, one seed; nested recovery cases are not independent samples',
   'qualification_note':'Every snapshot AST flag and complete passing program manually reviewed; this is not adversarial proof.'})
worker=load(B/'worker.json')
pid=worker['pid']
proc=Path('/proc')/str(pid)/'cmdline'
cmd=proc.read_bytes().replace(b'\0',b' ').decode() if proc.exists() else None
budget=0.75+(now-datetime.fromisoformat('2026-09-30T15:02:07.476404+00:00')).total_seconds()/3600*1.5
groups=defaultdict(lambda:{'completed':0,'raw_passes':0,'tokens':0})
for r in rows:
 g=groups[by_id[r['episode_id']]['logical_final_mode']]
 g['completed']+=1
 g['raw_passes']+=int(r['success'])
 g['tokens']+=r['usage']['total_tokens']
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
clean=not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],text=True)
progress={
 'checked_utc':now.isoformat(),'worker':worker,'actual_live_cmdline':cmd,'status':load(B/'status.json'),
 'completed_unique_final':len(rows),'by_mode':dict(groups),'manual_flag_reviews':len(reviews['reviews']),
 'final_passing_program_reviews':len(passes['reviews']),'expected_final_cells':56,'frozen_head':head,'tracked_clean':clean,
 'estimated_budget_spent_cny':budget,'estimated_budget_remaining_cny':200-budget,
 'scope':'unfinished seven-arm final grid; no strategy changes','unreviewed_flags':len(missing),'unreviewed_full_passes':pending}
save(B/'final-live-progress.json',progress)
print('PROGRESS',json.dumps(progress,ensure_ascii=False))
if stats: print('COMPLETED_ARM_STATS',json.dumps(stats,ensure_ascii=False))
