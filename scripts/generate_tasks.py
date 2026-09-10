"""Deterministic four-family benchmark construction; no model outcomes used."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def config_task(i: int, near: bool) -> tuple[dict[str, str], str, str]:
    key = [
        "quota",
        "workers",
        "capacity",
        "slots",
        "limit",
        "budget",
        "batch",
        "window",
    ][i]
    envkey = "APP_" + key.upper()
    contract = "file-over-environment" if near else "environment-over-file"
    readme = f"""Implement resolve(file_settings, environ, overrides) returning an integer.
The setting is {key!r}, environment variable {envkey!r}; built-in default is {20 + i}.
Explicit overrides have highest priority. Then follow the profile in profile.json.
An absent key advances to the next layer. A JSON null at a selected layer resets to the built-in default, without falling through. Empty environment strings mean absent; other values convert with int. Zero is valid.
"""
    files = {
        "solution.py": f"def resolve(file_settings, environ, overrides):\n    return int(overrides.get('{key}') or environ.get('{envkey}') or file_settings.get('{key}') or {20 + i})\n",
        "README.md": readme,
        "profile.json": json.dumps({"precedence": contract}),
    }
    layers = (
        f"[(overrides, '{key}'), (file_settings, '{key}'), (environ, '{envkey}')]"
        if near
        else f"[(overrides, '{key}'), (environ, '{envkey}'), (file_settings, '{key}')]"
    )
    reference = f"""def resolve(file_settings, environ, overrides):
    for mapping, key in {layers}:
        if key not in mapping:
            continue
        value = mapping[key]
        if mapping is environ and value == '':
            continue
        return {20 + i} if value is None else int(value)
    return {20 + i}
"""
    cases = [
        ({}, {}, {}, 20 + i),
        ({key: 7}, {envkey: "9"}, {}, 7 if near else 9),
        ({key: 7}, {envkey: "0"}, {}, 7 if near else 0),
        ({key: 0}, {envkey: "9"}, {}, 0 if near else 9),
        ({key: 7}, {envkey: "9"}, {key: None}, 20 + i),
        ({key: 7}, {envkey: ""}, {}, 7),
        ({key: 7}, {envkey: "9"}, {key: 0}, 0),
        ({key: None}, {envkey: None}, {}, 20 + i),
    ]
    verifier = f"from solution import resolve\nfor f,e,o,expected in {cases!r}:\n    actual = resolve(f,e,o)\n    assert actual == expected, (f,e,o,actual,expected)\n"
    return files, reference, verifier


def interval_task(i: int, near: bool) -> tuple[dict[str, str], str, str]:
    # Both profiles are conventional contracts; near-miss changes endpoint semantics.
    mode = "closed" if near else "half-open"
    files = {
        "solution.py": "def subtract(interval, blocked):\n    a,b=interval\n    return [(a, min(x,b)) for x,y in sorted(blocked) if a < x < b]\n",
        "README.md": f"""Implement subtract(interval, blocked): return sorted, nonempty maximal integer ranges remaining after removing the union of blocked ranges. Preserve interval's endpoint convention from contract.json. Inputs may overlap, repeat, touch, or extend outside the outer interval. Do not mutate inputs. Coordinates may be negative. Return list of tuples. Client edition {i}.
""",
        "contract.json": json.dumps({"endpoints": mode, "coordinate_type": "integer"}),
    }
    reference = f"""def subtract(interval, blocked):
    a,b=interval
    step={1 if near else 0}
    end=b+step
    cursor=a
    result=[]
    for x,y in sorted(blocked):
        y += step
        if y <= x or y <= cursor or x >= end:
            continue
        if x > cursor:
            result.append((cursor, min(x,end)-step))
        cursor=max(cursor,y)
        if cursor>=end:
            break
    if cursor<end:
        result.append((cursor,end-step))
    return result
"""
    # Oracle uses sets of integer points, independent of sweep implementation.
    verifier = f"""from solution import subtract
import random
rng=random.Random({120 + i})
for n in range(80):
    a=rng.randint(-8,1); b=rng.randint(2,12)
    blocks=[tuple(sorted((rng.randint(-10,14),rng.randint(-10,14)))) for _ in range(n%7)]
    original=list(blocks)
    points=set(range(a,b+{int(near)}))
    for x,y in blocks: points.difference_update(range(x,y+{int(near)}))
    expected=[]
    for x in sorted(points):
        if expected and x == expected[-1][1]+{1 if near else 0}: expected[-1]=(expected[-1][0],x+{0 if near else 1})
        else: expected.append((x,x+{0 if near else 1}))
    actual=subtract((a,b),blocks)
    assert actual == expected, ((a,b),blocks,actual,expected)
    assert blocks == original
"""
    return files, reference, verifier


def async_task(i: int, near: bool) -> tuple[dict[str, str], str, str]:
    key = [
        "request_id",
        "delivery_id",
        "message_id",
        "operation_id",
        "token",
        "job_id",
        "event_id",
        "call_id",
    ][i]
    mode = "new-per-attempt" if near else "stable-per-operation"
    files = {
        "solution.py": "async def deliver(client, payload, attempts, make_key, pause):\n    for i in range(attempts):\n        try:\n            return await client.send(payload, make_key())\n        except Exception:\n            await pause(i)\n    return None\n",
        "README.md": f"""Implement async deliver(client, payload, attempts, make_key, pause). client.send(payload, key) is async and returns a receipt. attempts is the total allowed sends; nonpositive attempts raise ValueError before any other calls. Consult protocol.json for key identity scope ({key}). Retry only TimeoutError, preserving the final exception when exhausted. Cancellation and other errors propagate. Between attempts await pause with delays 1, 2, 4,...; no pause after success or the last failure. Do not change payload.
""",
        "protocol.json": json.dumps({"key_scope": mode}),
    }
    reference = f"""async def deliver(client, payload, attempts, make_key, pause):
    if attempts <= 0: raise ValueError('attempts')
    {"key = None" if near else "key = make_key()"}
    for index in range(attempts):
        {"key = make_key()" if near else "# Reuse operation identity across uncertain sends."}
        try:
            return await client.send(payload, key)
        except TimeoutError:
            if index + 1 == attempts: raise
            await pause(2**index)
"""
    verifier = f"""import asyncio
from solution import deliver
async def check():
    for failures in range(4):
        keys=[]; pauses=[]; sends=[]; error=TimeoutError('uncertain delivery')
        def make_key():
            key=f'k{{len(keys)}}'; keys.append(key); return key
        async def pause(delay): pauses.append(delay)
        class Client:
            async def send(self,payload,key):
                sends.append(key)
                if len(sends)<=failures: raise error
                return {{'receipt': payload['value']}}
        payload={{'value':{i + 1}}}
        try:
            result=await deliver(Client(),payload,3,make_key,pause)
            assert failures<3 and result=={{'receipt':{i + 1}}}
        except TimeoutError as caught:
            assert failures==3 and caught is error
        assert len(sends)==min(failures+1,3)
        assert pauses==[1,2][:min(failures,2)], pauses
        assert len(keys)==(len(sends) if {near!r} else 1)
        assert sends==keys if {near!r} else len(set(sends))==1
        assert payload=={{'value':{i + 1}}}
    calls=[]
    def key(): calls.append('key'); return 'x'
    async def pause(delay): calls.append('pause')
    class Bad:
        async def send(self,payload,key): raise RuntimeError('fatal')
    try: await deliver(Bad(),{{}},0,key,pause)
    except ValueError: pass
    else: raise AssertionError('invalid attempts accepted')
    assert calls==[]
    try: await deliver(Bad(),{{}},3,key,pause)
    except RuntimeError: pass
    else: raise AssertionError('nonretryable swallowed')
    assert 'pause' not in calls
asyncio.run(check())
"""
    return files, reference, verifier


def merge_task(i: int, near: bool) -> tuple[dict[str, str], str, str]:
    mode = "literal-null" if near else "delete-null"
    files = {
        "solution.py": "def merge(document, patch):\n    result=dict(document)\n    result.update(patch)\n    return result\n",
        "README.md": f"""Implement merge(document, patch) for the patch profile in schema.json. Object patches recursively merge object members; merging an object into a non-object starts from an empty object. Non-object patches replace the entire value. Arrays are atomic replacement values. Neither input may be mutated, and output mutable containers must not alias either input. Profile edition {i}; keys and values are arbitrary JSON values.
""",
        "schema.json": json.dumps({"null_member_semantics": mode}),
    }
    reference = f"""import copy
def merge(document, patch):
    if not isinstance(patch,dict): return copy.deepcopy(patch)
    result=copy.deepcopy(document) if isinstance(document,dict) else {{}}
    for key,value in patch.items():
        if value is None and {not near!r}: result.pop(key,None)
        else: result[key]=merge(result.get(key),value)
    return result
"""
    k = f"field_{i}"
    cases = [
        ({k: 1}, {k: None}, {k: None} if near else {}),
        (
            {"nested": {"a": 1, "b": 2}},
            {"nested": {"a": None, "c": 3}},
            {"nested": {"a": None, "b": 2, "c": 3}}
            if near
            else {"nested": {"b": 2, "c": 3}},
        ),
        (7, {"x": {"y": 2}}, {"x": {"y": 2}}),
        ({"x": [1, 2]}, {"x": [3]}, {"x": [3]}),
        ({"x": 1}, None, None),
        ([1, 2], [3], [3]),
        ({}, {"missing": None}, {"missing": None} if near else {}),
    ]
    verifier = f"""from solution import merge
import copy
for document,patch,expected in {cases!r}:
    before=copy.deepcopy((document,patch))
    result=merge(document,patch)
    assert result==expected, (document,patch,result,expected)
    assert (document,patch)==before
    if isinstance(result,dict): result['touch']=1
    if isinstance(result,list): result.append('touch')
    assert (document,patch)==before, 'aliasing root'
doc={{'nested':{{'items':[1,2]}}}}; patch={{'extra':{{'items':[3]}}}}
result=merge(doc,patch)
result['nested']['items'].append(4); result['extra']['items'].append(5)
assert doc=={{'nested':{{'items':[1,2]}}}} and patch=={{'extra':{{'items':[3]}}}}, 'aliasing nested'
"""
    return files, reference, verifier


def main() -> None:
    index: list[dict[str, Any]] = []
    for family, factory in [
        ("config_precedence", config_task),
        ("interval_contract", interval_task),
        ("async_retry", async_task),
        ("json_merge", merge_task),
    ]:
        for i in range(8):
            split = "train" if i < 3 else "held_out" if i < 6 else "near_miss"
            files, reference, verifier = factory(i, split == "near_miss")
            task_id = f"{family}_{i:02}"
            features = {
                "profile": json.loads(
                    next(v for k, v in files.items() if k.endswith(".json"))
                )[
                    next(
                        iter(
                            json.loads(
                                next(v for k, v in files.items() if k.endswith(".json"))
                            )
                        )
                    )
                ]
            }
            task = {
                "task_id": task_id,
                "family": family,
                "split": split,
                "description": "Repair solution.py to satisfy this repository's documented API and data contract. Inspect the provided files; preserve the public function signature.",
                "features": features,
                "files": files,
                "verifier": "import sys\nsys.path.insert(0, '/task')\n"
                + verifier
                + "\nprint('FORKMEM_VERIFIER_COMPLETE')\n",
                "dataset_version": "microrepo-v1",
            }
            path = ROOT / "data/task_specs" / f"{task_id}.json"
            path.write_text(json.dumps(task, indent=2) + "\n")
            (ROOT / "data/reference_solutions" / f"{task_id}.py").write_text(reference)
            index.append(
                {
                    "task_id": task_id,
                    "family": family,
                    "split": split,
                    "path": str(path.relative_to(ROOT)),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    (ROOT / "data/task_manifest.json").write_text(
        json.dumps({"version": "microrepo-v1", "tasks": index}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
