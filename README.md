# ForkMem

ForkMem tests whether execution-verified counterfactual memory helps coding agents transfer operational decisions. It preserves a failed program and executed alternatives from the same checkpoint, then retrieves successful code together with aligned failure/recovery diagnostics.

This publication focuses on **eight coding actions** across migration, release, durable ingestion and compensation workflows. The primary displayed comparison gives flat verified memory and paired ForkMem the same positive source programs and IDs.

| Condition | Complete workflow success |
|---|---:|
| No memory | 42/48 (87.5%) |
| Flat verified code | 45/48 (93.8%) |
| Paired ForkMem | 47/48 (97.9%) |

The paired difference is **+4.2 percentage points**, task-cluster 95% bootstrap interval **[0,+12.5]**. This is a feasibility signal, not established general superiority. The eight-action presentation focus was selected after the original experiment; all eight memory conditions within this budget are retained. Source evidence, model outputs and task bytes have not been altered or regenerated.

Read the [analysis and cases](docs/v2/results_analysis.md), [complete tables](docs/v2/final_report.md), [protocol](docs/v2/protocol.md), [architecture](docs/v2/architecture.md), and [reproduction guide](docs/v2/reproduce.md).

## Run

Requires Linux, git, uv, Bubblewrap and util-linux. Orchestration uses Python 3.13; sandbox programs use `/usr/bin/python3`.

```bash
uv sync --locked
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
bash scripts/demo_workflows.sh
```

The demo replays archived source and eight-action transfer cases without a model service. Fresh experiments use the local OpenAI-compatible endpoint configured through `.env.example` variables (automatic dotenv loading is not implemented). Keep total model concurrency within eight requests.

## Publication scope

This standalone publication history contains the eight-action transfer results, shared source evidence, workflow fixtures and reusable implementation/tests. Earlier research history is retained locally and is not an ancestor of this branch. Shared source training retains its original collection settings; changing them would require collecting a different memory corpus. Test-only small action budgets exercise recovery and accounting, not additional empirical comparisons.

There are **384 condition cells, 264 actual model episodes, 16 held-out semantic contexts and three seeds**. Exact-input aliases are recorded and not treated as independent replications. Committed cases can be replayed; complete raw request bodies remain in local `runs/` directories. See the delivery manifest for publication hashes.
