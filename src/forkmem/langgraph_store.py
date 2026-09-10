"""ForkStore adapter over LangGraph's long-term BaseStore API."""

from __future__ import annotations

from threading import RLock
from typing import Any

from langgraph.store.base import BaseStore

from forkmem.models import DecisionFork, NegativeLesson


class LangGraphForkStore:
    """Single-writer append-only versions over any configured LangGraph Store.

    SQLite remains the default transactional backend. Multi-process deployments
    must provide an external write lock or a transactional Store implementation.
    """

    def __init__(self, backend: BaseStore, namespace: tuple[str, ...] = ("forkmem",)):
        self.backend = backend
        self.namespace = namespace
        self.lock = RLock()

    def _values(self, suffix: str) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self.backend.search(
                (*self.namespace, suffix), limit=100, offset=offset
            )
            values.extend(item.value for item in page)
            if len(page) < 100:
                return values
            offset += len(page)

    def put(self, fork: DecisionFork) -> None:
        fork = DecisionFork.model_validate_json(fork.model_dump_json())
        with self.lock:
            head = self.backend.get((*self.namespace, "heads"), fork.fork_id)
            expected = 1 if head is None else int(head.value["version"]) + 1
            if fork.version != expected:
                raise ValueError("append-only versions must increment by one")
            namespace = (*self.namespace, "versions", fork.fork_id)
            if self.backend.get(namespace, str(fork.version)) is not None:
                raise ValueError("immutable version already exists")
            self.backend.put(namespace, str(fork.version), fork.model_dump(mode="json"))
            self.backend.put(
                (*self.namespace, "heads"),
                fork.fork_id,
                {"fork_id": fork.fork_id, "version": fork.version},
            )

    def history(self, fork_id: str) -> list[DecisionFork]:
        head = self.backend.get((*self.namespace, "heads"), fork_id)
        if head is None:
            return []
        result = []
        for version in range(1, int(head.value["version"]) + 1):
            item = self.backend.get(
                (*self.namespace, "versions", fork_id), str(version)
            )
            if item is None:
                raise RuntimeError("missing immutable memory version")
            result.append(DecisionFork.model_validate(item.value))
        return result

    def all(self) -> list[DecisionFork]:
        result = []
        for head in self._values("heads"):
            item = self.backend.get(
                (*self.namespace, "versions", head["fork_id"]), str(head["version"])
            )
            if item is None:
                raise RuntimeError("head points to missing memory version")
            result.append(DecisionFork.model_validate(item.value))
        return sorted(result, key=lambda fork: fork.fork_id)

    def put_negative(self, lesson: NegativeLesson) -> None:
        lesson = NegativeLesson.model_validate_json(lesson.model_dump_json())
        namespace = (*self.namespace, "negative")
        with self.lock:
            if self.backend.get(namespace, lesson.lesson_id) is not None:
                raise ValueError("negative observation already exists")
            self.backend.put(
                namespace, lesson.lesson_id, lesson.model_dump(mode="json")
            )

    def negatives(self) -> list[NegativeLesson]:
        return sorted(
            [
                NegativeLesson.model_validate(value)
                for value in self._values("negative")
            ],
            key=lambda lesson: lesson.lesson_id,
        )
