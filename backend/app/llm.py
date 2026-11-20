from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Protocol

import httpx

from .config import settings


class LLMError(RuntimeError):
    pass


class BadRequest(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(body)
        self.status = status
        self.body = body


class LLMBackend(Protocol):
    label: str

    async def list_models(self) -> list[str]: ...

    async def resolve_model(self) -> str: ...

    async def chat(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> str: ...

    async def chat_json(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> Any: ...


def _normalize_base(url: str) -> str:
    return url.rstrip("/")


async def list_models(client: httpx.AsyncClient) -> list[str]:
    try:
        resp = await client.get(
            f"{_normalize_base(settings.lm_studio_url)}/models", timeout=5.0
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise LLMError(
            f"LM Studio is not reachable at {settings.lm_studio_url}. "
            "Open LM Studio, load a model, and start the local server on port 1234."
        ) from exc
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


def pick_model(models: list[str]) -> str:
    if not models:
        raise LLMError(
            "LM Studio is running but no model is loaded. Load a model in LM Studio first."
        )
    # Skip embedding-only models when auto-picking a chat model.
    chat_models = [m for m in models if "embed" not in m.lower()]
    return (chat_models or models)[0]


async def resolve_model(client: httpx.AsyncClient) -> str:
    if settings.lm_studio_model:
        return settings.lm_studio_model
    return pick_model(await list_models(client))


def build_payload(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1200,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "temperature": settings.lm_temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "result", "strict": True, "schema": schema},
        }
    # Reasoning models (e.g. Qwen3.x) spend many seconds emitting "thinking"
    # tokens before the answer. LM Studio honours reasoning_effort: none.
    if settings.lm_disable_thinking:
        payload["reasoning_effort"] = "none"
    return payload


def fallback_payload(payload: dict[str, Any], body: str) -> dict[str, Any] | None:
    adjusted = dict(payload)
    dropped = False
    if "reasoning_effort" in body:
        adjusted.pop("reasoning_effort", None)
        dropped = True
    if "response_format" in body:
        adjusted.pop("response_format", None)
        dropped = True
    return adjusted if dropped else None


def _process_sse_line(line: str, parts: list[str]) -> bool:
    line = line.rstrip("\r")
    if not line.startswith("data:"):
        return False
    chunk = line[5:].strip()
    if chunk == "[DONE]":
        return True
    try:
        event = json.loads(chunk)
    except json.JSONDecodeError:
        return False
    choices = event.get("choices") or []
    if not choices:
        return False
    text = (choices[0].get("delta") or {}).get("content")
    if text:
        parts.append(text)
    return False


async def consume_chat_chunks(
    content_type: str, chunks: AsyncIterator[str]
) -> str:
    if "text/event-stream" not in content_type:
        raw = "".join([chunk async for chunk in chunks])
        data = json.loads(raw)
        return (data["choices"][0]["message"]["content"] or "").strip()

    parts: list[str] = []
    buffer = ""
    async for chunk in chunks:
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if _process_sse_line(line, parts):
                return "".join(parts).strip()
    if buffer:
        _process_sse_line(buffer, parts)
    return "".join(parts).strip()


async def _stream_chat(
    client: httpx.AsyncClient, payload: dict[str, Any], timeout: httpx.Timeout
) -> str:
    async with client.stream(
        "POST",
        f"{_normalize_base(settings.lm_studio_url)}/chat/completions",
        json=payload,
        timeout=timeout,
    ) as resp:
        if resp.status_code >= 400:
            body = (await resp.aread())[:500].decode("utf-8", "replace")
            raise BadRequest(resp.status_code, body)

        content_type = resp.headers.get("content-type", "")
        return await consume_chat_chunks(content_type, resp.aiter_text())


async def chat(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1200,
    schema: dict[str, Any] | None = None,
) -> str:
    payload = build_payload(model, system, user, max_tokens, schema)
    timeout = httpx.Timeout(settings.lm_timeout, connect=15.0)
    try:
        content = await _stream_chat(client, payload, timeout)
    except BadRequest as exc:
        # Fall back gracefully if the server rejects optional fields.
        adjusted = fallback_payload(payload, exc.body)
        if adjusted is None:
            raise LLMError(
                f"LM Studio returned HTTP {exc.status}: {exc.body}"
            ) from exc
        try:
            content = await _stream_chat(client, adjusted, timeout)
        except BadRequest as retry_exc:
            raise LLMError(
                f"LM Studio returned HTTP {retry_exc.status}: {retry_exc.body}"
            ) from retry_exc
        except httpx.ReadTimeout as retry_exc:
            raise LLMError(timeout_message()) from retry_exc
        except httpx.HTTPError as retry_exc:
            raise LLMError(_connection_message(retry_exc)) from retry_exc
    except httpx.ReadTimeout as exc:
        raise LLMError(timeout_message()) from exc
    except httpx.HTTPError as exc:
        raise LLMError(_connection_message(exc)) from exc

    if not content:
        raise LLMError("LM Studio returned an empty response.")
    return content


def timeout_message() -> str:
    return (
        f"LM Studio stopped sending tokens for {int(settings.lm_timeout)}s. "
        "The model may still be loading or be too large for this machine. "
        "Try a smaller model, or raise LM_TIMEOUT in backend/.env."
    )


def _connection_message(exc: Exception) -> str:
    return (
        f"Request to LM Studio failed ({exc.__class__.__name__}). "
        "Check that the local server is still running."
    )


def extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("could not parse JSON from model output")


async def chat_json(
    client: httpx.AsyncClient,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1200,
    schema: dict[str, Any] | None = None,
) -> Any:
    raw = await chat(
        client, model, system, user, max_tokens=max_tokens, schema=schema
    )
    try:
        return extract_json(raw)
    except ValueError:
        retry_user = (
            f"{user}\n\nYour previous reply could not be parsed as JSON. "
            "Reply with ONLY the requested JSON object and nothing else."
        )
        raw = await chat(
            client, model, system, retry_user, max_tokens=max_tokens, schema=schema
        )
        return extract_json(raw)


class DirectLLM:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.label = f"LM Studio at {settings.lm_studio_url}"

    async def list_models(self) -> list[str]:
        return await list_models(self.client)

    async def resolve_model(self) -> str:
        return await resolve_model(self.client)

    async def chat(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> str:
        return await chat(
            self.client,
            model,
            system,
            user,
            max_tokens=max_tokens,
            schema=schema,
        )

    async def chat_json(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1200,
        schema: dict[str, Any] | None = None,
    ) -> Any:
        return await chat_json(
            self.client,
            model,
            system,
            user,
            max_tokens=max_tokens,
            schema=schema,
        )
