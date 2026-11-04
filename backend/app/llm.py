"""Vultr Serverless Inference client (OpenAI-compatible chat completions).

The LLM is untrusted. Callers get either a Pydantic-validated object or an LLMError; they must
handle the error with a deterministic fallback / "needs human review" status.
"""
from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """LLM unavailable, unconfigured, or returned output that failed validation twice."""


def _post_chat(messages: list[dict[str, str]], *, json_mode: bool) -> str:
    s = get_settings()
    if not s.llm_configured:
        raise LLMError("Vultr inference is not configured (VULTR_INFERENCE_API_KEY / VULTR_INFERENCE_MODEL)")
    payload: dict = {"model": s.vultr_inference_model, "messages": messages, "temperature": 0}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        resp = httpx.post(
            f"{s.vultr_inference_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {s.vultr_inference_api_key}"},
            json=payload,
            timeout=s.llm_timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"Inference request failed: {type(exc).__name__}: {exc}") from exc


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _parse_json(text: str) -> object:
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def chat_json(system: str, user: str, schema: type[T]) -> T:
    """Ask for JSON, validate against `schema`. One retry with the validation error fed back."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_error = ""
    for attempt in range(2):
        content = _post_chat(messages, json_mode=True)
        try:
            return schema.model_validate(_parse_json(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)[:500]
            log.warning("LLM output failed validation (attempt %d): %s", attempt + 1, last_error)
            messages = messages + [
                {"role": "assistant", "content": content[:2000]},
                {"role": "user", "content": f"That was not valid. Return ONLY JSON matching the schema. Error: {last_error}"},
            ]
    raise LLMError(f"LLM output invalid after retry: {last_error}")


def ping() -> tuple[bool, str]:
    """Connectivity check for /health. Cheap models endpoint call; never raises."""
    s = get_settings()
    if not s.llm_configured:
        return False, "not_configured"
    try:
        r = httpx.get(
            f"{s.vultr_inference_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {s.vultr_inference_api_key}"},
            timeout=8,
        )
        return (r.status_code < 400), f"http_{r.status_code}"
    except httpx.HTTPError as exc:
        return False, type(exc).__name__
