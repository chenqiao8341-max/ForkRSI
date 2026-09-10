# Reproduce the eight-action publication

Install with `uv sync --locked`. Run `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src`. Linux/git/Bubblewrap/util-linux and sandbox `/usr/bin/python3` are required.

For an offline replay of the shared source falsification case and the eight-action transfer cases:

```bash
bash scripts/demo_workflows.sh
```

Generate a fresh source corpus and eight-action transfer run from a clean committed checkout with an available local model service:

```bash
uv run forkmem benchmark --config configs/experiments/v2/source.yaml --output runs/my-source
uv run python scripts/run_workflow_transfer.py --source runs/my-source --output runs/my-transfer
uv run python scripts/report_workflow_transfer.py --runs runs/my-transfer
uv run python scripts/export_workflow_comparisons.py --runs runs/my-transfer --replays runs/my-case-replays
```

Shared source collection retains the original source action settings. Only transfer uses the eight-action comparison budget. Keep total model request concurrency within eight. Fresh generated responses need not match archived programs byte for byte.

The recorded publication is an explicitly labelled filtered archival view at local `runs/eight-action-recorded`. Full raw episodes/request bodies remain local and are not in Git. Committed summary rows, request indexes, task fixtures and portable cases support inspection and deterministic case replay. The original source/transfer revision hashes identify local research snapshots and are provenance identifiers, not ancestors guaranteed to exist in this standalone publication history. The presentation focus was selected after the experiment.
