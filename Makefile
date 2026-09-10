.PHONY: test check smoke replay

test:
	uv run pytest -q

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src

smoke:
	uv run forkmem smoke

replay:
	bash scripts/demo_workflows.sh
