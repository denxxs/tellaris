"""One client for every LLM provider.

All calls go through LiteLLM, so any provider it supports works (OpenAI,
Anthropic, Gemini, Azure, Mistral, Groq, DeepSeek, OpenRouter, Together, xAI,
Ollama and local OpenAI-compatible servers). Models named "mock/..." are served
by the offline mock so the whole system runs without keys.

Structured output: we ask for JSON (using native JSON mode when the provider
supports it), extract it robustly, validate it with Pydantic and, when it does
not validate, send the validation error back to the model to repair it.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..config import settings_store
from . import mock

log = logging.getLogger("oracle.llm")

T = TypeVar("T", bound=BaseModel)

TRANSIENT_ERROR_NAMES = {
    "RateLimitError",
    "APIConnectionError",
    "Timeout",
    "APITimeoutError",
    "ServiceUnavailableError",
    "InternalServerError",
    "BadGatewayError",
}


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    failures: int = 0
    repairs: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(self, model: str, prompt: int, completion: int, cost: float) -> None:
        self.calls += 1
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cost_usd += cost
        m = self.by_model.setdefault(model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0})
        m["calls"] += 1
        m["prompt_tokens"] += prompt
        m["completion_tokens"] += completion
        m["cost_usd"] += cost

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "failures": self.failures,
            "repairs": self.repairs,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "by_model": self.by_model,
        }


current_usage: contextvars.ContextVar[Usage | None] = contextvars.ContextVar("current_usage", default=None)

_semaphores: dict[int, asyncio.Semaphore] = {}


def _semaphore() -> asyncio.Semaphore:
    size = max(1, settings_store.get().max_concurrency)
    loop_id = id(asyncio.get_running_loop())
    key = hash((size, loop_id))
    if key not in _semaphores:
        _semaphores[key] = asyncio.Semaphore(size)
    return _semaphores[key]


def _strip_titles(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {k: _strip_titles(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_strip_titles(v) for v in schema]
    return schema


def schema_prompt(schema: type[BaseModel]) -> str:
    compact = json.dumps(_strip_titles(schema.model_json_schema()), separators=(",", ":"))
    return (
        "Respond with ONLY a single JSON object that matches this JSON Schema. "
        "No markdown, no code fences, no commentary.\n"
        f"JSON Schema: {compact}"
    )


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Pull the first JSON object out of a model reply."""
    if text is None:
        raise ValueError("empty reply")
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            text = m.group(1)
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        # Common slip: trailing commas.
                        try:
                            return json.loads(re.sub(r",\s*([}\]])", r"\1", candidate))
                        except json.JSONDecodeError:
                            break
        start = text.find("{", start + 1)
    raise ValueError("no JSON object found in reply")


def _supports_json_mode(model: str) -> bool:
    try:
        import litellm

        params = litellm.get_supported_openai_params(model=model) or []
        return "response_format" in params
    except Exception:
        return False


class LLM:
    """Async client. Use the module-level `llm` instance."""

    max_attempts = 4
    max_repairs = 2

    async def _raw(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int | None,
        json_mode: bool,
    ) -> str:
        import litellm

        s = settings_store.get()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "timeout": s.request_timeout_s,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if json_mode and _supports_json_mode(model):
            kwargs["response_format"] = {"type": "json_object"}

        last: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                async with _semaphore():
                    resp = await litellm.acompletion(**kwargs)
                content = resp.choices[0].message.content or ""
                usage = getattr(resp, "usage", None)
                prompt_t = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_t = int(getattr(usage, "completion_tokens", 0) or 0)
                try:
                    cost = float(litellm.completion_cost(completion_response=resp) or 0.0)
                except Exception:
                    cost = 0.0
                u = current_usage.get()
                if u is not None:
                    u.add(model, prompt_t, completion_t, cost)
                return content
            except Exception as exc:  # noqa: BLE001 - provider errors vary widely
                last = exc
                name = type(exc).__name__
                if "response_format" in str(exc) and "response_format" in kwargs:
                    kwargs.pop("response_format", None)
                    continue
                if name not in TRANSIENT_ERROR_NAMES or attempt == self.max_attempts - 1:
                    break
                delay = min(30.0, (2**attempt) + random.random())
                log.warning("LLM %s transient error (%s), retrying in %.1fs", model, name, delay)
                await asyncio.sleep(delay)
        u = current_usage.get()
        if u is not None:
            u.failures += 1
        raise LLMError(f"{model}: {type(last).__name__}: {last}") from last

    async def json(
        self,
        *,
        task: str,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        mock_ctx: dict[str, Any] | None = None,
    ) -> T:
        if model.startswith("mock/"):
            return await self._mock(task, schema, mock_ctx or {}, system, user)

        messages = [
            {"role": "system", "content": f"{system}\n\n{schema_prompt(schema)}"},
            {"role": "user", "content": user},
        ]
        error_note = ""
        for repair in range(self.max_repairs + 1):
            reply = await self._raw(model, messages, temperature=temperature, max_tokens=max_tokens, json_mode=True)
            try:
                data = extract_json(reply)
                return schema.model_validate(data)
            except (ValueError, ValidationError) as exc:
                error_note = str(exc)[:1500]
                if repair == self.max_repairs:
                    break
                u = current_usage.get()
                if u is not None:
                    u.repairs += 1
                messages = messages[:2] + [
                    {"role": "assistant", "content": reply[:6000]},
                    {
                        "role": "user",
                        "content": "That reply did not match the schema. Error:\n"
                        f"{error_note}\nReturn the corrected JSON object only.",
                    },
                ]
        raise LLMError(f"{model} could not produce valid {schema.__name__} for task '{task}': {error_note}")

    async def text(
        self,
        *,
        task: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int | None = 600,
        mock_ctx: dict[str, Any] | None = None,
    ) -> str:
        if model.startswith("mock/"):
            await asyncio.sleep(mock.latency())
            u = current_usage.get()
            if u is not None:
                u.add(model, 0, 0, 0.0)
            return mock.text(task, messages, mock_ctx or {})
        return await self._raw(model, messages, temperature=temperature, max_tokens=max_tokens, json_mode=False)

    async def _mock(self, task: str, schema: type[T], ctx: dict[str, Any], system: str, user: str) -> T:
        await asyncio.sleep(mock.latency())
        data = mock.respond(task, ctx, system=system, user=user)
        u = current_usage.get()
        if u is not None:
            u.add("mock/oracle", 0, 0, 0.0)
        return schema.model_validate(data)

    async def ping(self, model: str) -> dict[str, Any]:
        """Quick connectivity check used by the settings page."""
        start = time.perf_counter()
        if model.startswith("mock/"):
            return {"ok": True, "model": model, "latency_ms": 1, "reply": "offline mock"}
        try:
            reply = await self._raw(
                model,
                [{"role": "user", "content": "Reply with the single word: ready"}],
                temperature=0,
                max_tokens=10,
                json_mode=False,
            )
            return {
                "ok": True,
                "model": model,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "reply": reply.strip()[:60],
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": model, "error": str(exc)[:400]}


llm = LLM()
