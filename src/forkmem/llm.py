"""Bounded asynchronous OpenAI-compatible JSON client."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
PROMPT_VERSION = "forkrsi-json-response-repair-v2"


class ModelResponseError(ValueError):
    """A model response exhausted its fixed four-attempt schema repair budget."""

    def __init__(self, request_id: str):
        super().__init__("model JSON repair budget exhausted")
        self.request_id = request_id


def normalize_proposals(data: Any) -> Any:
    """Move only unambiguous misplaced fields; never change proposed code/values."""
    if not isinstance(data, dict) or not isinstance(data.get("proposals"), list):
        return data
    result = json.loads(json.dumps(data))
    action_fields = {"tool", "path", "content", "thought_summary"}
    proposal_fields = {"mechanism", "predicted_outcome", "requires", "excludes", "risk"}
    for proposal in result["proposals"]:
        if not isinstance(proposal, dict):
            continue
        if "action" not in proposal and "tool" in proposal:
            proposal["action"] = {
                key: proposal.pop(key) for key in list(proposal) if key in action_fields
            }
        action = proposal.get("action")
        if isinstance(action, dict):
            for key in list(action):
                if key in proposal_fields:
                    if key in proposal and proposal[key] != action[key]:
                        raise ValueError("ambiguous proposal wrapper fields")
                    proposal[key] = action.pop(key)
    return result


def parse_json(content: str, schema: type[T]) -> T:
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    if schema.__name__ == "Proposals":
        return schema.model_validate(normalize_proposals(json.loads(text)))
    return schema.model_validate_json(text)


class LLMClient:
    def __init__(
        self,
        log_path: Path,
        *,
        concurrency: int = 8,
        request_budget: int = 2000,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = os.getenv(
            "FORKMEM_LLM_BASE_URL", "http://127.0.0.1:8000/v1"
        ).rstrip("/")
        self.model = os.getenv("FORKMEM_LLM_MODEL", "Qwen3.8-27B")
        limit = min(concurrency, int(os.getenv("FORKMEM_LLM_MAX_CONCURRENCY", "8")))
        if not 1 <= limit <= 8:
            raise ValueError("concurrency must be between 1 and 8")
        self.semaphore = asyncio.Semaphore(limit)
        self.remaining = request_budget
        self.log_path = log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient(
            timeout=float(os.getenv("FORKMEM_LLM_TIMEOUT_SECONDS", "180")),
            transport=transport,
            trust_env=False,
        )

    async def close(self) -> None:
        await self.client.aclose()

    def log(self, event: dict[str, Any]) -> None:
        with self.log_path.open("a") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    async def generate(
        self,
        prompt: str,
        schema: type[T],
        *,
        seed: int = 0,
        temperature: float = 0.3,
        max_tokens: int = 3000,
        run_id: str = "smoke",
        episode_id: str = "",
        branch_id: str = "",
    ) -> T:
        if len(prompt) > 64000:
            raise ValueError("prompt exceeds 64000 character budget")
        request_id = uuid4().hex
        base_messages = [
            {
                "role": "system",
                "content": "Return only a JSON object matching this schema. Do not include markdown. "
                + json.dumps(schema.model_json_schema()),
            },
            {"role": "user", "content": prompt},
        ]
        messages = list(base_messages)
        for attempt in range(4):
            async with self.semaphore:
                if self.remaining <= 0:
                    raise RuntimeError("global LLM request budget exhausted")
                self.remaining -= 1
                start = time.monotonic()
                parsed_url = urlsplit(self.base_url)
                event: dict[str, Any] = {
                    "request_id": request_id,
                    "run_id": run_id,
                    "episode_id": episode_id,
                    "branch_id": branch_id,
                    "model": self.model,
                    "base_url": f"{parsed_url.scheme}://{parsed_url.hostname}:{parsed_url.port}",
                    "prompt_version": PROMPT_VERSION,
                    "schema": schema.__name__,
                    "json_protocol": "proposal-wrapper-compatible-v1"
                    if schema.__name__ == "Proposals"
                    else "strict",
                    "temperature": temperature,
                    "top_p": 1,
                    "max_tokens": max_tokens,
                    "seed": seed,
                    "attempt": attempt,
                    "messages": list(messages),
                }
                try:
                    response = await self.client.post(
                        self.base_url + "/chat/completions",
                        headers={
                            "Authorization": "Bearer "
                            + os.getenv("FORKMEM_LLM_API_KEY", "EMPTY"),
                            "X-Request-ID": request_id,
                        },
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": temperature,
                            "top_p": 1,
                            "max_tokens": max_tokens,
                            "seed": seed,
                            "response_format": {"type": "json_object"},
                            "chat_template_kwargs": {"enable_thinking": False},
                        },
                    )
                    response.raise_for_status()
                    body = response.json()
                    event["usage"] = body.get("usage", {})
                    event["finish_reason"] = body["choices"][0].get("finish_reason")
                    content = body["choices"][0]["message"]["content"]
                    event["response"] = content
                    result = parse_json(content, schema)
                    event["status"] = "ok"
                    return result
                except (ValidationError, ValueError, KeyError, TypeError) as exc:
                    event["status"] = "parse_error"
                    event["error_type"] = type(exc).__name__
                    details = (
                        exc.errors(
                            include_url=False,
                            include_context=False,
                            include_input=False,
                        )[:6]
                        if isinstance(exc, ValidationError)
                        else [{"type": type(exc).__name__, "msg": str(exc)[:500]}]
                    )
                    event["schema_errors"] = details
                    feedback = json.dumps(details, ensure_ascii=False)[:1500]
                    repair = (
                        "Your previous response was invalid JSON/schema. "
                        "Return the exact schema, all required fields, no extra fields. "
                        "Follow each field type exactly; quote precondition values when "
                        "their schema requires strings. Escape quotes and newlines in "
                        "JSON string fields. Keep the complete response compact without "
                        "repeated commentary. The previous response may be clipped for "
                        "context; generate one complete corrected object. Validation errors: "
                        + feedback
                    )
                    # Error offsets are useful only when the model can see its own
                    # invalid response. Keep just the last response, bounded by the
                    # existing character budget; never rewrite code or relax parsing.
                    available = max(
                        0,
                        64000
                        - sum(len(m["content"]) for m in base_messages)
                        - len(repair)
                        - 256,
                    )
                    previous = str(event.get("response", ""))[: min(16000, available)]
                    messages = list(base_messages)
                    if previous:
                        messages.append({"role": "assistant", "content": previous})
                    messages.append({"role": "user", "content": repair})
                    if attempt == 3:
                        raise ModelResponseError(request_id) from None
                except httpx.HTTPError as exc:
                    event["status"] = "transport_error"
                    event["error_type"] = type(exc).__name__
                    if isinstance(exc, httpx.HTTPStatusError):
                        event["http_status"] = exc.response.status_code
                        if (
                            exc.response.status_code < 500
                            and exc.response.status_code != 429
                        ):
                            raise RuntimeError(
                                f"model HTTP status {exc.response.status_code}"
                            ) from None
                    if attempt == 3:
                        raise RuntimeError("model request retries exhausted") from None
                finally:
                    event["latency_seconds"] = time.monotonic() - start
                    self.log(event)
            await asyncio.sleep(min(2**attempt, 8))
        raise AssertionError("unreachable")
