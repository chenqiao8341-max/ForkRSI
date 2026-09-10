import json
from pathlib import Path

import pytest
from langgraph.store.memory import InMemoryStore

from forkmem.langgraph_store import LangGraphForkStore
from forkmem.memory import ForkStore, retrieve
from forkmem.models import DecisionFork, NegativeLesson


def test_langgraph_store_versions_and_protocol() -> None:
    fork = DecisionFork.model_validate(
        json.loads(
            Path("artifacts/v2/cases/partial_repair_falsified.json").read_text()
        )["fork"]
    )
    backend = InMemoryStore()
    store = LangGraphForkStore(backend)
    protocol: ForkStore = store
    protocol.put(fork)
    assert retrieve(protocol, fork.state)
    with pytest.raises(ValueError, match="increment"):
        store.put(fork)
    revised = fork.model_copy(update={"version": 2, "lesson": "narrowed lesson"})
    store.put(revised)
    # A new adapter instance sees the same backend, including immutable history.
    reopened = LangGraphForkStore(backend)
    assert len(reopened.history(fork.fork_id)) == 2
    assert reopened.all()[0].lesson == "narrowed lesson"
    assert reopened.history(fork.fork_id)[0].lesson == fork.lesson
    store.put_negative(
        NegativeLesson(
            lesson_id="observed",
            source_episode_id="test",
            state=fork.state,
            action=fork.factual.first_action,
            outcome=fork.factual.outcomes[0],
            summary="failed",
        )
    )
    assert reopened.negatives()[0].lesson_id == "observed"
